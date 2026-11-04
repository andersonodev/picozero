# backend/picozero/ia/conferencia.py
# Confere a resposta do copiloto contra os dados: cada número, data e horário do texto precisa
# aparecer no que as ferramentas devolveram (ou na pergunta). O que não aparece é suspeito de
# alucinação e volta para o modelo corrigir; se insistir, o chat responde pelas regras.
import re
from dataclasses import dataclass, field
from typing import Any

_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_DDMM = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])")
_HORA = re.compile(r"(?<!\d)([01]?\d|2[0-3])(?:[:h]([0-5]\d))(?!\d)")
_HORA_CHEIA = re.compile(r"(?<![\d:])([01]?\d|2[0-3])\s?h(?![\w:])")
# 1.294 · 1294 · 2,6 · 77% · 2,6×; não pega pedaços de palavras (AP1, 5ª) nem de semestres (2026.2).
_NUMERO = re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?(?![\w.]\d|\w)\s*(%|×|x\b)?")
_MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_DIA_MES = re.compile(r"\b(\d{1,2})\s+de\s+(" + "|".join(_MESES) + r")\b", re.IGNORECASE)


@dataclass
class Base:
    numeros: set[float] = field(default_factory=set)
    datas: set[tuple[int, int]] = field(default_factory=set)
    horas: set[str] = field(default_factory=set)
    capacidades: set[float] = field(default_factory=set)


@dataclass
class Resultado:
    ok: bool
    conferidos: int
    suspeitos: list[str]


def _texto_para_base(texto: str, base: Base) -> None:
    for a, m, d in _ISO.findall(texto):
        base.datas.add((int(d), int(m)))
        base.numeros.add(float(a))
    for d, m, _ in _DDMM.findall(texto):
        base.datas.add((int(d), int(m)))
    for d, mes in _DIA_MES.findall(texto):
        base.datas.add((int(d), _MESES[mes.lower()]))
    for h, mi in _HORA.findall(texto):
        base.horas.add(f"{int(h):02d}:{mi}")
    for h in _HORA_CHEIA.findall(texto):
        base.horas.add(f"{int(h):02d}:00")
    limpo = _ISO.sub(" ", texto)
    for inteiro, dec, _ in _NUMERO.findall(limpo):
        base.numeros.add(float(inteiro.replace(".", "") + (f".{dec}" if dec else "")))


def _juntar(valor: Any, base: Base, chave: str = "") -> None:
    if isinstance(valor, bool) or valor is None:
        return
    if isinstance(valor, (int, float)):
        base.numeros.add(float(valor))
        if chave == "capacidade":
            base.capacidades.add(float(valor))
    elif isinstance(valor, str):
        _texto_para_base(valor, base)
    elif isinstance(valor, dict):
        for k, v in valor.items():
            _juntar(v, base, str(k))
    elif isinstance(valor, (list, tuple, set)):
        for v in valor:
            _juntar(v, base, chave)
    else:
        _juntar(getattr(valor, "__dict__", None) or str(valor), base, chave)


def montar_base(resultados: list[Any], textos: list[str], capacidade: float | None = None) -> Base:
    """Tudo o que o modelo pode citar: resultados das ferramentas, a pergunta e o contexto do prompt."""
    base = Base()
    for r in resultados:
        _juntar(r, base)
    for t in textos:
        _texto_para_base(t, base)
    if capacidade:
        base.capacidades.add(float(capacidade))
        base.numeros.add(float(capacidade))
    return base


def _perto(n: float, valores: set[float], tol_rel: float = 0.005, tol_abs: float = 0.5) -> bool:
    return any(abs(v - n) <= max(tol_abs, tol_rel * abs(v)) for v in valores)


def conferir(texto: str, base: Base) -> Resultado:
    suspeitos: list[str] = []
    conferidos = 0
    # Datas por extenso e dd/mm.
    for d, mes in _DIA_MES.findall(texto):
        conferidos += 1
        if (int(d), _MESES[mes.lower()]) not in base.datas:
            suspeitos.append(f"{d} de {mes}")
    for d, m, _ in _DDMM.findall(texto):
        conferidos += 1
        if (int(d), int(m)) not in base.datas:
            suspeitos.append(f"{d}/{m}")
    # Horários: "19:00", "19h30" e "19h" (este último vale se algum horário daquela hora existir).
    for h, mi in _HORA.findall(texto):
        conferidos += 1
        if f"{int(h):02d}:{mi}" not in base.horas:
            suspeitos.append(f"{int(h):02d}:{mi}")
    for h in _HORA_CHEIA.findall(texto):
        conferidos += 1
        if not any(x.startswith(f"{int(h):02d}:") for x in base.horas):
            suspeitos.append(f"{h}h")
    # Números: tira o que já foi conferido como data/hora antes de procurar.
    limpo = _ISO.sub(" ", texto)
    limpo = _DIA_MES.sub(" ", limpo)
    limpo = _DDMM.sub(" ", limpo)
    limpo = _HORA.sub(" ", limpo)
    limpo = _HORA_CHEIA.sub(" ", limpo)
    for m in _NUMERO.finditer(limpo):
        inteiro, dec, unidade = m.groups()
        n = float(inteiro.replace(".", "") + (f".{dec}" if dec else ""))
        bruto = m.group(0).strip()
        if unidade == "%":
            conferidos += 1
            ok = _perto(n, base.numeros, 0, 1) or _perto(n / 100, base.numeros, 0, 0.01) or any(
                _perto(n, {v / c * 100 for v in base.numeros}, 0, 1) for c in base.capacidades if c
            )
        elif unidade in ("×", "x"):
            conferidos += 1
            ok = _perto(n, base.numeros, 0, 0.05) or any(
                _perto(n, {v / c for v in base.numeros}, 0, 0.05) for c in base.capacidades if c
            )
        elif 2000 <= n <= 2100 and not dec:
            continue  # ano
        elif n < 10 and not dec:
            continue  # contagens pequenas ("3 turmas", "2 alertas"): não dá para conferir com segurança
        else:
            conferidos += 1
            ok = _perto(n, base.numeros)
        if not ok:
            suspeitos.append(bruto)
    return Resultado(ok=not suspeitos, conferidos=conferidos, suspeitos=list(dict.fromkeys(suspeitos)))
