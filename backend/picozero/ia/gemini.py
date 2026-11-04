# backend/picozero/ia/gemini.py
# Cliente do Gemini com tudo o que uma demo pública precisa para não cair:
# cadeia de modelos (404/429 → próximo), retry com backoff do próprio SDK, timeout, teto diário,
# cache das respostas estruturadas e trilha de auditoria de cada chamada e de cada ferramenta.
# Sem GEMINI_API_KEY (ou sem cota) `gerar` devolve None e quem chamou usa as regras determinísticas.
import concurrent.futures
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


_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini")


@dataclass
class RespostaIA:
    texto: str
    objeto: Any = None
    modelo: str = ""
    tokens: int = 0
    tempo_ms: int = 0
    cache: bool = False
    chamadas: list[dict] = field(default_factory=list)
    # Tudo o que as ferramentas devolveram nesta resposta (base para conferir os números do texto).
    resultados: list[Any] = field(default_factory=list)


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
        # Último modelo que respondeu em cada cadeia (o chat tem a sua) e quando passou a ser ele.
        self._fixos: dict[tuple[str, ...], tuple[str, float]] = {}
        self._trava = threading.Lock()
        self._uso: tuple[date, int] = (date.today(), 0)
        self.ultimo_erro: str | None = None
        # Modelos que deram 429 (sem cota) ou 404 (não existe) ficam de fora até este instante (monotonic).
        # Sem isso, cada pergunta gastava 4 ou 5 tentativas perdidas antes de chegar num modelo que responde.
        self._esgotados: dict[str, float] = {}

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
            "pulando": sorted(m for m, ate in self._esgotados.items() if ate > time.monotonic()),
            "limite_diario": CONFIG.ia_limite_diario,
            "ultimo_erro": self.ultimo_erro,
        }

    def _client(self):
        if self._cliente is None:
            self._cliente = genai.Client(
                api_key=CONFIG.gemini_api_key,
                http_options=types.HttpOptions(
                    timeout=CONFIG.gemini_timeout_ms,
                    # Sem retry no SDK: um 503 troca de modelo na hora (em dia de demanda alta o 503 é por modelo).
                    retry_options=types.HttpRetryOptions(attempts=1),
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
        prazo_s: float = 45.0,
        modelos: list[str] | None = None,
        pensamento: str | None = None,
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
        cadeia = tuple(modelos or CONFIG.gemini_modelos)
        nivel_pensamento = pensamento or CONFIG.gemini_pensamento
        # O último modelo que respondeu vai na frente, mas só por um tempo: depois o preferido ganha nova chance.
        fixo, desde = self._fixos.get(cadeia, (None, 0.0))
        if time.monotonic() - desde >= CONFIG.gemini_volta_s:
            fixo = None
        modelos = list(dict.fromkeys([m for m in [fixo, *cadeia] if m]))
        # Pula quem está sem cota; se todos estiverem, tenta ao menos o último da cadeia.
        agora_m = time.monotonic()
        modelos = [m for m in modelos if self._esgotados.get(m, 0.0) <= agora_m] or modelos[-1:]
        inicio = time.perf_counter()
        for modelo in modelos:
            restante = prazo_s - (time.perf_counter() - inicio)
            if restante < 3:
                self.registrar(etapa, f"prazo de {prazo_s:.0f} s esgotado: usando regras", modelo="regras", ok=False)
                return None
            # Prazo total da chamada (todas as tentativas): a rota interativa nunca fica presa.
            config.http_options = types.HttpOptions(
                timeout=int(min(restante, CONFIG.gemini_timeout_ms / 1000) * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            )
            # Só a família 3 aceita thinking_level; nos outros o modelo usa o próprio padrão.
            nivel = nivel_pensamento
            if nivel in ("medium", "high") and "lite" in modelo:
                nivel = "low"  # Flash-Lite com raciocínio alto passa de 30 s e volta 504
            config.thinking_config = (
                types.ThinkingConfig(thinking_level=nivel)
                if nivel and modelo.startswith("gemini-3")
                else None
            )
            t0 = time.perf_counter()
            try:
                # Com ferramentas o SDK faz várias idas e voltas, cada uma com o próprio timeout HTTP;
                # o prazo da thread garante o limite total. Uma chamada abandonada termina sozinha ao fundo.
                futuro = _EXECUTOR.submit(self._client().models.generate_content, model=modelo, contents=conteudo, config=config)
                resp = futuro.result(timeout=restante)
            except concurrent.futures.TimeoutError:
                ms = int((time.perf_counter() - t0) * 1000)
                self.ultimo_erro = f"{modelo}: prazo de {prazo_s:.0f} s esgotado"
                self.registrar(etapa, f"prazo de {prazo_s:.0f} s esgotado em {modelo}: usando regras", tempo_ms=ms, modelo=modelo, ok=False)
                return None
            except Exception as e:  # noqa: BLE001 - qualquer falha vira fallback, registrada na trilha
                ms = int((time.perf_counter() - t0) * 1000)
                codigo = getattr(e, "code", None)
                self.ultimo_erro = f"{modelo}: {codigo or type(e).__name__} {str(e)[:160]}"
                self.registrar(etapa, f"falhou em {modelo} ({codigo or type(e).__name__})", tempo_ms=ms, modelo=modelo, ok=False)
                if codigo == 429:
                    # Cota diária esgotada: fora por 1 h. Limite por minuto: fora por 1 min.
                    por_dia = "perday" in str(e).lower().replace(" ", "")
                    self._esgotados[modelo] = time.monotonic() + (3600 if por_dia else 60)
                elif codigo == 404:
                    self._esgotados[modelo] = time.monotonic() + 3600
                if codigo in (401, 403):
                    return None  # chave inválida: nenhum modelo vai funcionar
                if codigo == 400 and "API key" in str(e):
                    return None
                continue  # 404 (modelo inexistente), 429 (cota), 5xx, timeout → próximo modelo
            ms = int((time.perf_counter() - t0) * 1000)
            # Só chamada que respondeu conta no teto diário (429 e 404 não gastam a chave).
            self._contar()
            self._esgotados.pop(modelo, None)
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
            if self._fixos.get(cadeia, (None,))[0] != modelo:
                self._fixos[cadeia] = (modelo, time.monotonic())
            self.ultimo_erro = None
            self.registrar(etapa, detalhe or nome_schema, tokens=tokens, tempo_ms=ms, modelo=modelo)
            if chave:
                bruto = TypeAdapter(schema).dump_python(objeto, mode="json")
                self.armazem.kv_set(chave, {"objeto": bruto, "texto": texto, "modelo": modelo})
            resultados = [
                parte.function_response.response
                for c in (getattr(resp, "automatic_function_calling_history", None) or [])
                for parte in (c.parts or [])
                if getattr(parte, "function_response", None) is not None
            ]
            return RespostaIA(texto=texto, objeto=objeto, modelo=modelo, tokens=tokens, tempo_ms=ms, chamadas=chamadas,
                              resultados=resultados)
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
