# backend/picozero/dominio.py
# Modelos do domínio. O formato JSON é o mesmo de frontend/src/dados/previa.js:
# datas 'AAAA-MM-DD', horas 'HH:MM', níveis com as mesmas chaves das classes CSS do front.
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DATA = r"^\d{4}-\d{2}-\d{2}$"
HORA = r"^([01]\d|2[0-3]):[0-5]\d$"

TipoEvento = Literal["prova_online", "vencimento", "notas", "rematricula", "outro"]
# Mesmas chaves do front (tema.js / estilo.css): ok = folga, alerta = atenção, serio = alto, critico = crítico.
Nivel = Literal["ok", "alerta", "serio", "critico"]
Estagio = Literal["planejamento", "preparacao", "vespera", "iminente", "em_curso", "ao_vivo"]
OrigemIA = Literal["gemini", "regras"]

TIPOS: dict[str, str] = {
    "prova_online": "Prova online",
    "vencimento": "Vencimento",
    "notas": "Notas",
    "rematricula": "Rematrícula",
    "outro": "Acadêmico",
}
ROTULO_NIVEL: dict[str, str] = {"ok": "folga", "alerta": "atenção", "serio": "alto", "critico": "crítico"}
ORDEM_NIVEL: dict[str, int] = {"ok": 0, "alerta": 1, "serio": 2, "critico": 3}


# ---------- Contexto (white label: trocar o JSON troca a instituição) ----------


class Unidade(BaseModel):
    id: str
    nome: str
    curto: str
    alunos: int = Field(gt=0)
    capacidade: int = Field(gt=0)
    modelada: bool = False


class Feriado(BaseModel):
    data: str = Field(pattern=DATA)
    nome: str


class Marco(BaseModel):
    inicio: str = Field(pattern=DATA)
    fim: str = Field(pattern=DATA)
    nome: str
    tipo: TipoEvento = "outro"


class Contexto(BaseModel):
    instituicao: str
    semestre: str
    alunos: int
    capacidade: int
    inicio: str
    fim: str
    modelo: str
    feriados: list[Feriado]
    unidade: str
    ia: Literal["gemini", "fallback"]


# ---------- Entradas ----------


class Evento(BaseModel):
    data: str = Field(pattern=DATA)
    hora_inicio: str = Field(default="00:00", pattern=HORA)
    hora_fim: str = Field(default="23:59", pattern=HORA)
    tipo: TipoEvento = "outro"
    descricao: str = Field(min_length=1, max_length=300)
    turmas: list[str] = Field(default_factory=list)
    alunos: int | None = Field(default=None, ge=0, description="Alunos afetados; vazio = turmas × 60")
    fonte: str | None = None


class PontoMetrica(BaseModel):
    """Um ponto já normalizado: horário local (America/Sao_Paulo, sem fuso) alinhado em 15 min."""

    ts: datetime
    valor: float = Field(ge=0)
    metrica: str = "carga"


class ResultadoParse(BaseModel):
    """Saída de qualquer parser da ingestão, antes de gravar."""

    formato: str
    pontos: list[PontoMetrica] = Field(default_factory=list)
    eventos: list[Evento] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    mapeamento: dict[str, str] = Field(default_factory=dict)
    linhas_lidas: int = 0
    linhas_ignoradas: int = 0
    origem: OrigemIA = "regras"


class RelatorioIngestao(BaseModel):
    id: str
    quando: str
    canal: Literal["arquivo", "webhook", "mcp", "texto", "eventos", "metricas", "semente", "simulacao"]
    unidade: str
    formato: str
    arquivo: str | None = None
    linhas_lidas: int = 0
    pontos_inseridos: int = 0
    eventos_inseridos: int = 0
    ignorados: int = 0
    periodo: list[str] | None = None
    avisos: list[str] = Field(default_factory=list)
    mapeamento: dict[str, str] = Field(default_factory=dict)
    origem_parse: OrigemIA = "regras"
    duracao_ms: int = 0


# ---------- Curvas e picos ----------


class PontoCurva(BaseModel):
    hora: str
    carga: int
    p10: int | None = None
    p90: int | None = None
    real: int | None = None
    base: int | None = None


class Pico(BaseModel):
    hora: str
    carga: int


class Janela(BaseModel):
    inicio: str
    fim: str
    max: int
    hora_max: str
    nivel: Nivel


class CurvaDia(BaseModel):
    data: str
    unidade: str
    capacidade: int
    pontos: list[PontoCurva]
    pico: Pico
    pico_real: Pico | None = None
    janelas: list[Janela]
    nivel: Nivel
    rotulo: str
    razao: float
    eventos: list[Evento]
    feriado: str | None = None
    periodo: str | None = None
    tipo_dia: str
    fatores: dict[str, float]
    observado_ate: str | None = None
    ajuste_ao_vivo: float | None = None
    plano_aplicado: bool = False


