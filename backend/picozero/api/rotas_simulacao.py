# backend/picozero/api/rotas_simulacao.py
# Demonstração do alerta ANTES do pico: reproduz um dia como se as métricas chegassem ao vivo
# (com uma "surpresa" de carga acima do previsto), recalcula o nowcast a cada janela e transmite
# por SSE os pontos, a previsão corrigida e cada alerta no momento em que ele dispara.
import asyncio
import math
import random
from collections.abc import AsyncIterable
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from .. import servico
from ..dominio import ORDEM_NIVEL, PontoMetrica
from ..motor import alertas, carga
from .dependencias import UnidadeDep

router = APIRouter(prefix="/api/simulacao", tags=["simulação"])

Hora = Annotated[str, Query(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


def _passo(unidade: str, data: str, i: int, real: float) -> tuple[dict, list]:
    m = servico.motor()
    a = servico.armazem()
    ano, mes, dia = map(int, data.split("-"))
    ts = datetime(ano, mes, dia, i // 4, (i % 4) * 15)
    a.gravar_pontos(unidade, [PontoMetrica(ts=ts, valor=real)], origem="simulado", fonte="simulacao")
    c = m.curva(unidade, data, agora=ts)
    lista = alertas.avaliar(m, unidade, ts, horizonte=0)
    restante = c.pontos[i + 1 :] or c.pontos[-1:]
    topo = max(restante, key=lambda p: p.carga)
    return {
        "hora": carga.hora_da_janela(i),
        "real": round(real),
        "ajuste": c.ajuste_ao_vivo,
        "previsao_corrigida": [p.carga for p in c.pontos],
        "proximo_pico": {"hora": topo.hora, "carga": topo.carga},
        "nivel": c.nivel,
    }, lista


@router.get("/ao-vivo", response_class=EventSourceResponse)
async def ao_vivo(
    unidade: UnidadeDep,
    data: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = "2026-11-12",
    inicio: Hora = "16:00",
    fim: Hora = "22:00",
    passo_ms: Annotated[int, Query(ge=100, le=10_000)] = 1200,
    surpresa: Annotated[float, Query(ge=0.5, le=3.0, description="Carga real ÷ prevista a partir de surpresa_desde")] = 1.35,
    surpresa_desde: Hora = "17:30",
    semente: int = 7,
) -> AsyncIterable[ServerSentEvent]:
    """Eventos SSE: `inicio` (previsão original), `ponto` (a cada janela de 15 min), `alerta` (quando dispara), `fim`."""
    try:
        date.fromisoformat(data)
    except ValueError:
        raise HTTPException(422, "data inválida") from None
    m = servico.motor()
    a = servico.armazem()
    uid = unidade.id
    i0, i1 = carga.janela_da_hora(inicio), carga.janela_da_hora(fim)
    i_s = carga.janela_da_hora(surpresa_desde)
    rnd = random.Random(semente)
    await asyncio.to_thread(a.apagar_pontos, uid, data, data + "~", "simulado")
    original = await asyncio.to_thread(m.curva, uid, data)
    vistos: dict[str, str] = {}
    primeiro_alerta = None
    primeiro_ao_vivo = None
    pico_real = (0.0, "")
    try:
        yield ServerSentEvent(
            event="inicio",
            data={
                "data": data, "unidade": uid, "capacidade": original.capacidade, "pico_previsto": original.pico.model_dump(),
                "previsao_original": [p.carga for p in original.pontos], "eventos": [e.descricao for e in original.eventos],
                "surpresa": surpresa, "surpresa_desde": surpresa_desde,
            },
        )
        for i in range(i0, i1 + 1):
            rampa = min(1.0, (i - i_s + 1) / 3) if i >= i_s else 0.0  # surpresa entra em ~45 min
            fator = 1 + (surpresa - 1) * rampa
            real = original.pontos[i].carga * fator * math.exp(rnd.gauss(0, 0.04))
            if real > pico_real[0]:
                pico_real = (real, carga.hora_da_janela(i))
            ponto, lista = await asyncio.to_thread(_passo, uid, data, i, real)
            yield ServerSentEvent(event="ponto", data=ponto)
            for al in lista:
                assinatura = f"{al.nivel}|{al.estagio}"
                if vistos.get(al.id) == assinatura:
                    continue
                vistos[al.id] = assinatura
                if primeiro_alerta is None and ORDEM_NIVEL[al.nivel] >= ORDEM_NIVEL["serio"]:
                    primeiro_alerta = ponto["hora"]
                if primeiro_ao_vivo is None and al.origem == "ao_vivo":
                    primeiro_ao_vivo = {"hora": ponto["hora"], "pico_previsto": al.pico, "hora_pico": al.hora_pico}
                yield ServerSentEvent(event="alerta", data=al.model_dump(mode="json"))
            await asyncio.sleep(passo_ms / 1000)
        antecedencia = antecedencia_ao_vivo = None
        if primeiro_alerta and pico_real[1]:
            antecedencia = carga.minutos(pico_real[1]) - carga.minutos(primeiro_alerta)
        if primeiro_ao_vivo and pico_real[1]:
            antecedencia_ao_vivo = carga.minutos(pico_real[1]) - carga.minutos(primeiro_ao_vivo["hora"])
        yield ServerSentEvent(
            event="fim",
            data={
                "pico_real": {"hora": pico_real[1], "carga": round(pico_real[0])},
                "pico_previsto_original": original.pico.model_dump(),
                "primeiro_alerta_serio": primeiro_alerta,
                "antecedencia_min": antecedencia,
                "primeiro_alerta_ao_vivo": primeiro_ao_vivo,
                "antecedencia_ao_vivo_min": antecedencia_ao_vivo,
            },
        )
    finally:
        await asyncio.to_thread(a.apagar_pontos, uid, data, data + "~", "simulado")
