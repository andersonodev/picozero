# backend/picozero/ingestao/deteccao.py
# Descobre o formato pelo conteúdo (assinatura binária, estrutura do texto); extensão e
# content-type só desempatam, porque navegador manda CSV como 'application/vnd.ms-excel'.
import csv
import json
import re
from collections import Counter
from pathlib import PurePath

FORMATOS = (
    "csv", "tsv", "xlsx", "json", "ndjson", "log", "prometheus", "ics", "pdf", "imagem", "docx", "texto",
    "xls", "binario", "vazio",
)  # fmt: skip

POR_EXTENSAO = {
    ".csv": "csv", ".tsv": "tsv", ".tab": "tsv", ".xlsx": "xlsx", ".xlsm": "xlsx", ".xls": "xls",
    ".json": "json", ".geojson": "json", ".ndjson": "ndjson", ".jsonl": "ndjson", ".log": "log",
    ".prom": "prometheus", ".metrics": "prometheus", ".ics": "ics", ".ical": "ics", ".ifb": "ics",
    ".pdf": "pdf", ".png": "imagem", ".jpg": "imagem", ".jpeg": "imagem", ".webp": "imagem", ".gif": "imagem",
    ".heic": "imagem", ".heif": "imagem", ".docx": "docx", ".txt": "texto", ".md": "texto", ".eml": "texto",
}  # fmt: skip

POR_MIME = {
    "text/csv": "csv", "text/tab-separated-values": "tsv", "application/json": "json",
    "application/x-ndjson": "ndjson", "application/jsonl": "ndjson", "application/x-jsonlines": "ndjson",
    "text/calendar": "ics", "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "texto", "text/markdown": "texto", "message/rfc822": "texto",
    "application/openmetrics-text": "prometheus",
}  # fmt: skip

TEXTUAIS = {"csv", "tsv", "json", "ndjson", "log", "prometheus", "ics", "texto"}

RE_LOG_LINHA = re.compile(
    r'^(?P<ip>\S+) \S+ (?P<usuario>\S+) \[(?P<ts>[^\]]+)\] "(?P<req>[^"]*)" (?P<status>\d{3}|-) (?P<bytes>\d+|-)'
    r'(?: "(?P<ref>[^"]*)" "(?P<ua>[^"]*)")?'
)
RE_PROM_AMOSTRA = re.compile(
    r"^(?P<nome>[a-zA-Z_:][a-zA-Z0-9_:]*)(?P<labels>\{[^}]*\})?\s+"
    r"(?P<valor>[-+]?(?:\d+(?:\.\d*)?(?:[eE][-+]?\d+)?|\.\d+|NaN|Inf|\+Inf|-Inf))(?:\s+(?P<ts>-?\d+))?\s*$"
)


def decodificar(conteudo: bytes) -> tuple[str, str]:
    """Bytes → texto. Tenta UTF-16 (com BOM), UTF-8 (com/sem BOM), cp1252 e latin-1."""
    if conteudo.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return conteudo.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass
    if conteudo.startswith(b"\xef\xbb\xbf"):
        try:
            return conteudo.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return conteudo.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1", errors="replace"), "latin-1"


def mime_da_imagem(conteudo: bytes) -> str:
    if conteudo.startswith(b"\x89PNG"):
        return "image/png"
    if conteudo.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if conteudo.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return "image/webp"
    return "image/heic"


