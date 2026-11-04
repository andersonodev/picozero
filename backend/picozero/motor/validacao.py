# backend/picozero/motor/validacao.py
# Teste do motor contra dado REAL público: visitas mensais estimadas do domínio do portal
# (Domsilo, painel de tráfego). Compara a FORMA (sazonalidade mês a mês) prevista só a partir do
# calendário com a série real. O nível absoluto não é comparável (painel subestima tráfego logado),
# por isso a escala é informada, não usada para mudar a capacidade.
import calendar
import json
import statistics

from .. import contexto
from ..armazem import Armazem
from ..config import DADOS
from ..fmt import decimal, inteiro
from .previsao import Motor

ARQUIVO_PADRAO = DADOS / "publico_estudante_ibmec_br.json"


def serie_publica(armazem: Armazem, dominio: str | None = None) -> dict:
    """Série pública salva pela ingestão (kv publico:<dominio>) ou a que veio no pacote."""
    if dominio:
        salvo = armazem.kv_get(f"publico:{dominio}")
        if salvo:
            return salvo
    padrao = json.loads(ARQUIVO_PADRAO.read_text(encoding="utf-8"))
    if dominio and dominio != padrao["dominio"]:
        raise KeyError(dominio)
    return armazem.kv_get(f"publico:{padrao['dominio']}") or padrao


def _pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5
    return round(num / den, 3) if den else None


def validar(motor: Motor, armazem: Armazem, unidade: str, dominio: str | None = None) -> dict:
    pub = serie_publica(armazem, dominio)
    w = float(pub.get("snapshot", {}).get("duracao_media_s") or 180)
    meses = []
    for item in pub["visitas_mensais"]:
        ano, mes = map(int, item["mes"].split("-"))
        ini = f"{item['mes']}-01"
        fim = f"{item['mes']}-{calendar.monthrange(ano, mes)[1]:02d}"
        soma = 0.0
        for r in contexto.dias(ini, fim):
            soma += sum(p.carga for p in motor.curva(unidade, r).pontos)
        # Lei de Little: visitas ≈ Σ(concorrência × 900 s) ÷ duração média da visita.
        meses.append({"mes": item["mes"], "visitas_reais": item["visitas"], "visitas_modelo_bruto": soma * 900 / w})
    reais = [m["visitas_reais"] for m in meses]
    modelo = [m["visitas_modelo_bruto"] for m in meses]
    escala = sum(reais) / sum(modelo) if sum(modelo) else 0.0
    for m in meses:
        m["visitas_modelo"] = round(m["visitas_modelo_bruto"] * escala)
        m["erro_pct"] = round((m["visitas_modelo"] - m["visitas_reais"]) / m["visitas_reais"] * 100)
        m.pop("visitas_modelo_bruto")
    r = _pearson(reais, modelo)
    # Tendência de adoção: o quanto o uso do domínio cresce por mês além do calendário.
    melhor = (r, 0.0)
    for g in [i / 100 for i in range(1, 16)]:
        ajustado = [v * (1 + g * t) for t, v in enumerate(modelo)]
        rg = _pearson(reais, ajustado)
        if rg is not None and (melhor[0] is None or rg > melhor[0]):
            melhor = (rg, g)
    snap = pub.get("snapshot", {})
    dias_mes = calendar.monthrange(*map(int, snap["mes"].split("-")))[1] if snap.get("mes") else 30
    concorrencia_media = snap.get("visitas", 0) / (dias_mes * 86400) * w if snap else None
    pior = max(meses, key=lambda m: abs(m["erro_pct"]))
    return {
        "dominio": pub["dominio"],
        "fonte": pub["fonte"],
        "coletado_em": pub.get("coletado_em"),
        "unidade": unidade,
        "meses": meses,
        "correlacao": r,
        "correlacao_com_tendencia": melhor[0],
        "tendencia_mensal": melhor[1],
        "mape": round(statistics.mean(abs(m["erro_pct"]) for m in meses), 1),
        "escala_publico_sobre_modelo": round(escala, 3),
        "concorrencia_media_publica": round(concorrencia_media, 1) if concorrencia_media is not None else None,
        "fatores_modelo": motor.calibracao(unidade).fatores,
        "leitura": (
            f"Só com calendário, feriados e períodos, o motor acompanha a sazonalidade real do {pub['dominio']} "
            f"com correlação {decimal(r or 0, 2)}"
            + (f" ({decimal(melhor[0], 2)} com a tendência de adoção de {round(melhor[1] * 100)}%/mês)" if melhor[1] else "")
            + f". Maior desvio em {pior['mes']} ({pior['erro_pct']:+d}%). Nível absoluto: o painel público indica "
            f"~{inteiro(concorrencia_media or 0)} sessões simultâneas em média no domínio; ele subestima tráfego autenticado, "
            "então o nível de produção vem do export do APM quando liberado."
        ),
    }
