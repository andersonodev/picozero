# backend/picozero/api/rotas_alertas.py
# Alertas antecipados: lista, stream em tempo real (SSE) e reconhecimento pela equipe.
import asyncio
import time
from collections.abc import AsyncIterable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from .. import contexto, servico
from ..dominio import Alerta
from ..motor import alertas
from .dependencias import AgoraDep, TokenEscritaDep, UnidadeDep

router = APIRouter(prefix="/api/alertas", tags=["alertas"])


def _avaliar(unidade: str, agora: datetime, horizonte: int = alertas.HORIZONTE_DIAS) -> list[Alerta]:
    lista = alertas.avaliar(servico.motor(), unidade, agora, horizonte)
    alertas.sincronizar(servico.armazem(), lista)
    return lista


@router.get("")
def listar(
    unidade: UnidadeDep, agora: AgoraDep, horizonte: Annotated[int, Query(ge=0, le=60)] = alertas.HORIZONTE_DIAS
) -> list[Alerta]:
    """Alertas do mais urgente ao mais distante. `agora` permite viajar no tempo na demo."""
    return _avaliar(unidade.id, agora, horizonte)


@router.get("/stream", response_class=EventSourceResponse)
async def stream(unidade: UnidadeDep) -> AsyncIterable[ServerSentEvent]:
    """SSE: `snapshot` ao conectar; depois `alerta` (novo ou mudou), `ingestao` (dado novo) e ping a cada 15 s."""
    fila = alertas.BARRAMENTO.inscrever()
    try:
        lista = await asyncio.to_thread(_avaliar, unidade.id, contexto.agora())
        yield ServerSentEvent(data=[a.model_dump(mode="json") for a in lista], event="snapshot")
        ultimo = time.monotonic()
        while True:
            try:
                msg = await asyncio.wait_for(fila.get(), timeout=15)
                yield ServerSentEvent(data=msg["dados"], event=msg["tipo"])
            except TimeoutError:
                yield ServerSentEvent(comment="ping")
            if time.monotonic() - ultimo > 60:
                await asyncio.to_thread(_avaliar, unidade.id, contexto.agora())
                ultimo = time.monotonic()
    finally:
        alertas.BARRAMENTO.cancelar(fila)


@router.post("/{id_alerta}/reconhecer", dependencies=[TokenEscritaDep])
def reconhecer(id_alerta: str) -> Alerta:
    a = servico.armazem().reconhecer_alerta(id_alerta, contexto.agora().isoformat(timespec="minutes"))
    if a is None:
        raise HTTPException(404, "Alerta não encontrado")
    alertas.BARRAMENTO.publicar("alerta", a.model_dump(mode="json"))
    return a
