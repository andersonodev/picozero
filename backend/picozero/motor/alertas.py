# backend/picozero/motor/alertas.py
# Alertas antecipados: varre a previsão dos próximos dias e avisa ANTES do pico, em estágios
# (planejamento > 72 h, preparação 24–72 h, véspera 2–24 h, iminente < 2 h, em curso).
# Com métricas ao vivo, o nowcast compara real × previsto e dispara o alerta "ao vivo".
import asyncio
import hashlib
import threading
from datetime import date, datetime, time, timedelta

import httpx

from .. import contexto
from ..armazem import Armazem
from ..config import CONFIG
from ..dominio import ORDEM_NIVEL, ROTULO_NIVEL, Alerta, CurvaDia, Janela
from ..fmt import ddmm, decimal, inteiro
from .previsao import Motor, nivel_da_razao

HORIZONTE_DIAS = 14
ANTECEDENCIA_ATENCAO_H = 72  # nível "atenção" só entra quando faltam até 72 h

ACOES_ESTAGIO = {
    "planejamento": ["Revisar o plano do dia e aprovar a escala extra", "Mover o que for móvel (notas, lembretes) para fora do pico"],
    "preparacao": ["Congelar deploys e manutenções até o fim do pico", "Agendar a escala do portal e a fila virtual", "Avisar atendimento e comunicação"],
    "vespera": ["Confirmar escala automática e fila virtual", "Confirmar plantão de TI e o comunicado de crise pré-aprovado", "Rodar a checagem rápida de pagamentos e login"],
    "iminente": ["Escalar o portal agora", "Ligar a fila virtual de login", "Abrir o canal de incidente com TI e atendimento"],
    "em_curso": ["Acompanhar p95 e 503 a cada 5 min", "Segurar deploys e jobs pesados até o fim da janela"],
    "ao_vivo": ["Carga real acima do previsto: escalar agora", "Ligar a fila virtual de login", "Preparar o comunicado de instabilidade"],
}
ACOES_EVENTO = {
    "vencimento": "Testar Pix, boleto e 2ª via antes da reta final dos pagamentos",
    "prova_online": "Pré-aquecer o ambiente de provas e testar o salvamento automático",
    "notas": "Cachear boletins e liberar as notas em lotes",
    "rematricula": "Monitorar travas (locks) no banco de matrícula",
    "outro": "Checar login/SSO e criação de contas",
}


def estagio(antecedencia_min: int) -> str:
    if antecedencia_min <= 0:
        return "em_curso"
    if antecedencia_min <= 120:
        return "iminente"
    if antecedencia_min <= 24 * 60:
        return "vespera"
    if antecedencia_min <= 72 * 60:
        return "preparacao"
    return "planejamento"


def _dt(iso: str, hhmm: str) -> datetime:
    if hhmm == "23:59":
        return datetime.combine(date.fromisoformat(iso), time(23, 59))
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(date.fromisoformat(iso), time(h, m))


def _quando(min_: int) -> str:
    if min_ <= 0:
        return "agora"
    if min_ < 120:
        return f"em {min_} min"
    if min_ < 48 * 60:
        return f"em {round(min_ / 60)} h"
    return f"em {round(min_ / 1440)} dias"


def _gatilhos(c: CurvaDia, j: Janela) -> list:
    ini, fim = j.inicio, j.fim
    return [e for e in c.eventos if not (e.hora_fim < ini or e.hora_inicio >= fim)] or c.eventos


