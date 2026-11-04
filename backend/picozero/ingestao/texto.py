# backend/picozero/ingestao/texto.py
# Texto livre → eventos por regras (quando o Gemini não está disponível): e-mail da secretaria,
# texto de PDF, DOCX. Cada data encontrada vira um evento; o texto ao redor vira a descrição.
import re
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from pydantic import ValidationError

from ..dominio import Evento, ResultadoParse
from . import normalizacao as norm

MESES_EXTENSO = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}  # fmt: skip
HORA = r"(?:[01]?\d|2[0-3])(?:\s*(?:hrs|hs|h)\s*(?:[0-5]\d)?(?:\s*min)?|:[0-5]\d)"

RE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
RE_BARRA = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?(?![\d/])")
RE_EXTENSO = re.compile(
    r"(?<!\d)(\d{1,2})(?:º|°|o)?\s+de\s+(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro"
    r"|novembro|dezembro)(?:\s+de\s+(\d{4}))?",
    re.IGNORECASE,
)
RE_ABREV = re.compile(
    r"(?<![\d/])(\d{1,2})\s*[/-]\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\b\.?(?:\s*[/-]\s*(\d{4}|\d{2}))?",
    re.IGNORECASE,
)
RE_HORA = re.compile(rf"(?<![\d/:.,])({HORA})(?![\d/])", re.IGNORECASE)
RE_PREFIXO_HORA = re.compile(
    rf"^\s*,?\s*(?:(?:às|as|a partir das|a partir de|das|de|por volta das|até)\s+)?{HORA}"
    rf"(?:\s*(?:às|as|a|até|-|–)\s*{HORA})?",
    re.IGNORECASE,
)
RE_SEPARADOR = re.compile(r"^\s*(?:;|,|\.(?:\s|$)|\be\b|\bou\b|\||–|—)", re.IGNORECASE)
RE_INTERVALO = re.compile(r"^\s*(?:a|até|ate|à|ao|-|–|—)\s*$", re.IGNORECASE)
RE_RUIDO = re.compile(r"atualizad|publicad|\bvers[aã]o\b|p[aá]gina \d|impresso em|gerado em", re.IGNORECASE)
# Conectores nas pontas da descrição. Sensível a caixa de propósito: "AS" e "A" maiúsculos são
# siglas (Avaliação Substitutiva), "as"/"As" no começo da frase são artigo.
_CONECTORES = r"(?:[EeOoAa]|[OoAa]s|[Nn][oa]s?|[Ee]m|[Dd]ias?|[Dd][eoa]s?|[Ee]ntre|[Aa]t[ée]|[Àà]s?)"
RE_INICIO_LIXO = re.compile(
    rf"^(?:[\s,;:.\-–—•·*>|()]+|(?:[Ii]nformamos|[Cc]omunicamos|[Ll]embramos|[Aa]visamos)\s+que\b|{_CONECTORES}\b)+"
)
RE_FIM_LIXO = re.compile(
    r"(?:[\s,;:.\-–—•·*|(]+|\b(?:em|às|as|a|é|e|dia|no|na|de|do|da|das|dos|até|ate|partir|entre|para|será|serão"
    r"|sera|serao|são|sao|ocorre|ocorrerá|acontece|previsto|prevista|marcado|marcada)\b)+$"
)


@dataclass
class Data:
    inicio: int
    fim: int
    dia: date


def _ano(texto: str | None) -> int | None:
    if not texto:
        return None
    ano = int(texto)
    return ano + 2000 if ano < 100 else ano


def _dia(d: int, m: int, ano: int | None, referencia: date) -> date | None:
    if not (1 <= m <= 12 and 1 <= d <= 31):
        return None
    if ano is None:
        return norm.ano_provavel(d, m, referencia)
    try:
        return date(ano, m, d)
    except ValueError:
        return None


def achar_datas(linha: str, referencia: date) -> list[Data]:
    achados: list[Data] = []
    for m in RE_ISO.finditer(linha):
        if dia := _dia(int(m[3]), int(m[2]), int(m[1]), referencia):
            achados.append(Data(m.start(), m.end(), dia))
    for m in RE_BARRA.finditer(linha):
        if dia := _dia(int(m[1]), int(m[2]), _ano(m[3]), referencia):
            achados.append(Data(m.start(), m.end(), dia))
    for m in RE_EXTENSO.finditer(linha):
        mes = MESES_EXTENSO[norm.chave(m[2])]
        if dia := _dia(int(m[1]), mes, _ano(m[3]), referencia):
            achados.append(Data(m.start(), m.end(), dia))
    for m in RE_ABREV.finditer(linha):
        if (mes := norm.mes_por_nome(m[2])) and (dia := _dia(int(m[1]), mes, _ano(m[3]), referencia)):
            achados.append(Data(m.start(), m.end(), dia))
    # sem sobreposição: fica o achado mais longo que começa primeiro
    achados.sort(key=lambda d: (d.inicio, -(d.fim - d.inicio)))
    finais: list[Data] = []
    for d in achados:
        if not finais or d.inicio >= finais[-1].fim:
            finais.append(d)
    return finais


