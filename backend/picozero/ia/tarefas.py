# backend/picozero/ia/tarefas.py
# O que o Gemini faz no PicoZero. Regra de ouro: o Gemini lê, classifica, explica e escreve;
# números de carga, picos e horários vêm sempre do código (motor/). Cada tarefa tem fallback
# por regras, então a API responde igual com ou sem chave, só muda o campo `origem`.
import json
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field

from .. import contexto, servico
from ..dominio import (
    DATA,
    ORDEM_NIVEL,
    ROTULO_NIVEL,
    DiaRisco,
    DicasManutencao,
    Evento,
    Pico,
    TarefaManutencao,
    TipoEvento,
)
from ..motor import manutencao
from ..fmt import ddmmaaaa, decimal, inteiro
from .gemini import parte_arquivo

TIPOS_TXT = (
    "prova_online (provas/avaliações/testes online: AP1, AP2, AS, Teste de Progresso), "
    "vencimento (mensalidade/parcela/boleto), notas (divulgação de notas/resultados), "
    "rematricula (renovação de matrícula, ajuste de disciplinas), outro (início/fim de período, vestibular, eventos)"
)

# ---------- modelos que o Gemini preenche (strings simples: o schema do Gemini é mais restrito) ----------


class EventoIA(BaseModel):
    data: str = Field(description="AAAA-MM-DD")
    hora_inicio: str = Field(description="HH:MM; use o padrão do tipo se o texto não disser")
    hora_fim: str = Field(description="HH:MM")
    tipo: TipoEvento
    descricao: str
    turmas: list[str] = Field(default_factory=list)


class MapeamentoIA(BaseModel):
    ts: str | None = Field(default=None, description="coluna com data e hora juntas")
    data: str | None = Field(default=None, description="coluna só com a data (se separada)")
    hora: str | None = Field(default=None, description="coluna só com a hora (se separada)")
    valor: str | None = Field(default=None, description="coluna numérica de carga/acessos")
    agregacao: str | None = Field(default=None, description="max para sessões/usuários ativos; soma para contagens")
    fuso: str | None = Field(default=None, description="UTC ou America/Sao_Paulo")
    metrica: str | None = Field(default=None, description="o que a coluna de valor mede, em poucas palavras")
    descricao: str | None = Field(default=None, description="coluna de descrição, se for um calendário de eventos")
    tipo: str | None = Field(default=None, description="coluna de tipo de evento, se houver")


class DiaRiscoIA(BaseModel):
    data: str = Field(description="AAAA-MM-DD, um dos dias candidatos")
    gravidade: int = Field(description="1 a 5")
    eventos: list[str]
    motivo: str = Field(description="2 a 3 frases, cite horários e o histórico consultado")
    consultados: list[str] = Field(default_factory=list, description="datas AAAA-MM-DD do histórico que você consultou")


class DicasIA(BaseModel):
    resumo: str
    tarefas: list[TarefaManutencao]
    nao_fazer: list[str]


PADRAO_HORA = {
    "vencimento": ("00:00", "23:59"),
    "notas": ("14:00", "23:59"),
    "prova_online": ("19:00", "21:00"),
    "rematricula": ("09:00", "23:59"),
    "outro": ("08:00", "22:00"),
}


def _evento_valido(e: EventoIA, fonte: str) -> Evento | None:
    import re

    if not re.match(DATA, e.data or ""):
        return None
    ini, fim = PADRAO_HORA[e.tipo]
    hi = e.hora_inicio if re.match(r"^([01]\d|2[0-3]):[0-5]\d$", e.hora_inicio or "") else ini
    hf = e.hora_fim if re.match(r"^([01]\d|2[0-3]):[0-5]\d$", e.hora_fim or "") else fim
    if hf <= hi:
        hf = fim if fim > hi else "23:59"
    try:
        date.fromisoformat(e.data)
        return Evento(data=e.data, hora_inicio=hi, hora_fim=hf, tipo=e.tipo, descricao=e.descricao[:300] or "Evento",
                      turmas=e.turmas[:60], fonte=fonte)
    except ValueError:
        return None


