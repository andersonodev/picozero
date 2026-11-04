# deploy/env_servidor.py — monta o picozero.env do servidor a partir do backend/.env, só com as variáveis
# que o backend lê e sem valores vazios. Escreve na saída padrão (o publicar.sh manda direto pelo SSH);
# nunca imprime nada além disso.
import sys
from pathlib import Path

PERMITIDAS = {
    "VERTEX_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_MODEL_CHAT",
    "GEMINI_THINKING",
    "GEMINI_THINKING_CHAT",
    "GEMINI_VOLTA_S",
    "GEMINI_TIMEOUT_MS",
    "PICOZERO_IA_LIMITE_DIARIO",
    "PICOZERO_IA_POR_MINUTO",
    "PICOZERO_CORS",
    "PICOZERO_TOKEN",
    "ALERTA_WEBHOOK_URL",
    "PICOZERO_INGESTAO_MAX_MB",
    "PICOZERO_AGORA",
}

origem = Path(__file__).resolve().parent.parent / "backend" / ".env"
linhas = ["# picozero.env — gerado pelo deploy/publicar.sh a partir do backend/.env. Não editar à mão."]
if origem.exists():
    for linha in origem.read_text(encoding="utf-8").splitlines():
        nome, sep, valor = linha.partition("=")
        nome, valor = nome.strip(), valor.strip().strip("\"'")
        if sep and nome in PERMITIDAS and valor:
            linhas.append(f"{nome}={valor}")
sys.stdout.write("\n".join(linhas) + "\n")