def _agrupar(linha: str, datas: list[Data]) -> list[tuple[Data, Data | None]]:
    """'de 24/09 a 30/09' e 'entre 12/11 e 18/11' viram intervalos (um evento no 1º dia)."""
    grupos: list[tuple[Data, Data | None]] = []
    i = 0
    while i < len(datas):
        atual = datas[i]
        if i + 1 < len(datas):
            prox = datas[i + 1]
            entre = linha[atual.fim : prox.inicio]
            e_entre = re.fullmatch(r"\s*e\s*", entre) and re.search(r"entre\s*$", linha[: atual.inicio], re.IGNORECASE)
            if (RE_INTERVALO.match(entre) or e_entre) and 0 < (prox.dia - atual.dia).days <= 180:
                grupos.append((atual, prox))
                i += 2
                continue
        grupos.append((atual, None))
        i += 1
    return grupos


def _limpar(trecho: str) -> str:
    t = RE_HORA.sub(" ", trecho)
    for regex in (RE_ISO, RE_BARRA, RE_EXTENSO, RE_ABREV):
        t = regex.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    anterior = None
    while anterior != t:
        anterior = t
        t = RE_INICIO_LIXO.sub("", t)
        t = RE_FIM_LIXO.sub("", t).strip()
    return t[:1].upper() + t[1:] if t else ""


def _util(texto: str, minimo: int) -> bool:
    return len(texto) >= minimo and bool(re.search(r"[A-Za-zÀ-ÿ]{3}", texto))


def _escolher_descricao(antes: str, depois: str) -> str:
    """Lista ("24/09 Mostra de Ciência") usa o texto depois da data; frase ("a AP2 abre dia 12/11
    às 19h para as turmas…") usa o de antes quando só ele diz o que acontece."""
    antes = antes if _util(antes, 3) else ""
    depois = depois if _util(depois, 8) else ""
    if antes and depois:
        so_antes_diz = norm.inferir_tipo(antes) != "outro" and norm.inferir_tipo(depois) == "outro"
        return antes if so_antes_diz else depois
    return depois or antes


def _horas(*trechos: str) -> tuple[str | None, str | None]:
    horas: list[str] = []
    for trecho in trechos:
        for m in RE_HORA.finditer(trecho):
            if (h := norm.para_hora(m[1].replace(" ", ""))) and h not in horas:
                horas.append(h)
    if not horas:
        return None, None
    return horas[0], (horas[1] if len(horas) > 1 else None)


def eventos_de_texto(texto: str, *, formato: str = "texto", referencia: date | None = None) -> ResultadoParse:
    referencia = referencia or norm.hoje()
    res = ResultadoParse(formato=formato)
    eventos: dict[tuple[str, str], Evento] = {}
    contexto = ""
    sem_descricao = 0
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        res.linhas_lidas += 1
        datas = achar_datas(linha, referencia)
        if not datas:
            contexto = _limpar(linha)[:160]
            continue
        grupos = _agrupar(linha, datas)
        cortes = [0]
        for atual, prox in pairwise(grupos):
            fim_atual = (atual[1] or atual[0]).fim
            entre = linha[fim_atual : prox[0].inicio]
            m_hora = RE_PREFIXO_HORA.match(entre)
            resto = m_hora.end() if m_hora else 0
            m_sep = RE_SEPARADOR.match(entre[resto:])
            if m_sep:  # frase: "notas em 20/11 às 18h e o vencimento é 10/12" corta no "e"
                cortes.append(fim_atual + resto + m_sep.end() - len(m_sep[0].lstrip()))
            else:  # lista: "24/09 Mostra de Ciência 25/09 …" o texto entre as datas é do item anterior
                cortes.append(prox[0].inicio)
        cortes.append(len(linha))
        anterior = ""
        for k, (ini, fim) in enumerate(grupos):
            trecho = linha[cortes[k] : cortes[k + 1]]
            if RE_RUIDO.search(trecho):
                continue
            antes = linha[cortes[k] : ini.inicio]
            depois = linha[(fim or ini).fim : cortes[k + 1]]
            descricao = _escolher_descricao(_limpar(antes), _limpar(depois)) or anterior or contexto
            if not descricao:
                sem_descricao += 1
                continue
            anterior = descricao
            tipo = norm.inferir_tipo(descricao)
            if tipo == "outro":
                tipo = norm.inferir_tipo(trecho)
            if fim:
                descricao = f"{descricao} (de {ini.dia:%d/%m} a {fim.dia:%d/%m})"
            hora_ini, hora_fim = norm.horas_padrao(tipo, *_horas(depois, antes))
            alunos = re.search(r"(\d+)\s*(?:alunos|estudantes)", trecho, re.IGNORECASE)
            try:
                ev = Evento(
                    data=ini.dia.isoformat(),
                    hora_inicio=hora_ini,
                    hora_fim=hora_fim,
                    tipo=tipo,
                    descricao=descricao[:300],
                    alunos=int(alunos[1]) if alunos else None,
                )
            except ValidationError:
                continue
            eventos.setdefault((ev.data, ev.descricao.lower()), ev)
    res.eventos = list(eventos.values())
    res.mapeamento.update(metodo="regras (datas dd/mm, 'dd de mês', ISO)", referencia_ano=referencia.isoformat())
    if not res.eventos:
        res.avisos.append("nenhuma data reconhecida no texto")
    if sem_descricao:
        res.avisos.append(f"{sem_descricao} data(s) sem descrição ignorada(s)")
    return res
