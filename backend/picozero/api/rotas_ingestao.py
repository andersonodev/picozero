# backend/picozero/api/rotas_ingestao.py
# Entrada de dados por HTTP. Todas as rotas aceitam o mesmo destino (unidade) e devolvem o relatório
# de ingestão. Com PICOZERO_TOKEN definido, exigem o header X-PicoZero-Token.
from typing import Annotated, Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from .. import contexto, ingestor, servico
from ..config import CONFIG
from ..dominio import Evento, RelatorioIngestao
from .dependencias import TokenEscritaDep, UnidadeDep

router = APIRouter(prefix="/api/ingestao", tags=["ingestão"])
escrita = APIRouter(prefix="/api/ingestao", tags=["ingestão"], dependencies=[TokenEscritaDep])

FORMATOS = [
    {"formato": "csv/tsv", "exemplos": "export do Kibana/Grafana/planilha; ; ou , ; vírgula decimal; dd/mm/aaaa ou ISO"},
    {"formato": "xlsx", "exemplos": "planilha da secretaria ou do monitoramento (aba com mais dados)"},
    {"formato": "json", "exemplos": "Elasticsearch (hits, date_histogram), Prometheus query_range, Datadog, Grafana, lista de objetos"},
    {"formato": "ndjson", "exemplos": "export do Elastic/APM/RUM (usuários/sessões distintos por janela)"},
    {"formato": "log", "exemplos": "access log nginx/apache (IPs distintos por janela, % de 5xx)"},
    {"formato": "prometheus", "exemplos": "texto do /metrics"},
    {"formato": "ics", "exemplos": "calendário acadêmico (Google Agenda, Outlook)"},
    {"formato": "pdf/docx/texto", "exemplos": "calendário oficial, e-mail da secretaria — eventos extraídos pelo Gemini (regras sem chave)"},
    {"formato": "imagem", "exemplos": "foto ou print de calendário — Gemini multimodal"},
    {"formato": "metricas", "exemplos": "POST /api/ingestao/metricas — webhook ao vivo [{ts, valor}]"},
    {"formato": "trafego", "exemplos": "POST /api/ingestao/trafego — visitas mensais públicas (Domsilo, Similarweb, GA4)"},
    {"formato": "mcp", "exemplos": "ferramentas ingerir_* no servidor MCP em /mcp"},
]


class PedidoTexto(BaseModel):
    texto: str = Field(min_length=3, max_length=200_000)
    unidade: str = "rj"
    dica: str | None = None


def _unidade(id_: str) -> str:
    try:
        return contexto.unidade(id_).id
    except KeyError:
        raise HTTPException(404, f"Unidade '{id_}' não existe") from None


@router.get("/formatos")
def formatos() -> list[dict[str, str]]:
    return FORMATOS


@router.get("/historico")
def historico(limite: Annotated[int, Query(ge=1, le=200)] = 30) -> list[RelatorioIngestao]:
    return servico.armazem().ingestoes(limite)


@escrita.post("/arquivo")
async def arquivo(
    arquivo: Annotated[UploadFile, File(description="Qualquer formato suportado (ver /api/ingestao/formatos)")],
    unidade: Annotated[str, Form()] = "rj",
    dica: Annotated[str | None, Form(description="Ex.: 'coluna Count é sessões', 'horário em UTC'")] = None,
) -> RelatorioIngestao:
    """Upload universal: o formato é detectado pelo conteúdo; colunas desconhecidas e documentos vão ao Gemini."""
    limite = CONFIG.ingestao_max_mb * 1024 * 1024
    dados = await arquivo.read(limite + 1)
    if len(dados) > limite:
        raise HTTPException(413, f"Arquivo maior que {CONFIG.ingestao_max_mb} MB")
    if not dados:
        raise HTTPException(422, "Arquivo vazio")
    import asyncio

    return await asyncio.to_thread(
        ingestor.arquivo, dados, arquivo.filename, arquivo.content_type, _unidade(unidade), dica
    )


@escrita.post("/json")
def json_qualquer(
    corpo: Annotated[Any, Body(description="Qualquer JSON: série, export do Elastic/Prometheus, lista de eventos…")],
    unidade: UnidadeDep,
    dica: str | None = None,
) -> RelatorioIngestao:
    """Webhook genérico: aceita o JSON como vier (Grafana, Elastic Watcher, Datadog, script próprio)."""
    return ingestor.json_qualquer(corpo, unidade.id, dica)


@escrita.post("/texto")
def texto(pedido: PedidoTexto) -> RelatorioIngestao:
    """Texto livre (e-mail, aviso, ata): vira eventos do calendário."""
    return ingestor.texto(pedido.texto, _unidade(pedido.unidade), pedido.dica)


@escrita.post("/metricas")
def metricas(pontos: Annotated[list[ingestor.PontoEntrada], Body(min_length=1, max_length=50_000)], unidade: UnidadeDep) -> RelatorioIngestao:
    """Métricas ao vivo [{ts, valor}] — acessos simultâneos; agrega por máximo em janelas de 15 min."""
    return ingestor.metricas(pontos, unidade.id)


@escrita.post("/eventos")
def eventos(lista: Annotated[list[Evento], Body(min_length=1, max_length=5_000)], unidade: UnidadeDep) -> RelatorioIngestao:
    """Eventos do calendário no formato do front (data, hora_inicio, hora_fim, tipo, descricao, turmas)."""
    return ingestor.eventos(lista, unidade.id)


@escrita.post("/trafego")
def trafego(serie: ingestor.SerieTrafego) -> dict[str, Any]:
    """Série pública de visitas mensais de um domínio; usada em GET /api/validacao/publica?dominio=…"""
    return ingestor.trafego(serie)
