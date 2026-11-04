# backend/picozero/ingestao/normalizacao.py
# Peças comuns a todos os formatos: datas para o horário local alinhado em 15 min,
# números no padrão BR ou US, agregação por janela, nomes de coluna e tipo de evento pelo texto.
import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from itertools import pairwise
from typing import Any

from ..config import TZ
from ..dominio import Evento, PontoMetrica

MESES = {
    "jan": 1, "feb": 2, "fev": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5, "mai": 5, "jun": 6, "jul": 7,
    "aug": 8, "ago": 8, "sep": 9, "set": 9, "oct": 10, "out": 10, "nov": 11, "dec": 12, "dez": 12,
}  # fmt: skip

# Horários padrão por tipo quando a fonte não traz hora (mesmos do calendário 2026.2).
HORARIOS_PADRAO = {
    "vencimento": ("00:00", "23:59"),
    "notas": ("14:00", "23:59"),
    "prova_online": ("19:00", "21:00"),
    "rematricula": ("09:00", "23:59"),
    "outro": ("08:00", "22:00"),
}

VAZIOS = {"", "-", "—", "–", "null", "none", "nan", "n/a", "na", "nd", "n.d.", "?", "undefined"}


def hoje() -> date:
    """Data de referência para anos faltantes (os testes trocam esta função)."""
    return datetime.now(TZ).date()


# ---------- texto e nomes de coluna ----------


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def chave(texto: Any) -> str:
    return sem_acento(str(texto)).lower().strip()


def tokens(nome: Any) -> list[str]:
    """'Unique count of user.id' → ['unique', 'count', 'of', 'user', 'id']; separa camelCase."""
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(nome))
    return [t for t in re.split(r"[^a-z0-9]+", chave(s)) if t]


def _tem(toks: list[str], prefixos: Iterable[str]) -> bool:
    return any(t.startswith(p) for t in toks for p in prefixos)


GAUGE_FORTE = (
    "simult", "concurrent", "concorrent", "ativo", "ativa", "active", "sess", "online", "usuario", "user",
    "unique", "unico", "distint", "cardinal", "conectad", "connected", "logad", "logged",
)  # fmt: skip
GAUGE_FRACO = ("carga", "load", "valor", "value", "gauge", "nivel", "level", "medida", "metric")
CONTADOR = (
    "count", "contagem", "request", "requisic", "hit", "transac", "transaction", "doc", "total", "qtd",
    "quantidade", "acesso", "rpm", "rps", "throughput", "pageview", "visit",
)  # fmt: skip
NAO_CARGA = (
    "durac",
    "duration",
    "latenc",
    "latency",
    "tempo",
    "elapsed",
    "byte",
    "size",
    "tamanho",
    "status",
    "code",
    "codigo",
    "port",
    "porta",
    "versao",
    "version",
    "pid",
    "longitude",
    "latitude",
    "percent",
)
NAO_CARGA_EXATO = {"us", "ms", "lat", "lon", "ano", "mes", "dia", "hora", "minuto", "year", "month", "day"}
IDS_EXATO = {"id", "ids", "uuid", "guid"}
AGREGADORES = ("unique", "unico", "distint", "cardinal", "count", "contagem", "sum", "soma", "max", "avg", "media")
NOMES_TEMPO = (
    "timestamp", "datetime", "data", "date", "hora", "horario", "time", "quando", "period", "key", "dia",
    "dt", "ts", "momento", "instante", "bucket", "minut", "epoch", "created", "criado", "inicio", "start",
)  # fmt: skip


def prioridade_valor(nome: Any) -> int:
    """3 = gauge de usuários/sessões, 2 = carga/valor genérico, 1 = contador, 0 = nome sem pista."""
    toks = tokens(nome)
    if _tem(toks, GAUGE_FORTE):
        return 3
    if _tem(toks, GAUGE_FRACO):
        return 2
    if _tem(toks, CONTADOR):
        return 1
    return 0


def tipo_metrica(nome: Any) -> str:
    """'gauge' (agrega por máximo), 'contador' (agrega por soma) ou 'desconhecido'."""
    toks = tokens(nome)
    if _tem(toks, GAUGE_FORTE):
        return "gauge"
    if _tem(toks, CONTADOR):
        return "contador"
    if _tem(toks, GAUGE_FRACO):
        return "gauge"
    return "desconhecido"


