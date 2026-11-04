# backend/picozero/ingestao/documentos.py
# Documentos (PDF, imagem, DOCX): o Gemini lê o documento inteiro quando há chave; sem ela,
# o PDF vira texto pelo pypdf e o DOCX pelo XML interno, e as regras de texto.py extraem as datas.
import io
import logging
import zipfile
from typing import Any
from xml.etree import ElementTree

from pydantic import ValidationError

from ..dominio import Evento, ResultadoParse
from .tabular import analisar_tabela, tabela_de_linhas
from .texto import eventos_de_texto

log = logging.getLogger(__name__)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_PAGINAS = 60


def ia_disponivel(ia: Any) -> bool:
    return ia is not None and bool(getattr(ia, "disponivel", False))


def eventos_pela_ia(
    ia: Any, conteudo: bytes | str, mime: str, dica: str | None, formato: str, avisos: list[str]
) -> ResultadoParse | None:
    """Pede os eventos ao Gemini; None (com aviso) se ele falhar ou não responder."""
    try:
        brutos = ia.extrair_eventos(conteudo, mime, dica)
    except Exception as erro:  # noqa: BLE001  # a IA nunca derruba a ingestão
        log.warning("extrair_eventos falhou: %s", erro)
        avisos.append(f"Gemini falhou ({type(erro).__name__}); usei regras")
        return None
    if brutos is None:
        return None
    eventos, invalidos = [], 0
    for item in brutos:
        try:
            eventos.append(item if isinstance(item, Evento) else Evento.model_validate(item))
        except ValidationError:
            invalidos += 1
    res = ResultadoParse(
        formato=formato,
        eventos=eventos,
        origem="gemini",
        linhas_lidas=len(eventos) + invalidos,
        linhas_ignoradas=invalidos,
        avisos=list(avisos),
    )
    res.mapeamento["metodo"] = "Gemini (leitura do documento)"
    if invalidos:
        res.avisos.append(f"{invalidos} evento(s) do Gemini fora do formato descartado(s)")
    return res


def _texto_pdf(conteudo: bytes) -> tuple[str, str | None]:
    try:
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(conteudo))
        if leitor.is_encrypted and not leitor.decrypt(""):
            return "", "PDF protegido por senha"
        paginas = [pagina.extract_text() or "" for pagina in leitor.pages[:MAX_PAGINAS]]
    except Exception as erro:  # noqa: BLE001  # pypdf levanta vários tipos para PDF quebrado
        return "", f"PDF ilegível ({type(erro).__name__})"
    texto = "\n".join(paginas).strip()
    if not texto:
        return "", "PDF sem texto extraível (digitalizado?): precisa do Gemini para ler"
    return texto, None


def analisar_pdf(conteudo: bytes, *, dica: str | None = None, ia: Any = None) -> ResultadoParse:
    avisos: list[str] = []
    if ia_disponivel(ia) and (res := eventos_pela_ia(ia, conteudo, "application/pdf", dica, "pdf", avisos)):
        return res
    texto, erro = _texto_pdf(conteudo)
    if erro:
        return ResultadoParse(formato="pdf", avisos=[*avisos, erro])
    res = eventos_de_texto(texto, formato="pdf")
    res.avisos = avisos + res.avisos
    if not ia_disponivel(ia):
        res.avisos.append("sem Gemini: só datas explícitas do PDF (dd/mm, 'dd de mês') viraram eventos")
    return res


def analisar_imagem(conteudo: bytes, mime: str, *, dica: str | None = None, ia: Any = None) -> ResultadoParse:
    if not ia_disponivel(ia):
        return ResultadoParse(formato="imagem", avisos=["imagem precisa do Gemini (defina VERTEX_API_KEY)"])
    avisos: list[str] = []
    res = eventos_pela_ia(ia, conteudo, mime, dica, "imagem", avisos)
    return res or ResultadoParse(formato="imagem", avisos=[*avisos, "o Gemini não devolveu eventos da imagem"])


def _texto_no(no: ElementTree.Element) -> str:
    return "".join(t.text or "" for t in no.iter(f"{W}t"))


def _ler_docx(conteudo: bytes) -> tuple[list[str], list[list[list[str]]], str | None]:
    """→ (parágrafos, tabelas, erro). Parágrafos de tabela entram como 'célula | célula'."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            xml = pacote.read("word/document.xml")
        raiz = ElementTree.fromstring(xml)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as erro:
        return [], [], f"DOCX ilegível ({type(erro).__name__})"
    corpo = raiz.find(f"{W}body")
    paragrafos: list[str] = []
    tabelas: list[list[list[str]]] = []
    for filho in list(corpo) if corpo is not None else []:
        if filho.tag == f"{W}p":
            paragrafos.append(_texto_no(filho))
        elif filho.tag == f"{W}tbl":
            linhas = [[_texto_no(celula).strip() for celula in tr.iter(f"{W}tc")] for tr in filho.iter(f"{W}tr")]
            tabelas.append(linhas)
            paragrafos.extend(" | ".join(linha) for linha in linhas)
    return paragrafos, tabelas, None


def analisar_docx(conteudo: bytes, *, dica: str | None = None, ia: Any = None) -> ResultadoParse:
    paragrafos, tabelas, erro = _ler_docx(conteudo)
    if erro:
        return ResultadoParse(formato="docx", avisos=[erro])
    for tabela in tabelas:  # calendário em tabela: lê como planilha
        if len(tabela) >= 2 and max(len(linha) for linha in tabela) >= 2:
            cabecalho, dados, _ = tabela_de_linhas(tabela)
            res = analisar_tabela(cabecalho, dados, formato="docx", dica=dica, ia=ia)
            if res.eventos or res.pontos:
                return res
    texto = "\n".join(p for p in paragrafos if p.strip())
    if not texto:
        return ResultadoParse(formato="docx", avisos=["DOCX sem texto"])
    avisos: list[str] = []
    if ia_disponivel(ia) and (res := eventos_pela_ia(ia, texto, "text/plain", dica, "docx", avisos)):
        return res
    res = eventos_de_texto(texto, formato="docx")
    res.avisos = avisos + res.avisos
    return res


__all__ = ["analisar_docx", "analisar_imagem", "analisar_pdf", "eventos_pela_ia", "ia_disponivel"]
