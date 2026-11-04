// frontend/src/dados/previa.js
// DADOS DE PRÉVIA ancorados no CALENDÁRIO ACADÊMICO REAL do Ibmec RJ 2026.2.
// As datas de feriados, provas (AP1/AP2/AS), Teste de Progresso, rematrícula e
// vencimento (sempre dia 10) vêm do calendário oficial. O histórico de acesso e as
// curvas de carga são MODELADOS (ver aba Fonte de dados). Formato = schemas Pydantic.
// Na E9 este arquivo sai e as telas passam a chamar /api.

export const CONTEXTO = {
  instituicao: 'Ibmec RJ',
  semestre: '2026.2',
  alunos: 8000,
  capacidade: 500,
  inicio: '2026-08-03', // início do período letivo (veteranos)
  fim: '2026-12-07',    // conclusão do período letivo às 10h
  modelo: 'gemini-flash',
  // Feriados e recessos reais dentro da janela do semestre.
  feriados: [
    { data: '2026-09-07', nome: 'Independência do Brasil' },
    { data: '2026-10-12', nome: 'Nossa Senhora Aparecida' },
    { data: '2026-10-15', nome: 'Dia do Professor (recesso)' },
    { data: '2026-11-02', nome: 'Finados' },
    { data: '2026-11-15', nome: 'Proclamação da República' },
    { data: '2026-11-20', nome: 'Consciência Negra' },
  ],
}

export const TIPOS = {
  prova_online: 'Prova online',
  vencimento: 'Vencimento',
  notas: 'Notas',
  rematricula: 'Rematrícula',
  outro: 'Acadêmico',
}

const ALUNOS_POR_TURMA = 60

// Períodos do calendário (bandas na tela de Calendário). Não geram carga pontual.
export const MARCOS = [
  { inicio: '2026-08-03', fim: '2026-09-11', nome: 'Renovação de matrícula online', tipo: 'rematricula' },
  { inicio: '2026-09-24', fim: '2026-09-30', nome: 'Avaliações Parciais AP1', tipo: 'prova_online' },
  { inicio: '2026-10-05', fim: '2026-10-09', nome: 'Mostra de Iniciação Científica', tipo: 'outro' },
  { inicio: '2026-11-12', fim: '2026-11-18', nome: 'Avaliações Parciais AP2', tipo: 'prova_online' },
  { inicio: '2026-11-27', fim: '2026-11-28', nome: 'Vestibular Ibmec 2027.1', tipo: 'outro' },
  { inicio: '2026-11-25', fim: '2026-12-03', nome: 'Avaliações Substitutivas AS', tipo: 'prova_online' },
]

// Turmas de Teste de Progresso e AP2 online (muitos alunos simultâneos).
const TURMAS_TP = ['ADM-1A','ADM-1B','ADM-3A','ECO-1A','ECO-3A','ENG-1A','DIR-1A','DIR-3A','RI-1A','CDC-1A']
const TURMAS_AP2 = ['ADM-2A','ADM-2B','ECO-2A','ENG-1A','ENG-1B','ENG-2A','CDC-1A','DIR-2A','RI-2A','RI-4A','CCO-1A']

