# backend/picozero/motor/plano.py
# Evitar: plano em 3 níveis (calendário, comunicação, infraestrutura) + ações executáveis.
# O validador aplica as ações sobre os eventos, recalcula a curva com o motor e checa as regras.
# O Gemini propõe; quem decide se passa é o código (até 3 tentativas, erro devolvido ao modelo).
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

from pydantic import BaseModel, Field, ValidationError

from .. import contexto, servico
from ..dominio import (
    ROTULO_NIVEL,
    TIPOS,
    Acao,
    CurvaDia,
    Evento,
    ItemPlano,
    Pico,
    Plano,
    ResultadoPlano,
    Tentativa,
)
from . import carga
from .previsao import janelas, nivel_da_razao

PROTEGIDOS = ("vencimento", "prova_online")  # nunca mudam de data nem de horário
IMPACTO_NOTAS_MIN = 120  # quanto tempo um lote de notas/onda pesa no portal depois de abrir
FOLGA_PROVA_MIN = 30  # saída da prova ainda gera acesso
AREAS = [
    "Gestão",
    "Economia",
    "Direito",
    "Engenharia",
    "Relações Internacionais",
    "Computação",
    "Comunicação",
    "Design",
]
SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


# ---------- utilidades de data, hora e texto ----------


def eh_dia_util(iso: str) -> bool:
    return date.fromisoformat(iso).weekday() < 5 and not contexto.feriado(iso)


def proximo_dia_util(iso: str, n: int = 1) -> str:
    d = date.fromisoformat(iso)
    while n > 0:
        d += timedelta(days=1)
        if eh_dia_util(d.isoformat()):
            n -= 1
    return d.isoformat()


def dia_util_anterior(iso: str, n: int = 1) -> str:
    d = date.fromisoformat(iso)
    while n > 0:
        d -= timedelta(days=1)
        if eh_dia_util(d.isoformat()):
            n -= 1
    return d.isoformat()


def _somar_dias(iso: str, n: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=n)).isoformat()


def _hhmm(minutos_: int) -> str:
    minutos_ = max(0, min(minutos_, 23 * 60 + 59))
    return f"{minutos_ // 60:02d}:{minutos_ % 60:02d}"


def dm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def n_br(x: float) -> str:
    return f"{round(x):,}".replace(",", ".")


def h_br(hhmm: str) -> str:
    """'09:00' → '9h', '10:30' → '10h30' (como no front)."""
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    if hhmm == "23:59":
        return "23h59"
    return f"{h}h" + (f"{m:02d}" if m else "")


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in t).split())


def _sobrepoe(a_ini: int, a_fim: int, b_ini: int, b_fim: int) -> bool:
    return a_ini < b_fim and b_ini < a_fim


def _nome_curto(descricao: str) -> str:
    for prefixo in ("Divulgação de ", "Divulgação das ", "Divulgação dos "):
        if descricao.startswith(prefixo):
            resto = descricao[len(prefixo) :]
            return resto[:1].upper() + resto[1:]
    return descricao


def _minusculo(texto: str) -> str:
    return texto[:1].lower() + texto[1:] if texto[:2] != texto[:2].upper() else texto


# ---------- aplicar ações ----------


@dataclass
class Aplicacao:
    """Resultado de aplicar as ações do plano sobre o calendário.

    A fila virtual não vira teto global: `janelas_fila` diz em que horários a concorrência fica
    presa em `teto` (= capacidade da unidade). Fora dessas janelas a curva segue livre — assim um
    pico de manhã não some só porque a fila foi ligada à noite.
    """

    eventos_dia: list[Evento]
    movidos: dict[str, list[Evento]] = field(default_factory=dict)
    criados: list[Evento] = field(default_factory=list)
    opcoes: dict = field(default_factory=dict)
    teto: int | None = None
    janelas_fila: list[tuple[str, str]] = field(default_factory=list)
    violacoes: list[str] = field(default_factory=list)
    aplicadas: list[str] = field(default_factory=list)


def _achar(eventos: list[Evento], alvo: str | None, tipos: tuple[str, ...]) -> Evento | None:
    if alvo:
        a = _norm(alvo)
        for ev in eventos:
            d = _norm(ev.descricao)
            if a and (a == d or a in d or d in a):
                return ev
        tokens = set(a.split())
        melhor = max(eventos, key=lambda e: len(tokens & set(_norm(e.descricao).split())), default=None)
        if melhor is not None and len(tokens & set(_norm(melhor.descricao).split())) >= 3:
            return melhor
    candidatos = [e for e in eventos if e.tipo in tipos]
    if not alvo or len(candidatos) == 1:
        return candidatos[0] if candidatos else None
    return None


def _protegido(ev: Evento) -> str:
    return (
        f"Vencimento e provas não mudam de data nem de horário: “{ev.descricao}” ({dm(ev.data)} às "
        f"{h_br(ev.hora_inicio)}) fica onde está."
    )


