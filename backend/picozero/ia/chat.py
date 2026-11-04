# backend/picozero/ia/chat.py
# Copiloto de operação: a equipe pergunta em português ("qual o pico de quinta?", "o que fazer amanhã?")
# e o Gemini responde chamando as mesmas funções do motor (function calling). Sem IA, um roteador
# por palavras-chave responde com os mesmos dados.
import re
import time
from datetime import date, datetime, timedelta

from google.genai import types

from .. import contexto, servico
from ..dominio import ORDEM_NIVEL, PedidoChat, RegistroTrilha, RespostaChat
from ..fmt import ddmm, decimal, inteiro
from ..config import CONFIG
from ..motor import alertas as alertas_mod
from . import tarefas
from .conferencia import conferir, montar_base

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
# O painel espera até 60 s; o chat inteiro (resposta + uma correção) cabe em 50.
PRAZO_CHAT_S = 50.0
# Perguntas de "maior/pior pico" ou de um período: só valem respostas que varreram o período inteiro.
_PEDE_RANKING = re.compile(r"maior|pior|mais (alto|cheio|pesado|cr[ií]tico)|recorde|ranking|semana d|per[ií]odo|\bap ?[12]\b|\bas\b|substitutiv|rematr|renova", re.I)
_FERRAMENTAS_DE_PERIODO = {"picos_historicos", "picos_previstos"}


def _ferramentas(unidade: str, agora: datetime) -> list:
    m = servico.motor()

    def previsao_do_dia(data: str) -> dict:
        """Previsão de carga de um dia (AAAA-MM-DD): pico, horário, janelas de pico, nível e eventos."""
        c = m.curva(unidade, data, agora=agora)
        return {
            "data": data, "pico": c.pico.carga, "hora_pico": c.pico.hora, "capacidade": c.capacidade,
            "razao": c.razao, "nivel": c.rotulo, "janelas": [f"{j.inicio}–{j.fim} (máx {j.max})" for j in c.janelas],
            "eventos": [f"{e.hora_inicio} {e.descricao}" for e in c.eventos], "feriado": c.feriado, "periodo": c.periodo,
            "real_ate_agora": c.pico_real.carga if c.pico_real else None,
        }

    def proximos_picos(dias: int) -> list[dict]:
        """Dias com risco (≥ 60% da capacidade) nos próximos `dias` dias a partir de hoje."""
        return tarefas.proximos_dias_criticos(unidade, agora, max(1, min(int(dias), 60)))

    def alertas_ativos() -> list[dict]:
        """Alertas antecipados ativos agora (nível, estágio, horário do pico, ações recomendadas)."""
        return [
            {k: a.model_dump()[k] for k in ("titulo", "nivel", "estagio", "data", "inicio", "fim", "pico", "acoes")}
            for a in alertas_mod.avaliar(m, unidade, agora)
        ]

    def dicas_de_manutencao(data: str) -> dict:
        """Plano de manutenção do dia para a equipe: janela de manutenção, congelamento, escala e tarefas."""
        d = tarefas.dicas(unidade, data, agora=agora)
        return {
            "resumo": d.resumo,
            "janela_manutencao": f"{d.janela_manutencao.inicio}–{d.janela_manutencao.fim}" if d.janela_manutencao else None,
            "congelar": [f"{z.inicio}–{z.fim}" for z in d.congelamento], "escalar_ate": d.escalar_ate,
            "tarefas": [f"[{t.prioridade}] {t.horario} · {t.titulo} ({t.responsavel})" for t in d.tarefas],
            "nao_fazer": d.nao_fazer,
        }

    def consultar_historico(data: str) -> dict:
        """Pico real observado num dia passado (AAAA-MM-DD) e os eventos daquele dia."""
        return tarefas.consultar_historico(unidade, data)

    def picos_historicos(inicio: str, fim: str, quantos: int = 5) -> dict:
        """Maiores picos REGISTRADOS no histórico entre duas datas AAAA-MM-DD (inclusive), já ordenados do maior
        para o menor, com hora, % da capacidade e eventos do dia. Use para "maior pico de 2026", "semana da AP1",
        "pior dia do mês" etc. Para até 31 dias devolve também `por_dia`."""
        return tarefas.picos_historicos(unidade, inicio, fim, quantos)

    def picos_previstos(inicio: str, fim: str, quantos: int = 5) -> dict:
        """Maiores picos PREVISTOS pelo motor entre duas datas AAAA-MM-DD (inclusive), do maior para o menor."""
        try:
            dias = m.resumo(unidade, inicio, fim, agora=agora)
        except Exception as e:  # noqa: BLE001 - data inválida volta como erro para o modelo
            return {"erro": str(e)[:120]}
        top = sorted(dias, key=lambda r: -r.pico)[: max(1, min(int(quantos), 20))]
        return {"inicio": inicio, "fim": fim, "capacidade": contexto.unidade(unidade).capacidade,
                "maiores": [{"data": r.data, "pico_previsto": r.pico, "hora": r.hora, "razao": r.razao,
                             "nivel": r.nivel, "eventos": r.eventos} for r in top]}

    def periodos_academicos() -> list[dict]:
        """Datas de início e fim de AP1, AP2, AS, rematrícula etc. de todos os semestres (2025.2 em diante)."""
        return tarefas.periodos_academicos()

    def eventos_no_periodo(inicio: str, fim: str) -> list[dict]:
        """Eventos do calendário acadêmico entre duas datas (AAAA-MM-DD)."""
        return [e.model_dump(exclude={"fonte", "alunos"}) for e in servico.armazem().eventos(
            m._unidade_eventos(unidade), inicio, fim)][:40]

    def desempenho_do_modelo() -> dict:
        """Erro do modelo fora da amostra (backtest) e fatores aprendidos por tipo de evento."""
        return m.backtest(unidade)

    return [previsao_do_dia, proximos_picos, alertas_ativos, dicas_de_manutencao, consultar_historico,
            picos_historicos, picos_previstos, periodos_academicos, eventos_no_periodo, desempenho_do_modelo]


