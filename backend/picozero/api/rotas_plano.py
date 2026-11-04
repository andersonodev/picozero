# backend/picozero/api/rotas_plano.py
# Evitar (plano validado), reagir (comunicado de crise) e provar (latência antes × depois × controle).
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field, field_validator

from .. import contexto
from ..dominio import Comunicado, ResultadoPlano
from ..ia.crise import gerar_comunicado
from ..motor import plano as planos
from ..motor import prova_carga
from .dependencias import LimiteIADep, UnidadeDep

router = APIRouter(prefix="/api", tags=["evitar e reagir"])

DataPath = Annotated[str, Path(description="Dia no formato AAAA-MM-DD", examples=["2026-09-10"])]


def _data(texto: str, campo: str = "data") -> str:
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError:
        raise HTTPException(422, f"{campo} inválida: {texto!r}. Use AAAA-MM-DD (ex.: 2026-09-10).") from None


class PedidoCrise(BaseModel):
    data: str = Field(description="Dia da falha, AAAA-MM-DD", examples=["2026-09-10"])
    falha: str = Field(min_length=3, max_length=2000, description="O que falhou, nas palavras da operação")
    unidade: str = "rj"

    @field_validator("data")
    @classmethod
    def _data_valida(cls, v: str) -> str:
        try:
            return date.fromisoformat(v).isoformat()
        except ValueError:
            raise ValueError(f"data inválida: {v!r}. Use AAAA-MM-DD") from None


class PontoLatencia(BaseModel):
    hora: str
    antes: int
    depois: int
    controle: int
    erroAntes: float


class ResumoLatencia(BaseModel):
    chave: str
    nome: str
    sub: str
    p95: int
    p50: int
    erros: float


class ProvaCarga(BaseModel):
    data: str
    controle: str
    capacidade: int
    series: list[PontoLatencia]
    resumo: list[ResumoLatencia]


@router.get("/plano/{data}")
def ler_plano(data: DataPath, unidade: UnidadeDep) -> ResultadoPlano:
    """Plano do dia: o último gerado (inclusive pelo Gemini) ou o das regras. Não chama IA."""
    return planos.obter_plano(unidade.id, _data(data))


@router.post("/plano/{data}/gerar", dependencies=[LimiteIADep])
def gerar_plano(data: DataPath, unidade: UnidadeDep) -> ResultadoPlano:
    """Gera o plano com o Gemini (até 3 tentativas validadas pelo código; sem chave, regras)."""
    return planos.planejar(unidade.id, _data(data), usar_ia=True)


@router.post("/crise", dependencies=[LimiteIADep])
def crise(pedido: PedidoCrise) -> Comunicado:
    """Comunicado aos alunos depois de uma falha: prazo novo em dia útil e regras de tolerância."""
    try:
        uni = contexto.unidade(pedido.unidade)
    except KeyError:
        raise HTTPException(404, f"Unidade '{pedido.unidade}' não existe.") from None
    return gerar_comunicado(uni.id, pedido.data, pedido.falha)


@router.get("/prova-carga")
def prova(
    unidade: UnidadeDep,
    data: Annotated[str, Query(description="Dia de pico, AAAA-MM-DD")] = "2026-09-10",
    controle: Annotated[
        str | None, Query(description="Dia tranquilo de comparação (padrão: o mais próximo antes)")
    ] = None,
) -> ProvaCarga:
    """Latência p95 ao longo do dia: antes × depois (plano + fila) × controle."""
    dia = _data(data)
    ctrl = _data(controle, "controle") if controle else prova_carga.dia_controle(unidade.id, dia)
    serie = prova_carga.series_latencia(unidade.id, dia, ctrl)
    return ProvaCarga(
        data=dia,
        controle=ctrl,
        capacidade=unidade.capacidade,
        series=serie,
        resumo=prova_carga.resumo_latencia(unidade.id, dia, ctrl, serie),
    )
