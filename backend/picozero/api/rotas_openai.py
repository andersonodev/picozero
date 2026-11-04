# backend/picozero/api/rotas_openai.py
# API compatível com a da OpenAI sobre o mesmo copiloto do painel (picozero.ia.chat.responder).
# Serve para ligar clientes de chat prontos (LibreChat em /chat) ao assistente do PicoZero: mesmas regras,
# mesmas ferramentas do motor e mesma conferência de números. Só a rede interna alcança /v1 (o nginx não a expõe).
import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from ..dominio import MensagemChat, PedidoChat
from ..ia import chat
from .dependencias import LimiteIADep

router = APIRouter(prefix="/v1", tags=["openai"])

MODELO = "picozero-assistente"
MAX_MENSAGENS = 30
MAX_TEXTO = 4000


class MensagemOpenAI(BaseModel):
    model_config = ConfigDict(extra="allow")  # clientes mandam name, tool_calls etc.: ignoramos
    role: str
    content: str | list[Any] | None = None


class PedidoOpenAI(BaseModel):
    model_config = ConfigDict(extra="allow")  # temperature, max_tokens, user...: o copiloto não usa
    model: str | None = None
    messages: list[MensagemOpenAI]
    stream: bool = False


def _texto(conteudo: str | list[Any] | None) -> str:
    """O conteúdo vem como texto ou como lista de partes {type: 'text', text: ...}; só o texto interessa."""
    if isinstance(conteudo, str):
        return conteudo.strip()
    if isinstance(conteudo, list):
        partes = []
        for p in conteudo:
            if isinstance(p, str):
                partes.append(p)
            elif isinstance(p, dict) and p.get("type") in (None, "text") and isinstance(p.get("text"), str):
                partes.append(p["text"])
        return "\n".join(partes).strip()
    return ""


def _mensagens(msgs: list[MensagemOpenAI]) -> list[MensagemChat]:
    papeis = {"user": "usuario", "assistant": "assistente"}
    saida = [
        MensagemChat(papel=papeis[m.role], texto=t[:MAX_TEXTO])
        for m in msgs
        if m.role in papeis and (t := _texto(m.content))
    ]
    return saida[-MAX_MENSAGENS:]


def _erro(status: int, mensagem: str, tipo: str = "invalid_request_error") -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": mensagem, "type": tipo}})


def _blob(id_: str, criado: int, delta: dict[str, Any], fim: str | None) -> str:
    chunk = {
        "id": id_, "object": "chat.completion.chunk", "created": criado, "model": MODELO,
        "choices": [{"index": 0, "delta": delta, "finish_reason": fim}],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


@router.get("/models")
def modelos() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": MODELO, "object": "model", "created": 0, "owned_by": "picozero"}]}


@router.post("/chat/completions", dependencies=[LimiteIADep], response_model=None)
async def completar(pedido: PedidoOpenAI) -> Any:
    """Mesmo copiloto do painel (Gemini com ferramentas do motor; sem IA, regras), no formato da OpenAI."""
    mensagens = _mensagens(pedido.messages)
    if not mensagens:
        return _erro(400, "Envie ao menos uma mensagem de usuário com texto.")
    pedido_chat = PedidoChat(mensagens=mensagens, unidade="rj")
    id_, criado = f"chatcmpl-{uuid.uuid4().hex[:24]}", int(time.time())

    if pedido.stream:
        async def fluxo():
            # O primeiro pedaço sai já: a conexão não fica muda enquanto o copiloto consulta o motor.
            yield _blob(id_, criado, {"role": "assistant", "content": ""}, None)
            try:
                texto = (await asyncio.to_thread(chat.responder, pedido_chat)).resposta
            except Exception as e:  # noqa: BLE001 - depois dos cabeçalhos só dá para avisar dentro do texto
                texto = f"Não consegui responder agora ({type(e).__name__}). Tente de novo em instantes."
            yield _blob(id_, criado, {"content": texto}, None)
            yield _blob(id_, criado, {}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(fluxo(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    texto = (await asyncio.to_thread(chat.responder, pedido_chat)).resposta
    return {
        "id": id_, "object": "chat.completion", "created": criado, "model": MODELO,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": texto}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
