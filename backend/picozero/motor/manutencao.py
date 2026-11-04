# backend/picozero/motor/manutencao.py
# Dicas de manutenção do dia para a equipe, calculadas da curva prevista:
# melhor janela de manutenção (menor carga), congelamento de deploys em volta das janelas de pico,
# até quando escalar e um checklist por tipo de evento. O Gemini só reescreve/prioriza (ia/tarefas.py);
# os horários sempre vêm daqui.
from datetime import date

from ..dominio import ORDEM_NIVEL, CurvaDia, DicasManutencao, Janela, TarefaManutencao
from ..fmt import decimal, inteiro
from . import carga
from .previsao import nivel_da_razao

DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _hhmm(minutos_: int) -> str:
    minutos_ = max(0, min(minutos_, 24 * 60 - 1))
    return f"{minutos_ // 60:02d}:{minutos_ % 60:02d}"


def janela_manutencao(c: CurvaDia, horas: int = 2) -> Janela:
    """Bloco contíguo de menor carga máxima, preferindo a madrugada (00h–07h)."""
    tam = horas * 4
    melhor = None
    for ini in range(0, carga.JANELAS - tam + 1):
        trecho = c.pontos[ini : ini + tam]
        pior = max(p.carga for p in trecho)
        penal = 0 if ini < 7 * 4 else 0.15 * pior  # fora da madrugada só se for bem melhor
        nota = pior + penal
        if melhor is None or nota < melhor[0]:
            melhor = (nota, ini, pior, max(trecho, key=lambda p: p.carga).hora)
    _, ini, pior, hora_max = melhor
    return Janela(
        inicio=carga.hora_da_janela(ini),
        fim=_hhmm((ini + tam) * 15),
        max=pior,
        hora_max=hora_max,
        nivel=nivel_da_razao(pior / c.capacidade),
    )


def congelamentos(c: CurvaDia) -> list[Janela]:
    """Sem deploy de 2 h antes até 1 h depois de cada janela alta/crítica (janelas próximas se fundem)."""
    trechos: list[list] = []
    for j in c.janelas:
        if ORDEM_NIVEL[j.nivel] < ORDEM_NIVEL["serio"]:
            continue
        ini = carga.minutos(j.inicio) - 120
        fim = carga.minutos(j.fim) + 60
        if trechos and ini <= trechos[-1][1]:
            trechos[-1][1] = max(trechos[-1][1], fim)
            trechos[-1][2] = max(trechos[-1][2], j, key=lambda x: x.max)
        else:
            trechos.append([ini, fim, j])
    return [
        Janela(inicio=_hhmm(a), fim=_hhmm(b), max=j.max, hora_max=j.hora_max, nivel=j.nivel) for a, b, j in trechos
    ]


def escalar_ate(c: CurvaDia) -> str | None:
    for j in c.janelas:
        if ORDEM_NIVEL[j.nivel] >= ORDEM_NIVEL["serio"]:
            return _hhmm(carga.minutos(j.inicio) - 60)
    return None


def _tarefas_evento(c: CurvaDia, escalar: str | None) -> list[TarefaManutencao]:
    t: list[TarefaManutencao] = []
    vistos: set[str] = set()
    for ev in c.eventos:
        ini, fim = ev.hora_inicio, ev.hora_fim
        antes = _hhmm(carga.minutos(ini) - 60)
        if ev.tipo == "vencimento" and "vencimento" not in vistos:
            t += [
                TarefaManutencao(
                    horario="até 12:00", prioridade="alta", area="pagamentos",
                    titulo="Testar Pix, boleto e 2ª via de ponta a ponta",
                    detalhe="Gerar um boleto e um Pix de teste e confirmar a baixa; checar certificado e limite de chamadas da API do banco antes da reta final da noite.",
                    responsavel="Financeiro + TI",
                ),
                TarefaManutencao(
                    horario="20:00–00:30", prioridade="media", area="banco",
                    titulo="Pool de conexões do financeiro reforçado",
                    detalhe="A concentração de pagamentos é entre 20h e 23h59; subir o pool e acompanhar filas de webhook do banco.",
                    responsavel="DBA",
                ),
            ]
        elif ev.tipo == "prova_online":
            t += [
                TarefaManutencao(
                    horario=f"até {antes}", prioridade="alta", area="aplicacao",
                    titulo=f"Pré-aquecer o ambiente de provas ({ev.descricao})",
                    detalhe=f"Subir instâncias extras e carregar as provas em cache antes das {ini}; testar login e salvamento automático com um aluno de teste.",
                    responsavel="TI Acadêmico",
                ),
                TarefaManutencao(
                    horario=f"{_hhmm(carga.minutos(ini) - 30)}–{fim}", prioridade="alta", area="infra",
                    titulo="Fila virtual de login ligada",
                    detalhe=f"A entrada em massa acontece nos primeiros 15 min ({len(ev.turmas) or 'várias'} turmas). Quem espera vê a posição em vez de erro 503.",
                    responsavel="SRE",
                ),
            ]
        elif ev.tipo == "notas" and "notas" not in vistos:
            t.append(
                TarefaManutencao(
                    horario=f"até {ini}", prioridade="media", area="aplicacao",
                    titulo="Cachear boletins e liberar notas em lotes",
                    detalhe="Pré-gerar as páginas de notas e liberar por curso a cada 30–60 min; o salto após a divulgação dura cerca de 2 h.",
                    responsavel="TI Acadêmico + Secretaria",
                )
            )
        elif ev.tipo == "rematricula" and "rematricula" not in vistos:
            t.append(
                TarefaManutencao(
                    horario=f"{ini}–{_hhmm(carga.minutos(ini) + 180)}", prioridade="alta", area="banco",
                    titulo="Vigiar travas (locks) no banco de matrícula",
                    detalhe="As primeiras 3 h concentram a base inteira; acompanhar locks, índices e tempo das transações de matrícula.",
                    responsavel="DBA",
                )
            )
        elif ev.tipo == "outro" and "outro" not in vistos:
            t.append(
                TarefaManutencao(
                    horario=f"até {antes}", prioridade="baixa", area="seguranca",
                    titulo="Checar login/SSO e reset de senha",
                    detalhe=f"{ev.descricao}: picos de primeiro acesso e de senha esquecida.",
                    responsavel="TI",
                )
            )
        vistos.add(ev.tipo)
    return t