# ---------- assistente da ingestão (contrato ingestao.AssistenteIA) ----------


class AssistenteIngestao:
    """Ajuda a ingestão quando as regras não bastam: mapeia colunas desconhecidas e lê documentos."""

    @property
    def disponivel(self) -> bool:
        return servico.ia().disponivel

    def mapear_colunas(self, cabecalho: list[str], amostra: list[list[str]], dica: str | None) -> dict[str, str] | None:
        linhas = "\n".join(" | ".join(map(str, l)) for l in amostra[:8])
        prompt = (
            "Você recebe o cabeçalho e linhas de amostra de uma planilha exportada de um sistema de monitoramento "
            "(Kibana, Grafana, APM, logs) ou de um calendário acadêmico. Diga quais colunas usar. "
            f"Dica do usuário: {dica or 'nenhuma'}.\nCabeçalho: {cabecalho}\nAmostra:\n{linhas}"
        )
        r = servico.ia().gerar("mapear_colunas", prompt, schema=MapeamentoIA, temperatura=0,
                               detalhe=f"response_schema MapeamentoIA · {len(cabecalho)} colunas")
        if r is None:
            return None
        validas = set(cabecalho)
        out = {k: v for k, v in r.objeto.model_dump().items() if v}
        for k in ("ts", "data", "hora", "valor", "descricao", "tipo"):
            if k in out and out[k] not in validas:
                out.pop(k)
        return out or None

    def extrair_eventos(self, conteudo: bytes | str, mime: str, dica: str | None) -> list[Evento] | None:
        sem = contexto.semestre()
        sistema = (
            "Você extrai eventos de calendário acadêmico que geram acesso em massa ao portal do aluno. "
            f"Tipos: {TIPOS_TXT}. Semestre de referência {sem['nome']} ({sem['inicio']} a {sem['fim']}); "
            "datas sem ano: escolha o ano que deixa a data dentro ou perto desse semestre. "
            "Horários padrão quando o texto não disser: vencimento 00:00–23:59, notas 14:00–23:59, "
            "prova_online 19:00–21:00, rematricula 09:00–23:59, outro 08:00–22:00. "
            "Períodos (de X a Y): gere um evento no primeiro dia e outro no último, dizendo isso na descrição. "
            "Ignore feriados (eles já são conhecidos). Descrição curta em português. Não invente eventos."
        )
        if isinstance(conteudo, bytes) and not mime.startswith("text/"):
            partes = [parte_arquivo(conteudo, mime), f"Extraia os eventos deste arquivo. Dica: {dica or 'nenhuma'}"]
        else:
            texto = conteudo.decode("utf-8", "replace") if isinstance(conteudo, bytes) else conteudo
            partes = f"Extraia os eventos deste texto. Dica: {dica or 'nenhuma'}\n\n{texto[:60000]}"
        r = servico.ia().gerar("extrair_eventos", partes, schema=list[EventoIA], sistema=sistema, temperatura=0,
                               detalhe=f"response_schema list[Evento] · {mime}")
        if r is None:
            return None
        eventos = [ev for e in r.objeto if (ev := _evento_valido(e, f"gemini:{r.modelo}"))]
        return eventos


ASSISTENTE = AssistenteIngestao()

# ---------- histórico consultável (ferramentas do Gemini e do MCP) ----------


def periodos_academicos() -> list[dict]:
    """Períodos do calendário (AP1, AP2, AS, rematrícula…) de todos os semestres, do mais antigo ao mais novo."""
    marcos = [*contexto.historico_eventos().get("marcos", []), *contexto.calendario_atual()["marcos"]]
    vistos = set()
    saida = []
    for m in sorted(marcos, key=lambda m: m["inicio"]):
        chave = (m["inicio"], m["nome"])
        if chave not in vistos:
            vistos.add(chave)
            saida.append({"nome": m["nome"], "inicio": m["inicio"], "fim": m["fim"], "tipo": m.get("tipo", "outro")})
    return saida


