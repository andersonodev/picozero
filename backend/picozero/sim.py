# backend/picozero/sim.py
# Portal simulado para o teste de carga real (ferramentas/prova_carga.py): a latência cresce com o
# cubo da ocupação e, acima de 1,5× a capacidade, a rota devolve 503. Com FILA_VIRTUAL=1 (ou ?fila=1)
# um semáforo segura a concorrência na capacidade: quem espera vê a fila andar, não erro.
import asyncio
import os
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import contexto

router = APIRouter(prefix="/sim", tags=["simulador"])

BASE_MS = 120


class EstadoSim(BaseModel):
    capacidade: int
    ativos: int
    na_fila: int
    servidos: int
    recusados_503: int
    fila_virtual_env: bool


class Atendimento(BaseModel):
    rota: str
    ativos: int
    servico_ms: int
    espera_ms: int
    fila: bool


class _Estado:
    def __init__(self) -> None:
        self.zerar()

    def zerar(self) -> None:
        self.ativos = 0
        self.na_fila = 0
        self.servidos = 0
        self.recusados = 0
        self.semaforos: dict[tuple[int, int], asyncio.Semaphore] = {}


_estado = _Estado()

CapQuery = Annotated[int | None, Query(ge=1, le=100_000, description="Capacidade simulada (padrão: a da unidade)")]
FilaQuery = Annotated[bool, Query(description="Liga a fila virtual nesta requisição")]


def _capacidade(cap: int | None) -> int:
    return cap or contexto.unidade_padrao().capacidade


def _fila_ligada(fila: bool) -> bool:
    return fila or os.getenv("FILA_VIRTUAL") == "1"


def _semaforo(cap: int) -> asyncio.Semaphore:
    # Um semáforo por capacidade e por event loop (testes rodam loops diferentes).
    chave = (cap, id(asyncio.get_running_loop()))
    if chave not in _estado.semaforos:
        _estado.semaforos[chave] = asyncio.Semaphore(cap)
    return _estado.semaforos[chave]


async def _servir(rota: str, cap: int, espera_ms: int, fila: bool) -> Atendimento:
    _estado.ativos += 1
    try:
        ativos = _estado.ativos
        if ativos > 1.5 * cap:
            _estado.recusados += 1
            raise HTTPException(503, "Portal sobrecarregado (simulado). Tente de novo.", headers={"Retry-After": "2"})
        servico_ms = BASE_MS * (1 + (ativos / cap) ** 3)
        await asyncio.sleep(servico_ms / 1000)
        _estado.servidos += 1
        return Atendimento(rota=rota, ativos=ativos, servico_ms=round(servico_ms), espera_ms=espera_ms, fila=fila)
    finally:
        _estado.ativos -= 1


async def _atender(rota: str, cap: int | None, fila: bool) -> Atendimento:
    cap = _capacidade(cap)
    if not _fila_ligada(fila):
        return await _servir(rota, cap, 0, False)
    t0 = time.perf_counter()
    _estado.na_fila += 1
    entrou = False
    try:
        async with _semaforo(cap):
            _estado.na_fila -= 1
            entrou = True
            return await _servir(rota, cap, round((time.perf_counter() - t0) * 1000), True)
    finally:
        if not entrou:
            _estado.na_fila -= 1


@router.get("/login")
async def login(cap: CapQuery = None, fila: FilaQuery = False) -> Atendimento:
    return await _atender("login", cap, fila)


@router.get("/prova")
async def prova(cap: CapQuery = None, fila: FilaQuery = False) -> Atendimento:
    return await _atender("prova", cap, fila)


@router.get("/estado")
async def estado(cap: CapQuery = None) -> EstadoSim:
    return EstadoSim(
        capacidade=_capacidade(cap),
        ativos=_estado.ativos,
        na_fila=_estado.na_fila,
        servidos=_estado.servidos,
        recusados_503=_estado.recusados,
        fila_virtual_env=os.getenv("FILA_VIRTUAL") == "1",
    )


@router.post("/zerar")
async def zerar() -> EstadoSim:
    _estado.zerar()
    return await estado()