def _alerta(unidade: str, c: CurvaDia, j: Janela, agora: datetime, origem: str = "previsao", extra: str = "") -> Alerta:
    antecedencia = int((_dt(c.data, j.inicio) - agora).total_seconds() // 60)
    est = "ao_vivo" if origem == "ao_vivo" else estagio(antecedencia)
    evs = _gatilhos(c, j)
    razao = j.max / c.capacidade
    nomes = [e.descricao for e in evs]
    acoes = list(ACOES_ESTAGIO[est])
    acoes += [ACOES_EVENTO[t] for t in dict.fromkeys(e.tipo for e in evs)]
    titulo = f"{ROTULO_NIVEL[j.nivel].capitalize()} · {ddmm(c.data)} às {j.hora_max}: pico de {inteiro(j.max)} ({decimal(razao)}× a capacidade)"
    mensagem = (
        f"{extra}Previsão de {inteiro(j.max)} acessos simultâneos às {j.hora_max} de {ddmm(c.data)} "
        f"({_quando(antecedencia)}), janela {j.inicio}–{j.fim}, capacidade {c.capacidade}."
    )
    if nomes:
        mensagem += " Gatilhos: " + "; ".join(nomes) + "."
    chave = f"{unidade}|{c.data}|{j.inicio}|{origem}"
    return Alerta(
        id=hashlib.sha1(chave.encode()).hexdigest()[:12],
        unidade=unidade,
        nivel=j.nivel,
        rotulo=ROTULO_NIVEL[j.nivel],
        estagio=est,
        origem=origem,
        data=c.data,
        inicio=j.inicio,
        fim=j.fim,
        hora_pico=j.hora_max,
        pico=j.max,
        capacidade=c.capacidade,
        razao=round(razao, 2),
        antecedencia_min=antecedencia,
        titulo=titulo,
        mensagem=mensagem,
        acoes=list(dict.fromkeys(acoes)),
        eventos=nomes,
        criado_em=agora.isoformat(timespec="minutes"),
    )


def avaliar(motor: Motor, unidade: str, agora: datetime, horizonte: int = HORIZONTE_DIAS) -> list[Alerta]:
    """Alertas ativos e futuros, do mais urgente ao mais distante."""
    saida: list[Alerta] = []
    for i in range(horizonte + 1):
        iso = (agora.date() + timedelta(days=i)).isoformat()
        c = motor.curva(unidade, iso, agora=agora)
        for j in c.janelas:
            if _dt(iso, j.fim) <= agora:
                continue
            antecedencia_h = (_dt(iso, j.inicio) - agora).total_seconds() / 3600
            if j.nivel == "alerta" and antecedencia_h > ANTECEDENCIA_ATENCAO_H:
                continue
            saida.append(_alerta(unidade, c, j, agora))
        if i == 0 and c.ajuste_ao_vivo is not None:
            saida.extend(_ao_vivo(motor, unidade, c, agora))
    saida.sort(key=lambda a: (a.antecedencia_min if a.antecedencia_min > 0 else -1, -ORDEM_NIVEL[a.nivel]))
    return saida


def _ao_vivo(motor: Motor, unidade: str, c: CurvaDia, agora: datetime) -> list[Alerta]:
    """Real × previsto: se o dia está fugindo da previsão, avisa o novo pico antes de ele chegar."""
    ajuste = c.ajuste_ao_vivo or 1.0
    if abs(ajuste - 1) < 0.12:
        return []
    i_agora = (agora.hour * 60 + agora.minute) // 15
    futuro = [p for p in c.pontos[i_agora + 1 :]]
    if not futuro:
        return []
    topo = max(futuro, key=lambda p: p.carga)
    nivel = nivel_da_razao(topo.carga / c.capacidade)
    if ajuste < 1 or nivel in ("ok",):
        return []
    j = Janela(inicio=topo.hora, fim=topo.hora, max=topo.carga, hora_max=topo.hora, nivel=nivel)
    for jan in c.janelas:
        if jan.inicio <= topo.hora < jan.fim:
            j = jan
    extra = f"Carga real {round((ajuste - 1) * 100)}% acima do previsto até {c.observado_ate}. "
    return [_alerta(unidade, c, j, agora, origem="ao_vivo", extra=extra)]


# ---------- barramento (SSE) e saída por webhook ----------


class Barramento:
    """Pub/sub em memória: quem grava (thread do servidor) publica; cada conexão SSE tem uma fila."""

    def __init__(self) -> None:
        self._inscritos: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._trava = threading.Lock()

    def inscrever(self) -> asyncio.Queue:
        fila: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._trava:
            self._inscritos.append((asyncio.get_running_loop(), fila))
        return fila

    def cancelar(self, fila: asyncio.Queue) -> None:
        with self._trava:
            self._inscritos = [(lp, f) for lp, f in self._inscritos if f is not fila]

    def publicar(self, tipo: str, dados: dict) -> None:
        with self._trava:
            alvos = list(self._inscritos)
        for loop, fila in alvos:
            try:
                loop.call_soon_threadsafe(fila.put_nowait, {"tipo": tipo, "dados": dados})
            except (RuntimeError, asyncio.QueueFull):
                pass


BARRAMENTO = Barramento()


def _webhook(a: Alerta) -> None:
    texto = f"PicoZero · {a.titulo}\n{a.mensagem}\nAções: " + "; ".join(a.acoes[:3])
    try:
        httpx.post(CONFIG.alerta_webhook_url, json={"text": texto}, timeout=5)
    except httpx.HTTPError:
        pass


def sincronizar(armazem: Armazem, alertas: list[Alerta]) -> list[Alerta]:
    """Grava, preserva reconhecimentos e publica só o que é novo ou mudou."""
    mudaram = []
    for a in alertas:
        if armazem.salvar_alerta(a):
            mudaram.append(a)
            BARRAMENTO.publicar("alerta", a.model_dump(mode="json"))
            serio = ORDEM_NIVEL[a.nivel] >= ORDEM_NIVEL["serio"]
            if CONFIG.alerta_webhook_url and serio and armazem.marcar_notificado(a.id):
                threading.Thread(target=_webhook, args=(a,), daemon=True).start()
    rec = armazem.reconhecimentos(alertas[0].unidade) if alertas else {}
    for a in alertas:
        a.reconhecido_em = rec.get(a.id)
    return mudaram
