# backend/picozero/ingestao/tabular.py
# Tabelas (CSV, TSV, XLSX e listas de objetos JSON achatadas). Escolhe a coluna de tempo e a
# de carga pelo nome e pelo conteúdo; vira lista de eventos quando a tabela é um calendário e
# conta identificadores distintos quando só há usuários/sessões/IPs (RUM, APM).
import csv
import io
import logging
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from ..dominio import Evento, ResultadoParse
from . import normalizacao as norm
from .deteccao import delimitador_tabular

log = logging.getLogger(__name__)

AMOSTRA = 400
LIMITE_LINHAS = 500_000

NOMES_DESCRICAO = (
    "descr",
    "evento",
    "event",
    "titulo",
    "title",
    "summary",
    "assunto",
    "atividade",
    "compromisso",
    "subject",
    "nome",
    "name",
)
NOMES_TIPO = ("tipo", "type", "categoria", "category")
NOMES_INICIO = ("inicio", "start", "comeco", "abertura")
NOMES_FIM = ("fim", "end", "termino", "encerr")
NOMES_HORA = ("hora", "horario", "time")
NOMES_TURMAS = ("turma", "classes", "class")
NOMES_ALUNOS = ("alunos", "estudantes", "students", "afetados", "inscritos")


@dataclass
class Perfil:
    indice: int
    nome: str
    preenchidos: int = 0
    taxa_data: float = 0.0
    taxa_hora: float = 0.0
    taxa_num: float = 0.0
    taxa_texto: float = 0.0
    variancia: float = 0.0
    so_data: bool = False
    com_fuso: bool = False
    serial: bool = False
    decimal: str = "."


# ---------- leitura ----------


def _vazio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and valor.strip().lower() in norm.VAZIOS)


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _celula(linha: list[Any], indice: int) -> Any:
    return linha[indice] if indice < len(linha) else None


def _e_so_hora(valor: Any) -> bool:
    if hasattr(valor, "hour") and not hasattr(valor, "year"):
        return True  # datetime.time
    return isinstance(valor, str) and bool(norm.RE_SO_HORA.match(valor.strip().lower()))


def _tem_cabecalho(primeira: list[Any]) -> bool:
    preenchidas = [c for c in primeira if not _vazio(c)]
    if not preenchidas:
        return False
    textuais = [
        c for c in preenchidas
        if isinstance(c, str) and norm.para_numero(c) is None and norm.para_datetime(c) is None and not _e_so_hora(c)
    ]  # fmt: skip
    return len(textuais) >= max(1, len(preenchidas) / 2)


def tabela_de_linhas(linhas: list[list[Any]]) -> tuple[list[Any], list[list[Any]], list[str]]:
    """Acha o cabeçalho (1ª linha com o nº modal de colunas) e separa título/cabeçalho/dados."""
    if not linhas:
        return [], [], []
    moda = Counter(len(linha) for linha in linhas[:50]).most_common(1)[0][0]
    inicio = next(i for i, linha in enumerate(linhas) if len(linha) == moda)
    avisos = [f"{inicio} linha(s) de título antes do cabeçalho ignoradas"] if inicio else []
    primeira = linhas[inicio]
    if _tem_cabecalho(primeira):
        return primeira, linhas[inicio + 1 :], avisos
    nomes = [f"coluna_{i + 1}" for i in range(len(primeira))]
    return nomes, linhas[inicio:], [*avisos, "sem cabeçalho: colunas nomeadas por posição"]


def _delimitador_csv(texto: str, formato: str) -> str:
    if formato == "tsv":
        return "\t"
    linhas = [linha for linha in texto.splitlines() if linha.strip()][:30]
    try:
        sniff = csv.Sniffer().sniff("\n".join(linhas), delimiters=",;\t|").delimiter
    except csv.Error:
        sniff = None
    consistente = delimitador_tabular(linhas)
    if sniff and sniff == consistente:
        return sniff
    return consistente or sniff or ","