def responder(pedido: PedidoChat) -> RespostaChat:
    agora = contexto.ler_agora(pedido.agora)
    unidade = contexto.unidade(pedido.unidade).id
    ia = servico.ia()
    if ia.disponivel:
        try:
            r = _responder_gemini(pedido, unidade, agora)
        except Exception as e:  # noqa: BLE001 - erro no copiloto não pode derrubar a rota: responde pelas regras
            ia.registrar("chat", f"erro no copiloto ({type(e).__name__}: {str(e)[:120]}): usando regras",
                         modelo="regras", ok=False)
            r = None
        if r is not None:
            return r
    return _por_regras(pedido.mensagens[-1].texto, unidade, agora)


def _responder_gemini(pedido: PedidoChat, unidade: str, agora: datetime) -> RespostaChat | None:
    """Gemini com conferência: números fora dos dados voltam para correção; se insistir, None (regras)."""
    ia = servico.ia()
    uni = contexto.unidade(unidade)
    hist = servico.armazem().dias_com_dados(unidade)
    sistema = (
        f"Você é o PicoZero, copiloto de capacidade do portal do aluno ({contexto.instituicao()} {uni.nome}, "
        f"{inteiro(uni.alunos)} alunos, capacidade {uni.capacidade} acessos simultâneos). "
        f"Agora é {DIAS[agora.weekday()]}, {agora:%d/%m/%Y %H:%M}. Responda em português do Brasil, curto e "
        "operacional (o que acontece, quando, o que fazer).\n"
        "REGRAS DE DADOS (obrigatórias):\n"
        "1. Todo número, data e horário da resposta precisa vir de uma ferramenta chamada NESTA resposta. Nunca "
        "estime, arredonde de cabeça nem complete com conhecimento geral. Se a ferramenta não tiver o dado, diga "
        "que não há esse dado na base.\n"
        f"2. Passado (até {ddmm(hist[-1]) if hist else 'hoje'}) é HISTÓRICO: use picos_historicos ou "
        "consultar_historico. Futuro é PREVISÃO: use picos_previstos ou previsao_do_dia. Diga qual dos dois é.\n"
        "3. 'Maior/pior pico', 'semana de…', 'em 2026', 'no mês': chame picos_historicos/picos_previstos com o "
        "período INTEIRO e use o primeiro item de `maiores`. Nunca escolha um dia por palpite.\n"
        "4. AP1, AP2, AS, rematrícula: chame periodos_academicos para achar as datas do semestre certo antes.\n"
        "5. Se `origem_dados` for 'modelo', avise que o histórico é simulado (ainda não há tráfego real ingerido).\n"
        "6. Nível exatamente como a ferramenta devolve: folga < 60% da capacidade, atenção 60–80%, alto 80–100%, "
        "crítico acima de 100%. Converta 'amanhã', 'quinta' etc. para AAAA-MM-DD antes de chamar."
    )
    conteudo = [
        types.Content(role="user" if m.papel == "usuario" else "model", parts=[types.Part(text=m.texto)])
        for m in pedido.mensagens
    ]
    pergunta = pedido.mensagens[-1].texto
    textos_usuario = [m.texto for m in pedido.mensagens if m.papel == "usuario"] + [sistema]
    ferramentas = _ferramentas(unidade, agora)
    inicio = time.perf_counter()
    resultados: list = []
    chamadas: list[dict] = []
    for tentativa in range(2):
        restante = PRAZO_CHAT_S - (time.perf_counter() - inicio)
        if restante < 8:
            break
        r = ia.gerar("chat", conteudo, sistema=sistema, ferramentas=ferramentas, temperatura=0.2, usar_cache=False,
                     detalhe=f"copiloto · {len(pedido.mensagens)} mensagens" + (" · correção" if tentativa else ""),
                     max_chamadas=8, prazo_s=restante, modelos=CONFIG.gemini_modelos_chat,
                     pensamento=pedido.raciocinio or CONFIG.gemini_pensamento_chat)
        if r is None or not r.texto.strip():
            return None
        resultados += r.resultados
        chamadas += r.chamadas
        conf = conferir(r.texto, montar_base(resultados, textos_usuario, uni.capacidade))
        usadas = {c["nome"] for c in chamadas}
        sem_periodo = bool(_PEDE_RANKING.search(pergunta)) and not (usadas & _FERRAMENTAS_DE_PERIODO)
        if conf.ok and not sem_periodo:
            ia.registrar("conferência", f"ok · {conf.conferidos} valores batem com as ferramentas", modelo=r.modelo)
            return RespostaChat(
                resposta=r.texto.strip(), ferramentas=[_reg(c["nome"], c["args"]) for c in chamadas],
                origem="gemini", modelo=r.modelo,
                dados={"conferencia": {"ok": True, "conferidos": conf.conferidos, "correcoes": tentativa}},
            )
        problemas = []
        if conf.suspeitos:
            problemas.append(f"estes valores não aparecem nos dados das ferramentas: {', '.join(conf.suspeitos[:12])}")
        if sem_periodo:
            problemas.append("a pergunta é sobre um período ou um 'maior pico', mas você não chamou picos_historicos "
                             "nem picos_previstos com o período inteiro")
        ia.registrar("conferência", "reprovada: " + "; ".join(problemas), modelo=r.modelo, ok=False)
        conteudo = [
            *conteudo,
            types.Content(role="model", parts=[types.Part(text=r.texto)]),
            types.Content(role="user", parts=[types.Part(text=(
                "[Conferência automática do PicoZero] Sua resposta foi reprovada: " + "; ".join(problemas) + ". "
                "Chame as ferramentas necessárias e refaça a resposta à minha pergunta anterior usando SOMENTE "
                "números, datas e horários devolvidos por elas. Não mencione esta conferência."
            ))]),
        ]
    ia.registrar("conferência", "Gemini não passou na conferência: respondendo pelas regras", modelo="regras", ok=False)
    return None