def elegivel_valor(nome: Any) -> bool:
    """Exclui colunas numéricas que não medem carga (ids, duração, status, bytes…)."""
    toks = tokens(nome)
    if any(t in IDS_EXATO for t in toks) and not _tem(toks, AGREGADORES):
        return False
    nao_carga = _tem(toks, NAO_CARGA) or any(t in NAO_CARGA_EXATO for t in toks)
    return not nao_carga or _tem(toks, GAUGE_FORTE)


def nome_de_tempo(nome: Any) -> bool:
    return _tem(tokens(nome), NOMES_TEMPO)


# ---------- datas ----------

RE_NUMERICO = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$")
RE_BR = re.compile(
    r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?:[ T,]+(\d{1,2})[:h](\d{2})(?::(\d{2}))?(?:[.,]\d+)?)?\s*(?:h|hs)?$"
)
RE_AMD_BARRA = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:[.,]\d+)?)?$")
RE_KIBANA = re.compile(
    r"^([A-Za-zÀ-ÿ]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\s*@?\s*(?:(\d{1,2}):(\d{2})(?::(\d{2}))?(?:[.,]\d+)?)?$"
)
RE_LOG = re.compile(r"^(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})(?:\s*([+-]\d{4}))?$")
RE_SO_HORA = re.compile(
    r"^([01]?\d|2[0-4])\s*(?:h(?:s|rs)?|:)\s*([0-5]\d)?(?::([0-5]\d))?(?:[.,]\d+)?\s*(?:h|hs|min)?$"
)
RE_FUSO_TEXTO = re.compile(r"(Z|[+-]\d{2}:?\d{2}|\bUTC|\bGMT)\s*$")


def para_local(dt: datetime, fuso: Any = None) -> datetime:
    """Com fuso → converte para America/Sao_Paulo e tira o fuso; sem fuso → assume `fuso` (ou já local)."""
    if dt.tzinfo is None:
        if fuso is None:
            return dt
        dt = dt.replace(tzinfo=fuso)
    return dt.astimezone(TZ).replace(tzinfo=None)


def de_epoch(valor: float) -> datetime | None:
    """Epoch em s, ms, µs ou ns (pela magnitude) → horário local."""
    v = abs(valor)
    if 1e9 <= v < 1e11:
        seg = valor
    elif 1e11 <= v < 1e14:
        seg = valor / 1e3
    elif 1e14 <= v < 1e17:
        seg = valor / 1e6
    elif 1e17 <= v < 1e20:
        seg = valor / 1e9
    else:
        return None
    try:
        return datetime.fromtimestamp(seg, UTC).astimezone(TZ).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def de_serial_excel(valor: float) -> datetime | None:
    if not 20000 <= valor <= 80000:
        return None
    return datetime(1899, 12, 30) + timedelta(days=valor)


def _montar(a: int, m: int, d: int, hh: Any = None, mm: Any = None, ss: Any = None) -> datetime | None:
    if a < 100:
        a += 2000
    try:
        return datetime(a, m, d, int(hh or 0) % 24, int(mm or 0), int(ss or 0))
    except ValueError:
        return None


def mes_por_nome(nome: str) -> int | None:
    return MESES.get(chave(nome)[:3])