def _dividir(ap: Aplicacao, data: str, acao: Acao, alvo: Evento, partes: int, intervalo: int, rotulo: str, total: int):
    destino = acao.para_data or data
    inicio = carga.minutos(acao.para_hora or alvo.hora_inicio)
    novos = []
    for k in range(partes):
        m = inicio + k * intervalo
        if m > 23 * 60 + 45:
            ap.violacoes.append(
                f"{rotulo.capitalize()} {k + 1} de {partes} passaria da meia-noite de {dm(destino)} "
                f"(começa às {h_br(acao.para_hora or alvo.hora_inicio)} com intervalo de {intervalo} min)."
            )
            return
        atualizacao = {"data": destino, "hora_inicio": _hhmm(m), "fonte": "plano"}
        if partes > 1:
            atualizacao |= {
                "alunos": round(total / partes),
                "descricao": f"{alvo.descricao} · {rotulo} {k + 1}/{partes}",
            }
        novos.append(alvo.model_copy(update=atualizacao))
    ap.eventos_dia.remove(alvo)
    if destino == data:
        ap.eventos_dia.extend(novos)
    else:
        ap.movidos.setdefault(destino, []).extend(novos)
    ap.criados.extend(novos)


def aplicar_acoes(unidade: str, data: str, acoes: list[Acao]) -> Aplicacao:
    m = servico.motor()
    uni = contexto.unidade(unidade)
    # Alunos na escala da calibração: o motor multiplica pela razão da unidade depois.
    alunos_ref = m.calibracao(unidade).alunos
    ap = Aplicacao(eventos_dia=m.eventos_do_dia(unidade, data))
    for acao in acoes:
        alvo_texto = acao.evento
        if acao.tipo in ("mover_notas", "rematricula_em_ondas"):
            tipo_alvo = "notas" if acao.tipo == "mover_notas" else "rematricula"
            alvo = _achar(ap.eventos_dia, alvo_texto, (tipo_alvo,))
            if alvo is None:
                nome = "divulgação de notas" if tipo_alvo == "notas" else "rematrícula"
                ap.violacoes.append(f"Não há {nome} em {dm(data)} para {acao.tipo.replace('_', ' ')}.")
                continue
            if alvo.tipo in PROTEGIDOS:
                ap.violacoes.append(_protegido(alvo))
                continue
            if alvo.tipo != tipo_alvo:
                ap.violacoes.append(f"{acao.tipo} não vale para “{alvo.descricao}” ({TIPOS[alvo.tipo]}).")
                continue
            total = alvo.alunos if alvo.alunos is not None else alunos_ref
            if acao.tipo == "mover_notas":
                partes, intervalo = acao.lotes or 1, acao.intervalo_min or 90
                _dividir(ap, data, acao, alvo, partes, intervalo, "lote", total)
            else:
                partes, intervalo = acao.grupos or 3, acao.intervalo_min or 120
                _dividir(ap, data, acao, alvo, partes, intervalo, "onda", total)
            ap.aplicadas.append(acao.tipo)
        elif acao.tipo == "escalonar_lembretes":
            venc = _achar(ap.eventos_dia, alvo_texto, ("vencimento",)) or _achar(ap.eventos_dia, None, ("vencimento",))
            if venc is not None and (acao.para_data or acao.para_hora):
                ap.violacoes.append(_protegido(venc))
            elif venc is not None:
                ap.opcoes["lembretes_escalonados"] = True
                ap.aplicadas.append("escalonar_lembretes")
            else:
                ap.aplicadas.append("escalonar_lembretes sem vencimento no dia (sem efeito na curva)")
        elif acao.tipo == "fila_virtual":
            ini, fim = acao.inicio or "00:00", acao.fim or "23:59"
            if ini >= fim:
                ap.violacoes.append(f"Janela da fila virtual inválida: {ini}–{fim}.")
                continue
            ap.janelas_fila.append((ini, fim))
            ap.teto = uni.capacidade
            ap.aplicadas.append("fila_virtual")
        else:
            # escalar_infra e congelar_deploys entram só no checklist.
            if (acao.para_data or acao.para_hora) and alvo_texto:
                alvo = _achar(ap.eventos_dia, alvo_texto, ())
                if alvo is not None and alvo.tipo in PROTEGIDOS:
                    ap.violacoes.append(_protegido(alvo))
                    continue
            ap.aplicadas.append(acao.tipo)
    return ap


# ---------- curva com o plano ----------


def _dentro(hhmm: str, janelas_: list[tuple[str, str]]) -> bool:
    return any(ini <= hhmm < fim for ini, fim in janelas_)


def curvas_aplicadas(unidade: str, data: str, ap: Aplicacao) -> tuple[CurvaDia, CurvaDia]:
    """(sem fila, com fila) do dia depois das ações. A fila prende a concorrência na capacidade
    só dentro das janelas em que foi ligada."""
    sem_fila = servico.motor().curva(unidade, data, eventos=ap.eventos_dia, opcoes=ap.opcoes or None, observado={})
    if not ap.janelas_fila:
        return sem_fila, sem_fila.model_copy(update={"plano_aplicado": True})
    cap = sem_fila.capacidade
    pontos = []
    for p in sem_fila.pontos:
        if _dentro(p.hora, ap.janelas_fila):
            p = p.model_copy(
                update={
                    "carga": min(p.carga, cap),
                    "p10": min(p.p10, cap) if p.p10 is not None else None,
                    "p90": min(p.p90, cap) if p.p90 is not None else None,
                }
            )
        pontos.append(p)
    topo = max(pontos, key=lambda p: p.carga)
    razao = topo.carga / cap
    nivel = nivel_da_razao(razao)
    com_fila = sem_fila.model_copy(
        update={
            "pontos": pontos,
            "pico": Pico(hora=topo.hora, carga=topo.carga),
            "janelas": janelas(pontos, cap),
            "nivel": nivel,
            "rotulo": ROTULO_NIVEL[nivel],
            "razao": round(razao, 2),
            "plano_aplicado": True,
        }
    )
    return sem_fila, com_fila


