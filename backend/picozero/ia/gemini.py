# backend/picozero/ia/gemini.py
# Cliente do Gemini com tudo o que uma demo pública precisa para não cair:
# cadeia de modelos (404/429 → próximo), retry com backoff do próprio SDK, timeout, teto diário,
# cache das respostas estruturadas e trilha de auditoria de cada chamada e de cada ferramenta.
# Sem GEMINI_API_KEY (ou sem cota) `gerar` devolve None e quem chamou usa as regras determinísticas.
import hashlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import TypeAdapter

from ..armazem import Armazem
from ..config import CONFIG
from ..dominio import RegistroTrilha

try:
    from google import genai
    from google.genai import errors, types
except ImportError:  # pragma: no cover - o SDK é dependência, mas o motor roda sem ele
    genai = None


@dataclass
class RespostaIA:
    texto: str
    objeto: Any = None
    modelo: str = ""
    tokens: int = 0
    tempo_ms: int = 0
    cache: bool = False
    chamadas: list[dict] = field(default_factory=list)


def _resumo(valor: Any, limite: int = 160) -> str:
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _serializar(conteudo: Any) -> str:
    if isinstance(conteudo, (str, bytes)):
        return conteudo if isinstance(conteudo, str) else hashlib.sha256(conteudo).hexdigest()
    if isinstance(conteudo, list):
        return "|".join(_serializar(c) for c in conteudo)
    inline = getattr(conteudo, "inline_data", None)
    if inline is not None and getattr(inline, "data", None):
        return hashlib.sha256(inline.data).hexdigest()
    return str(conteudo)