def para_datetime(valor: Any, *, fuso: Any = None, serial_excel: bool = False, epoch: bool = True) -> datetime | None:
    """Qualquer representação de data/hora → datetime local sem fuso (None se não for data)."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, datetime):
        return para_local(valor, fuso)
    if isinstance(valor, date):
        return datetime.combine(valor, time())
    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and not math.isfinite(valor):
            return None
        if serial_excel and (dt := de_serial_excel(float(valor))):
            return dt
        return de_epoch(float(valor)) if epoch else None
    texto = str(valor).strip().strip("\"'").strip()
    if not texto or len(texto) > 64:
        return None
    if RE_NUMERICO.match(texto):
        return para_datetime(float(texto), fuso=fuso, serial_excel=serial_excel, epoch=epoch)
    iso = re.sub(r"\s*UTC$", "+00:00", texto)
    try:
        return para_local(datetime.fromisoformat(iso), fuso)
    except ValueError:
        pass
    if m := RE_BR.match(texto):
        d, mes, a = int(m[1]), int(m[2]), int(m[3])
        if mes > 12 >= d:  # mm/dd (padrão americano)
            d, mes = mes, d
        dt = _montar(a, mes, d, m[4], m[5], m[6])
        return para_local(dt, fuso) if dt else None
    if m := RE_AMD_BARRA.match(texto):
        dt = _montar(int(m[1]), int(m[2]), int(m[3]), m[4], m[5], m[6])
        return para_local(dt, fuso) if dt else None
    if (m := RE_KIBANA.match(texto)) and (mes := mes_por_nome(m[1])):
        dt = _montar(int(m[3]), mes, int(m[2]), m[4], m[5], m[6])
        return para_local(dt, fuso) if dt else None
    if (m := RE_LOG.match(texto)) and (mes := mes_por_nome(m[2])):
        dt = _montar(int(m[3]), mes, int(m[1]), m[4], m[5], m[6])
        if dt and m[7]:
            sinal = 1 if m[7][0] == "+" else -1
            desloc = timedelta(hours=int(m[7][1:3]), minutes=int(m[7][3:5]))
            dt = dt.replace(tzinfo=timezone(sinal * desloc))
        return para_local(dt, fuso) if dt else None
    try:
        return para_local(parsedate_to_datetime(texto), fuso)
    except (TypeError, ValueError, IndexError):
        return None


def tem_fuso_explicito(valor: Any) -> bool:
    if isinstance(valor, datetime):
        return valor.tzinfo is not None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return True  # epoch é sempre UTC
    return bool(RE_FUSO_TEXTO.search(str(valor).strip()))


def para_hora(valor: Any) -> str | None:
    """'19h', '19h30', '19:00', '19:00:00', time/datetime → 'HH:MM' (24:00 vira 23:59)."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%H:%M")
    if isinstance(valor, time):
        return valor.strftime("%H:%M")
    if isinstance(valor, float) and 0 <= valor < 1:  # fração de dia do Excel
        minutos_dia = round(valor * 24 * 60)
        return f"{min(minutos_dia // 60, 23):02d}:{minutos_dia % 60:02d}"
    m = RE_SO_HORA.match(str(valor).strip().lower())
    if not m:
        return None
    h, mi = int(m[1]), int(m[2] or 0)
    if h == 24:
        return "23:59"
    return f"{h:02d}:{mi:02d}"


def ano_provavel(dia: int, mes: int, referencia: date | None = None) -> date | None:
    """Ano faltante: o que deixa a data mais perto da referência (hoje)."""
    referencia = referencia or hoje()
    candidatos = []
    for ano in (referencia.year - 1, referencia.year, referencia.year + 1):
        try:
            candidatos.append(date(ano, mes, dia))
        except ValueError:
            continue
    return min(candidatos, key=lambda d: abs((d - referencia).days)) if candidatos else None


# ---------- números ----------


def _limpo(texto: str) -> str:
    return re.sub(r"[\s %]|R\$", "", texto)


def detectar_decimal(valores: Iterable[Any], delimitador: str | None = None) -> str:
    """Decide se a coluna usa vírgula (BR) ou ponto como separador decimal."""
    virgula = ponto = 0
    for bruto in valores:
        if bruto is None or isinstance(bruto, (int, float)):
            continue
        s = _limpo(str(bruto))
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                virgula += 1
            else:
                ponto += 1
        elif "," in s:
            partes = s.split(",")
            if len(partes) > 2:
                ponto += 1  # 1,234,567: vírgula é milhar
            elif len(partes[1]) != 3:
                virgula += 1  # 345,5
        elif "." in s:
            partes = s.split(".")
            if len(partes) > 2:
                virgula += 1  # 1.234.567: ponto é milhar
            elif len(partes[1]) != 3:
                ponto += 1
    if virgula != ponto:
        return "," if virgula > ponto else "."
    return "," if delimitador == ";" else "."


def para_numero(valor: Any, decimal: str = ".") -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if math.isfinite(valor) else None
    s = _limpo(str(valor))
    if s.lower() in VAZIOS:
        return None
    s = s.replace("." if decimal == "," else ",", "")
    if decimal == ",":
        s = s.replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        return None
    return n if math.isfinite(n) else None


# ---------- agregação em janelas de 15 min ----------


def alinhar(dt: datetime) -> datetime:
    return dt.replace(minute=dt.minute - dt.minute % 15, second=0, microsecond=0)


def agregar(pares: Iterable[tuple[datetime, float]], modo: str) -> list[PontoMetrica]:
    """modo 'max' (gauge) ou 'soma' (contador); valores negativos já devem ter saído."""
    janelas: dict[datetime, float] = {}
    for ts, valor in pares:
        j = alinhar(ts)
        if modo == "soma":
            janelas[j] = janelas.get(j, 0.0) + valor
        else:
            janelas[j] = max(janelas.get(j, valor), valor)
    return [PontoMetrica(ts=j, valor=round(v, 4), metrica="carga") for j, v in sorted(janelas.items())]


