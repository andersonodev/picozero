# backend/ferramentas/testar_modelos.py
# Testa, com a chave do backend/.env, quais modelos das cadeias GEMINI_MODEL e GEMINI_MODEL_CHAT respondem.
# Uso (na pasta backend):  uv run python ferramentas/testar_modelos.py
# Cada modelo gasta uma chamada curta. No fim, sugere as linhas do .env só com os que passaram.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google import genai  # noqa: E402

from picozero.config import CONFIG  # noqa: E402

if not CONFIG.gemini_api_key:
    sys.exit("Sem GEMINI_API_KEY no backend/.env.")

cliente = genai.Client(api_key=CONFIG.gemini_api_key)
candidatos = list(dict.fromkeys([*CONFIG.gemini_modelos_chat, *CONFIG.gemini_modelos]))
ok: list[str] = []
for modelo in candidatos:
    try:
        cliente.models.generate_content(model=modelo, contents="Responda só: ok")
        ok.append(modelo)
        print(f"OK    {modelo}")
    except Exception as e:  # noqa: BLE001
        codigo = getattr(e, "code", "") or type(e).__name__
        texto = str(e).replace("\n", " ")
        motivo = "cota diária esgotada" if "perday" in texto.lower().replace(" ", "") else texto[:90]
        print(f"ERRO  {modelo}  ({codigo}) {motivo}")

print()
if not ok:
    print("Nenhum modelo respondeu. Veja a cota em https://aistudio.google.com (Dashboard > Usage).")
else:
    chat = [m for m in CONFIG.gemini_modelos_chat if m in ok] or ok
    geral = [m for m in CONFIG.gemini_modelos if m in ok] or ok
    print("Sugestão para o backend/.env:")
    print("GEMINI_MODEL=" + ",".join(geral))
    print("GEMINI_MODEL_CHAT=" + ",".join(chat))