def _reg(nome: str, args: dict) -> RegistroTrilha:
    agora = datetime.now()
    return RegistroTrilha(hora=agora.strftime("%H:%M:%S"), quando=agora.isoformat(timespec="seconds"), etapa=nome,
                          detalhe=", ".join(f"{k}={v}" for k, v in args.items()), ferramenta=True)


# ---------- sem IA: roteador por palavras-chave ----------


def _data_citada(texto: str, agora: datetime) -> str | None:
    t = texto.lower()
    hoje = agora.date()
    if "depois de amanhã" in t:
        return (hoje + timedelta(days=2)).isoformat()
    if "amanhã" in t or "amanha" in t:
        return (hoje + timedelta(days=1)).isoformat()
    if "hoje" in t:
        return hoje.isoformat()
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        d, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
        a = int(ano) + (2000 if ano and len(ano) == 2 else 0) if ano else hoje.year
        try:
            return date(a, mes, d).isoformat()
        except ValueError:
            return None
    abreviados = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    for i, nome in enumerate(DIAS):
        # palavra inteira: "qual" não é "qua(rta)"
        if re.search(rf"\b({nome}|{nome.replace('ç', 'c').replace('á', 'a')}|{abreviados[i]})(-feira)?\b", t):
            delta = (i - hoje.weekday()) % 7 or 7
            return (hoje + timedelta(days=delta)).isoformat()
    return None