def _causa(unidade: str, eventos: list[Evento], hhmm: str, opcoes: dict) -> str:
    cal = servico.motor().calibracao(unidade)
    m = carga.minutos(hhmm)
    contrib = [(cal.fatores[e.tipo] * carga.contribuicao(e, m, cal.alunos, opcoes), e) for e in eventos]
    contrib = [c for c in contrib if c[0] >= 20]
    if not contrib:
        return "o pico orgânico do portal (sem evento puxando a carga)"
    ev = max(contrib, key=lambda c: c[0])[1]
    if ev.tipo == "vencimento":
        return f"a reta final dos pagamentos ({_minusculo(ev.descricao)})"
    if ev.tipo == "prova_online":
        return f"a prova online “{ev.descricao}”, que não muda de horário"
    if ev.tipo == "notas":
        return f"a divulgação “{ev.descricao}”"
    if ev.tipo == "rematricula":
        return f"a rematrícula (“{ev.descricao}”)"
    return f"“{ev.descricao}”"


def _janelas_prova(eventos: list[Evento]) -> list[tuple[int, int, Evento]]:
    return [
        (carga.minutos(e.hora_inicio), carga.minutos(e.hora_fim) + FOLGA_PROVA_MIN, e)
        for e in eventos
        if e.tipo == "prova_online"
    ]


# ---------- validação ----------


def _descrever(acoes: list[Acao]) -> str:
    partes = []
    for a in acoes:
        if a.tipo == "mover_notas":
            quando = f"em {dm(a.para_data)}" if a.para_data else "no mesmo dia"
            hora = f" a partir das {h_br(a.para_hora)}" if a.para_hora else ""
            partes.append(f"notas em {a.lotes} lotes {quando}{hora}" if (a.lotes or 1) > 1 else f"notas {quando}{hora}")
        elif a.tipo == "escalonar_lembretes":
            partes.append(f"lembretes do vencimento em {a.grupos or 3} grupos")
        elif a.tipo == "rematricula_em_ondas":
            partes.append(f"rematrícula em {a.grupos or 3} ondas")
        elif a.tipo == "fila_virtual":
            partes.append(f"fila virtual das {h_br(a.inicio or '00:00')} às {h_br(a.fim or '23:59')}")
        elif a.tipo == "escalar_infra":
            partes.append("escala do portal")
        elif a.tipo == "congelar_deploys":
            partes.append("congelamento de deploys")
    if not partes:
        return "Manter o calendário, sem ações."
    texto = ", ".join(partes[:-1]) + (" e " if len(partes) > 1 else "") + partes[-1]
    return texto[:1].upper() + texto[1:] + "."