def agregar_distintos(pares: Iterable[tuple[datetime, str]]) -> list[PontoMetrica]:
    """Carga da janela = nº de identificadores distintos (usuários, sessões ou IPs)."""
    janelas: dict[datetime, set[str]] = defaultdict(set)
    for ts, ident in pares:
        janelas[alinhar(ts)].add(ident)
    return [PontoMetrica(ts=j, valor=float(len(ids)), metrica="carga") for j, ids in sorted(janelas.items())]


def resolucao_minutos(instantes: list[datetime]) -> float | None:
    """Mediana do intervalo entre leituras consecutivas, em minutos."""
    unicos = sorted(set(instantes))
    if len(unicos) < 2:
        return None
    difs = sorted((b - a).total_seconds() / 60 for a, b in pairwise(unicos))
    return difs[len(difs) // 2]


def avisos_de_resolucao(instantes: list[datetime], modo: str) -> list[str]:
    res = resolucao_minutos(instantes)
    if res is None:
        return []
    if res < 15:
        como = {"soma": "somadas", "distintos": "contadas sem repetição"}.get(modo, "pelo máximo")
        return [f"leituras a cada {res:g} min agregadas em janelas de 15 min ({como})"]
    if res > 15:
        return [f"leituras a cada {res:g} min: cada valor ocupa só a janela de 15 min em que caiu"]
    return []


# ---------- eventos ----------


def inferir_tipo(texto: Any) -> str:
    """Tipo do evento pelas palavras (notas antes de prova: 'notas da AP1' é divulgação de notas)."""
    bruto = str(texto)
    t = chave(bruto)
    if re.search(r"\bnotas?\b|resultado|divulga|boletim", t):
        return "notas"
    if re.search(r"vencimento|parcela|mensalidade|boleto|pagamento|semestralidade|\bpix\b", t):
        return "vencimento"
    if re.search(r"rematricula|matricula|renovacao|\bajustes?\b|trancamento|reabertura|readmissao|transferencia", t):
        return "rematricula"
    if re.search(r"\bprovas?\b|avaliac|\bap ?[123]\b|\bav ?[123]\b|\btestes?\b|\bexames?\b|simulado|substitutiva", t):
        return "prova_online"
    if re.search(r"\bAS\b", bruto):
        return "prova_online"
    return "outro"


def tipo_de_valor(valor: Any, contexto: str = "") -> str | None:
    """Valor de uma coluna 'tipo' → TipoEvento (None se vazio)."""
    if valor is None or not str(valor).strip():
        return None
    c = chave(valor).replace(" ", "_")
    if c in HORARIOS_PADRAO:
        return c
    if c in ("prova", "prova_on_line", "avaliacao", "exame"):
        return "prova_online"
    if c in ("academico", "outros", "geral"):
        return "outro"
    tipo = inferir_tipo(valor)
    return tipo if tipo != "outro" else inferir_tipo(f"{valor} {contexto}")


def _minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _somar_horas(hhmm: str, horas: int) -> str:
    total = min(_minutos(hhmm) + horas * 60, 23 * 60 + 59)
    return f"{total // 60:02d}:{total % 60:02d}"


def horas_padrao(tipo: str, inicio: str | None, fim: str | None) -> tuple[str, str]:
    """Completa início/fim que faltam com o padrão do tipo, sem deixar fim antes do início."""
    pi, pf = HORARIOS_PADRAO.get(tipo, HORARIOS_PADRAO["outro"])
    if inicio is None and fim is None:
        return pi, pf
    if inicio is None:
        return (pi if _minutos(pi) < _minutos(fim) else "00:00"), fim
    if fim is None or _minutos(fim) <= _minutos(inicio):
        fim = _somar_horas(inicio, 2) if tipo in ("prova_online", "outro") else "23:59"
        if _minutos(fim) <= _minutos(inicio):
            fim = "23:59"
    return inicio, fim


def dividir_turmas(valor: Any) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return [str(t).strip() for t in valor if str(t).strip()]
    return [t.strip() for t in re.split(r"[;,|]", str(valor)) if t.strip()]


def avisos_eventos(eventos: list[Evento]) -> list[str]:
    """Provas sem turmas nem alunos somam zero no modelo de carga: avisa."""
    sem_publico = [e for e in eventos if e.tipo == "prova_online" and not e.turmas and e.alunos is None]
    if not sem_publico:
        return []
    return [f"{len(sem_publico)} prova(s) sem turmas/alunos: informe a quantidade para o cálculo de carga"]
