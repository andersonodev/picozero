# backend/picozero/api/dependencias.py
# Dependências compartilhadas: unidade válida, relógio da demo, limite por IP nas rotas que
# gastam Gemini e token opcional nas rotas de escrita.
import threading
import time
from collections import deque
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request

from .. import contexto
from ..config import CONFIG
from ..dominio import Unidade


def _unidade(unidade: Annotated[str, Query(description="Unidade (rj, sp, bh, df)")] = "rj") -> Unidade:
    try:
        return contexto.unidade(unidade)
    except KeyError:
        ids = ", ".join(u.id for u in contexto.unidades())
        raise HTTPException(404, f"Unidade '{unidade}' não existe. Use uma de: {ids}") from None


def _agora(
    agora: Annotated[
        str | None,
        Query(description="Relógio da demo: 'AAAA-MM-DD' ou 'AAAA-MM-DDTHH:MM' (vazio = agora real)"),
    ] = None,
) -> datetime:
    try:
        return contexto.ler_agora(agora)
    except ValueError:
        raise HTTPException(422, f"agora inválido: {agora!r}") from None


UnidadeDep = Annotated[Unidade, Depends(_unidade)]
AgoraDep = Annotated[datetime, Depends(_agora)]

_janelas: dict[str, deque] = {}
_trava = threading.Lock()


def _limite_ia(request: Request) -> None:
    """Janela deslizante de 60 s por IP: protege a chave do Gemini numa URL pública."""
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0]
    agora = time.monotonic()
    with _trava:
        fila = _janelas.setdefault(ip, deque())
        while fila and agora - fila[0] > 60:
            fila.popleft()
        if len(fila) >= CONFIG.ia_limite_por_minuto_ip:
            raise HTTPException(429, "Muitas chamadas de IA por minuto. Tente de novo em instantes.")
        fila.append(agora)


def _token_escrita(
    x_picozero_token: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not CONFIG.token_escrita:
        return
    enviado = x_picozero_token or (authorization or "").removeprefix("Bearer ").strip()
    if enviado != CONFIG.token_escrita:
        raise HTTPException(401, "Token de escrita ausente ou inválido (X-PicoZero-Token).")


LimiteIADep = Depends(_limite_ia)
TokenEscritaDep = Depends(_token_escrita)
