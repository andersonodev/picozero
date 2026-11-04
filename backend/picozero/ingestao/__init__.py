# backend/picozero/ingestao/__init__.py
# Porta de entrada da ingestão: qualquer arquivo, JSON de webhook ou texto livre vira
# ResultadoParse (pontos de carga alinhados em 15 min e/ou eventos). Entrada ruim nunca
# levanta exceção: volta com o formato detectado e avisos curtos explicando o problema.
#
# Formatos: csv, tsv, xlsx, json (Prometheus, Elasticsearch, Datadog, Grafana, genérico),
# ndjson (Elastic/APM/RUM), log (nginx/apache), prometheus (/metrics), ics, pdf, imagem,
# docx e texto. 'xls', 'binario' e 'vazio' voltam só com aviso.
import json
import logging
from typing import Any, Protocol

from ..dominio import Evento, PontoMetrica, ResultadoParse
from . import normalizacao
from .deteccao import detectar_formato, extensao, ler_texto, mime_da_imagem
from .documentos import analisar_docx, analisar_imagem, analisar_pdf, eventos_pela_ia, ia_disponivel
from .estruturado import analisar_ndjson, analisar_objeto
from .ics import analisar_ics
from .logs import analisar_exposicao, analisar_log
from .tabular import analisar_csv, analisar_xlsx
from .texto import eventos_de_texto

log = logging.getLogger(__name__)

__all__ = [
    "AssistenteIA", "Evento", "PontoMetrica", "ResultadoParse", "analisar_arquivo", "analisar_json",
    "analisar_texto", "detectar_formato", "normalizacao",
]  # fmt: skip


class AssistenteIA(Protocol):
    disponivel: bool

    def mapear_colunas(self, cabecalho: list[str], amostra: list[list[str]], dica: str | None) -> dict[str, str] | None:
        """{"ts", "valor", "agregacao": "max"|"soma", "fuso", "metrica"} ou {"data", "hora_inicio", "descricao", "tipo"}."""
        ...

    def extrair_eventos(self, conteudo: bytes | str, mime: str, dica: str | None) -> list[Evento] | None: ...


def _texto_livre(texto: str, *, formato: str, dica: str | None, ia: Any) -> ResultadoParse:
    avisos: list[str] = []
    if ia_disponivel(ia) and (res := eventos_pela_ia(ia, texto, "text/plain", dica, formato, avisos)):
        res.linhas_lidas = len([linha for linha in texto.splitlines() if linha.strip()])
        return res
    res = eventos_de_texto(texto, formato=formato)
    res.avisos = avisos + res.avisos
    return res


def _textual(formato: str, texto: str, *, dica: str | None, ia: Any, tabular_obrigatorio: bool) -> ResultadoParse:
    if formato in ("csv", "tsv"):
        res = analisar_csv(texto, formato=formato, dica=dica, ia=ia)
        if res.pontos or res.eventos or tabular_obrigatorio:
            return res
        # parecia tabela mas não tem data/valor: tenta como texto livre (e-mail com vírgulas)
        alternativa = _texto_livre(texto, formato="texto", dica=dica, ia=ia)
        return alternativa if alternativa.eventos else res
    if formato == "json":
        try:
            obj = json.loads(texto)
        except json.JSONDecodeError as erro:
            res = analisar_ndjson(texto, dica=dica, ia=ia)
            if res.pontos or res.eventos:
                return res
            return ResultadoParse(formato="json", avisos=[f"JSON inválido (linha {erro.lineno}, coluna {erro.colno})"])
        return analisar_objeto(obj, formato="json", dica=dica, ia=ia)
    if formato == "ndjson":
        return analisar_ndjson(texto, dica=dica, ia=ia)
    if formato == "log":
        return analisar_log(texto)
    if formato == "prometheus":
        return analisar_exposicao(texto, dica=dica)
    if formato == "ics":
        return analisar_ics(texto)
    return _texto_livre(texto, formato="texto", dica=dica, ia=ia)