def analisar_csv(texto: str, *, formato: str = "csv", dica: str | None = None, ia: Any = None) -> ResultadoParse:
    delim = _delimitador_csv(texto, formato)
    linhas: list[list[Any]] = []
    for linha in csv.reader(io.StringIO(texto), delimiter=delim):
        celulas = [c.strip() for c in linha]
        if any(celulas):
            linhas.append(celulas)
        if len(linhas) > LIMITE_LINHAS:
            break
    if not linhas:
        return ResultadoParse(formato=formato, avisos=["CSV sem linhas"])
    cabecalho, dados, avisos = tabela_de_linhas(linhas)
    res = analisar_tabela(cabecalho, dados, formato=formato, dica=dica, ia=ia, delimitador=delim)
    res.avisos = avisos + res.avisos
    res.mapeamento.setdefault("delimitador", {"\t": "tab"}.get(delim, delim))
    if len(linhas) > LIMITE_LINHAS:
        res.avisos.append(f"arquivo truncado em {LIMITE_LINHAS} linhas")
    return res


def analisar_xlsx(conteudo: bytes, *, dica: str | None = None, ia: Any = None) -> ResultadoParse:
    try:
        from openpyxl import load_workbook

        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as erro:  # noqa: BLE001  # arquivo corrompido ou não-xlsx
        return ResultadoParse(formato="xlsx", avisos=[f"planilha ilegível ({type(erro).__name__})"])
    melhor: tuple[str, int, list[list[Any]]] | None = None
    try:
        for aba in livro.worksheets:
            linhas: list[list[Any]] = []
            for linha in aba.iter_rows(values_only=True):
                valores = list(linha)
                while valores and _vazio(valores[-1]):
                    valores.pop()
                if valores and not all(_vazio(v) for v in valores):
                    linhas.append(valores)
                if len(linhas) >= LIMITE_LINHAS:
                    break
            uteis = sum(1 for linha in linhas if sum(not _vazio(v) for v in linha) >= 2)
            if melhor is None or uteis > melhor[1]:
                melhor = (aba.title, uteis, linhas)
    finally:
        livro.close()
    if not melhor or not melhor[2]:
        return ResultadoParse(formato="xlsx", avisos=["planilha vazia"])
    cabecalho, dados, avisos = tabela_de_linhas(melhor[2])
    res = analisar_tabela(cabecalho, dados, formato="xlsx", dica=dica, ia=ia)
    res.avisos = avisos + res.avisos
    res.mapeamento["planilha"] = melhor[0]
    return res


# ---------- perfil das colunas ----------


def _nomes(cabecalho: list[Any], ncol: int) -> list[str]:
    nomes, vistos = [], Counter()
    for i in range(ncol):
        bruto = cabecalho[i] if i < len(cabecalho) else None
        nome = _texto(bruto).strip("\"'") or f"coluna_{i + 1}"
        vistos[nome] += 1
        nomes.append(nome if vistos[nome] == 1 else f"{nome}_{vistos[nome]}")
    return nomes


def _perfilar(indice: int, nome: str, valores: list[Any], delimitador: str | None) -> Perfil:
    amostra = [v for v in valores if not _vazio(v)][:AMOSTRA]
    perfil = Perfil(indice=indice, nome=nome, preenchidos=len(amostra))
    if not amostra:
        return perfil
    n = len(amostra)
    nome_tempo = norm.nome_de_tempo(nome)
    numericos = [v for v in amostra if isinstance(v, (int, float)) and not isinstance(v, bool)]
    perfil.serial = nome_tempo and bool(numericos) and all(20000 <= v <= 80000 for v in numericos)
    perfil.decimal = norm.detectar_decimal(amostra, delimitador)
    datas, numeros, textos, horas = [], [], 0, 0
    for v in amostra:
        e_numero_puro = (isinstance(v, (int, float)) and not isinstance(v, bool)) or (
            isinstance(v, str) and bool(norm.RE_NUMERICO.match(v.strip()))
        )
        dt = None if e_numero_puro and not nome_tempo else norm.para_datetime(v, serial_excel=perfil.serial)
        num = norm.para_numero(v, perfil.decimal)
        so_hora = _e_so_hora(v)
        if dt:
            datas.append(dt)
        if num is not None:
            numeros.append(num)
        horas += so_hora
        textos += isinstance(v, str) and dt is None and num is None and not so_hora
    perfil.taxa_data = len(datas) / n
    perfil.taxa_num = len(numeros) / n
    perfil.taxa_hora = horas / n
    perfil.taxa_texto = textos / n
    perfil.variancia = statistics.pvariance(numeros) if len(numeros) > 1 else 0.0
    perfil.so_data = bool(datas) and all(d.hour == 0 and d.minute == 0 for d in datas)
    perfil.com_fuso = any(norm.tem_fuso_explicito(v) for v in amostra[:20] if not isinstance(v, (int, float)))
    if numericos and perfil.taxa_data >= 0.8 and not perfil.serial:
        perfil.com_fuso = True  # epoch é UTC
    return perfil