export const EVENTOS = [
  { data: '2026-08-03', hora_inicio: '08:00', hora_fim: '22:00', tipo: 'outro', descricao: 'Início do período letivo (veteranos)', turmas: [] },
  { data: '2026-08-10', hora_inicio: '00:00', hora_fim: '23:59', tipo: 'vencimento', descricao: 'Vencimento da 2ª parcela da semestralidade', turmas: [] },
  { data: '2026-08-10', hora_inicio: '08:00', hora_fim: '22:00', tipo: 'outro', descricao: 'Início do período letivo (calouros)', turmas: [] },
  { data: '2026-09-10', hora_inicio: '00:00', hora_fim: '23:59', tipo: 'vencimento', descricao: 'Vencimento da 3ª parcela da semestralidade', turmas: [] },
  { data: '2026-09-10', hora_inicio: '09:00', hora_fim: '18:00', tipo: 'prova_online', descricao: 'Aplicação do Teste de Progresso', turmas: TURMAS_TP },
  { data: '2026-09-10', hora_inicio: '18:00', hora_fim: '23:59', tipo: 'notas', descricao: 'Divulgação de notas da Avaliação Contínua (AC)', turmas: [] },
  { data: '2026-09-11', hora_inicio: '09:00', hora_fim: '23:59', tipo: 'rematricula', descricao: 'Fim da renovação de matrícula online 2026.2', turmas: [] },
  { data: '2026-09-11', hora_inicio: '09:00', hora_fim: '18:00', tipo: 'outro', descricao: 'Fim dos prazos de ajuste de disciplinas pelo portal', turmas: [] },
  { data: '2026-09-24', hora_inicio: '19:00', hora_fim: '21:00', tipo: 'prova_online', descricao: 'AP1 online · início do período', turmas: ['ADM-1A','ADM-1B','ECO-1A'] },
  { data: '2026-10-10', hora_inicio: '00:00', hora_fim: '23:59', tipo: 'vencimento', descricao: 'Vencimento da 4ª parcela (10/10 cai no sábado)', turmas: [] },
  { data: '2026-10-13', hora_inicio: '14:00', hora_fim: '23:59', tipo: 'notas', descricao: 'Divulgação de notas das Avaliações Parciais AP1', turmas: [] },
  { data: '2026-11-10', hora_inicio: '00:00', hora_fim: '23:59', tipo: 'vencimento', descricao: 'Vencimento da 5ª parcela da semestralidade', turmas: [] },
  { data: '2026-11-12', hora_inicio: '19:00', hora_fim: '21:00', tipo: 'prova_online', descricao: 'Abertura da AP2 online', turmas: TURMAS_AP2 },
  { data: '2026-11-12', hora_inicio: '21:00', hora_fim: '23:59', tipo: 'notas', descricao: 'Prazo final de notas da Avaliação Contínua (AC)', turmas: [] },
  { data: '2026-12-03', hora_inicio: '14:00', hora_fim: '23:59', tipo: 'notas', descricao: 'Divulgação de notas finais (AS e Teste de Progresso)', turmas: [] },
  { data: '2026-12-07', hora_inicio: '08:00', hora_fim: '12:00', tipo: 'outro', descricao: 'Conclusão do período letivo 2026.2', turmas: [] },
]

// list[DiaRisco] — gravidade, eventos e motivo escritos pelo Gemini; pico calculado pelo código.
export const DIAS_RISCO = [
  {
    data: '2026-09-10',
    gravidade: 5,
    eventos: ['Vencimento da 3ª parcela da semestralidade', 'Aplicação do Teste de Progresso', 'Divulgação de notas da Avaliação Contínua (AC)'],
    motivo:
      'Três gatilhos reais no mesmo dia. O Teste de Progresso ocupa o portal com muitas turmas das 9h às 18h, as notas da AC saem às 18h e o vencimento concentra pagamentos entre 20h e 23h59. Nos vencimentos de 10/03/2026 e 10/06/2026 o portal já passava de 340 acessos simultâneos só com os pagamentos.',
    consultados: ['2026-06-10', '2026-03-10', '2025-09-10'],
  },
  {
    data: '2026-11-12',
    gravidade: 5,
    eventos: ['Abertura da AP2 online', 'Prazo final de notas da Avaliação Contínua (AC)', 'Resíduo do vencimento de 10/11'],
    motivo:
      'A AP2 online abre às 19h com treze turmas, o prazo de notas da AC vence no mesmo dia e os pagamentos atrasados do vencimento de 10/11 ainda chegam. No histórico, a abertura de provas online dobrou os acessos em menos de 15 minutos.',
    consultados: ['2026-05-12', '2025-11-13'],
  },
  {
    data: '2026-09-11',
    gravidade: 4,
    eventos: ['Fim da renovação de matrícula online 2026.2', 'Fim dos prazos de ajuste de disciplinas pelo portal'],
    motivo:
      'Colisão discreta: não tem prova nem vencimento, mas é o último dia da rematrícula e de vários ajustes de disciplina. A base inteira tenta resolver tudo nas primeiras horas. Em 11/09/2025 a véspera do fim da renovação manteve o portal acima de 300 acessos das 9h às 11h.',
    consultados: ['2025-09-11', '2026-03-31'],
  },
  {
    data: '2026-12-03',
    gravidade: 3,
    eventos: ['Divulgação de notas finais (AS e Teste de Progresso)'],
    motivo:
      'As notas finais costumam gerar o maior salto isolado do semestre, mas sem prova ou vencimento no mesmo horário a carga fica perto do limite, não acima.',
    consultados: ['2026-07-03'],
  },
  {
    data: '2026-10-13',
    gravidade: 3,
    eventos: ['Divulgação de notas das Avaliações Parciais AP1'],
    motivo: 'Salto previsível às 14h, logo após o feriado de 12/10, sem sobreposição com prova ou vencimento.',
    consultados: ['2026-05-13'],
  },
  {
    data: '2026-11-10',
    gravidade: 2,
    eventos: ['Vencimento da 5ª parcela da semestralidade'],
    motivo: 'Vencimento isolado. A concentração das 22h fica dentro da capacidade, mas a AP2 abre dois dias depois: semana sem folga.',
    consultados: [],
  },
  {
    data: '2026-08-10',
    gravidade: 2,
    eventos: ['Vencimento da 2ª parcela da semestralidade', 'Início do período letivo (calouros)'],
    motivo: 'Vencimento somado à primeira entrada dos calouros. Fica abaixo da capacidade.',
    consultados: [],
  },
]