def _validar(
    unidade: str, data: str, plano: Plano, numero: int = 1, proposta: str | None = None
) -> tuple[Tentativa, CurvaDia | None]:
    m = servico.motor()
    cap = contexto.unidade(unidade).capacidade
    proposta = proposta or _descrever(plano.acoes)
    ap = aplicar_acoes(unidade, data, plano.acoes)
    erros = list(ap.violacoes)

    # Datas de destino: nada em feriado ou fim de semana.
    for destino in sorted(ap.movidos):
        nome = contexto.feriado(destino)
        if nome or date.fromisoformat(destino).weekday() >= 5:
            motivo = f"no feriado de {nome}" if nome else f"num {SEMANA[date.fromisoformat(destino).weekday()]}"
            erros.append(f"A carga levada para {dm(destino)} cai {motivo}.")

    # Nenhum lote/onda encosta em prova online no dia de destino.
    for ev in ap.criados:
        evs_destino = ap.eventos_dia if ev.data == data else m.eventos_do_dia(unidade, ev.data)
        ini = carga.minutos(ev.hora_inicio)
        for p_ini, p_fim, prova in _janelas_prova(evs_destino):
            if _sobrepoe(ini, ini + IMPACTO_NOTAS_MIN, p_ini, p_fim):
                erros.append(
                    f"O lote das {h_br(ev.hora_inicio)} de {dm(ev.data)} cai durante a prova online "
                    f"“{prova.descricao}” ({h_br(prova.hora_inicio)}–{h_br(prova.hora_fim)})."
                )
                break

    # Nada empurrado para dia crítico, nem dia que vira crítico.
    destinos_ok: list[str] = []
    for destino, novos in sorted(ap.movidos.items()):
        antes = m.curva(unidade, destino, observado={})
        if antes.nivel == "critico":
            erros.append(
                f"A carga foi empurrada para {dm(destino)}, que já é dia crítico "
                f"(pico de {n_br(antes.pico.carga)} às {h_br(antes.pico.hora)})."
            )
            continue
        depois = m.curva(unidade, destino, eventos=m.eventos_do_dia(unidade, destino) + novos, observado={})
        if depois.pico.carga > cap:
            erros.append(
                f"{dm(destino)} passaria a ter pico de {n_br(depois.pico.carga)} às {h_br(depois.pico.hora)}, "
                f"acima da capacidade de {n_br(cap)}."
            )
            continue
        destinos_ok.append(
            f"{dm(destino)} fica com pico de {n_br(depois.pico.carga)} às {h_br(depois.pico.hora)} "
            f"({round(100 * depois.pico.carga / cap)}% da capacidade)"
        )

    if ap.violacoes:
        return Tentativa(numero=numero, ok=False, proposta=proposta, erro=" ".join(erros[:3])), None

    sem_fila, com_fila = curvas_aplicadas(unidade, data, ap)
    pico = com_fila.pico
    if pico.carga > cap:
        erros.append(
            f"A carga recalculada às {h_br(pico.hora)} fica em {n_br(pico.carga)}, acima da capacidade de "
            f"{n_br(cap)}: o horário coincide com {_causa(unidade, ap.eventos_dia, pico.hora, ap.opcoes)}."
        )
    if erros:
        return Tentativa(numero=numero, ok=False, proposta=proposta, erro=" ".join(erros[:3]), pico=pico), com_fila

    checagens = [
        "Vencimento e provas mantidos na data e no horário",
        "Nenhuma ação cai em feriado ou fim de semana",
        "Nenhuma ação conflita com prova online",
        "Nenhuma carga foi empurrada para outro dia crítico",
    ]
    checagens += [c[:1].upper() + c[1:] for c in destinos_ok]
    texto_pico = (
        f"Pico recalculado {n_br(pico.carga)} às {h_br(pico.hora)} ({round(100 * pico.carga / cap)}% da capacidade)"
    )
    if ap.janelas_fila:
        excesso = max(
            (p.carga - cap for p in sem_fila.pontos if _dentro(p.hora, ap.janelas_fila) and p.carga > cap), default=0
        )
        if excesso > 0:
            faixas = " e ".join(f"das {h_br(i)} às {h_br(f)}" for i, f in ap.janelas_fila)
            texto_pico += f", com a fila virtual segurando até {n_br(excesso)} acessos acima da capacidade {faixas}"
    checagens.append(texto_pico)
    return Tentativa(numero=numero, ok=True, proposta=proposta, checagens=checagens, pico=pico), com_fila


def validar(unidade: str, data: str, plano: Plano, *, numero: int = 1, proposta: str | None = None) -> Tentativa:
    return _validar(unidade, data, plano, numero, proposta)[0]


# ---------- planejador por regras ----------


def _lotes_notas(
    ev: Evento, destino: str, inicio_min: int, lotes: int, intervalo: int, alunos_ref: int
) -> list[Evento]:
    total = ev.alunos if ev.alunos is not None else alunos_ref
    return [
        ev.model_copy(
            update={
                "data": destino,
                "hora_inicio": _hhmm(inicio_min + k * intervalo),
                "alunos": round(total / lotes),
                "descricao": f"{ev.descricao} · lote {k + 1}/{lotes}",
                "fonte": "plano",
            }
        )
        for k in range(lotes)
    ]


def _melhor_destino_notas(
    unidade: str, data: str, ev: Evento, lotes: int = 4, intervalo: int = 90
) -> tuple[str, str] | None:
    """Próximo dia útil que não é crítico, no horário comercial de menor carga, sem encostar em prova."""
    m = servico.motor()
    cap = contexto.unidade(unidade).capacidade
    alunos_ref = m.calibracao(unidade).alunos
    d = data
    for _ in range(10):
        d = proximo_dia_util(d)
        antes = m.curva(unidade, d, observado={})
        if antes.nivel in ("critico", "serio"):
            continue
        provas = _janelas_prova(antes.eventos)
        melhor = None
        for inicio in range(9 * 60, 15 * 60 + 1, 30):
            novos = _lotes_notas(ev, d, inicio, lotes, intervalo, alunos_ref)
            if any(
                _sobrepoe(carga.minutos(n.hora_inicio), carga.minutos(n.hora_inicio) + IMPACTO_NOTAS_MIN, a, b)
                for n in novos
                for a, b, _ in provas
            ):
                continue
            depois = m.curva(unidade, d, eventos=antes.eventos + novos, observado={})
            if depois.pico.carga >= 0.8 * cap:
                continue
            if melhor is None or depois.pico.carga < melhor[0]:
                melhor = (depois.pico.carga, inicio)
        if melhor:
            return d, _hhmm(melhor[1])
    return None


def _janelas_acima(unidade: str, data: str, acoes: list[Acao]) -> list[tuple[str, str]]:
    """Trechos ainda acima da capacidade depois das ações de calendário (30 min de antecedência)."""
    ap = aplicar_acoes(unidade, data, acoes)
    sem_fila, _ = curvas_aplicadas(unidade, data, ap)
    trechos = []
    for j in janelas(sem_fila.pontos, sem_fila.capacidade, limiar=1.0):
        ini = _hhmm(carga.minutos(j.inicio) - 30)
        if trechos and ini <= trechos[-1][1]:
            trechos[-1] = (trechos[-1][0], j.fim)
        else:
            trechos.append((ini, j.fim))
    return trechos


