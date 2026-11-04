# backend/picozero/api/__init__.py
# App FastAPI: API REST em /api, simulador de portal em /sim, servidor MCP em /mcp e docs em /docs.
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from .. import servico
from ..config import CONFIG
from ..mcp_servidor import mcp
from . import rotas_alertas, rotas_ia, rotas_ingestao, rotas_openai, rotas_painel, rotas_plano, rotas_simulacao
from ..sim import router as rotas_sim

# MCP sem estado e com respostas JSON: funciona atrás de load balancer e em serverless.
mcp.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
_gerente = mcp.session_manager


class _MCPSobDemanda:
    """Garante o gerenciador de sessões do MCP rodando mesmo quando o host não dispara o lifespan."""

    def __init__(self) -> None:
        self._trava = asyncio.Lock()

    async def _garantir(self) -> None:
        if _gerente._task_group is not None or _gerente._has_started:
            return
        async with self._trava:
            if _gerente._task_group is not None or _gerente._has_started:
                return
            pronto = asyncio.Event()

            async def manter() -> None:
                async with _gerente.run():
                    pronto.set()
                    await asyncio.Event().wait()

            asyncio.get_running_loop().create_task(manter())
            await pronto.wait()

    async def __call__(self, scope, receive, send) -> None:
        await self._garantir()
        await _gerente.handle_request(scope, receive, send)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(servico.iniciar)
    async with _gerente.run():
        yield


app = FastAPI(
    title="PicoZero API",
    version="0.1.0",
    summary="Previsão de picos de acesso do portal acadêmico, alertas antecipados e dicas de manutenção.",
    description=(
        "Motor de capacidade do Innovation Day (Ibmec · Yduqs · Google). Entradas: arquivos em qualquer formato, "
        "webhooks, métricas ao vivo, texto livre, tráfego público e MCP. IA: Gemini com fallback por regras. "
        "Números de carga sempre do código; o Gemini lê, classifica e explica."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CONFIG.cors_origens,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"],
)
for r in (rotas_painel, rotas_alertas, rotas_ia, rotas_plano, rotas_simulacao, rotas_openai):
    app.include_router(r.router)
app.include_router(rotas_ingestao.router)
app.include_router(rotas_ingestao.escrita)
app.include_router(rotas_sim)
app.router.routes.append(Route("/mcp", endpoint=_MCPSobDemanda()))


@app.exception_handler(Exception)
async def _erro_interno(_request: Request, erro: Exception) -> JSONResponse:
    # Erro inesperado sai em JSON, não em texto puro: assim o painel sabe que o backend está de pé
    # (e mostra "tente de novo") em vez de achar que ele está desligado e cair na prévia local.
    return JSONResponse(status_code=500, content={"detail": f"Erro interno no backend ({type(erro).__name__})."})


@app.get("/", include_in_schema=False)
def raiz() -> RedirectResponse:
    return RedirectResponse("/docs")