class ClienteGemini:
    def __init__(self, armazem: Armazem | None = None):
        self.armazem = armazem
        self._cliente = None
        self._modelo_ok: str | None = None
        self._trava = threading.Lock()
        self._uso: tuple[date, int] = (date.today(), 0)
        self.ultimo_erro: str | None = None

    # ---------- estado ----------

    @property
    def configurado(self) -> bool:
        return bool(CONFIG.gemini_api_key) and genai is not None

    @property
    def disponivel(self) -> bool:
        dia, n = self._uso
        if dia != date.today():
            return self.configurado
        return self.configurado and n < CONFIG.ia_limite_diario

    @property
    def modelo(self) -> str:
        return self._modelo_ok or (CONFIG.gemini_modelos[0] if CONFIG.gemini_modelos else "gemini")

    def estado(self) -> dict:
        dia, n = self._uso
        return {
            "modo": "gemini" if self.disponivel else "fallback",
            "configurado": self.configurado,
            "modelo": self.modelo,
            "cadeia": CONFIG.gemini_modelos,
            "chamadas_hoje": n if dia == date.today() else 0,
            "limite_diario": CONFIG.ia_limite_diario,
            "ultimo_erro": self.ultimo_erro,
        }

    def _client(self):
        if self._cliente is None:
            self._cliente = genai.Client(
                api_key=CONFIG.gemini_api_key,
                http_options=types.HttpOptions(
                    timeout=CONFIG.gemini_timeout_ms,
                    retry_options=types.HttpRetryOptions(
                        # Um retry curto e segue para o próximo modelo: em dia de demanda alta o 503 é por modelo.
                        attempts=2, initial_delay=1.0, max_delay=4.0, http_status_codes=[408, 429, 500, 502, 503, 504]
                    ),
                ),
            )
        return self._cliente

    def _contar(self) -> None:
        with self._trava:
            dia, n = self._uso
            self._uso = (date.today(), 1) if dia != date.today() else (dia, n + 1)

    # ---------- trilha ----------

    def registrar(
        self,
        etapa: str,
        detalhe: str,
        *,
        tokens: int | None = None,
        tempo_ms: int | None = None,
        ferramenta: bool = False,
        modelo: str | None = None,
        ok: bool = True,
    ) -> RegistroTrilha:
        agora = datetime.now()
        reg = RegistroTrilha(
            hora=agora.strftime("%H:%M:%S"),
            quando=agora.isoformat(timespec="seconds"),
            etapa=etapa,
            detalhe=detalhe,
            tokens=tokens,
            tempo=f"{tempo_ms / 1000:.1f} s".replace(".", ",") if tempo_ms is not None else None,
            ferramenta=ferramenta,
            modelo=modelo,
            ok=ok,
        )
        if self.armazem is not None:
            self.armazem.registrar_trilha(reg)
        return reg

    # ---------- chamada ----------

    def gerar(
        self,
        etapa: str,
        conteudo: Any,
        *,
        schema: Any = None,
        sistema: str | None = None,
        temperatura: float = 0.2,
        ferramentas: list[Callable] | None = None,
        detalhe: str = "",
        usar_cache: bool = True,
        max_chamadas: int = 10,
    ) -> RespostaIA | None:
        """Chama o Gemini. Devolve None quando não há chave, cota ou resposta válida (use o fallback)."""
        if not self.disponivel:
            return None
        nome_schema = getattr(schema, "__name__", None) or str(schema)
        chave = None
        if usar_cache and schema is not None and not ferramentas and self.armazem is not None:
            bruto = f"{etapa}|{sistema}|{nome_schema}|{temperatura}|{_serializar(conteudo)}"
            chave = "ia:" + hashlib.sha256(bruto.encode()).hexdigest()
            guardado = self.armazem.kv_get(chave)
            if guardado is not None:
                try:
                    objeto = TypeAdapter(schema).validate_python(guardado["objeto"])
                    self.registrar(etapa, f"{detalhe} · cache", tokens=0, tempo_ms=0, modelo=guardado.get("modelo"))
                    return RespostaIA(texto=guardado.get("texto", ""), objeto=objeto, modelo=guardado.get("modelo", ""), cache=True)
                except Exception:
                    pass

        config = types.GenerateContentConfig(
            system_instruction=sistema,
            temperature=temperatura,
            response_mime_type="application/json" if schema is not None else None,
            response_schema=schema,
            tools=ferramentas or None,
            automatic_function_calling=(
                types.AutomaticFunctionCallingConfig(maximum_remote_calls=max_chamadas) if ferramentas else None
            ),
        )
        modelos = list(dict.fromkeys([m for m in [self._modelo_ok, *CONFIG.gemini_modelos] if m]))
        for modelo in modelos:
            t0 = time.perf_counter()
            try:
                self._contar()
                resp = self._client().models.generate_content(model=modelo, contents=conteudo, config=config)
            except Exception as e:  # noqa: BLE001 - qualquer falha vira fallback, registrada na trilha
                ms = int((time.perf_counter() - t0) * 1000)
                codigo = getattr(e, "code", None)
                self.ultimo_erro = f"{modelo}: {codigo or type(e).__name__} {str(e)[:160]}"
                self.registrar(etapa, f"falhou em {modelo} ({codigo or type(e).__name__})", tempo_ms=ms, modelo=modelo, ok=False)
                if codigo in (401, 403):
                    return None  # chave inválida: nenhum modelo vai funcionar
                if codigo == 400 and "API key" in str(e):
                    return None
                continue  # 404 (modelo inexistente), 429 (cota), 5xx, timeout → próximo modelo
            ms = int((time.perf_counter() - t0) * 1000)
            texto = resp.text or ""
            objeto = None
            if schema is not None:
                objeto = resp.parsed
                if objeto is None:
                    try:
                        objeto = TypeAdapter(schema).validate_python(json.loads(texto))
                    except Exception as e:  # noqa: BLE001
                        self.ultimo_erro = f"{modelo}: JSON inválido ({str(e)[:120]})"
                        self.registrar(etapa, f"resposta fora do schema em {modelo}", tempo_ms=ms, modelo=modelo, ok=False)
                        continue
            uso = resp.usage_metadata
            tokens = (uso.total_token_count or 0) if uso else 0
            chamadas = self._registrar_ferramentas(resp)
            self._modelo_ok = modelo
            self.ultimo_erro = None
            self.registrar(etapa, detalhe or nome_schema, tokens=tokens, tempo_ms=ms, modelo=modelo)
            if chave:
                bruto = TypeAdapter(schema).dump_python(objeto, mode="json")
                self.armazem.kv_set(chave, {"objeto": bruto, "texto": texto, "modelo": modelo})
            return RespostaIA(texto=texto, objeto=objeto, modelo=modelo, tokens=tokens, tempo_ms=ms, chamadas=chamadas)
        return None

    def _registrar_ferramentas(self, resp) -> list[dict]:
        """Cada chamada de ferramenta que o Gemini decidiu fazer vira uma linha da trilha."""
        chamadas: list[dict] = []
        historico = getattr(resp, "automatic_function_calling_history", None) or []
        pendentes: dict[str, dict] = {}
        for conteudo in historico:
            for parte in conteudo.parts or []:
                fc = getattr(parte, "function_call", None)
                if fc is not None and fc.name:
                    item = {"nome": fc.name, "args": dict(fc.args or {}), "resultado": None}
                    chamadas.append(item)
                    pendentes[fc.name] = item
                fr = getattr(parte, "function_response", None)
                if fr is not None and fr.name in pendentes:
                    pendentes[fr.name]["resultado"] = fr.response
        for c in chamadas:
            args = ", ".join(f"{k}={v}" for k, v in c["args"].items())
            res = c["resultado"] or {}
            resumo = res.get("resumo") if isinstance(res, dict) else None
            self.registrar(c["nome"], f"{args} → {_resumo(resumo or res)}", ferramenta=True, modelo=self.modelo)
        return chamadas


def parte_arquivo(dados: bytes, mime: str):
    """Arquivo (PDF, imagem) inline na chamada — até ~20 MB, sem precisar da Files API."""
    return types.Part.from_bytes(data=dados, mime_type=mime)
