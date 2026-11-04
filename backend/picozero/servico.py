# backend/picozero/servico.py
# Raiz de composição: um armazém, um motor e um cliente Gemini por processo, criados sob demanda
# (o mesmo código serve a API HTTP, o MCP por HTTP e o MCP por stdio).
import threading

from . import semente
from .armazem import Armazem
from .config import CONFIG
from .ia.gemini import ClienteGemini
from .motor.previsao import Motor

_trava = threading.Lock()
_armazem: Armazem | None = None
_motor: Motor | None = None
_ia: ClienteGemini | None = None


def iniciar() -> None:
    global _armazem, _motor, _ia
    with _trava:
        if _armazem is not None:
            return
        a = Armazem(CONFIG.db_path)
        semente.popular(a)
        _motor = Motor(a)
        _ia = ClienteGemini(a)
        _armazem = a


def armazem() -> Armazem:
    iniciar()
    return _armazem


def motor() -> Motor:
    iniciar()
    return _motor


def ia() -> ClienteGemini:
    iniciar()
    return _ia
