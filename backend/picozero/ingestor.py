# backend/picozero/ingestor.py
# Porta de entrada única dos dados: arquivo (qualquer formato), JSON de webhook, texto livre,
# métricas ao vivo, eventos, série pública de tráfego. Tudo passa por aqui — HTTP, MCP e simulação —
# e sai com um relatório auditável (o que entrou, o que foi ignorado e por quê).
import hashlib
import time
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from . import contexto, servico
from .config import TZ
from .dominio import Evento, PontoMetrica, RelatorioIngestao, ResultadoParse
from .ia import tarefas
from .motor import alertas


class PontoEntrada(BaseModel):
    ts: str | float | int = Field(description="ISO 8601 (com ou sem fuso) ou epoch em s/ms")
    valor: float = Field(ge=0)


class MesTrafego(BaseModel):
    mes: str = Field(pattern=r"^\d{4}-\d{2}$")
    visitas: int = Field(ge=0)


class SerieTrafego(BaseModel):
    dominio: str
    fonte: str = "informada pelo usuário"
    visitas_mensais: list[MesTrafego] = Field(min_length=1)
    duracao_media_s: float | None = Field(default=None, gt=0)
    paginas_por_visita: float | None = None


def _ts(valor: str | float | int) -> datetime:
    if isinstance(valor, (int, float)) or (isinstance(valor, str) and valor.replace(".", "", 1).isdigit()):
        n = float(valor)
        n = n / 1000 if n > 1e11 else n
        return datetime.fromtimestamp(n, TZ).replace(tzinfo=None)
    d = datetime.fromisoformat(str(valor).strip().replace(" ", "T").replace("Z", "+00:00"))
    return d.astimezone(TZ).replace(tzinfo=None) if d.tzinfo else d


def _alinhar(d: datetime) -> datetime:
    return d.replace(minute=d.minute - d.minute % 15, second=0, microsecond=0)


PROVA_TURMAS_PADRAO = 5  # prova online sem turmas nem alunos: assume 5 turmas (300 alunos) e avisa


def _completar_eventos(res: ResultadoParse, fonte: str) -> None:
    for i, ev in enumerate(res.eventos):
        mudou = {}
        if not ev.fonte:
            mudou["fonte"] = fonte
        if ev.tipo == "prova_online" and not ev.turmas and ev.alunos is None:
            mudou["alunos"] = PROVA_TURMAS_PADRAO * 60
            res.avisos.append(f"'{ev.descricao[:60]}' sem turmas: assumi {PROVA_TURMAS_PADRAO * 60} alunos")
        if mudou:
            res.eventos[i] = ev.model_copy(update=mudou)


def _registrar(unidade: str, canal: str, res: ResultadoParse, arquivo: str | None, t0: float, origem: str) -> RelatorioIngestao:
    a = servico.armazem()
    _completar_eventos(res, f"{canal}:{arquivo}" if arquivo else canal)
    pontos = a.gravar_pontos(unidade, res.pontos, origem=origem, fonte=arquivo or canal) if res.pontos else 0
    eventos = a.gravar_eventos(unidade, res.eventos, origem="ingerido") if res.eventos else 0
    if (res.pontos and origem != "ao_vivo") or eventos:
        servico.motor().invalidar()  # histórico novo → recalibra na próxima consulta
    if eventos:
        a.kv_apagar_prefixo(f"riscos:{unidade}")
        a.kv_apagar_prefixo(f"plano:{unidade}")
    periodo = None
    if res.pontos:
        tss = sorted(p.ts for p in res.pontos)
        periodo = [tss[0].isoformat(timespec="minutes"), tss[-1].isoformat(timespec="minutes")]
    rel = RelatorioIngestao(
        id=uuid.uuid4().hex[:12],
        quando=datetime.now(TZ).replace(tzinfo=None).isoformat(timespec="seconds"),
        canal=canal,
        unidade=unidade,
        formato=res.formato,
        arquivo=arquivo,
        linhas_lidas=res.linhas_lidas,
        pontos_inseridos=pontos,
        eventos_inseridos=eventos,
        ignorados=res.linhas_ignoradas,
        periodo=periodo,
        avisos=res.avisos,
        mapeamento=res.mapeamento,
        origem_parse=res.origem,
        duracao_ms=int((time.perf_counter() - t0) * 1000),
    )
    a.registrar_ingestao(rel)
    alertas.BARRAMENTO.publicar("ingestao", rel.model_dump(mode="json"))
    if pontos or eventos:
        try:
            alertas.sincronizar(a, alertas.avaliar(servico.motor(), unidade, contexto.agora(), horizonte=3))
        except Exception:  # noqa: BLE001 - alerta nunca derruba a ingestão
            pass
    return rel


