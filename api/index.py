# api/index.py
# Função Python da Vercel: expõe o FastAPI do backend (backend/picozero) na mesma origem do front.
# Os rewrites do vercel.json mandam /api/*, /mcp, /sim/*, /docs e /openapi.json para cá.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from picozero.api import app  # noqa: E402,F401
