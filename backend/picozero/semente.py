# backend/picozero/semente.py
# Semente do banco: calendário 2026.2 (datas reais) + histórico de acesso MODELADO com seed fixa.
# O histórico é gerado com amplitudes "verdadeiras" diferentes das do modelo do front, para que a
# calibração (previsao.py) tenha o que aprender — e é trocado pelo real quando o export chegar
# (a ingestão sobrescreve os mesmos horários, com origem 'real'/'ingerido').
import math
import random
from datetime import datetime

from . import contexto
from .armazem import Armazem
from .dominio import Evento, PontoMetrica
from .motor import carga

SEED = 20261104
# "Realidade" oculta do histórico modelado: o que a calibração deve redescobrir.
VERDADE = {"vencimento": 0.93, "prova_online": 1.06, "notas": 1.18, "rematricula": 1.12, "outro": 1.0, "periodo": 0.55}
FATOR_DIA = {"util": 1.0, "sexta": 0.88, "sabado": 0.52, "domingo": 0.4, "feriado": 0.36, "ferias": 0.3}


def _curva_verdadeira(eventos: list[Evento], alunos: int, tipo_dia: str, em_periodo: bool) -> list[float]:
    b = carga.curva_base(alunos)
    comp = carga.componentes(eventos, alunos)
    f = FATOR_DIA[tipo_dia] * (1 + VERDADE["periodo"] if em_periodo else 1)
    return [b[i] * f + sum(VERDADE[t] * comp[t][i] for t in carga.TIPOS_EVENTO) for i in range(carga.JANELAS)]


def gerar_historico(unidade_id: str, inicio: str, fim: str, eventos: list[Evento]) -> list[PontoMetrica]:
    uni = contexto.unidade(unidade_id)
    rnd = random.Random(f"{SEED}-{unidade_id}")
    por_dia: dict[str, list[Evento]] = {}
    for ev in eventos:
        por_dia.setdefault(ev.data, []).append(ev)
    incidentes: dict[str, list[dict]] = {}
    for inc in contexto.historico_eventos().get("incidentes", []):
        incidentes.setdefault(inc["data"], []).append(inc)

    pontos: list[PontoMetrica] = []
    for iso in contexto.dias(inicio, fim):
        curva = _curva_verdadeira(por_dia.get(iso, []), uni.alunos, contexto.tipo_dia(iso), bool(contexto.periodo(iso)))
        nivel_dia = math.exp(rnd.gauss(0, 0.05))
        erro = 0.0
        ano, mes, dia = map(int, iso.split("-"))
        for i, valor in enumerate(curva):
            erro = 0.6 * erro + rnd.gauss(0, 0.06)  # ruído autocorrelacionado entre janelas
            v = valor * nivel_dia * math.exp(erro)
            hhmm = carga.hora_da_janela(i)
            for inc in incidentes.get(iso, []):
                if inc["inicio"] <= hhmm < inc["fim"]:
                    v *= inc["fator"]
            pontos.append(PontoMetrica(ts=datetime(ano, mes, dia, i // 4, (i % 4) * 15), valor=round(max(v, 0.0))))
    return pontos


def popular(armazem: Armazem) -> dict:
    """Idempotente: só semeia se o banco estiver vazio."""
    if not armazem.vazio():
        return {"semeado": False}
    padrao = contexto.unidade_padrao().id
    atuais = contexto.eventos_semente()
    passados = contexto.eventos_historicos()
    armazem.gravar_eventos(padrao, atuais, origem="calendario")
    armazem.gravar_eventos(padrao, passados, origem="modelo")
    hist = contexto.historico()
    pontos = gerar_historico(padrao, hist["inicio"], hist["fim"], atuais + passados)
    armazem.gravar_pontos(padrao, pontos, origem="modelo", fonte="semente:gerar_historico")
    return {"semeado": True, "pontos": len(pontos), "eventos": len(atuais) + len(passados)}