def arquivo(conteudo: bytes, nome: str | None, content_type: str | None, unidade: str, dica: str | None = None,
            canal: str = "arquivo") -> RelatorioIngestao:
    from . import ingestao

    t0 = time.perf_counter()
    res = ingestao.analisar_arquivo(conteudo, nome, content_type, dica=dica, ia=tarefas.ASSISTENTE)
    return _registrar(unidade, canal, res, nome, t0, origem="real")


def json_qualquer(obj: Any, unidade: str, dica: str | None = None, canal: str = "webhook") -> RelatorioIngestao:
    from . import ingestao

    t0 = time.perf_counter()
    res = ingestao.analisar_json(obj, dica=dica, ia=tarefas.ASSISTENTE)
    return _registrar(unidade, canal, res, None, t0, origem="real")


def texto(conteudo: str, unidade: str, dica: str | None = None, canal: str = "texto") -> RelatorioIngestao:
    from . import ingestao

    t0 = time.perf_counter()
    res = ingestao.analisar_texto(conteudo, dica=dica, ia=tarefas.ASSISTENTE)
    return _registrar(unidade, canal, res, None, t0, origem="real")


def metricas(pontos: list[PontoEntrada], unidade: str, canal: str = "metricas", origem: str = "ao_vivo") -> RelatorioIngestao:
    """Caminho rápido para métricas ao vivo (APM, Grafana, script, MCP): máximo por janela de 15 min."""
    t0 = time.perf_counter()
    janelas: dict[datetime, float] = {}
    avisos: list[str] = []
    ignorados = 0
    for p in pontos:
        try:
            ts = _alinhar(_ts(p.ts))
        except (ValueError, OSError, OverflowError):
            ignorados += 1
            continue
        janelas[ts] = max(janelas.get(ts, 0.0), p.valor)
    if ignorados:
        avisos.append(f"{ignorados} ponto(s) com horário inválido foram ignorados")
    res = ResultadoParse(
        formato="metricas_json",
        pontos=[PontoMetrica(ts=t, valor=v) for t, v in sorted(janelas.items())],
        avisos=avisos,
        mapeamento={"agregacao": "max", "janela": "15min"},
        linhas_lidas=len(pontos),
        linhas_ignoradas=ignorados,
    )
    return _registrar(unidade, canal, res, None, t0, origem=origem)


def eventos(lista: list[Evento], unidade: str, canal: str = "eventos") -> RelatorioIngestao:
    t0 = time.perf_counter()
    res = ResultadoParse(formato="eventos_json", eventos=lista, linhas_lidas=len(lista))
    return _registrar(unidade, canal, res, None, t0, origem="real")


def trafego(serie: SerieTrafego, canal: str = "metricas") -> dict:
    """Série pública de visitas mensais (Domsilo, Similarweb, GA4…): usada para validar a sazonalidade."""
    dado = serie.model_dump()
    dado["coletado_em"] = datetime.now(TZ).date().isoformat()
    if serie.duracao_media_s:
        dado["snapshot"] = {
            "mes": serie.visitas_mensais[-1].mes,
            "visitas": serie.visitas_mensais[-1].visitas,
            "duracao_media_s": serie.duracao_media_s,
        }
    servico.armazem().kv_set(f"publico:{serie.dominio}", dado)
    chave = hashlib.sha1(serie.model_dump_json().encode()).hexdigest()[:8]
    servico.ia().registrar("ingerir_trafego", f"{serie.dominio}: {len(serie.visitas_mensais)} meses ({serie.fonte}) #{chave}",
                           modelo="regras")
    return {"dominio": serie.dominio, "meses": len(serie.visitas_mensais), "canal": canal}