def picos_historicos(unidade: str, inicio: str, fim: str, quantos: int = 5) -> dict:
    """Maiores picos registrados no histórico entre duas datas (inclusive), com os eventos de cada dia."""
    try:
        a, b = date.fromisoformat(inicio), date.fromisoformat(fim)
    except ValueError:
        return {"erro": f"datas inválidas: {inicio}, {fim}", "resumo": "datas inválidas"}
    if b < a:
        a, b = b, a
    m = servico.motor()
    por_dia: dict[str, tuple[float, str, str]] = {}
    for ts, valor, origem in servico.armazem().serie(unidade, a.isoformat(), (b + timedelta(days=1)).isoformat()):
        d = ts[:10]
        if d not in por_dia or valor > por_dia[d][0]:
            por_dia[d] = (valor, ts[11:16], origem)
    dias = servico.armazem().dias_com_dados(unidade)
    base = {"inicio": a.isoformat(), "fim": b.isoformat(), "historico_de": dias[0] if dias else None,
            "historico_ate": dias[-1] if dias else None}
    if not por_dia:
        return {**base, "tem_dados": False, "resumo": f"sem histórico entre {a.isoformat()} e {b.isoformat()}"}
    cap = contexto.unidade(unidade).capacidade
    eventos = m.eventos_por_dia(unidade)

    def item(d: str) -> dict:
        valor, hora, _ = por_dia[d]
        return {"data": d, "pico_real": round(valor), "hora": hora, "pct_capacidade": round(valor / cap * 100),
                "eventos": [f"{e.hora_inicio} {e.descricao}" for e in eventos.get(d, [])]}

    maiores = [item(d) for d in sorted(por_dia, key=lambda d: -por_dia[d][0])[: max(1, min(int(quantos), 20))]]
    origens = sorted({o for _, _, o in por_dia.values()})
    topo = maiores[0]
    saida = {
        **base, "tem_dados": True, "dias_com_dados": len(por_dia), "capacidade": cap,
        # 'modelo' = histórico simulado pela semente; 'real'/'ingerido' = dados enviados pela ingestão.
        "origem_dados": origens, "maiores": maiores,
        "resumo": f"maior pico real entre {a.isoformat()} e {b.isoformat()}: {topo['pico_real']} em {topo['data']} "
                  f"às {topo['hora']} (origem: {', '.join(origens)})",
    }
    if len(por_dia) <= 31:
        saida["por_dia"] = [item(d) for d in sorted(por_dia)]
    return saida


def consultar_historico(unidade: str, data: str) -> dict:
    """Pico observado num dia do histórico, com os eventos daquele dia."""
    try:
        date.fromisoformat(data)
    except ValueError:
        return {"erro": f"data inválida: {data}", "resumo": "data inválida"}
    m = servico.motor()
    c = m.curva(unidade, data)
    if c.pico_real is None:
        return {"data": data, "tem_dados": False, "resumo": f"{data}: sem dados no histórico"}
    evs = [f"{e.hora_inicio} {e.descricao}" for e in c.eventos]
    resumo = f"{data}: pico real {c.pico_real.carga} às {c.pico_real.hora}"
    if evs:
        resumo += " · " + "; ".join(evs)
    return {
        "data": data,
        "tem_dados": True,
        "tipo_dia": c.tipo_dia,
        "pico_real": c.pico_real.carga,
        "hora_pico_real": c.pico_real.hora,
        "capacidade": c.capacidade,
        "eventos": evs,
        "resumo": resumo,
    }


def _dominante(evs: list[Evento]) -> str | None:
    return max(evs, key=lambda e: ORDEM_TIPO.get(e.tipo, 0)).tipo if evs else None