_SIGLAS_PERIODO = [
    (re.compile(r"\bap ?1\b"), lambda m: "AP1" in m["nome"]),
    (re.compile(r"\bap ?2\b"), lambda m: "AP2" in m["nome"]),
    (re.compile(r"\bas\b|substitutiv"), lambda m: "Substitutiva" in m["nome"]),
    (re.compile(r"rematr|renova"), lambda m: m["tipo"] == "rematricula"),
]


def _periodo_citado(t: str, agora: datetime) -> dict | None:
    """AP1, AP2, AS ou rematrícula citados na pergunta → o período do calendário (semestre citado ou o atual)."""
    filtro = next((f for rx, f in _SIGLAS_PERIODO if rx.search(t)), None)
    if filtro is None:
        return None
    candidatos = [p for p in tarefas.periodos_academicos() if filtro(p)]
    sem = re.search(r"\b(20\d\d)(?:\.([12]))?\b", t)
    if sem:
        ano, metade = sem.group(1), sem.group(2)
        candidatos = [p for p in candidatos if p["inicio"].startswith(ano)
                      and (not metade or (int(p["inicio"][5:7]) >= 7) == (metade == "2"))]
    if not candidatos:
        return None
    hoje = agora.date().isoformat()
    semestre = contexto.semestre()
    atuais = [p for p in candidatos if semestre["inicio"] <= p["inicio"] <= semestre["fim"]]
    if not sem and atuais:
        return atuais[0]
    passados = [p for p in candidatos if p["inicio"] <= hoje]
    return passados[-1] if passados else candidatos[0]


def _aviso_origem(h: dict) -> str:
    if "modelo" in h.get("origem_dados", []):
        return "\n\nAtenção: o histórico desta base é simulado (origem 'modelo'); ainda não há tráfego real ingerido."
    return ""


def _resposta_periodo(p: dict, unidade: str, agora: datetime, usadas: list[RegistroTrilha]) -> str:
    titulo = f"{p['nome']} ({ddmm(p['inicio'])} a {ddmm(p['fim'])}/{p['fim'][:4]})"
    if p["fim"] < agora.date().isoformat():
        h = tarefas.picos_historicos(unidade, p["inicio"], p["fim"])
        usadas.append(_reg("picos_historicos", {"inicio": p["inicio"], "fim": p["fim"]}))
        if not h.get("tem_dados"):
            return f"{titulo}: não há histórico desse período na base."
        topo = h["maiores"][0]
        return (f"{titulo} · histórico: maior pico de {inteiro(topo['pico_real'])} em {ddmm(topo['data'])} às "
                f"{topo['hora']} ({topo['pct_capacidade']}% da capacidade de {h['capacidade']}).\nPor dia: "
                + " · ".join(f"{ddmm(x['data'])} {inteiro(x['pico_real'])}" for x in h.get("por_dia", h["maiores"]))
                + _aviso_origem(h))
    m = servico.motor()
    dias = m.resumo(unidade, p["inicio"], p["fim"], agora=agora)
    usadas.append(_reg("picos_previstos", {"inicio": p["inicio"], "fim": p["fim"]}))
    topo = max(dias, key=lambda r: r.pico)
    return (f"{titulo} · previsão: maior pico de {inteiro(topo.pico)} em {ddmm(topo.data)} às {topo.hora} "
            f"({decimal(topo.razao)}× a capacidade).\nPor dia: "
            + " · ".join(f"{ddmm(r.data)} {inteiro(r.pico)}" for r in dias))