def _por_nome(
    perfis: list[Perfil], prefixos: tuple[str, ...], excluir: set[int], *, texto: bool = False
) -> Perfil | None:
    for p in perfis:
        if p.indice in excluir or not p.preenchidos:
            continue
        if norm._tem(norm.tokens(p.nome), prefixos) and (not texto or p.taxa_texto >= 0.5):
            return p
    return None


def _coluna_tempo(perfis: list[Perfil], preferidas: list[str]) -> Perfil | None:
    candidatos = [p for p in perfis if p.preenchidos and p.taxa_data >= 0.8]
    if not candidatos:
        return None
    return max(
        candidatos,
        key=lambda p: (p.nome in preferidas, norm.nome_de_tempo(p.nome), not p.so_data, p.taxa_data, -p.indice),
    )


def _coluna_hora(perfis: list[Perfil], excluir: set[int]) -> Perfil | None:
    candidatos = [p for p in perfis if p.indice not in excluir and p.preenchidos and p.taxa_hora >= 0.8]
    if not candidatos:
        return None
    return max(
        candidatos,
        key=lambda p: (
            norm._tem(norm.tokens(p.nome), NOMES_HORA),
            not norm._tem(norm.tokens(p.nome), NOMES_FIM),
            -p.indice,
        ),
    )


def _candidatos_valor(perfis: list[Perfil], excluir: set[int]) -> list[Perfil]:
    return [
        p for p in perfis
        if p.indice not in excluir and p.preenchidos and p.taxa_num >= 0.8 and p.taxa_data < 0.5
        and norm.elegivel_valor(p.nome)
    ]  # fmt: skip


def _escolher_valor(candidatos: list[Perfil], preferidas: list[str]) -> tuple[Perfil, bool]:
    for p in candidatos:
        if p.nome in preferidas:
            return p, False
    ordem = sorted(candidatos, key=lambda p: (norm.prioridade_valor(p.nome), p.variancia), reverse=True)
    melhor = ordem[0]
    return melhor, norm.prioridade_valor(melhor.nome) == 0 and len(candidatos) > 1


def _prioridade_id(nome: str) -> int:
    toks = norm.tokens(nome)
    if norm._tem(toks, ("user", "usuario", "aluno", "matricula", "login")):
        return 4
    if norm._tem(toks, ("sess",)):
        return 3
    if "ip" in toks or norm._tem(toks, ("addr", "client", "remote")):
        return 2
    if norm._tem(toks, ("transaction", "transac", "trace", "request")) and any(t in norm.IDS_EXATO for t in toks):
        return 1
    return 0


def _coluna_id(perfis: list[Perfil], excluir: set[int]) -> Perfil | None:
    candidatos = [p for p in perfis if p.indice not in excluir and p.preenchidos and _prioridade_id(p.nome) > 0]
    return max(candidatos, key=lambda p: (_prioridade_id(p.nome), -p.indice)) if candidatos else None


# ---------- dica do usuário e mapa do Gemini ----------