class ResumoDia(BaseModel):
    data: str
    pico: int
    hora: str
    p90: int
    nivel: Nivel
    razao: float
    eventos: list[str]
    feriado: str | None = None
    real: int | None = None


# ---------- IA: riscos, plano, crise, manutenção ----------


class DiaRisco(BaseModel):
    data: str = Field(pattern=DATA)
    gravidade: int = Field(ge=1, le=5)
    eventos: list[str]
    motivo: str
    consultados: list[str] = Field(default_factory=list)
    pico: Pico | None = None
    nivel: Nivel = "ok"
    origem: OrigemIA = "regras"


class ItemPlano(BaseModel):
    titulo: str
    detalhe: str


class Acao(BaseModel):
    """Ação executável do plano: o validador recalcula a curva aplicando estas ações."""

    tipo: Literal[
        "mover_notas", "escalonar_lembretes", "fila_virtual", "escalar_infra", "rematricula_em_ondas", "congelar_deploys"
    ]
    evento: str | None = Field(default=None, description="Descrição do evento alvo")
    para_data: str | None = Field(default=None, pattern=DATA)
    para_hora: str | None = Field(default=None, pattern=HORA)
    lotes: int | None = Field(default=None, ge=1, le=12)
    intervalo_min: int | None = Field(default=None, ge=15, le=600)
    inicio: str | None = Field(default=None, pattern=HORA)
    fim: str | None = Field(default=None, pattern=HORA)
    grupos: int | None = Field(default=None, ge=1, le=10)


class Plano(BaseModel):
    calendario: list[ItemPlano] = Field(default_factory=list)
    comunicacao: list[ItemPlano] = Field(default_factory=list)
    infra_checklist: list[ItemPlano] = Field(default_factory=list)
    acoes: list[Acao] = Field(default_factory=list)


class Tentativa(BaseModel):
    numero: int
    ok: bool
    proposta: str
    erro: str | None = None
    checagens: list[str] | None = None
    pico: Pico | None = None


class ResultadoPlano(BaseModel):
    data: str
    plano: Plano | None
    tentativas: list[Tentativa]
    pico_sem: Pico
    pico_com: Pico | None = None
    pontos_com: list[PontoCurva] | None = None
    capacidade: int
    origem: OrigemIA = "regras"


class Comunicado(BaseModel):
    titulo: str
    mensagem: str
    nova_data_prazo: str = Field(pattern=DATA)
    regras_tolerancia: list[str]
    origem: OrigemIA = "regras"


class TarefaManutencao(BaseModel):
    horario: str = Field(description="Quando fazer, ex.: '02:00–04:00' ou 'até 18:00'")
    prioridade: Literal["alta", "media", "baixa"]
    area: Literal["infra", "banco", "aplicacao", "pagamentos", "atendimento", "comunicacao", "seguranca", "observabilidade"]
    titulo: str
    detalhe: str
    responsavel: str


class DicasManutencao(BaseModel):
    data: str
    unidade: str
    nivel: Nivel
    resumo: str
    pico: Pico
    janela_manutencao: Janela | None = None
    congelamento: list[Janela] = Field(default_factory=list)
    escalar_ate: str | None = None
    tarefas: list[TarefaManutencao]
    nao_fazer: list[str]
    origem: OrigemIA = "regras"
    modelo: str | None = None


# ---------- Alertas ----------


class Alerta(BaseModel):
    id: str
    unidade: str
    nivel: Nivel
    rotulo: str
    estagio: Estagio
    origem: Literal["previsao", "ao_vivo"] = "previsao"
    data: str
    inicio: str
    fim: str
    hora_pico: str
    pico: int
    capacidade: int
    razao: float
    antecedencia_min: int
    titulo: str
    mensagem: str
    acoes: list[str] = Field(default_factory=list)
    eventos: list[str] = Field(default_factory=list)
    criado_em: str
    reconhecido_em: str | None = None


# ---------- Trilha do Gemini e chat ----------


class RegistroTrilha(BaseModel):
    hora: str
    quando: str
    etapa: str
    detalhe: str
    tokens: int | None = None
    tempo: str | None = None
    ferramenta: bool = False
    modelo: str | None = None
    ok: bool = True


class MensagemChat(BaseModel):
    papel: Literal["usuario", "assistente"]
    texto: str = Field(min_length=1, max_length=4000)


class PedidoChat(BaseModel):
    mensagens: list[MensagemChat] = Field(min_length=1, max_length=30)
    unidade: str = "rj"
    agora: str | None = None


class RespostaChat(BaseModel):
    resposta: str
    ferramentas: list[RegistroTrilha] = Field(default_factory=list)
    origem: OrigemIA
    modelo: str | None = None
    dados: dict[str, Any] | None = None