def _por_assinatura(conteudo: bytes) -> str | None:
    inicio = conteudo.lstrip()[:16]
    if inicio.startswith(b"%PDF"):
        return "pdf"
    if conteudo.startswith(b"PK\x03\x04"):
        trecho = conteudo[:200_000]
        if b"xl/" in trecho or (b"[Content_Types].xml" in trecho and b"spreadsheetml" in trecho):
            return "xlsx"
        if b"word/" in trecho:
            return "docx"
        return "binario"
    if conteudo.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"  # Excel 97-2003 (OLE2)
    if conteudo.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")):
        return "imagem"
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return "imagem"
    if conteudo[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypheif"):
        return "imagem"
    return None


def _parece_binario(amostra: bytes) -> bool:
    if not amostra or amostra.startswith((b"\xff\xfe", b"\xfe\xff")):
        return False
    if b"\x00" in amostra:
        return True
    controle = sum(1 for b in amostra if b < 9 or 13 < b < 32)
    return controle / len(amostra) > 0.1


def _e_objeto_json(linha: str) -> bool:
    linha = linha.strip()
    if not (linha.startswith("{") and linha.endswith("}")):
        return False
    try:
        return isinstance(json.loads(linha), dict)
    except json.JSONDecodeError:
        return False


def delimitador_tabular(linhas: list[str]) -> str | None:
    """Delimitador que dá o mesmo nº de campos (≥ 2) em pelo menos 80% das linhas."""
    melhor, melhor_nota = None, 0.0
    for delim in (",", ";", "\t", "|"):
        contagens = [len(campos) for campos in csv.reader(linhas, delimiter=delim)]
        if not contagens:
            continue
        campos, vezes = Counter(contagens).most_common(1)[0]
        if campos < 2 or vezes / len(contagens) < 0.8:
            continue
        nota = vezes / len(contagens) + campos / 1000
        if nota > melhor_nota:
            melhor, melhor_nota = delim, nota
    return melhor


def _por_texto(texto: str, completo: bool) -> str:
    s = texto.lstrip("﻿ \t\r\n")
    if s[:15].upper().startswith("BEGIN:VCALENDAR"):
        return "ics"
    linhas = [linha for linha in s.splitlines() if linha.strip()][:30]
    if s and s[0] in "{[":
        if completo:
            try:
                json.loads(s)
                return "json"
            except json.JSONDecodeError:
                pass
        objetos = sum(_e_objeto_json(linha) for linha in linhas)
        if linhas and objetos >= max(1, 0.8 * len(linhas)) and (len(linhas) > 1 or not completo):
            return "ndjson"
        if not completo:
            return "json"
    if linhas and sum(bool(RE_LOG_LINHA.match(linha)) for linha in linhas) >= 0.6 * len(linhas):
        return "log"
    if linhas:
        comentarios = [linha for linha in linhas if linha.startswith(("# HELP", "# TYPE"))]
        amostras = [linha for linha in linhas if not linha.startswith("#")]
        casam = sum(bool(RE_PROM_AMOSTRA.match(linha.strip())) for linha in amostras)
        if amostras and casam >= 0.8 * len(amostras) and (comentarios or casam >= 3):
            return "prometheus"
    if len(linhas) >= 3:
        delim = delimitador_tabular(linhas[:20])
        if delim:
            return "tsv" if delim == "\t" else "csv"
    return "texto"


def extensao(nome: str | None) -> str | None:
    if not nome:
        return None
    return POR_EXTENSAO.get(PurePath(nome).suffix.lower())


def formato_do_mime(content_type: str | None) -> str | None:
    if not content_type:
        return None
    mime = content_type.split(";")[0].strip().lower()
    if mime.startswith("image/"):
        return "imagem"
    return POR_MIME.get(mime)


def detectar_formato(conteudo: bytes, nome: str | None = None, content_type: str | None = None) -> str:
    """Um de FORMATOS. Conteúdo primeiro; extensão/content-type desempatam texto ambíguo."""
    if not conteudo or not conteudo.strip():
        return "vazio"
    if magica := _por_assinatura(conteudo):
        if magica == "binario":
            return extensao(nome) if extensao(nome) in ("xlsx", "docx") else "binario"
        return magica
    ext, mime = extensao(nome), formato_do_mime(content_type)
    if _parece_binario(conteudo[:4096]):
        return ext if ext in ("xlsx", "docx", "pdf", "imagem", "xls") else "binario"
    limite = 262_144
    texto, _ = decodificar(conteudo[:limite])
    detectado = _por_texto(texto, completo=len(conteudo) <= limite)
    if detectado == "texto":
        dica = ext if ext in TEXTUAIS else mime if mime in TEXTUAIS else None
        if dica in ("csv", "tsv") and any(x.strip() for x in texto.splitlines()):
            return dica
        if dica in ("log", "prometheus", "ics", "json", "ndjson"):
            return dica
    return detectado


def ler_texto(conteudo: bytes) -> tuple[str, str]:
    """Atalho para os parsers textuais: decodifica e normaliza quebras de linha."""
    texto, encoding = decodificar(conteudo)
    return texto.replace("\r\n", "\n").replace("\r", "\n"), encoding


__all__ = ["FORMATOS", "decodificar", "delimitador_tabular", "detectar_formato", "extensao", "ler_texto"]