def _candidatos(unidade: str, data: str, sem: CurvaDia) -> list[list[Acao]]:
    evs = sem.eventos
    calendario: list[Acao] = []
    sem_notas: list[Acao] = []
    venc = next((e for e in evs if e.tipo == "vencimento"), None)
    if venc is not None:
        a = Acao(tipo="escalonar_lembretes", evento=venc.descricao, grupos=3)
        calendario.append(a)
        sem_notas.append(a)
    if sem.razao >= 0.8:
        for ev in (e for e in evs if e.tipo == "notas"):
            destino = _melhor_destino_notas(unidade, data, ev)
            if destino:
                calendario.append(
                    Acao(
                        tipo="mover_notas",
                        evento=ev.descricao,
                        para_data=destino[0],
                        para_hora=destino[1],
                        lotes=4,
                        intervalo_min=90,
                    )
                )
    for ev in (e for e in evs if e.tipo == "rematricula"):
        a = Acao(tipo="rematricula_em_ondas", evento=ev.descricao, grupos=3, intervalo_min=120)
        calendario.append(a)
        sem_notas.append(a)
    # Checklist só quando o dia pede: escala a partir de 80% da capacidade, congelamento a partir de 60%.
    infra = ([Acao(tipo="escalar_infra")] if sem.razao >= 0.8 else []) + (
        [Acao(tipo="congelar_deploys")] if sem.razao >= 0.6 else []
    )

    def com_fila(base: list[Acao]) -> list[Acao]:
        fila = [Acao(tipo="fila_virtual", inicio=i, fim=f) for i, f in _janelas_acima(unidade, data, base)]
        return base + fila + infra

    lista: list[list[Acao]] = []
    if calendario:
        lista.append(calendario + infra)  # 1) só calendário e comunicação
    lista.append(com_fila(calendario))  # 2) + fila virtual no que sobrar acima da capacidade
    if sem_notas != calendario:
        lista.append(com_fila(sem_notas))  # 3) sem mexer nas notas, fila segura o resto
    unicos: list[list[Acao]] = []
    for c in lista:
        if c not in unicos:
            unicos.append(c)
    return unicos


def _escolher(candidatos: list[list[Acao]], restantes: int) -> list[list[Acao]]:
    if restantes >= len(candidatos):
        return candidatos
    if restantes == 1:
        return [candidatos[1] if len(candidatos) > 1 else candidatos[0]]
    return candidatos[:restantes]


# ---------- textos do plano (template no tom de previa.js) ----------