def _preferencias(dica: str | None, nomes: list[str]) -> dict[str, Any]:
    prefs: dict[str, Any] = {"colunas": []}
    if not dica:
        return prefs
    d = norm.chave(dica)
    if re.search(r"\b(utc|gmt)\b", d):
        prefs["fuso"] = norm.UTC
    if re.search(r"\b(soma|somar|sum)\b", d):
        prefs["agregacao"] = "soma"
    elif re.search(r"\b(max|maximo|pico)\b", d):
        prefs["agregacao"] = "max"
    for nome in sorted(nomes, key=len, reverse=True):
        c = norm.chave(nome)
        if len(c) >= 3 and c in d:
            prefs["colunas"].append(nome)
    return prefs


def _fuso_do_mapa(valor: str | None) -> Any:
    if not valor:
        return None
    if valor.strip().upper() in ("UTC", "GMT", "Z", "+00:00"):
        return norm.UTC
    try:
        return ZoneInfo(valor.strip())
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _agregacao_do_mapa(valor: str | None) -> str | None:
    c = norm.chave(valor or "")
    if c in ("soma", "sum", "somar", "total"):
        return "soma"
    if c in ("max", "maximo", "maximum", "pico"):
        return "max"
    return None


def _pedir_mapa(ia: Any, nomes: list[str], linhas: list[list[Any]], dica: str | None, res: ResultadoParse) -> dict:
    amostra = [[_texto(_celula(linha, i)) for i in range(len(nomes))] for linha in linhas[:8]]
    try:
        mapa = ia.mapear_colunas(list(nomes), amostra, dica)
    except Exception as erro:  # noqa: BLE001  # a IA nunca derruba a ingestão
        log.warning("mapear_colunas falhou: %s", erro)
        res.avisos.append(f"Gemini não mapeou as colunas ({type(erro).__name__}); usei regras")
        return {}
    if not isinstance(mapa, dict):
        return {}
    return {str(k): str(v) for k, v in mapa.items() if v not in (None, "")}


# ---------- análise ----------


def analisar_tabela(
    cabecalho: list[Any],
    linhas: list[list[Any]],
    *,
    formato: str,
    dica: str | None = None,
    ia: Any = None,
    delimitador: str | None = None,
) -> ResultadoParse:
    """Cabeçalho + linhas → pontos de carga, eventos ou contagem de distintos."""
    res = ResultadoParse(formato=formato)
    linhas = [list(linha) for linha in linhas if any(not _vazio(c) for c in linha)]
    res.linhas_lidas = len(linhas)
    if not linhas:
        res.avisos.append("tabela sem linhas de dados")
        return res
    ncol = max([len(cabecalho), *(len(linha) for linha in linhas)])
    nomes = _nomes(cabecalho, ncol)
    perfis = [_perfilar(i, nomes[i], [_celula(linha, i) for linha in linhas], delimitador) for i in range(ncol)]
    por_nome = {p.nome: p for p in perfis}
    prefs = _preferencias(dica, nomes)
    fuso, agregacao = prefs.get("fuso"), prefs.get("agregacao")

    tempo = _coluna_tempo(perfis, prefs["colunas"])
    excluir = {tempo.indice} if tempo else set()
    hora = _coluna_hora(perfis, excluir) if tempo and tempo.so_data else None
    if hora:
        excluir.add(hora.indice)
    candidatos = _candidatos_valor(perfis, excluir)
    descricao = _por_nome(perfis, NOMES_DESCRICAO, excluir, texto=True)
    valor, ambigua = _escolher_valor(candidatos, prefs["colunas"]) if candidatos else (None, False)
    nomeado = valor is not None and (norm.prioridade_valor(valor.nome) >= 1 or valor.nome in prefs["colunas"])

    precisa_ia = (tempo is None and (candidatos or descricao)) or (valor is not None and ambigua)
    if precisa_ia and ia is not None and getattr(ia, "disponivel", False):
        mapa = _pedir_mapa(ia, nomes, linhas, dica, res)
        if mapa.get("ts") in por_nome and mapa.get("valor") in por_nome:
            tempo, valor, ambigua, nomeado, hora = por_nome[mapa["ts"]], por_nome[mapa["valor"]], False, True, None
            agregacao = _agregacao_do_mapa(mapa.get("agregacao")) or agregacao
            fuso = _fuso_do_mapa(mapa.get("fuso")) or fuso
            res.origem = "gemini"
        elif mapa.get("data") in por_nome and mapa.get("descricao") in por_nome:
            tempo, descricao, valor, nomeado = por_nome[mapa["data"]], por_nome[mapa["descricao"]], None, False
            res.origem = "gemini"
        if res.origem == "gemini":
            res.mapeamento["mapeado_por"] = "gemini"

    if tempo and valor and (nomeado or descricao is None):
        return _metricas(res, linhas, tempo, hora, valor, fuso=fuso, agregacao=agregacao, ambigua=ambigua)
    if tempo and descricao:
        return _eventos(res, linhas, perfis, tempo, hora, descricao, excluir)
    if tempo and (identificador := _coluna_id(perfis, excluir)):
        return _distintos(res, linhas, tempo, identificador, fuso=fuso)
    if tempo is None:
        res.avisos.append("não encontrei coluna de data/hora (confira o cabeçalho ou mande uma dica)")
    else:
        res.avisos.append("não encontrei coluna numérica de carga nem descrição de evento")
    return res


