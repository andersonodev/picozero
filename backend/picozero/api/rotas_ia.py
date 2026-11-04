# backend/picozero/api/rotas_ia.py
# Rotas que usam o Gemini (com fallback por regras): dias de risco, dicas de manutenção, copiloto e trilha.
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query

from .. import servico
from ..dominio import DiaRisco, DicasManutencao, PedidoChat, RegistroTrilha, RespostaChat
from ..ia import chat, tarefas
from .dependencias import AgoraDep, LimiteIADep, UnidadeDep

router = APIRouter(prefix="/api", tags=["ia"])

DataPath = Annotated[str, Path(pattern=r"^\d{4}-\d{2}-\d{2}$", description="AAAA-MM-DD")]


@router.get("/riscos")
def riscos(unidade: UnidadeDep) -> list[DiaRisco]:
    """Último resultado (Gemini ou regras). Nunca chama o Gemini: use POST /api/riscos/analisar."""
    return tarefas.riscos(unidade.id)


@router.post("/riscos/analisar", dependencies=[LimiteIADep])
def analisar_riscos(unidade: UnidadeDep) -> list[DiaRisco]:
    """Gemini consulta o histórico por function calling e escreve gravidade e motivo de cada dia."""
    return tarefas.analisar_riscos(unidade.id, usar_ia=True)


@router.get("/manutencao/{data}")
def dicas(data: DataPath, unidade: UnidadeDep, agora: AgoraDep) -> DicasManutencao:
    """Dicas do dia para a equipe (última versão do Gemini se houver; senão regras)."""
    return tarefas.dicas(unidade.id, data, agora=agora)


@router.post("/manutencao/{data}/gerar", dependencies=[LimiteIADep])
def gerar_dicas(data: DataPath, unidade: UnidadeDep, agora: AgoraDep) -> DicasManutencao:
    """Gemini reescreve o plano de manutenção do dia; janelas e horários continuam os do motor."""
    return tarefas.dicas(unidade.id, data, usar_ia=True, agora=agora)


@router.post("/chat", dependencies=[LimiteIADep])
def conversar(pedido: PedidoChat) -> RespostaChat:
    """Copiloto de operação: pergunte em português; as respostas vêm das ferramentas do motor."""
    return chat.responder(pedido)


@router.get("/trilha")
def trilha(limite: Annotated[int, Query(ge=1, le=500)] = 120) -> list[RegistroTrilha]:
    """Registro do modelo: cada chamada ao Gemini, cada ferramenta usada e cada fallback."""
    return servico.armazem().trilha(limite)


@router.get("/ia")
def estado_ia() -> dict[str, Any]:
    return servico.ia().estado()
