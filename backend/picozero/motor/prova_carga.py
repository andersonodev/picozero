# backend/picozero/motor/prova_carga.py
# Prova de carga (forma da tela ProvaCarga do front): latência p95 ao longo do dia em três perfis
# — antes (curva original, sem fila), depois (plano aprovado + fila) e controle (dia tranquilo).
# A curva vem do motor (histórico + cálculo), nunca da saída do Gemini: a prova não é circular.
import math
from datetime import date, timedelta

from .. import contexto, servico
from . import plano as planos

BASE_MS = 120


def ruido(i: int) -> float:
    return 1 + 0.05 * math.sin(i * 1.7) + 0.03 * math.cos(i * 0.6)


def latencia_ms(ativos: float, capacidade: int) -> float:
    """Mesmo modelo do servidor simulado (/sim): cresce com o cubo da ocupação."""
    return BASE_MS * (1 + (ativos / capacidade) ** 3)


def dia_controle(unidade: str, data: str) -> str:
    """Dia útil (seg–qui), letivo e sem eventos mais próximo antes do dia de pico."""
    m = servico.motor()
    d = date.fromisoformat(data)
    for k in range(1, 120):
        iso = (d - timedelta(days=k)).isoformat()
        if contexto.tipo_dia(iso) == "util" and not m.eventos_do_dia(unidade, iso):
            return iso
    return (d - timedelta(days=7)).isoformat()


def series_latencia(unidade: str, data: str, controle: str | None = None) -> list[dict]:
    m = servico.motor()
    cap = contexto.unidade(unidade).capacidade
    controle = controle or dia_controle(unidade, data)
    antes = m.curva(unidade, data, observado={}).pontos
    aprovado = planos.obter_plano(unidade, data)
    depois = aprovado.pontos_com or antes
    ctrl = m.curva(unidade, controle, observado={}).pontos
    serie = []
    for i, p in enumerate(antes):
        ua = p.carga
        ud = min(depois[i].carga, cap)  # fila virtual: semáforo na capacidade
        uc = ctrl[i].carga
        p95_antes = latencia_ms(ua, cap) * (1 + max(0, ua - cap) / 250) * ruido(i)
        serie.append(
            {
                "hora": p.hora,
                "antes": round(p95_antes),
                "depois": round(latencia_ms(ud, cap) * ruido(i + 3)),
                "controle": round(latencia_ms(uc, cap) * ruido(i + 7)),
                "erroAntes": (ua - 1.5 * cap) / ua if ua > 1.5 * cap else 0,
            }
        )
    return serie


def resumo_latencia(
    unidade: str, data: str, controle: str | None = None, serie: list[dict] | None = None
) -> list[dict]:
    controle = controle or dia_controle(unidade, data)
    s = serie if serie is not None else series_latencia(unidade, data, controle)

    def pico(chave: str) -> int:
        return max(p[chave] for p in s)

    return [
        {
            "chave": "antes",
            "nome": "Antes",
            "sub": f"{planos.dm(data)} · perfil original · sem fila",
            "p95": pico("antes"),
            "p50": round(pico("antes") * 0.46),
            "erros": max(p["erroAntes"] for p in s),
        },
        {
            "chave": "depois",
            "nome": "Depois",
            "sub": f"{planos.dm(data)} · plano aplicado · fila ligada",
            "p95": pico("depois"),
            "p50": round(pico("depois") * 0.55),
            "erros": 0,
        },
        {
            "chave": "controle",
            "nome": "Controle",
            "sub": f"{planos.dm(controle)} · dia tranquilo · sem plano",
            "p95": pico("controle"),
            "p50": round(pico("controle") * 0.6),
            "erros": 0,
        },
    ]