def _descricao_fuso(tempo: Perfil, fuso: Any) -> str:
    if fuso is not None:
        return f"{getattr(fuso, 'key', 'UTC')} → America/Sao_Paulo"
    if tempo.com_fuso:
        return "convertido para America/Sao_Paulo"
    return "America/Sao_Paulo (sem fuso na origem)"


def _ts_da_linha(linha: list[Any], tempo: Perfil, hora: Perfil | None, fuso: Any):
    ts = norm.para_datetime(_celula(linha, tempo.indice), fuso=fuso, serial_excel=tempo.serial)
    if ts is None or hora is None:
        return ts
    hhmm = norm.para_hora(_celula(linha, hora.indice))
    return ts.replace(hour=int(hhmm[:2]), minute=int(hhmm[3:])) if hhmm else None


def _metricas(res, linhas, tempo, hora, valor, *, fuso, agregacao, ambigua) -> ResultadoParse:
    pares, ignoradas, negativos = [], 0, 0
    for linha in linhas:
        ts = _ts_da_linha(linha, tempo, hora, fuso)
        v = norm.para_numero(_celula(linha, valor.indice), valor.decimal)
        if ts is None or v is None:
            ignoradas += 1
            continue
        if v < 0:
            negativos += 1
            continue
        pares.append((ts, v))
    tipo = norm.tipo_metrica(valor.nome)
    modo = agregacao or ("soma" if tipo == "contador" else "max")
    res.pontos = norm.agregar(pares, modo)
    res.linhas_ignoradas += ignoradas + negativos
    res.mapeamento.update(
        ts=tempo.nome + (f" + {hora.nome}" if hora else ""),
        valor=valor.nome,
        agregacao=modo,
        metrica_original=valor.nome,
        fuso=_descricao_fuso(tempo, fuso),
        decimal=valor.decimal,
    )
    if not pares:
        res.avisos.append(f"nenhuma linha com data e valor válidos em '{tempo.nome}' / '{valor.nome}'")
        return res
    if modo == "soma":
        res.avisos.append(
            f"'{valor.nome}' é contagem: somei por janela de 15 min; a capacidade do portal é em acessos "
            "simultâneos, confira a escala"
        )
    if ambigua:
        res.avisos.append(f"coluna de carga escolhida pela variância: '{valor.nome}' (confira ou mande uma dica)")
    elif tipo == "desconhecido" and modo == "max":
        res.avisos.append(f"'{valor.nome}' tratada como acessos simultâneos (máximo por janela)")
    if negativos:
        res.avisos.append(f"{negativos} valor(es) negativo(s) descartado(s)")
    if ignoradas:
        res.avisos.append(f"{ignoradas} linha(s) sem data ou valor legível ignorada(s)")
    res.avisos.extend(norm.avisos_de_resolucao([ts for ts, _ in pares], modo))
    return res