// Trilha das chamadas ao Gemini (o que o cliente.py registra).
export const TRILHA_GEMINI = [
  { hora: '10:18:04', etapa: 'Files API', detalhe: 'upload de CALENDARIO_ACADEMICO_26_2_RJ.pdf (1 página)', tokens: null, tempo: '0,8 s' },
  { hora: '10:18:07', etapa: 'extrair_eventos', detalhe: 'response_schema list[Evento] · temperature 0 · 16 eventos', tokens: 5980, tempo: '2,7 s' },
  { hora: '10:18:11', etapa: 'analisar_riscos', detalhe: 'tools=[consultar_historico] · temperature 0.2', tokens: 9410, tempo: '4,0 s' },
  { hora: '10:18:12', etapa: 'consultar_historico', detalhe: '2026-06-10 → pico 352 às 22h45', ferramenta: true },
  { hora: '10:18:12', etapa: 'consultar_historico', detalhe: '2026-03-10 → pico 341 às 23h00', ferramenta: true },
  { hora: '10:18:13', etapa: 'consultar_historico', detalhe: '2025-09-10 → Teste de Progresso, 480 às 10h', ferramenta: true },
  { hora: '10:18:13', etapa: 'consultar_historico', detalhe: '2026-05-12 → abertura de AP2, 430 às 19h', ferramenta: true },
  { hora: '10:18:14', etapa: 'consultar_historico', detalhe: '2025-09-11 → fim da rematrícula, 300+ às 10h', ferramenta: true },
  { hora: '10:18:14', etapa: 'consultar_historico', detalhe: '2026-07-03 → notas finais', ferramenta: true },
  { hora: '10:18:16', etapa: 'formatar_riscos', detalhe: 'response_schema list[DiaRisco] · 7 dias', tokens: 2240, tempo: '1,8 s' },
]

// ---------- Modelo de carga (espelho simplificado do calculo/carga.py) ----------

const P_ACESSO = { vencimento: 1, notas: 0.05, rematricula: 0.05, prova_online: 1, outro: 0 }

function sino(h, centro, largura) {
  return Math.exp(-0.5 * ((h - centro) / largura) ** 2)
}

