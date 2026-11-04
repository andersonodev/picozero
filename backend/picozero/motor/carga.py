# backend/picozero/motor/carga.py
# Modelo determinístico de carga por janela de 15 minutos (o mesmo de frontend/src/dados/previa.js).
# Cada tipo de evento tem uma forma explicável; a previsão (previsao.py) calibra a amplitude
# de cada forma com o histórico. O Gemini nunca escreve estes números.
import math
from collections.abc import Iterable

from ..dominio import Evento

JANELAS = 96  # 24 h × 4
ALUNOS_REFERENCIA = 8000  # unidade em que as amplitudes abaixo foram ajustadas (RJ)
ALUNOS_POR_TURMA = 60
P_ACESSO = {"notas": 0.05, "rematricula": 0.05}
TIPOS_EVENTO = ("vencimento", "prova_online", "notas", "rematricula", "outro")


def sino(h: float, centro: float, largura: float) -> float:
    return math.exp(-0.5 * ((h - centro) / largura) ** 2)


def minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def hora_da_janela(i: int) -> str:
    m = i * 15
    return f"{m // 60:02d}:{m % 60:02d}"


def janela_da_hora(hhmm: str) -> int:
    return min(JANELAS - 1, max(0, minutos(hhmm) // 15))


def base(h: float) -> float:
    """Uso orgânico de um dia letivo comum: manhã, tarde e o pico das 21h."""
    return 20 + 55 * sino(h, 10.5, 1.8) + 45 * sino(h, 15, 2.2) + 80 * sino(h, 21, 1.5)


def contribuicao(ev: Evento, m: int, alunos: int, opcoes: dict | None = None) -> float:
    """Acessos simultâneos que o evento adiciona no minuto m do dia."""
    opcoes = opcoes or {}
    h = m / 60
    ini = minutos(ev.hora_inicio)
    fim = minutos(ev.hora_fim)
    escala = alunos / ALUNOS_REFERENCIA
    if ev.tipo == "vencimento":
        escalonado = bool(opcoes.get("lembretes_escalonados"))
        manha = (60 if escalonado else 30) * sino(h, 9, 1.5)
        noite = 380 * ((h - 12) / 12) ** 2.2 if h > 12 else 0.0
        return escala * (manha + (0.4 if escalonado else 1.0) * noite)
    if ev.tipo == "prova_online":
        afetados = ev.alunos if ev.alunos is not None else len(ev.turmas) * ALUNOS_POR_TURMA
        if ini <= m < ini + 15:
            return afetados * 1.25
        if ini + 15 <= m < fim:
            return afetados * 0.9
        if fim <= m < fim + 30:
            return afetados * 0.15
        return 0.0
    if ev.tipo == "notas":
        if opcoes.get("notas_movidas") or m < ini:
            return 0.0
        alvo = ev.alunos if ev.alunos is not None else alunos
        return alvo * P_ACESSO["notas"] * math.exp(-(m - ini) / 120)
    if ev.tipo == "rematricula":
        if m < ini:
            return 0.0
        alvo = ev.alunos if ev.alunos is not None else alunos
        return alvo * P_ACESSO["rematricula"] * math.exp(-(m - ini) / 150) + 25 * escala
    if ev.tipo == "outro":
        return 30 * escala * sino(h, ini / 60 + 1, 1) if ini <= m < fim else 0.0
    return 0.0


def curva_base(alunos: int) -> list[float]:
    escala = alunos / ALUNOS_REFERENCIA
    return [escala * base(i * 15 / 60) for i in range(JANELAS)]


def componentes(eventos: Iterable[Evento], alunos: int, opcoes: dict | None = None) -> dict[str, list[float]]:
    """Contribuição de cada tipo de evento por janela (amplitude 1 = modelo sem calibrar)."""
    comp = {t: [0.0] * JANELAS for t in TIPOS_EVENTO}
    for ev in eventos:
        serie = comp[ev.tipo]
        for i in range(JANELAS):
            serie[i] += contribuicao(ev, i * 15, alunos, opcoes)
    return comp


def curva_modelo(eventos: Iterable[Evento], alunos: int, opcoes: dict | None = None) -> list[float]:
    """Curva do front (previa.js curvaDoDia): base + soma dos eventos, sem calibração."""
    eventos = list(eventos)
    b = curva_base(alunos)
    comp = componentes(eventos, alunos, opcoes)
    return [b[i] + sum(comp[t][i] for t in TIPOS_EVENTO) for i in range(JANELAS)]
