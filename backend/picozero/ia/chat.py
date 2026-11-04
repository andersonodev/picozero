# backend/picozero/ia/chat.py
# Copiloto de operação: a equipe pergunta em português ("qual o pico de quinta?", "o que fazer amanhã?")
# e o Gemini responde chamando as mesmas funções do motor (function calling). Sem IA, um roteador
# por palavras-chave responde com os mesmos dados.
import re
from datetime import date, datetime, timedelta

from google.genai import types

from .. import contexto, servico
from ..dominio import ORDEM_NIVEL, PedidoChat, RegistroTrilha, RespostaChat
from ..fmt import ddmm, decimal, inteiro
from ..motor import alertas as alertas_mod
from . import tarefas

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


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

    def eventos_no_periodo(inicio: str, fim: str) -> list[dict]:
        """Eventos do calendário acadêmico entre duas datas (AAAA-MM-DD)."""
        return [e.model_dump(exclude={"fonte", "alunos"}) for e in servico.armazem().eventos(
            m._unidade_eventos(unidade), inicio, fim)][:40]

    def desempenho_do_modelo() -> dict:
        """Erro do modelo fora da amostra (backtest) e fatores aprendidos por tipo de evento."""
        return m.backtest(unidade)

    return [previsao_do_dia, proximos_picos, alertas_ativos, dicas_de_manutencao, consultar_historico,
            eventos_no_periodo, desempenho_do_modelo]


def responder(pedido: PedidoChat) -> RespostaChat:
    agora = contexto.ler_agora(pedido.agora)
    unidade = contexto.unidade(pedido.unidade).id
    ia = servico.ia()
    if ia.disponivel:
        uni = contexto.unidade(unidade)
        sistema = (
            f"Você é o PicoZero, copiloto de capacidade do portal do aluno ({contexto.instituicao()} {uni.nome}, "
            f"{inteiro(uni.alunos)} alunos, capacidade {uni.capacidade} acessos simultâneos). "
            f"Agora é {DIAS[agora.weekday()]}, {agora:%d/%m/%Y %H:%M}. Responda em português do Brasil, curto e "
            "operacional (o que acontece, quando, o que fazer). Use as ferramentas para QUALQUER número: nunca "
            "estime carga, horário ou data de cabeça. Converta 'amanhã', 'quinta' etc. para AAAA-MM-DD antes de chamar."
        )
        conteudo = [
            types.Content(role="user" if m.papel == "usuario" else "model", parts=[types.Part(text=m.texto)])
            for m in pedido.mensagens
        ]
        r = ia.gerar("chat", conteudo, sistema=sistema, ferramentas=_ferramentas(unidade, agora), temperatura=0.3,
                     usar_cache=False, detalhe=f"copiloto · {len(pedido.mensagens)} mensagens", max_chamadas=6)
        if r is not None and r.texto.strip():
            trilha = [_reg(c["nome"], c["args"]) for c in r.chamadas]
            return RespostaChat(resposta=r.texto.strip(), ferramentas=trilha, origem="gemini", modelo=r.modelo)
    return _por_regras(pedido.mensagens[-1].texto, unidade, agora)


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