def _por_regras(texto: str, unidade: str, agora: datetime) -> RespostaChat:
    m = servico.motor()
    t = texto.lower()
    data = _data_citada(texto, agora)
    usadas: list[RegistroTrilha] = []
    if re.search(r"alert|avis", t):
        als = alertas_mod.avaliar(m, unidade, agora)
        usadas.append(_reg("alertas_ativos", {}))
        if not als:
            resp = "Nenhum alerta ativo nos próximos 14 dias: a previsão fica abaixo de 80% da capacidade."
        else:
            resp = f"{len(als)} alerta(s):\n" + "\n".join(f"• {a.titulo} — {a.acoes[0]}" for a in als[:6])
    elif re.search(r"manuten|dica|equipe|fazer|checklist|deploy", t):
        d = tarefas.dicas(unidade, data or agora.date().isoformat(), agora=agora)
        usadas.append(_reg("dicas_de_manutencao", {"data": d.data}))
        resp = d.resumo + "\n" + "\n".join(f"• [{x.prioridade}] {x.horario} — {x.titulo}" for x in d.tarefas[:6])
    elif (marco := _periodo_citado(t, agora)) is not None:
        resp = _resposta_periodo(marco, unidade, agora, usadas)
    elif (ano := re.search(r"\b(20\d\d)\b", t)) and re.search(r"pior|maior|recorde|mais (alto|cheio|pesado|cr[ií]tico)", t) and not data:
        h = tarefas.picos_historicos(unidade, f"{ano.group(1)}-01-01", f"{ano.group(1)}-12-31")
        usadas.append(_reg("picos_historicos", {"inicio": h["inicio"], "fim": h["fim"]}))
        if not h.get("tem_dados"):
            resp = f"Não há histórico de {ano.group(1)} na base."
        else:
            topo, resto = h["maiores"][0], h["maiores"][1:]
            resp = (f"Maior pico registrado em {ano.group(1)} (histórico até {ddmm(h['historico_ate'])}): "
                    f"{inteiro(topo['pico_real'])} em {ddmm(topo['data'])} às {topo['hora']} "
                    f"({topo['pct_capacidade']}% da capacidade de {h['capacidade']})"
                    + (f" · {'; '.join(topo['eventos'])}" if topo["eventos"] else "") + ".\nEm seguida: "
                    + "; ".join(f"{ddmm(x['data'])} ({inteiro(x['pico_real'])} às {x['hora']})" for x in resto) + "."
                    + _aviso_origem(h))
    elif re.search(r"pior|maior|mais (cr[ií]tico|cheio|pesado)|semestre|ranking", t) and not data:
        sem = contexto.semestre()
        dias = sorted(m.resumo(unidade, sem["inicio"], sem["fim"], agora=agora), key=lambda r: -r.pico)[:5]
        usadas.append(_reg("picos_do_semestre", {"inicio": sem["inicio"], "fim": sem["fim"]}))
        topo = dias[0]
        resp = (f"Pior dia do semestre: {DIAS[date.fromisoformat(topo.data).weekday()]}, {ddmm(topo.data)}, pico de "
                f"{inteiro(topo.pico)} às {topo.hora} ({decimal(topo.razao)}× a capacidade). Em seguida: "
                + "; ".join(f"{ddmm(r.data)} ({inteiro(r.pico)} às {r.hora})" for r in dias[1:]) + ".")
    elif re.search(r"semana|próxim|proxim|calend", t) and not data:
        dias = tarefas.proximos_dias_criticos(unidade, agora, 7)
        usadas.append(_reg("proximos_picos", {"dias": 7}))
        resp = ("Próximos 7 dias sem risco." if not dias else "Próximos dias de risco:\n" + "\n".join(
            f"• {ddmm(x['data'])}: pico {inteiro(x['pico'])} às {x['hora']} ({x['nivel']})" for x in dias))
    elif re.search(r"modelo|erro|precis|acert|backtest", t):
        b = m.backtest(unidade)
        usadas.append(_reg("desempenho_do_modelo", {}))
        resp = (f"Fora da amostra ({b['dias_avaliados']} dias de {contexto.semestre()['nome']}): erro médio de "
                f"{decimal(b['mape_pico'])}% no pico e {b['erro_mediano_hora_min']} min no horário. "
                f"Fatores aprendidos: {b['fatores_treino']}.")
    else:
        alvo = data or agora.date().isoformat()
        c = m.curva(unidade, alvo, agora=agora)
        usadas.append(_reg("previsao_do_dia", {"data": alvo}))
        jan = ", ".join(f"{j.inicio}–{j.fim}" for j in c.janelas if ORDEM_NIVEL[j.nivel] >= 1) or "nenhuma"
        resp = (f"{DIAS[date.fromisoformat(alvo).weekday()].capitalize()}, {ddmm(alvo)}: pico previsto de "
                f"{inteiro(c.pico.carga)} às {c.pico.hora} ({decimal(c.razao)}× a capacidade de {c.capacidade}), "
                f"nível {c.rotulo}. Janelas de pico: {jan}.")
        if c.eventos:
            resp += " Eventos: " + "; ".join(f"{e.hora_inicio} {e.descricao}" for e in c.eventos) + "."
    servico.ia().registrar("chat", "roteador por regras (sem Gemini)", modelo="regras")
    return RespostaChat(resposta=resp, ferramentas=usadas, origem="regras")