def dias_semelhantes(unidade: str, tipo: str, antes_de: str | None = None, limite: int = 6,
                     turmas: int | None = None) -> list[dict]:
    """Dias do histórico em que `tipo` foi o gatilho dominante, com o pico observado.
    Ordena pelo tamanho parecido (nº de turmas, para provas) e depois pelo mais recente."""
    m = servico.motor()
    corte = antes_de or contexto.agora().date().isoformat()
    candidatos = []
    for d, evs in m.eventos_por_dia(unidade).items():
        if d >= corte or _dominante(evs) != tipo:
            continue
        n = sum(len(e.turmas) for e in evs if e.tipo == tipo)
        dist = abs(n - turmas) if turmas is not None else 0
        candidatos.append((dist, -date.fromisoformat(d).toordinal(), d))
    saida = []
    for _, _, d in sorted(candidatos):
        h = consultar_historico(unidade, d)
        if h.get("tem_dados"):
            saida.append(h)
        if len(saida) >= limite:
            break
    return saida


# ---------- dias de risco ----------


def _candidatos(unidade: str) -> list[dict]:
    m = servico.motor()
    sem = contexto.semestre()
    saida = []
    for r in m.resumo(unidade, sem["inicio"], sem["fim"]):
        if not r.eventos and ORDEM_NIVEL[r.nivel] < ORDEM_NIVEL["alerta"]:
            continue
        c = m.curva(unidade, r.data)
        saida.append({
            "data": r.data,
            "dia_semana": ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"][date.fromisoformat(r.data).weekday()],
            "eventos": [f"{e.hora_inicio}–{e.hora_fim} [{e.tipo}] {e.descricao}" + (f" ({len(e.turmas)} turmas)" if e.turmas else "")
                        for e in c.eventos],
            "pico_previsto": c.pico.carga,
            "hora_pico": c.pico.hora,
            "capacidade": c.capacidade,
            "razao": c.razao,
            "janelas": [f"{j.inicio}–{j.fim} máx {j.max}" for j in c.janelas],
            "nivel": c.nivel,
            "_curva": c,
        })
    return saida


def _gravidade_regras(c: dict) -> int:
    r = c["razao"]
    g = 5 if r >= 1.4 else 4 if r >= 1.0 else 3 if r >= 0.8 else 2 if r >= 0.5 else 1
    tipos = {e.tipo for e in c["_curva"].eventos}
    if len(tipos) >= 3 and g < 5:
        g += 1
    return g


def _gatilho_txt(e: Evento) -> str:
    if e.tipo == "vencimento":
        return f"{e.descricao} (pagamentos concentrados entre 20h e 23h59)"
    turmas = f", {len(e.turmas)} turmas" if e.turmas else ""
    return f"{e.descricao} às {e.hora_inicio}{turmas}"


def _motivo_regras(unidade: str, c: dict) -> tuple[str, list[str]]:
    curva = c["_curva"]
    evs = curva.eventos
    texto = ""
    if len(evs) >= 2:
        texto = f"{len(evs)} gatilhos no mesmo dia: " + "; ".join(_gatilho_txt(e) for e in evs[:4]) + ". "
    elif evs:
        texto = _gatilho_txt(evs[0]) + ". "
    texto += (f"Pico calculado de {inteiro(c['pico_previsto'])} às {c['hora_pico']} "
              f"({decimal(c['razao'])}× a capacidade de {c['capacidade']})")
    consultados = []
    tipo = _dominante(evs)
    if tipo:
        turmas = sum(len(e.turmas) for e in evs if e.tipo == tipo) if tipo == "prova_online" else None
        sem = dias_semelhantes(unidade, tipo, antes_de=c["data"], limite=2, turmas=turmas)
        if sem:
            consultados = [s["data"] for s in sem]
            refs = ", ".join(f"{ddmmaaaa(s['data'])} ({inteiro(s['pico_real'])} às {s['hora_pico_real']})" for s in sem)
            texto += f". No histórico, dias com o mesmo gatilho dominante chegaram a {refs}"
    return texto + ".", consultados


ORDEM_TIPO = {"prova_online": 4, "rematricula": 3, "notas": 2, "vencimento": 1, "outro": 0}


