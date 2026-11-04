# backend/picozero/mcp_servidor.py
# Servidor MCP do PicoZero: qualquer agente (Gemini CLI, Cursor, um bot do APM) consulta a
# previsão e EMPURRA dados pelo protocolo — métricas ao vivo, eventos, texto, arquivos e tráfego público.
# Mesmo motor da API HTTP. Transportes: HTTP em /mcp (montado na API) e stdio (python -m picozero.mcp_servidor).
import base64
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import contexto, ingestor, servico
from .dominio import Evento, PedidoChat
from .ia import chat, tarefas
from .motor import alertas as alertas_mod
from .motor import validacao

mcp = MCPServer(
    name="PicoZero",
    title="PicoZero · capacidade do portal acadêmico",
    instructions=(
        "Motor de previsão de picos de acesso do portal do aluno. Datas em AAAA-MM-DD, horas HH:MM (America/Sao_Paulo). "
        "Use previsao_dia/proximos_picos/alertas para consultar; ingerir_* para enviar dados (métricas ao vivo, "
        "eventos do calendário, texto de e-mail/aviso, arquivos CSV/XLSX/JSON/ICS/PDF/imagem em base64, "
        "tráfego mensal público). Números de carga vêm do motor; nunca invente."
    ),
    version="0.1.0",
)


def _u(unidade: str) -> str:
    return contexto.unidade(unidade).id


@mcp.tool()
def previsao_dia(data: str, unidade: str = "rj", agora: str | None = None) -> dict[str, Any]:
    """Curva prevista do dia (96 janelas de 15 min), pico, janelas acima de 60% da capacidade, nível e eventos."""
    c = servico.motor().curva(_u(unidade), data, agora=contexto.ler_agora(agora) if agora else None)
    return c.model_dump(mode="json")


@mcp.tool()
def proximos_picos(dias: int = 7, unidade: str = "rj", agora: str | None = None) -> list[dict[str, Any]]:
    """Dias com risco (≥ 60% da capacidade) a partir de agora, com pico, horário e nível."""
    return tarefas.proximos_dias_criticos(_u(unidade), contexto.ler_agora(agora), max(1, min(dias, 90)))


@mcp.tool()
def alertas(unidade: str = "rj", agora: str | None = None) -> list[dict[str, Any]]:
    """Alertas antecipados ativos (planejamento, preparação, véspera, iminente, em curso, ao vivo) com ações."""
    m = servico.motor()
    lista = alertas_mod.avaliar(m, _u(unidade), contexto.ler_agora(agora))
    alertas_mod.sincronizar(servico.armazem(), lista)
    return [a.model_dump(mode="json") for a in lista]


@mcp.tool()
def dicas_manutencao(data: str, unidade: str = "rj", usar_ia: bool = False) -> dict[str, Any]:
    """Plano de manutenção do dia para a equipe: janela de manutenção, congelamento de deploys, escala e tarefas."""
    return tarefas.dicas(_u(unidade), data, usar_ia=usar_ia).model_dump(mode="json")


@mcp.tool()
def dias_de_risco(unidade: str = "rj") -> list[dict[str, Any]]:
    """Dias de risco do semestre com gravidade 1–5 e motivo (Gemini ou regras); pico calculado pelo código."""
    return [r.model_dump(mode="json") for r in tarefas.riscos(_u(unidade))]


@mcp.tool()
def consultar_historico(data: str, unidade: str = "rj") -> dict[str, Any]:
    """Pico real observado num dia passado e os eventos daquele dia."""
    return tarefas.consultar_historico(_u(unidade), data)


@mcp.tool()
def desempenho_modelo(unidade: str = "rj") -> dict[str, Any]:
    """Backtest fora da amostra: erro no pico, no horário e acerto de dias críticos."""
    return servico.motor().backtest(_u(unidade))


@mcp.tool()
def validacao_publica(unidade: str = "rj", dominio: str | None = None) -> dict[str, Any]:
    """Compara a sazonalidade prevista com visitas mensais públicas do domínio do portal (Domsilo)."""
    return validacao.validar(servico.motor(), servico.armazem(), _u(unidade), dominio)


@mcp.tool()
def ingerir_metricas(pontos: list[dict[str, Any]], unidade: str = "rj") -> dict[str, Any]:
    """Envia métricas ao vivo: lista de {"ts": ISO ou epoch, "valor": acessos simultâneos}. Agrega em 15 min."""
    entrada = [ingestor.PontoEntrada(**p) for p in pontos]
    return ingestor.metricas(entrada, _u(unidade), canal="mcp").model_dump(mode="json")


@mcp.tool()
def ingerir_eventos(eventos: list[Evento], unidade: str = "rj") -> dict[str, Any]:
    """Envia eventos do calendário (data, hora_inicio, hora_fim, tipo, descricao, turmas)."""
    return ingestor.eventos(eventos, _u(unidade), canal="mcp").model_dump(mode="json")


@mcp.tool()
def ingerir_texto(texto: str, unidade: str = "rj", dica: str | None = None) -> dict[str, Any]:
    """Texto livre (e-mail da secretaria, aviso, ata): o Gemini extrai os eventos (regras sem chave)."""
    return ingestor.texto(texto, _u(unidade), dica, canal="mcp").model_dump(mode="json")


@mcp.tool()
def ingerir_arquivo(nome: str, conteudo_base64: str, unidade: str = "rj", dica: str | None = None) -> dict[str, Any]:
    """Arquivo em base64 (CSV, TSV, XLSX, JSON, NDJSON, log de acesso, ICS, PDF, DOCX, imagem). Formato detectado."""
    dados = base64.b64decode(conteudo_base64)
    return ingestor.arquivo(dados, nome, None, _u(unidade), dica, canal="mcp").model_dump(mode="json")


@mcp.tool()
def ingerir_trafego_mensal(
    dominio: str, visitas_mensais: list[dict[str, Any]], duracao_media_s: float | None = None, fonte: str | None = None
) -> dict[str, Any]:
    """Série pública de visitas mensais [{"mes": "AAAA-MM", "visitas": n}] para validar a sazonalidade do motor."""
    serie = ingestor.SerieTrafego(
        dominio=dominio, fonte=fonte or "MCP", visitas_mensais=visitas_mensais, duracao_media_s=duracao_media_s
    )
    return ingestor.trafego(serie, canal="mcp")


@mcp.tool()
def perguntar(pergunta: str, unidade: str = "rj", agora: str | None = None) -> dict[str, Any]:
    """Pergunta em português ao copiloto de operação (ex.: 'o que a equipe faz amanhã?')."""
    pedido = PedidoChat(mensagens=[{"papel": "usuario", "texto": pergunta}], unidade=unidade, agora=agora)
    return chat.responder(pedido).model_dump(mode="json")


@mcp.resource("picozero://contexto")
def recurso_contexto() -> dict[str, Any]:
    """Instituição, unidades, semestre e feriados."""
    return {
        "instituicao": contexto.instituicao(),
        "unidades": [u.model_dump() for u in contexto.unidades()],
        "semestre": contexto.semestre(),
        "feriados": [f.model_dump() for f in contexto.feriados()],
    }


if __name__ == "__main__":
    mcp.run("stdio")
