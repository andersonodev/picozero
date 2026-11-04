# backend/picozero/contexto.py
# Contexto da instituição (white label): unidades, semestre, períodos letivos e feriados.
# Trocar dados/contexto.json + o calendário aplica o motor a outra marca (Estácio, Wyden, IDOMED).
import json
from datetime import date, datetime, timedelta
from functools import lru_cache

from .config import CONFIG, DADOS, TZ
from .dominio import Evento, Feriado, Marco, Unidade


@lru_cache(maxsize=1)
def _bruto() -> dict:
    return json.loads((DADOS / "contexto.json").read_text(encoding="utf-8"))


def instituicao() -> str:
    return _bruto()["instituicao"]


def unidades() -> list[Unidade]:
    return [Unidade(**u) for u in _bruto()["unidades"]]


def unidade_padrao() -> Unidade:
    return unidade(_bruto()["unidade_padrao"])


def unidade(id_: str) -> Unidade:
    for u in unidades():
        if u.id == id_.lower():
            return u
    raise KeyError(id_)


def semestre() -> dict:
    return _bruto()["semestre"]


def historico() -> dict:
    return _bruto()["historico"]


@lru_cache(maxsize=1)
def _feriados() -> dict[str, str]:
    return {f["data"]: f["nome"] for f in _bruto()["feriados"]}


def feriado(iso: str) -> str | None:
    return _feriados().get(iso)


def feriados(inicio: str | None = None, fim: str | None = None) -> list[Feriado]:
    return [
        Feriado(data=d, nome=n)
        for d, n in sorted(_feriados().items())
        if (not inicio or d >= inicio) and (not fim or d <= fim)
    ]


def em_periodo_letivo(iso: str) -> bool:
    return any(p["inicio"] <= iso <= p["fim"] for p in _bruto()["periodos_letivos"])


def tipo_dia(iso: str) -> str:
    """util | sexta | sabado | domingo | feriado | ferias — a base orgânica muda com isto."""
    if feriado(iso):
        return "feriado"
    if not em_periodo_letivo(iso):
        return "ferias"
    dia = date.fromisoformat(iso).weekday()
    return {4: "sexta", 5: "sabado", 6: "domingo"}.get(dia, "util")


@lru_cache(maxsize=1)
def calendario_atual() -> dict:
    return json.loads((DADOS / "calendario_2026_2.json").read_text(encoding="utf-8"))


def marcos() -> list[Marco]:
    return [Marco(**m) for m in calendario_atual()["marcos"]]


@lru_cache(maxsize=1)
def _periodos() -> tuple[Marco, ...]:
    todos = [Marco(**m) for m in historico_eventos().get("marcos", [])] + marcos()
    return tuple(m for m in todos if m.tipo in ("rematricula", "prova_online"))


def periodo(iso: str) -> Marco | None:
    """Período de rematrícula ou de provas que cobre o dia (carga sustentada, não um pico pontual)."""
    for m in _periodos():
        if m.inicio <= iso <= m.fim:
            return m
    return None


def eventos_semente() -> list[Evento]:
    fonte = "calendario_2026_2"
    return [Evento(**e, fonte=fonte) for e in calendario_atual()["eventos"]]


@lru_cache(maxsize=1)
def historico_eventos() -> dict:
    return json.loads((DADOS / "historico_eventos.json").read_text(encoding="utf-8"))


def eventos_historicos() -> list[Evento]:
    return [Evento(**e, fonte="historico_modelo") for e in historico_eventos()["eventos"]]


def agora() -> datetime:
    """Relógio do motor (naive, America/Sao_Paulo). PICOZERO_AGORA fixa o relógio da demo."""
    if CONFIG.agora_fixo:
        return datetime.fromisoformat(CONFIG.agora_fixo)
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0)


def ler_agora(texto: str | None) -> datetime:
    """Aceita 'AAAA-MM-DD', 'AAAA-MM-DDTHH:MM' (ou com fuso); vazio = relógio do motor."""
    if not texto:
        return agora()
    texto = texto.strip().replace(" ", "T")
    if len(texto) == 10:
        return datetime.fromisoformat(texto + "T08:00")
    d = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if d.tzinfo:
        d = d.astimezone(TZ).replace(tzinfo=None)
    return d.replace(second=0, microsecond=0)


def dias(inicio: str, fim: str) -> list[str]:
    a, b = date.fromisoformat(inicio), date.fromisoformat(fim)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]
