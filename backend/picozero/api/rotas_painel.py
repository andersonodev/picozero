# backend/picozero/api/rotas_painel.py
# Leitura do painel: contexto, calendário, curva do dia, picos do período, previsão dos próximos dias,
# modelo (calibração + backtest), validação com dado público e fontes de dados.
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query

from .. import contexto, servico
from ..config import CONFIG
from ..dominio import Contexto, CurvaDia, Evento, Marco, ResumoDia, Unidade
from ..motor import validacao
from .dependencias import AgoraDep, UnidadeDep

router = APIRouter(prefix="/api", tags=["painel"])

DataPath = Annotated[str, Path(pattern=r"^\d{4}-\d{2}-\d{2}$", description="AAAA-MM-DD")]
DataQuery = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")]


def _data_valida(iso: str) -> str:
    try:
        date.fromisoformat(iso)
    except ValueError:
        raise HTTPException(422, f"Data inválida: {iso}") from None
    return iso


@router.get("/saude")
def saude() -> dict[str, Any]:
    a = servico.armazem()
    return {
        "status": "ok",
        "servico": "picozero-backend",
        "versao": "0.1.0",
        "agora": contexto.agora().isoformat(timespec="minutes"),
        "ia": servico.ia().estado(),
        "armazem": a.contagens(),
        "banco": "sqlite",
        "mcp": "/mcp",
        "docs": "/docs",
    }


@router.get("/contexto")
def obter_contexto(unidade: UnidadeDep) -> Contexto:
    sem = contexto.semestre()
    return Contexto(
        instituicao=f"{contexto.instituicao()} {unidade.curto}",
        semestre=sem["nome"],
        alunos=unidade.alunos,
        capacidade=unidade.capacidade,
        inicio=sem["inicio"],
        fim=sem["fim"],
        modelo=servico.ia().modelo if servico.ia().disponivel else "regras",
        feriados=contexto.feriados(sem["inicio"], sem["fim"]),
        unidade=unidade.id,
        ia="gemini" if servico.ia().disponivel else "fallback",
    )


@router.get("/unidades")
def listar_unidades() -> list[Unidade]:
    return contexto.unidades()


@router.get("/eventos")
def listar_eventos(unidade: UnidadeDep, inicio: DataQuery = None, fim: DataQuery = None) -> list[Evento]:
    """Eventos do calendário (padrão: semestre atual; passe inicio/fim para ver o histórico)."""
    sem = contexto.semestre()
    m = servico.motor()
    return servico.armazem().eventos(m._unidade_eventos(unidade.id), inicio or sem["inicio"], fim or sem["fim"])


@router.get("/marcos")
def listar_marcos() -> list[Marco]:
    return contexto.marcos()


@router.get("/carga/{data}")
def curva_do_dia(data: DataPath, unidade: UnidadeDep, agora: AgoraDep, ao_vivo: bool = True) -> CurvaDia:
    """Curva prevista (96 janelas de 15 min) com banda p10–p90, real observado, pico e janelas de pico.
    Se `data` é hoje e há métricas ao vivo, o resto do dia vem corrigido pelo nowcast."""
    _data_valida(data)
    return servico.motor().curva(unidade.id, data, agora=agora if ao_vivo else None)


@router.get("/picos")
def picos_do_periodo(
    unidade: UnidadeDep, agora: AgoraDep, inicio: DataQuery = None, fim: DataQuery = None
) -> list[ResumoDia]:
    """Pico diário previsto (e real, onde houver) — alimenta a fita de capacidade do semestre."""
    sem = contexto.semestre()
    ini, fi = _data_valida(inicio or sem["inicio"]), _data_valida(fim or sem["fim"])
    if (date.fromisoformat(fi) - date.fromisoformat(ini)).days > 400:
        raise HTTPException(422, "Período máximo de 400 dias")
    return servico.motor().resumo(unidade.id, ini, fi, agora=agora)


@router.get("/previsao")
def previsao(unidade: UnidadeDep, agora: AgoraDep, dias: Annotated[int, Query(ge=1, le=60)] = 7) -> dict[str, Any]:
    """Próximos dias a partir de agora, com o próximo dia de risco em destaque."""
    ini = agora.date()
    resumo = servico.motor().resumo(unidade.id, ini.isoformat(), (ini + timedelta(days=dias)).isoformat(), agora=agora)
    risco = [r for r in resumo if r.nivel != "ok"]
    return {
        "agora": agora.isoformat(timespec="minutes"),
        "unidade": unidade.id,
        "capacidade": unidade.capacidade,
        "dias": resumo,
        "proximo_risco": risco[0] if risco else None,
        "pior": max(resumo, key=lambda r: r.razao) if resumo else None,
    }


@router.get("/modelo")
def modelo(unidade: UnidadeDep) -> dict[str, Any]:
    """Como o motor prevê: fatores aprendidos por tipo de evento, bandas de erro e backtest fora da amostra."""
    m = servico.motor()
    cal = m.calibracao(unidade.id)
    return {
        "unidade_de_calibracao": cal.unidade,
        "fatores": cal.fatores,
        "bandas": cal.bandas,
        "dias_usados": cal.dias_usados,
        "dias_com_evento_ou_periodo": cal.dias_com_evento,
        "periodo_historico": cal.periodo,
        "origem_dos_pontos": cal.origem_dados,
        "backtest": m.backtest(unidade.id),
        "formula": "carga = perfil(tipo de dia) × (1 + fator_periodo) + Σ fator[tipo] × forma(evento) → nowcast ao vivo",
    }


@router.get("/validacao/publica")
def validacao_publica(unidade: UnidadeDep, dominio: str | None = None) -> dict[str, Any]:
    """Teste do motor com dado real público (visitas mensais do domínio do portal)."""
    try:
        return validacao.validar(servico.motor(), servico.armazem(), unidade.id, dominio)
    except KeyError:
        raise HTTPException(404, f"Sem série pública para {dominio}. Envie em POST /api/ingestao/trafego.") from None


@router.get("/fontes")
def fontes() -> dict[str, Any]:
    """O que é real, o que é modelo e o que foi ingerido — para a aba Fonte de dados."""
    a = servico.armazem()
    pub = validacao.serie_publica(a)
    ultimo = pub["visitas_mensais"][-1]
    eventos = a.eventos(contexto.unidade_padrao().id)
    por_fonte: dict[str, int] = {}
    for e in eventos:
        por_fonte[e.fonte or "?"] = por_fonte.get(e.fonte or "?", 0) + 1
    return {
        "metricas": a.fontes_metricas(),
        "publico": [{
            "tipo": "real",
            "dominio": pub["dominio"],
            "fonte": pub["fonte"],
            "coletado_em": pub.get("coletado_em"),
            "meses": len(pub["visitas_mensais"]),
            "ultimo_mes": ultimo["mes"],
            "visitas_ultimo_mes": ultimo["visitas"],
            "duracao_media_s": pub.get("snapshot", {}).get("duracao_media_s"),
        }],
        "calendario": {"eventos": len(eventos), "por_fonte": por_fonte},
        "ingestoes": [r.model_dump(mode="json") for r in a.ingestoes(10)],
        "ia": servico.ia().estado(),
        "token_escrita": bool(CONFIG.token_escrita),
    }