def _montar_plano(unidade: str, data: str, sem: CurvaDia, acoes: list[Acao]) -> Plano:
    uni = contexto.unidade(unidade)
    cap = uni.capacidade
    evs = sem.eventos
    calendario: list[ItemPlano] = []
    comunicacao: list[ItemPlano] = []
    infra: list[ItemPlano] = []

    for a in acoes:
        if a.tipo == "mover_notas":
            lotes, intervalo = a.lotes or 1, a.intervalo_min or 90
            destino = a.para_data or data
            ev = _achar(evs, a.evento, ("notas",))
            nome = _nome_curto(ev.descricao) if ev else "Notas"
            inicio = carga.minutos(a.para_hora or (ev.hora_inicio if ev else "09:00"))
            if lotes > 1:
                horarios = ", ".join(
                    f"{AREAS[k % len(AREAS)]} às {h_br(_hhmm(inicio + k * intervalo))}" for k in range(lotes)
                )
                dia_txt = "no dia seguinte" if destino == proximo_dia_util(data) else f"em {dm(destino)}"
                calendario.append(
                    ItemPlano(
                        titulo=f"{nome} em {lotes} lotes {dia_txt}",
                        detalhe=f"{dm(destino)}: {horarios}. Nenhum lote encosta em prova online nem em dia crítico.",
                    )
                )
            else:
                calendario.append(
                    ItemPlano(
                        titulo=f"{nome} às {h_br(_hhmm(inicio))} de {dm(destino)}",
                        detalhe="Fora das janelas de pico do portal.",
                    )
                )
            comunicacao.append(
                ItemPlano(
                    titulo="Aviso das notas por curso",
                    detalhe=f"Avisar em {dm(data)} que as notas saem em {dm(destino)}, por curso, nos horários do calendário.",
                )
            )
        elif a.tipo == "rematricula_em_ondas":
            grupos, intervalo = a.grupos or 3, a.intervalo_min or 120
            ev = _achar(evs, a.evento, ("rematricula",))
            inicio = carga.minutos(a.para_hora or (ev.hora_inicio if ev else "09:00"))
            ondas = [h_br(_hhmm(inicio + k * intervalo)) for k in range(grupos)]
            calendario.append(
                ItemPlano(
                    titulo=f"Rematrícula em {grupos} ondas por período",
                    detalhe=f"{dm(a.para_data or data)}: ondas às {', '.join(ondas[:-1])} e {ondas[-1]} (1º–3º, 4º–6º e 7º período em diante).",
                )
            )
            comunicacao.append(
                ItemPlano(
                    titulo="Horário da onda de cada período",
                    detalhe=f"Mandar a cada período o horário da sua onda em {dm(dia_util_anterior(data))}, com o link direto da rematrícula.",
                )
            )
        elif a.tipo == "escalonar_lembretes":
            ev = _achar(evs, a.evento, ("vencimento",))
            nome = _minusculo(ev.descricao) if ev else "vencimento"
            grupos = a.grupos or 3
            tamanho = uni.alunos / grupos
            agendas = [
                (dia_util_anterior(data, 5), "10h", "quem costuma pagar cedo"),
                (dia_util_anterior(data, 2), "12h", "com Pix e boleto no corpo da mensagem"),
                (dia_util_anterior(data, 1), "9h", f"para quem paga no dia. O vencimento continua {dm(data)}"),
            ]
            for k in range(min(grupos, 3)):
                qtd = (
                    round(tamanho / 100) * 100
                    if k < grupos - 1
                    else uni.alunos - round(tamanho / 100) * 100 * (grupos - 1)
                )
                d, h, extra = agendas[k]
                comunicacao.append(
                    ItemPlano(
                        titulo=f"Grupo {'ABC'[k]} · {n_br(qtd)} alunos",
                        detalhe=f"Lembrete do {nome} em {dm(d)} às {h} ({extra}).",
                    )
                )

    for ev in (e for e in evs if e.tipo == "prova_online"):
        comunicacao.append(
            ItemPlano(
                titulo=f"Turmas de {ev.descricao}",
                detalhe=f"Aviso em {dm(dia_util_anterior(data))}: a prova abre às {h_br(ev.hora_inicio)}, não recarregue a página e use a fila se ela aparecer.",
            )
        )

    if not calendario:
        calendario.append(
            ItemPlano(
                titulo="Calendário mantido",
                detalhe="Vencimento e provas não mudam de data nem de horário; o ajuste fica na comunicação e na infraestrutura.",
            )
        )
    if not comunicacao:
        comunicacao.append(
            ItemPlano(
                titulo="Aviso preventivo",
                detalhe=f"Lembrete em {dm(dia_util_anterior(data))} com os horários de pico previstos e o link da página de status.",
            )
        )

    # Infraestrutura: horários tirados da curva sem plano (o pior caso).
    altas = janelas(sem.pontos, cap, limiar=0.8)
    filas = [(a.inicio or "00:00", a.fim or "23:59") for a in acoes if a.tipo == "fila_virtual"]
    if altas:
        primeiro, ultimo = altas[0], altas[-1]
        escalar = _hhmm(carga.minutos(primeiro.inicio) - 60)
        fim_min = carga.minutos(ultimo.fim) + 30
        desfazer = "0h30 do dia seguinte" if ultimo.fim == "23:59" or fim_min >= 24 * 60 else h_br(_hhmm(fim_min))
        infra.append(
            ItemPlano(
                titulo=f"Escalar o portal até {h_br(escalar)} de {dm(data)}",
                detalhe=(
                    f"O primeiro trecho acima de 80% começa às {h_br(primeiro.inicio)}; o pico previsto sem plano é "
                    f"{n_br(sem.pico.carga)} às {h_br(sem.pico.hora)}. Escala desfeita às {desfazer}."
                ),
            )
        )
    else:
        infra.append(
            ItemPlano(
                titulo="Sem escala extra",
                detalhe=f"Pico previsto de {n_br(sem.pico.carga)} às {h_br(sem.pico.hora)} ({round(100 * sem.razao)}% da capacidade).",
            )
        )
    if any(a.tipo == "congelar_deploys" for a in acoes) or altas:
        infra.append(
            ItemPlano(
                titulo="Congelar deploys e manutenções",
                detalhe=f"De {dm(_somar_dias(data, -2))} a {dm(_somar_dias(data, 1))}.",
            )
        )
    if filas:
        trechos = []
        for ini, fim in filas:
            # O motivo citado é o evento mais pesado do trecho: prova > rematrícula > notas > vencimento.
            peso = {"prova_online": 0, "rematricula": 1, "notas": 2, "vencimento": 3}
            motivos = sorted(
                (
                    e
                    for e in evs
                    if e.tipo in peso
                    and _sobrepoe(
                        carga.minutos(ini),
                        carga.minutos(fim),
                        carga.minutos(e.hora_inicio),
                        carga.minutos(e.hora_fim) + 1,
                    )
                ),
                key=lambda e: peso[e.tipo],
            )
            sufixo = f" ({motivos[0].descricao})" if motivos else ""
            trechos.append(f"das {h_br(ini)} às {h_br(fim)}{sufixo}")
        infra.append(ItemPlano(titulo="Fila virtual de login", detalhe="Ligada " + " e ".join(trechos) + "."))
    else:
        infra.append(
            ItemPlano(
                titulo="Fila virtual de prontidão", detalhe="Pronta para ligar se a carga passar de 80% da capacidade."
            )
        )
    if altas:
        ini = _hhmm(carga.minutos(altas[0].inicio) - 60)
        fim_min = carga.minutos(altas[-1].fim) + 60
        fim = "0h" if fim_min >= 24 * 60 else h_br(_hhmm(fim_min))
        infra.append(
            ItemPlano(
                titulo="Plantão de TI e atendimento",
                detalhe=f"Das {h_br(ini)} às {fim}, com o comunicado de crise pré-aprovado.",
            )
        )
    else:
        infra.append(ItemPlano(titulo="Plantão padrão", detalhe="Equipe de sobreaviso no horário comercial."))
    return Plano(calendario=calendario, comunicacao=comunicacao, infra_checklist=infra, acoes=acoes)


