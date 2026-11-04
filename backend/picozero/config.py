# backend/picozero/config.py
# Configuração lida do ambiente (.env local ou variáveis da Vercel). Nada aqui é segredo
# versionado: a chave do Gemini só existe no ambiente.
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
TZ = ZoneInfo("America/Sao_Paulo")

try:
    from dotenv import load_dotenv

    load_dotenv(RAIZ.parent / ".env")
except ImportError:  # pragma: no cover - dotenv é opcional
    pass


def _lista(nome: str, padrao: str) -> list[str]:
    return [p.strip() for p in os.getenv(nome, padrao).split(",") if p.strip()]


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, str(padrao)))
    except ValueError:
        return padrao


def _db_padrao() -> str:
    # Na Vercel só /tmp é gravável; localmente o banco fica ao lado do código.
    if os.getenv("VERCEL"):
        return "/tmp/picozero.db"
    return str(RAIZ.parent / "picozero.db")


@dataclass(frozen=True)
class Config:
    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    # Cadeia de modelos: tenta o primeiro; se não existir ou estiver sem cota, cai para o próximo.
    gemini_modelos: list[str] = field(
        default_factory=lambda: _lista(
            "GEMINI_MODEL",
            "gemini-3-flash-preview,gemini-3.6-flash,gemini-3.5-flash,gemini-3.8-flash,gemini-3.1-flash-lite,gemini-flash-lite-latest",
        )
    )
    gemini_timeout_ms: int = field(default_factory=lambda: _int("GEMINI_TIMEOUT_MS", 30000))
    # Teto diário de chamadas ao Gemini (protege a chave numa demo pública).
    ia_limite_diario: int = field(default_factory=lambda: _int("PICOZERO_IA_LIMITE_DIARIO", 400))
    ia_limite_por_minuto_ip: int = field(default_factory=lambda: _int("PICOZERO_IA_POR_MINUTO", 12))
    db_path: str = field(default_factory=lambda: os.getenv("PICOZERO_DB", _db_padrao()))
    cors_origens: list[str] = field(default_factory=lambda: _lista("PICOZERO_CORS", "*"))
    # Se definido, rotas de escrita (ingestão, reconhecer alerta) exigem este token.
    token_escrita: str | None = field(default_factory=lambda: os.getenv("PICOZERO_TOKEN") or None)
    # Webhook de saída (Slack, Google Chat, Teams): recebe alertas sério/crítico.
    alerta_webhook_url: str | None = field(default_factory=lambda: os.getenv("ALERTA_WEBHOOK_URL") or None)
    ingestao_max_mb: int = field(default_factory=lambda: _int("PICOZERO_INGESTAO_MAX_MB", 25))
    # Relógio de demonstração: 'AAAA-MM-DDTHH:MM' fixa o "agora" do motor (vazio = relógio real).
    agora_fixo: str | None = field(default_factory=lambda: os.getenv("PICOZERO_AGORA") or None)


CONFIG = Config()
