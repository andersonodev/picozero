# backend/picozero/ingestao/ics.py
# iCalendar (Google Agenda, Outlook, export do calendário acadêmico) → eventos.
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from ..config import TZ
from ..dominio import Evento, ResultadoParse
from . import normalizacao as norm

RE_DATA_ICS = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?$")


def _desdobrar(texto: str) -> list[str]:
    """RFC 5545: linha que começa com espaço/tab continua a anterior."""
    linhas: list[str] = []
    for linha in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if linha[:1] in (" ", "\t") and linhas:
            linhas[-1] += linha[1:]
        else:
            linhas.append(linha)
    return linhas


def _separar(linha: str) -> tuple[str, dict[str, str], str] | None:
    """'DTSTART;TZID=America/Sao_Paulo:20261112T190000' → ('DTSTART', {'TZID': …}, '2026…')."""
    entre_aspas, corte = False, -1
    for i, c in enumerate(linha):
        if c == '"':
            entre_aspas = not entre_aspas
        elif c == ":" and not entre_aspas:
            corte = i
            break
    if corte < 0:
        return None
    nome, *params = linha[:corte].split(";")
    parametros = {}
    for p in params:
        if "=" in p:
            k, v = p.split("=", 1)
            parametros[k.upper()] = v.strip('"')
    return nome.upper(), parametros, linha[corte + 1 :]


def _desescapar(texto: str) -> str:
    return texto.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _data_ics(valor: str, params: dict[str, str]) -> tuple[datetime, bool] | None:
    """→ (datetime local sem fuso, dia_inteiro)."""
    m = RE_DATA_ICS.match(valor.strip())
    if not m:
        return None
    try:
        if m[4] is None or params.get("VALUE", "").upper() == "DATE":
            return datetime(int(m[1]), int(m[2]), int(m[3])), True
        dt = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6] or 0))
    except ValueError:
        return None
    if m[7]:
        return norm.para_local(dt, norm.UTC), False
    if tzid := params.get("TZID"):
        try:
            return norm.para_local(dt, ZoneInfo(tzid)), False
        except (ZoneInfoNotFoundError, ValueError):
            return dt, False  # fuso desconhecido: assume local
    return dt, False  # "flutuante": horário local


def _evento(props: dict[str, tuple[dict[str, str], str]]) -> Evento | None:
    if "DTSTART" not in props:
        return None
    inicio = _data_ics(props["DTSTART"][1], props["DTSTART"][0])
    if inicio is None:
        return None
    ini_dt, dia_inteiro = inicio
    fim = _data_ics(props["DTEND"][1], props["DTEND"][0]) if "DTEND" in props else None
    resumo = _desescapar(props.get("SUMMARY", ({}, ""))[1]).strip()
    detalhe = _desescapar(props.get("DESCRIPTION", ({}, ""))[1])
    categorias = _desescapar(props.get("CATEGORIES", ({}, ""))[1])
    tipo = norm.inferir_tipo(f"{resumo} {categorias}")
    if tipo == "outro":
        tipo = norm.inferir_tipo(f"{resumo} {categorias} {detalhe}")
    descricao = resumo or detalhe.strip().split("\n")[0] or "Evento do calendário"
    hora_ini = hora_fim = None
    if not dia_inteiro:
        hora_ini = ini_dt.strftime("%H:%M")
        if fim and fim[0].date() == ini_dt.date():
            hora_fim = fim[0].strftime("%H:%M")
        elif fim:
            hora_fim = "23:59"
    if fim:
        # DTEND é exclusivo: dia inteiro ou término à 00:00 encerram no dia anterior.
        termina_meia_noite = fim[1] or (fim[0].hour == 0 and fim[0].minute == 0)
        ultimo: date = fim[0].date() - timedelta(days=1) if termina_meia_noite else fim[0].date()
        if ultimo > ini_dt.date():
            descricao = f"{descricao} (até {ultimo:%d/%m})"
    hora_ini, hora_fim = norm.horas_padrao(tipo, hora_ini, hora_fim)
    turmas = []
    if m := re.search(r"turmas?\s*:\s*([^\n]+)", detalhe, re.IGNORECASE):
        turmas = norm.dividir_turmas(m[1])
    alunos = None
    if m := re.search(r"(\d+)\s*(?:alunos|estudantes)", f"{resumo} {detalhe}", re.IGNORECASE):
        alunos = int(m[1])
    try:
        return Evento(
            data=ini_dt.date().isoformat(),
            hora_inicio=hora_ini,
            hora_fim=hora_fim,
            tipo=tipo,
            descricao=descricao[:300],
            turmas=turmas,
            alunos=alunos,
        )
    except ValidationError:
        return None


def analisar_ics(texto: str) -> ResultadoParse:
    res = ResultadoParse(formato="ics")
    eventos: dict[tuple[str, str], Evento] = {}
    atual: dict | None = None
    recorrentes = 0
    for linha in _desdobrar(texto):
        cabeca = linha.strip().upper()
        if cabeca == "BEGIN:VEVENT":
            atual = {}
            continue
        if cabeca == "END:VEVENT":
            if atual is not None:
                res.linhas_lidas += 1
                recorrentes += "RRULE" in atual
                ev = _evento(atual)
                if ev is None:
                    res.linhas_ignoradas += 1
                else:
                    eventos.setdefault((ev.data, ev.descricao.lower()), ev)
            atual = None
            continue
        if atual is not None and (partes := _separar(linha)):
            nome, params, valor = partes
            atual.setdefault(nome, (params, valor))
    res.eventos = list(eventos.values())
    res.mapeamento.update(fonte="iCalendar", fuso=f"convertido para {TZ.key}")
    if not res.linhas_lidas:
        res.avisos.append("nenhum VEVENT no calendário")
    if res.linhas_ignoradas:
        res.avisos.append(f"{res.linhas_ignoradas} VEVENT(s) sem DTSTART válido ignorado(s)")
    if recorrentes:
        res.avisos.append(f"{recorrentes} evento(s) recorrente(s) (RRULE): só a primeira ocorrência entrou")
    return res