def _eventos(res, linhas, perfis, tempo, hora, descricao, excluir) -> ResultadoParse:
    usados = excluir | {descricao.indice}
    tipo_col = _por_nome(perfis, NOMES_TIPO, usados)
    inicio_col = hora or _por_nome(perfis, NOMES_INICIO, usados)
    fim_col = _por_nome(perfis, NOMES_FIM, usados | ({inicio_col.indice} if inicio_col else set()))
    turmas_col = _por_nome(perfis, NOMES_TURMAS, usados)
    alunos_col = _por_nome(perfis, NOMES_ALUNOS, usados)
    eventos: dict[tuple[str, str], Evento] = {}
    ignoradas = 0
    for linha in linhas:
        dt = norm.para_datetime(_celula(linha, tempo.indice), serial_excel=tempo.serial)
        desc = _texto(_celula(linha, descricao.indice))[:300]
        if dt is None or not desc or _vazio(desc):
            ignoradas += 1
            continue
        tipo = (norm.tipo_de_valor(_celula(linha, tipo_col.indice), desc) if tipo_col else None) or norm.inferir_tipo(
            desc
        )
        ini = norm.para_hora(_celula(linha, inicio_col.indice)) if inicio_col else None
        if ini is None and (dt.hour or dt.minute):
            ini = dt.strftime("%H:%M")
        fim_bruto = _celula(linha, fim_col.indice) if fim_col else None
        fim = norm.para_hora(fim_bruto)
        fim_dt = norm.para_datetime(fim_bruto) if fim is None and fim_bruto is not None else None
        if fim_dt and fim_dt.date() > dt.date():
            desc = f"{desc} (até {fim_dt:%d/%m})"[:300]
        ini, fim = norm.horas_padrao(tipo, ini, fim)
        alunos = norm.para_numero(_celula(linha, alunos_col.indice)) if alunos_col else None
        try:
            ev = Evento(
                data=dt.date().isoformat(),
                hora_inicio=ini,
                hora_fim=fim,
                tipo=tipo,
                descricao=desc,
                turmas=norm.dividir_turmas(_celula(linha, turmas_col.indice)) if turmas_col else [],
                alunos=int(alunos) if alunos is not None and alunos >= 0 else None,
            )
        except ValidationError:
            ignoradas += 1
            continue
        eventos.setdefault((ev.data, ev.descricao.lower()), ev)
    res.eventos = list(eventos.values())
    res.linhas_ignoradas += ignoradas
    res.mapeamento.update(data=tempo.nome, descricao=descricao.nome)
    for chave_mapa, perfil in (
        ("tipo", tipo_col),
        ("hora_inicio", inicio_col),
        ("hora_fim", fim_col),
        ("turmas", turmas_col),
        ("alunos", alunos_col),
    ):
        if perfil:
            res.mapeamento[chave_mapa] = perfil.nome
    if ignoradas:
        res.avisos.append(f"{ignoradas} linha(s) sem data ou descrição ignorada(s)")
    return res


def _distintos(res, linhas, tempo, identificador, *, fuso) -> ResultadoParse:
    pares, ignoradas = [], 0
    for linha in linhas:
        ts = norm.para_datetime(_celula(linha, tempo.indice), fuso=fuso, serial_excel=tempo.serial)
        ident = _celula(linha, identificador.indice)
        if ts is None or _vazio(ident):
            ignoradas += 1
            continue
        pares.append((ts, str(ident).strip()))
    res.pontos = norm.agregar_distintos(pares)
    res.linhas_ignoradas += ignoradas
    res.mapeamento.update(
        ts=tempo.nome,
        valor=f"distintos de {identificador.nome}",
        agregacao="distintos",
        metrica_original=identificador.nome,
        fuso=_descricao_fuso(tempo, fuso),
    )
    res.avisos.append(f"sem coluna numérica de carga: carga = '{identificador.nome}' distintos por janela de 15 min")
    if ignoradas:
        res.avisos.append(f"{ignoradas} registro(s) sem data ou identificador ignorado(s)")
    res.avisos.extend(norm.avisos_de_resolucao([ts for ts, _ in pares], "distintos"))
    return res
