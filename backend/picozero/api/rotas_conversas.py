# backend/picozero/api/rotas_conversas.py
# Conversas do assistente salvas no servidor. O painel não tem login: todas ficam num usuário global, e o histórico
# salvo volta como contexto quando a conversa continua (o painel manda as últimas mensagens a cada pergunta).
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from .. import servico

router = APIRouter(prefix="/api/conversas", tags=["conversas"])

IdConversa = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{8,64}$")]


class MensagemSalva(BaseModel):
    # O painel guarda o que mostra (origem, modelo, ferramentas, conferida...); só papel e texto são obrigatórios.
    model_config = ConfigDict(extra="allow")
    papel: Literal["usuario", "assistente"]
    texto: str = Field(max_length=20000)


class ConversaEntrada(BaseModel):
    titulo: str | None = Field(default=None, max_length=120)
    unidade: str = Field(default="rj", max_length=8)
    mensagens: list[MensagemSalva] = Field(max_length=400)


@router.get("")
def listar(limite: Annotated[int, Query(ge=1, le=200)] = 50) -> list[dict[str, Any]]:
    """Conversas salvas, da mais recente para a mais antiga (sem as mensagens)."""
    return servico.armazem().conversas(limite)


@router.get("/{id_conversa}")
def abrir(id_conversa: IdConversa) -> dict[str, Any]:
    c = servico.armazem().conversa(id_conversa)
    if c is None:
        raise HTTPException(404, "Conversa não encontrada.")
    return c


@router.put("/{id_conversa}")
def salvar(id_conversa: IdConversa, corpo: ConversaEntrada) -> dict[str, Any]:
    """Cria ou substitui a conversa inteira. Sem título, usa a primeira pergunta."""
    mensagens = [m.model_dump() for m in corpo.mensagens]
    primeira = next((m["texto"] for m in mensagens if m["papel"] == "usuario"), "") or "Conversa"
    titulo = " ".join((corpo.titulo or primeira).split())[:80]
    servico.armazem().salvar_conversa(id_conversa, titulo, corpo.unidade, mensagens)
    return {"id": id_conversa, "titulo": titulo, "mensagens": len(mensagens)}


@router.delete("/{id_conversa}")
def apagar(id_conversa: IdConversa) -> dict[str, bool]:
    return {"apagada": servico.armazem().apagar_conversa(id_conversa)}