def gerar(c: CurvaDia) -> DicasManutencao:
    """Dicas por regras (sem IA). Também são os fatos que o Gemini recebe para reescrever."""
    janela = janela_manutencao(c)
    congela = congelamentos(c)
    escalar = escalar_ate(c)
    critico = ORDEM_NIVEL[c.nivel] >= ORDEM_NIVEL["serio"]
    tarefas: list[TarefaManutencao] = []

    tarefas.append(
        TarefaManutencao(
            horario=f"{janela.inicio}–{janela.fim}", prioridade="media" if critico else "baixa", area="infra",
            titulo="Janela de manutenção recomendada",
            detalhe=f"Menor carga prevista do dia (até {inteiro(janela.max)} acessos). Concentre aqui backups, rotação de logs, reindexação e patches.",
            responsavel="SRE",
        )
    )
    if escalar:
        tarefas.append(
            TarefaManutencao(
                horario=f"até {escalar}", prioridade="alta", area="infra",
                titulo="Escalar o portal antes da primeira janela de pico",
                detalhe=f"Pico previsto de {inteiro(c.pico.carga)} às {c.pico.hora} ({decimal(c.razao)}× a capacidade de {c.capacidade}). Desfazer a escala 1 h depois da última janela.",
                responsavel="SRE",
            )
        )
    for z in congela:
        tarefas.append(
            TarefaManutencao(
                horario=f"{z.inicio}–{z.fim}", prioridade="alta", area="aplicacao",
                titulo="Congelar deploys e mudanças",
                detalhe=f"Janela de risco com pico de {inteiro(z.max)} às {z.hora_max}: nada de deploy, migração ou job pesado.",
                responsavel="Líder de TI",
            )
        )
    tarefas += _tarefas_evento(c, escalar)
    if critico:
        ini = congela[0].inicio if congela else escalar or "08:00"
        fim = congela[-1].fim if congela else "23:59"
        tarefas += [
            TarefaManutencao(
                horario=f"{ini}–{fim}", prioridade="alta", area="atendimento",
                titulo="Plantão de TI e atendimento com o comunicado de crise pronto",
                detalhe="Comunicado pré-aprovado (prazo estendido e tolerância) para publicar em minutos se o portal oscilar.",
                responsavel="Atendimento + Comunicação",
            ),
            TarefaManutencao(
                horario="durante as janelas", prioridade="media", area="observabilidade",
                titulo="Alarmes de p95 e 503 com limiar apertado",
                detalhe="SLO de capacidade: p95 < 400 ms e 503 < 0,5%. Acompanhar a cada 5 min no pico.",
                responsavel="SRE",
            ),
        ]
    tarefas.append(
        TarefaManutencao(
            horario="dia seguinte", prioridade="baixa", area="observabilidade",
            titulo="Comparar previsto × real",
            detalhe="Enviar as métricas do dia ao PicoZero (CSV, webhook ou MCP); o modelo recalibra os fatores por tipo de evento sozinho.",
            responsavel="SRE",
        )
    )

    nao_fazer = []
    for z in congela:
        nao_fazer.append(f"Deploy, migração de banco ou reinício de serviço entre {z.inicio} e {z.fim}")
    if critico:
        nao_fazer += [
            "Backup full, reindexação ou ETL pesado durante as janelas de pico",
            "Disparo de e-mail/push em massa durante o pico (puxa ainda mais acessos)",
        ]
    tipos = {e.tipo for e in c.eventos}
    if "prova_online" in tipos and "notas" in tipos:
        nao_fazer.append("Liberar notas enquanto a prova online estiver aberta")
    if not nao_fazer:
        nao_fazer.append("Nada bloqueado: dia dentro da capacidade, manutenção pode seguir a agenda normal")

    dia = date.fromisoformat(c.data)
    resumo = (
        f"{DIAS_SEMANA[dia.weekday()].capitalize()}, {c.data[8:10]}/{c.data[5:7]}: pico previsto de {inteiro(c.pico.carga)} "
        f"às {c.pico.hora} ({decimal(c.razao)}× a capacidade de {c.capacidade}). "
    )
    if critico:
        resumo += f"Manutenção só em {janela.inicio}–{janela.fim}"
        resumo += f"; congelar deploys {', '.join(f'{z.inicio}–{z.fim}' for z in congela)}" if congela else ""
        resumo += f"; escalar o portal até {escalar}." if escalar else "."
    else:
        resumo += f"Dia tranquilo: melhor janela de manutenção {janela.inicio}–{janela.fim}."
    if c.feriado:
        resumo += f" Feriado: {c.feriado}."

    ordem = {"alta": 0, "media": 1, "baixa": 2}
    tarefas.sort(key=lambda x: ordem[x.prioridade])
    return DicasManutencao(
        data=c.data,
        unidade=c.unidade,
        nivel=c.nivel,
        resumo=resumo,
        pico=c.pico,
        janela_manutencao=janela,
        congelamento=congela,
        escalar_ate=escalar,
        tarefas=tarefas,
        nao_fazer=nao_fazer,
        origem="regras",
    )