# ---------- Gemini ----------


class AcaoIA(BaseModel):
    tipo: str = Field(
        description="mover_notas | escalonar_lembretes | fila_virtual | escalar_infra | rematricula_em_ondas | congelar_deploys"
    )
    evento: str | None = Field(default=None, description="Descrição do evento alvo, copiada dos FATOS")
    para_data: str | None = Field(default=None, description="AAAA-MM-DD")
    para_hora: str | None = Field(default=None, description="HH:MM")
    lotes: int | None = None
    intervalo_min: int | None = None
    inicio: str | None = Field(default=None, description="HH:MM (fila virtual)")
    fim: str | None = Field(default=None, description="HH:MM (fila virtual)")
    grupos: int | None = None


class PlanoIA(BaseModel):
    proposta: str = Field(description="Uma frase com o resumo do plano")
    calendario: list[ItemPlano]
    comunicacao: list[ItemPlano]
    infra_checklist: list[ItemPlano]
    acoes: list[AcaoIA]


SISTEMA_PLANO = """Você é o planejador de capacidade do portal acadêmico. Recebe FATOS em JSON calculados pelo código:
eventos do dia, curva prevista de acessos simultâneos (janelas de 15 min), capacidade, feriados e dias críticos vizinhos.
Proponha um plano em 3 níveis (calendario, comunicacao, infra_checklist) e as ACOES executáveis que o validador vai
aplicar sobre o calendário e recalcular. Regras:
- Vencimento e provas NUNCA mudam de data nem de horário.
- Ações permitidas: mover_notas (evento, para_data, para_hora, lotes, intervalo_min), escalonar_lembretes (evento de
  vencimento; lembretes em grupos nos dias anteriores), rematricula_em_ondas (evento, grupos, intervalo_min),
  fila_virtual (inicio, fim: prende a concorrência na capacidade nesse trecho), escalar_infra, congelar_deploys.
- Não leve carga para feriado, fim de semana, prova online (nem 2 h antes dela) ou dia crítico/alto.
- Você não calcula carga: não invente números de acesso. Datas AAAA-MM-DD, horas HH:MM, textos curtos em PT-BR no tom de
  runbook de operação (título até 60 caracteres, detalhe com datas dd/mm e horários).
- Se houver tentativa anterior reprovada, corrija exatamente o motivo informado pelo validador."""

ACOES_PERMITIDAS = {
    "mover_notas": "move a divulgação de notas (pode dividir em lotes espaçados por intervalo_min)",
    "escalonar_lembretes": "lembretes do vencimento em grupos antes do dia; reduz a concentração noturna de pagamentos",
    "rematricula_em_ondas": "abre a rematrícula em ondas por período, espaçadas por intervalo_min",
    "fila_virtual": "fila de login que segura a concorrência na capacidade entre inicio e fim",
    "escalar_infra": "aumenta a capacidade de atendimento antes do pico (checklist)",
    "congelar_deploys": "congela deploys e manutenções em volta do dia (checklist)",
}


def _fatos(unidade: str, data: str, sem: CurvaDia, tentativas: list[Tentativa]) -> dict:
    m = servico.motor()
    uni = contexto.unidade(unidade)
    por_hora = {}
    for i in range(0, len(sem.pontos), 4):
        bloco = sem.pontos[i : i + 4]
        por_hora[bloco[0].hora] = max(p.carga for p in bloco)
    vizinhos = [
        {"data": r.data, "pico": r.pico, "hora": r.hora, "nivel": r.nivel, "eventos": r.eventos}
        for r in m.resumo(unidade, _somar_dias(data, -7), _somar_dias(data, 7))
        if r.data != data and r.nivel in ("serio", "critico")
    ]
    uteis, d = [], data
    for _ in range(6):
        d = proximo_dia_util(d)
        uteis.append(d)
    return {
        "instituicao": contexto.instituicao(),
        "unidade": {"id": uni.id, "nome": uni.nome, "alunos": uni.alunos, "capacidade": uni.capacidade},
        "dia": data,
        "dia_semana": SEMANA[date.fromisoformat(data).weekday()],
        "eventos_do_dia": [
            {
                "descricao": e.descricao,
                "tipo": e.tipo,
                "hora_inicio": e.hora_inicio,
                "hora_fim": e.hora_fim,
                "turmas": len(e.turmas),
            }
            for e in sem.eventos
        ],
        "curva_sem_plano": {
            "pico": sem.pico.model_dump(),
            "razao_capacidade": sem.razao,
            "janelas_acima_de_60pct": [j.model_dump() for j in sem.janelas],
            "maximo_por_hora": por_hora,
        },
        "feriados_proximos": [f.model_dump() for f in contexto.feriados(_somar_dias(data, -14), _somar_dias(data, 21))],
        "proximos_dias_uteis": uteis,
        "dias_criticos_vizinhos": vizinhos,
        "tentativas_reprovadas": [
            {"numero": t.numero, "proposta": t.proposta, "erro": t.erro} for t in tentativas if not t.ok
        ],
        "acoes_permitidas": ACOES_PERMITIDAS,
    }