def riscos_por_regras(unidade: str) -> list[DiaRisco]:
    saida = []
    for c in _candidatos(unidade):
        g = _gravidade_regras(c)
        if g < 2:
            continue
        motivo, consultados = _motivo_regras(unidade, c)
        saida.append(DiaRisco(
            data=c["data"], gravidade=g, eventos=[e.descricao for e in c["_curva"].eventos] or ["Uso orgânico"],
            motivo=motivo, consultados=consultados, pico=c["_curva"].pico, nivel=c["nivel"], origem="regras",
        ))
    saida.sort(key=lambda d: (-d.gravidade, d.data))
    return saida


def analisar_riscos(unidade: str, usar_ia: bool = True) -> list[DiaRisco]:
    """Gemini decide quais dias do histórico consultar (function calling) e escreve gravidade e motivo."""
    ia = servico.ia()
    candidatos = _candidatos(unidade)
    if not usar_ia or not ia.disponivel or not candidatos:
        res = riscos_por_regras(unidade)
        ia.registrar("analisar_riscos", f"regras determinísticas · {len(res)} dias", modelo="regras")
        servico.armazem().kv_set(f"riscos:{unidade}", [r.model_dump(mode="json") for r in res])
        return res

    def ferramenta_consultar_historico(data: str) -> dict:
        """Consulta o pico real de um dia do histórico de acesso do portal (data no formato AAAA-MM-DD)."""
        return consultar_historico(unidade, data)

    def ferramenta_dias_semelhantes(tipo: str, antes_de: str) -> list[dict]:
        """Lista dias do histórico com eventos do mesmo tipo (prova_online, vencimento, notas, rematricula, outro)
        anteriores a antes_de (AAAA-MM-DD), com o pico real de cada um."""
        return dias_semelhantes(unidade, tipo, antes_de=antes_de, limite=4)

    ferramenta_consultar_historico.__name__ = "consultar_historico"
    ferramenta_dias_semelhantes.__name__ = "dias_semelhantes"
    fatos = [{k: v for k, v in c.items() if k != "_curva"} for c in candidatos]
    sistema = (
        "Você é analista de capacidade do portal do aluno. Para cada dia candidato, avalie o risco de o portal "
        "não aguentar o acesso. Use as ferramentas para consultar dias parecidos do histórico ANTES de concluir "
        "(consulte pelo menos 3 dias no total). Os picos e horários dos candidatos foram calculados pelo código: "
        "use-os como estão, não recalcule. Gravidade: 5 = muito acima da capacidade com gatilhos somados; "
        "4 = acima da capacidade; 3 = perto do limite; 2 = atenção; 1 = tranquilo. "
        "Explique o motivo em português simples, citando horários dos gatilhos e o que o histórico mostrou. "
        "Não afirme queda, lentidão ou falha do sistema: as ferramentas só informam picos e eventos. "
        "Datas no texto em dd/mm/aaaa."
    )
    analise = ia.gerar(
        "analisar_riscos",
        "Dias candidatos (JSON):\n" + json.dumps(fatos, ensure_ascii=False),
        sistema=sistema,
        ferramentas=[ferramenta_consultar_historico, ferramenta_dias_semelhantes],
        temperatura=0.2,
        detalhe="tools=[consultar_historico, dias_semelhantes] · temperature 0.2",
    )
    if analise is None:
        return analisar_riscos(unidade, usar_ia=False)
    formatado = ia.gerar(
        "formatar_riscos",
        "Transforme a análise abaixo na lista de dias de risco (só dias com gravidade ≥ 2, use apenas datas "
        "dos candidatos).\n\nCANDIDATOS:\n" + json.dumps(fatos, ensure_ascii=False) + "\n\nANÁLISE:\n" + analise.texto,
        schema=list[DiaRiscoIA],
        temperatura=0,
        usar_cache=False,
        detalhe="response_schema list[DiaRisco]",
    )
    if formatado is None:
        return analisar_riscos(unidade, usar_ia=False)
    por_data = {c["data"]: c for c in candidatos}
    consultaveis = {d for d in servico.armazem().dias_com_dados(unidade)}
    saida = []
    for d in formatado.objeto:
        c = por_data.get(d.data)
        if not c:
            continue
        # Só vale como "consultado" o que existe no histórico (o modelo não inventa referência).
        consultados = list(dict.fromkeys(x for x in d.consultados if x in consultaveis))
        saida.append(DiaRisco(
            data=d.data, gravidade=max(1, min(5, d.gravidade)), eventos=d.eventos or [e.descricao for e in c["_curva"].eventos],
            motivo=d.motivo, consultados=consultados, pico=c["_curva"].pico, nivel=c["nivel"], origem="gemini",
        ))
    if not saida:
        return analisar_riscos(unidade, usar_ia=False)
    saida.sort(key=lambda r: (-r.gravidade, r.data))
    servico.armazem().kv_set(f"riscos:{unidade}", [r.model_dump(mode="json") for r in saida])
    return saida