def _finalizar(res: ResultadoParse) -> ResultadoParse:
    for aviso in normalizacao.avisos_eventos(res.eventos):
        if aviso not in res.avisos:
            res.avisos.append(aviso)
    return res


def analisar_arquivo(
    conteudo: bytes,
    nome: str | None = None,
    content_type: str | None = None,
    *,
    dica: str | None = None,
    ia: AssistenteIA | None = None,
) -> ResultadoParse:
    """Bytes de qualquer arquivo → ResultadoParse. O formato vem do conteúdo, não da extensão."""
    formato = detectar_formato(conteudo, nome, content_type)
    try:
        if formato == "vazio":
            return ResultadoParse(formato="vazio", avisos=["arquivo vazio"])
        if formato == "xls":
            return ResultadoParse(
                formato="xls", avisos=["Excel 97-2003 (.xls) não é suportado: salve como .xlsx ou .csv"]
            )
        if formato == "binario":
            return ResultadoParse(
                formato="binario",
                avisos=[
                    (
                        "conteúdo binário não reconhecido (aceito csv, tsv, xlsx, json, ndjson, log, prometheus, "
                        "ics, pdf, imagem, docx e texto)"
                    )
                ],
            )
        if formato == "pdf":
            return _finalizar(analisar_pdf(conteudo, dica=dica, ia=ia))
        if formato == "imagem":
            return _finalizar(analisar_imagem(conteudo, mime_da_imagem(conteudo), dica=dica, ia=ia))
        if formato == "docx":
            return _finalizar(analisar_docx(conteudo, dica=dica, ia=ia))
        if formato == "xlsx":
            return _finalizar(analisar_xlsx(conteudo, dica=dica, ia=ia))
        texto, encoding = ler_texto(conteudo)
        res = _textual(formato, texto, dica=dica, ia=ia, tabular_obrigatorio=extensao(nome) in ("csv", "tsv"))
        res.mapeamento.setdefault("encoding", encoding)
        return _finalizar(res)
    except Exception as erro:  # nunca derruba a ingestão; o log guarda o detalhe
        log.exception("falha ao ler %s (%s)", nome or "arquivo", formato)
        return ResultadoParse(formato=formato, avisos=[f"não consegui ler como {formato} ({type(erro).__name__})"])


def analisar_json(obj: Any, *, dica: str | None = None, ia: AssistenteIA | None = None) -> ResultadoParse:
    """Corpo JSON de webhook, já decodificado (dict, lista ou escalar), em qualquer formato."""
    try:
        if isinstance(obj, bytes):
            return analisar_arquivo(obj, None, "application/json", dica=dica, ia=ia)
        if isinstance(obj, str):
            return analisar_texto(obj, dica=dica, ia=ia)
        return _finalizar(analisar_objeto(obj, formato="json", dica=dica, ia=ia))
    except Exception as erro:
        log.exception("falha ao ler JSON de webhook")
        return ResultadoParse(formato="json", avisos=[f"não consegui ler o JSON ({type(erro).__name__})"])


def analisar_texto(texto: str, *, dica: str | None = None, ia: AssistenteIA | None = None) -> ResultadoParse:
    """Texto livre (e-mail da secretaria, aviso no portal). JSON/CSV/ICS colados como texto também valem."""
    if not texto or not texto.strip():
        return ResultadoParse(formato="vazio", avisos=["texto vazio"])
    try:
        bruto = texto.encode("utf-8")
        formato = detectar_formato(bruto, None, "text/plain")
        texto_norm = texto.replace("\r\n", "\n").replace("\r", "\n")
        return _finalizar(_textual(formato, texto_norm, dica=dica, ia=ia, tabular_obrigatorio=False))
    except Exception as erro:
        log.exception("falha ao ler texto")
        return ResultadoParse(formato="texto", avisos=[f"não consegui ler o texto ({type(erro).__name__})"])