def _converter(pia: PlanoIA) -> tuple[list[Acao], list[str]]:
    acoes, invalidas = [], []
    for a in pia.acoes:
        try:
            acoes.append(Acao.model_validate(a.model_dump(exclude_none=True)))
        except ValidationError as e:
            campos = ", ".join(str(err["loc"][0]) for err in e.errors() if err.get("loc"))
            invalidas.append(f"Ação “{a.tipo}” inválida ({campos or 'formato'}).")
    return acoes, invalidas


def _pedir_ia(unidade: str, data: str, sem: CurvaDia, tentativas: list[Tentativa], numero: int) -> PlanoIA | None:
    fatos = _fatos(unidade, data, sem, tentativas)
    prompt = "FATOS (calculados pelo código):\n" + json.dumps(fatos, ensure_ascii=False) + "\n\nProponha o plano."
    resp = servico.ia().gerar(
        "gerar_plano",
        prompt,
        schema=PlanoIA,
        sistema=SISTEMA_PLANO,
        temperatura=0.3,
        detalhe=f"response_schema PlanoIA · tentativa {numero} · temperature 0.3",
    )
    return resp.objeto if resp else None


# ---------- orquestração ----------


def _registrar(etapa: str, detalhe: str, ok: bool = True, modelo: str | None = "regras") -> None:
    servico.ia().registrar(etapa, detalhe, modelo=modelo, ok=ok)


def planejar(unidade: str, data: str, usar_ia: bool = True) -> ResultadoPlano:
    m = servico.motor()
    ia = servico.ia()
    sem = m.curva(unidade, data, observado={})
    tentativas: list[Tentativa] = []
    aprovado: tuple[Plano, CurvaDia] | None = None
    origem = "regras"

    if usar_ia and ia.disponivel:
        # Gemini tem até 2 tentativas com o erro do validador de volta; a 3ª, se preciso, é das regras
        # (garante um plano aprovado dentro do limite de 3).
        for numero in (1, 2):
            pia = _pedir_ia(unidade, data, sem, tentativas, numero)
            if pia is None:
                break
            acoes, invalidas = _converter(pia)
            plano = Plano(
                calendario=pia.calendario, comunicacao=pia.comunicacao, infra_checklist=pia.infra_checklist, acoes=acoes
            )
            if invalidas:
                t, com = Tentativa(numero=numero, ok=False, proposta=pia.proposta, erro=" ".join(invalidas)), None
            else:
                t, com = _validar(unidade, data, plano, numero, pia.proposta)
            tentativas.append(t)
            _registrar(
                "validar_plano",
                f"tentativa {numero} do Gemini {'aprovada' if t.ok else 'reprovada'}"
                + (f" · pico {n_br(t.pico.carga)} às {t.pico.hora}" if t.pico else ""),
                ok=t.ok,
                modelo=ia.modelo,
            )
            if t.ok and com is not None:
                # Níveis vazios no texto do Gemini são completados pelo template.
                base = _montar_plano(unidade, data, sem, acoes)
                plano.calendario = plano.calendario or base.calendario
                plano.comunicacao = plano.comunicacao or base.comunicacao
                plano.infra_checklist = plano.infra_checklist or base.infra_checklist
                aprovado, origem = (plano, com), "gemini"
                break

    if aprovado is None:
        candidatos = _escolher(_candidatos(unidade, data, sem), 3 - len(tentativas))
        _registrar("gerar_plano", f"planejador determinístico · {len(candidatos)} candidato(s) para {dm(data)}")
        for acoes in candidatos:
            plano = _montar_plano(unidade, data, sem, acoes)
            numero = len(tentativas) + 1
            t, com = _validar(unidade, data, plano, numero)
            tentativas.append(t)
            _registrar(
                "validar_plano",
                f"tentativa {numero} {'aprovada' if t.ok else 'reprovada'}"
                + (f" · pico {n_br(t.pico.carga)} às {t.pico.hora}" if t.pico else ""),
                ok=t.ok,
            )
            if t.ok and com is not None:
                aprovado = (plano, com)
                break

    resultado = ResultadoPlano(
        data=data,
        plano=aprovado[0] if aprovado else None,
        tentativas=tentativas,
        pico_sem=sem.pico,
        pico_com=aprovado[1].pico if aprovado else None,
        pontos_com=aprovado[1].pontos if aprovado else None,
        capacidade=sem.capacidade,
        origem=origem,
    )
    servico.armazem().kv_set(f"plano:{unidade}:{data}", resultado.model_dump(mode="json"))
    return resultado


def obter_plano(unidade: str, data: str) -> ResultadoPlano:
    """Plano em cache (o último gerado, inclusive pelo Gemini) ou o das regras, sem chamar IA.
    Se a curva do dia mudou desde o cache (novos dados), o plano é refeito."""
    guardado = servico.armazem().kv_get(f"plano:{unidade}:{data}")
    if guardado is not None:
        try:
            r = ResultadoPlano.model_validate(guardado)
            if r.pico_sem == servico.motor().curva(unidade, data, observado={}).pico:
                return r
        except ValidationError:
            pass
    return planejar(unidade, data, usar_ia=False)