def riscos(unidade: str) -> list[DiaRisco]:
    """Último resultado salvo (Gemini ou regras); calcula por regras na primeira vez."""
    salvo = servico.armazem().kv_get(f"riscos:{unidade}")
    if salvo:
        return [DiaRisco.model_validate(r) for r in salvo]
    return analisar_riscos(unidade, usar_ia=False)


# ---------- dicas de manutenção ----------


def dicas(unidade: str, data: str, usar_ia: bool = False, agora: datetime | None = None) -> DicasManutencao:
    """Regras sempre; com usar_ia o Gemini reescreve resumo/tarefas para a equipe (horários continuam os do código)."""
    m = servico.motor()
    c = m.curva(unidade, data, agora=agora)
    base = manutencao.gerar(c)
    chave = f"dicas:{unidade}:{data}"
    if not usar_ia:
        salvo = servico.armazem().kv_get(chave)
        if salvo and salvo.get("pico", {}).get("carga") == base.pico.carga:
            return DicasManutencao.model_validate(salvo)
        return base
    ia = servico.ia()
    fatos = base.model_dump(mode="json")
    fatos["eventos"] = [f"{e.hora_inicio}–{e.hora_fim} [{e.tipo}] {e.descricao}" for e in c.eventos]
    fatos["janelas_de_pico"] = [f"{j.inicio}–{j.fim} máx {j.max} ({j.nivel})" for j in c.janelas]
    sistema = (
        "Você é o líder de SRE de uma universidade e escreve o plano de manutenção do dia para a equipe "
        "(infra, banco, aplicação, pagamentos, atendimento). Use SOMENTE os horários e números dos fatos. "
        "Priorize o que evita queda no pico; seja específico e prático (o que fazer, quando, quem). "
        "Máximo 10 tarefas, frases curtas, português do Brasil. Mantenha a janela de manutenção, o congelamento "
        "e o horário de escalar exatamente como nos fatos."
    )
    r = ia.gerar("dicas_manutencao", "Fatos do dia (JSON):\n" + json.dumps(fatos, ensure_ascii=False),
                 schema=DicasIA, sistema=sistema, temperatura=0.3, detalhe=f"response_schema DicasManutencao · {data}")
    if r is None or len(r.objeto.tarefas) < 3:
        return base
    final = base.model_copy(update={
        "resumo": r.objeto.resumo,
        "tarefas": r.objeto.tarefas[:12],
        "nao_fazer": r.objeto.nao_fazer[:8] or base.nao_fazer,
        "origem": "gemini",
        "modelo": r.modelo,
    })
    servico.armazem().kv_set(chave, final.model_dump(mode="json"))
    return final


def proximos_dias_criticos(unidade: str, agora: datetime, dias: int = 7) -> list[dict]:
    m = servico.motor()
    ini = agora.date().isoformat()
    fim = (agora.date() + timedelta(days=dias)).isoformat()
    return [
        {**r.model_dump(), "rotulo": ROTULO_NIVEL[r.nivel], "acima_da_capacidade": r.nivel == "critico"}
        for r in m.resumo(unidade, ini, fim, agora=agora)
        if ORDEM_NIVEL[r.nivel] >= ORDEM_NIVEL["alerta"]
    ]


def pico_resumo(p: Pico) -> str:
    return f"{p.carga} às {p.hora}"