function minutos(hhmm) {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function base(h) {
  return 20 + 55 * sino(h, 10.5, 1.8) + 45 * sino(h, 15, 2.2) + 80 * sino(h, 21, 1.5)
}

function contribuicao(ev, m, opcoes = {}) {
  const h = m / 60
  const ini = minutos(ev.hora_inicio)
  const fim = minutos(ev.hora_fim)
  if (ev.tipo === 'vencimento') {
    const fatorNoite = opcoes.lembretesEscalonados ? 0.4 : 1
    const manha = (opcoes.lembretesEscalonados ? 60 : 30) * sino(h, 9, 1.5)
    const noite = h > 12 ? 380 * ((h - 12) / 12) ** 2.2 : 0
    return manha + fatorNoite * noite
  }
  if (ev.tipo === 'prova_online') {
    const alunos = ev.turmas.length * ALUNOS_POR_TURMA
    if (m >= ini && m < ini + 15) return alunos * 1.25
    if (m >= ini + 15 && m < fim) return alunos * 0.9
    if (m >= fim && m < fim + 30) return alunos * 0.15
    return 0
  }
  if (ev.tipo === 'notas') {
    if (opcoes.notasMovidas) return 0
    if (m < ini) return 0
    return CONTEXTO.alunos * P_ACESSO.notas * Math.exp(-(m - ini) / 120)
  }
  if (ev.tipo === 'rematricula') {
    if (m < ini) return 0
    return CONTEXTO.alunos * P_ACESSO.rematricula * Math.exp(-(m - ini) / 150) + 25
  }
  if (ev.tipo === 'outro') {
    return m >= ini && m < fim ? 30 * sino(h, ini / 60 + 1, 1) : 0
  }
  return 0
}

export function curvaDoDia(data, opcoes = {}) {
  const eventos = EVENTOS.filter((e) => e.data === data)
  const pontos = []
  for (let i = 0; i < 96; i++) {
    const m = i * 15
    const h = m / 60
    let carga = base(h)
    for (const ev of eventos) carga += contribuicao(ev, m, opcoes)
    const hh = String(Math.floor(m / 60)).padStart(2, '0')
    const mm = String(m % 60).padStart(2, '0')
    pontos.push({ hora: `${hh}:${mm}`, carga: Math.round(carga) })
  }
  return pontos
}

export function picoDoDia(data, opcoes) {
  return curvaDoDia(data, opcoes).reduce((a, b) => (b.carga > a.carga ? b : a))
}

// ---------- Evitar: plano + tentativas de validação (10/09 na prévia) ----------

const DIA_PLANO = '2026-09-10'

export const PLANOS = {
  [DIA_PLANO]: {
    calendario: [
      { titulo: 'Notas da AC em 4 lotes no dia seguinte', detalhe: '11/09: Gestão às 9h, Economia às 10h30, Direito às 12h e Engenharia às 13h30. Nenhum lote encosta no pico da rematrícula de 11/09.' },
    ],
    comunicacao: [
      { titulo: 'Grupo A · 2.700 alunos', detalhe: 'Lembrete da 3ª parcela em 05/09 às 10h (quem costuma pagar cedo).' },
      { titulo: 'Grupo B · 2.700 alunos', detalhe: 'Lembrete em 08/09 às 12h, com Pix e boleto no corpo da mensagem.' },
      { titulo: 'Grupo C · 2.600 alunos', detalhe: 'Lembrete em 09/09 às 9h para quem paga no dia. O vencimento continua 10/09.' },
      { titulo: 'Turmas do Teste de Progresso', detalhe: 'Aviso em 09/09: a prova abre às 9h, não recarregue a página e use a fila se ela aparecer.' },
    ],
    infra_checklist: [
      { titulo: 'Escalar o portal até 8h de 10/09', detalhe: 'O Teste de Progresso começa às 9h; o segundo pico é à noite no vencimento. Escala desfeita às 0h30.' },
      { titulo: 'Congelar deploys e manutenções', detalhe: 'De 08/09 a 12/09.' },
      { titulo: 'Fila virtual de login', detalhe: 'Ligada das 8h30 às 18h (Teste de Progresso) e das 20h às 23h59 (vencimento).' },
      { titulo: 'Plantão de TI e atendimento', detalhe: 'Das 8h às 0h, com o comunicado de crise pré-aprovado.' },
    ],
  },
}

export const TENTATIVAS = {
  [DIA_PLANO]: [
    {
      numero: 1,
      ok: false,
      proposta: 'Liberar as notas da AC às 22h de 10/09, depois do Teste de Progresso.',
      erro: 'A carga recalculada às 22h fica em 739, acima da capacidade de 500: o horário coincide com a reta final dos pagamentos da 3ª parcela.',
    },
    {
      numero: 2,
      ok: false,
      proposta: 'Notas em lotes em 11/09, último lote às 10h.',
      erro: 'O lote das 10h de 11/09 cai no pico do fim da renovação de matrícula, que já é um dia de risco (gravidade 4).',
    },
    {
      numero: 3,
      ok: true,
      proposta: 'Notas da AC em 4 lotes em 11/09 das 12h às 15h, lembretes da 3ª parcela em 3 grupos e checklist de TI.',
      checagens: [
        'Nenhuma ação cai em feriado',
        'Nenhuma ação conflita com prova online',
        'Nenhuma carga foi empurrada para outro dia crítico',
        'Pico recalculado 486 às 10h (97% da capacidade)',
      ],
    },
  ],
}

// ---------- Reagir: crise ----------

export const FALHA_EXEMPLO = 'Portal do aluno fora do ar das 10h05 às 10h50 de 10/09, durante a aplicação do Teste de Progresso e no dia do vencimento.'

export const COMUNICADO = {
  titulo: 'Instabilidade no portal em 10/09: prazos estendidos',
  mensagem:
    'Entre 10h05 e 10h50 de hoje, o portal do aluno ficou instável. Sabemos que isso aconteceu num momento importante, com o Teste de Progresso em andamento e o vencimento da mensalidade no mesmo dia. Ninguém será prejudicado: as respostas já enviadas estão salvas e os prazos abaixo foram ajustados.',
  nova_data_prazo: '2026-09-12',
  regras_tolerancia: [
    'Mensalidades de setembro pagas até 12/09 não terão multa nem juros.',
    'Quem não concluiu o Teste de Progresso fará a prova em nova janela em 11/09, das 10h às 12h.',
    'Respostas enviadas antes da falha foram salvas e não precisam ser refeitas.',
    'Não é preciso abrir chamado: a tolerância é aplicada automaticamente.',
  ],
}

// ---------- Prova de carga (forma da saída de carga/comparar.py) ----------

const DIA_PICO = '2026-09-10'
const DIA_CONTROLE = '2026-08-18' // terça tranquila, sem eventos
const BASE_MS = 120

function ruido(i) {
  return 1 + 0.05 * Math.sin(i * 1.7) + 0.03 * Math.cos(i * 0.6)
}

export function seriesLatencia() {
  const antes = curvaDoDia(DIA_PICO)
  const depois = curvaDoDia(DIA_PICO, { notasMovidas: true, lembretesEscalonados: true })
  const controle = curvaDoDia(DIA_CONTROLE)
  const cap = CONTEXTO.capacidade
  return antes.map((p, i) => {
    const ua = p.carga
    const ud = Math.min(depois[i].carga, cap) // fila virtual: semáforo na capacidade
    const uc = controle[i].carga
    const p95Antes = BASE_MS * (1 + (ua / cap) ** 3) * (1 + Math.max(0, ua - cap) / 250) * ruido(i)
    return {
      hora: p.hora,
      antes: Math.round(p95Antes),
      depois: Math.round(BASE_MS * (1 + (ud / cap) ** 3) * ruido(i + 3)),
      controle: Math.round(BASE_MS * (1 + (uc / cap) ** 3) * ruido(i + 7)),
      erroAntes: ua > 1.5 * cap ? (ua - 1.5 * cap) / ua : 0,
    }
  })
}

export function resumoLatencia() {
  const s = seriesLatencia()
  const pico = (chave) => Math.max(...s.map((p) => p[chave]))
  const erroPico = Math.max(...s.map((p) => p.erroAntes))
  return [
    { chave: 'antes', nome: 'Antes', sub: '10/09 · perfil original · sem fila', p95: pico('antes'), p50: Math.round(pico('antes') * 0.46), erros: erroPico },
    { chave: 'depois', nome: 'Depois', sub: '10/09 · plano aplicado · fila ligada', p95: pico('depois'), p50: Math.round(pico('depois') * 0.55), erros: 0 },
    { chave: 'controle', nome: 'Controle', sub: '18/08 · dia tranquilo · sem plano', p95: pico('controle'), p50: Math.round(pico('controle') * 0.6), erros: 0 },
  ]
}
