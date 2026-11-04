// frontend/src/dados/previa.js
// DADOS DE PRÉVIA: servem só para visualizar as telas antes do backend existir.
// O formato é o mesmo dos schemas Pydantic (Evento, DiaRisco, Plano, Comunicado).
// Na E9 este arquivo sai e as telas passam a chamar /api.

export const CONTEXTO = {
  instituicao: 'Ibmec',
  semestre: '2027.1',
  alunos: 8000,
  capacidade: 500,
  inicio: '2027-02-15',
  fim: '2027-07-02',
  modelo: 'gemini-flash',
  feriados: [
    { data: '2027-03-26', nome: 'Sexta-feira Santa' },
    { data: '2027-04-21', nome: 'Tiradentes' },
    { data: '2027-04-23', nome: 'São Jorge (RJ)' },
    { data: '2027-05-27', nome: 'Corpus Christi' },
  ],
}

export const TIPOS = {
  prova_online: 'Prova online',
  vencimento: 'Vencimento',
  notas: 'Notas',
  rematricula: 'Rematrícula',
  outro: 'Outro',
}

const ALUNOS_POR_TURMA = 60

export const EVENTOS = [
  { data: '2027-02-15', hora_inicio: '08:00', hora_fim: '22:00', tipo: 'outro', descricao: 'Início das aulas 2027.1', turmas: [] },
  { data: '2027-02-26', hora_inicio: '09:00', hora_fim: '18:00', tipo: 'outro', descricao: 'Último dia de ajuste de matrícula', turmas: [] },
  { data: '2027-03-10', hora_inicio: '00:00', hora_fim: '23:59', tipo: 'vencimento', descricao: 'Vencimento da mensalidade de março', turmas: [] },
  { data: '2027-03-10', hora_inicio: '18:00', hora_fim: '23:59', tipo: 'notas', descricao: 'Divulgação das notas do Simulado Integrado', turmas: [] },
  { data: '2027-03-10', hora_inicio: '19:00', hora_fim: '21:00', tipo: 'prova_online', descricao: 'AV1 online de Gestão e Economia', turmas: ['ADM-1A', 'ADM-1B', 'ADM-2A', 'ECO-1A', 'ECO-2A'] },
  { data: '2027-03-11', hora_inicio: '19:00', hora_fim: '21:00', tipo: 'prova_online', descricao: 'AV1 online de Cálculo I', turmas: ['ENG-1A', 'ENG-1B'] },
  { data: '2027-03-17', hora_inicio: '19:00', hora_fim: '21:00', tipo: 'prova_online', descricao: 'AV1 online de Direito', turmas: ['DIR-1A', 'DIR-3A'] },
  { data: '2027-04-05', hora_inicio: '14:00', hora_fim: '23:59', tipo: 'notas', descricao: 'Divulgação das notas da AV1', turmas: [] },
  { data: '2027-04-12', hora_inicio: '00:00', hora_fim: '23:59', tipo: 'vencimento', descricao: 'Vencimento da mensalidade de abril (10/04 cai no sábado)', turmas: [] },
  { data: '2027-04-28', hora_inicio: '19:00', hora_fim: '21:00', tipo: 'prova_online', descricao: 'Prova online de Relações Internacionais', turmas: ['RI-2A'] },
  { data: '2027-05-10', hora_inicio: '00:00', hora_fim: '23:59', tipo: 'vencimento', descricao: 'Vencimento da mensalidade de maio', turmas: [] },
  { data: '2027-05-10', hora_inicio: '19:00', hora_fim: '21:00', tipo: 'prova_online', descricao: 'AV2 online de Cálculo e Estatística', turmas: ['ENG-1A', 'ENG-1B', 'ADM-2A', 'ECO-1A', 'CDC-1A'] },
  { data: '2027-05-10', hora_inicio: '21:00', hora_fim: '23:59', tipo: 'notas', descricao: 'Divulgação das notas dos trabalhos (N2)', turmas: [] },
  { data: '2027-06-10', hora_inicio: '00:00', hora_fim: '23:59', tipo: 'vencimento', descricao: 'Vencimento da mensalidade de junho', turmas: [] },
  { data: '2027-06-14', hora_inicio: '09:00', hora_fim: '23:59', tipo: 'rematricula', descricao: 'Abertura da rematrícula 2027.2', turmas: [] },
  { data: '2027-06-14', hora_inicio: '10:00', hora_fim: '12:00', tipo: 'prova_online', descricao: 'AV2 online de Direito e Relações Internacionais', turmas: ['DIR-1A', 'DIR-3A', 'RI-2A', 'RI-4A'] },
  { data: '2027-06-21', hora_inicio: '14:00', hora_fim: '23:59', tipo: 'notas', descricao: 'Divulgação das notas finais', turmas: [] },
  { data: '2027-07-02', hora_inicio: '18:00', hora_fim: '22:00', tipo: 'outro', descricao: 'Encerramento do semestre', turmas: [] },
]

// O que o Gemini devolve em analisar_riscos (texto simulado na prévia).
export const DIAS_RISCO = [
  {
    data: '2027-03-10',
    gravidade: 5,
    eventos: ['Vencimento da mensalidade de março', 'Divulgação das notas do Simulado Integrado', 'AV1 online de Gestão e Economia'],
    motivo:
      'Três gatilhos se somam no mesmo fim de tarde. As notas saem às 18h, a AV1 online coloca cinco turmas no portal às 19h e o vencimento concentra pagamentos entre 20h e 23h59. Nos vencimentos de 10/09/2026 e 10/03/2026 o portal já passava de 340 acessos simultâneos só com os pagamentos.',
    consultados: ['2026-09-10', '2026-03-10', '2026-04-06'],
  },
  {
    data: '2027-05-10',
    gravidade: 5,
    eventos: ['Vencimento da mensalidade de maio', 'AV2 online de Cálculo e Estatística', 'Divulgação das notas dos trabalhos (N2)'],
    motivo:
      'As notas saem às 21h, no minuto em que a AV2 online termina e quando os pagamentos do vencimento entram na reta final. No histórico, a divulgação de notas de 06/04/2026 dobrou os acessos em menos de 15 minutos.',
    consultados: ['2026-04-06', '2025-11-10'],
  },
  {
    data: '2027-06-14',
    gravidade: 4,
    eventos: ['Abertura da rematrícula 2027.2', 'AV2 online de Direito e Relações Internacionais'],
    motivo:
      'Colisão discreta: a rematrícula abre às 9h e puxa a base inteira nas primeiras horas, e uma hora depois quatro turmas entram para a AV2 online. Em 15/06/2026 a abertura da rematrícula sozinha manteve o portal acima de 300 acessos até as 11h.',
    consultados: ['2026-06-15', '2025-12-14'],
  },
  {
    data: '2027-06-21',
    gravidade: 3,
    eventos: ['Divulgação das notas finais'],
    motivo:
      'Notas finais costumam gerar o maior salto isolado do semestre, mas sem outro evento no mesmo horário a carga fica abaixo da capacidade.',
    consultados: ['2026-06-22'],
  },
  {
    data: '2027-04-05',
    gravidade: 2,
    eventos: ['Divulgação das notas da AV1'],
    motivo: 'Salto previsível às 14h, sem sobreposição com prova ou vencimento.',
    consultados: [],
  },
  {
    data: '2027-04-12',
    gravidade: 2,
    eventos: ['Vencimento da mensalidade de abril (10/04 cai no sábado)'],
    motivo: 'Vencimento isolado. A concentração das 22h fica dentro da capacidade.',
    consultados: [],
  },
  {
    data: '2027-06-10',
    gravidade: 2,
    eventos: ['Vencimento da mensalidade de junho'],
    motivo: 'Vencimento isolado, mesmo padrão de abril.',
    consultados: [],
  },
]

// Trilha das chamadas ao Gemini (o que o cliente.py registra).
export const TRILHA_GEMINI = [
  { hora: '11:42:08', etapa: 'Files API', detalhe: 'upload de calendario_2027-1.pdf (3 páginas)', tokens: null, tempo: '0,9 s' },
  { hora: '11:42:11', etapa: 'extrair_eventos', detalhe: 'response_schema list[Evento] · temperature 0 · 18 eventos', tokens: 6204, tempo: '2,8 s' },
  { hora: '11:42:15', etapa: 'analisar_riscos', detalhe: 'tools=[consultar_historico] · temperature 0.2', tokens: 9870, tempo: '4,1 s' },
  { hora: '11:42:16', etapa: 'consultar_historico', detalhe: '2026-09-10 → pico 352 às 22h45', ferramenta: true },
  { hora: '11:42:16', etapa: 'consultar_historico', detalhe: '2026-03-10 → pico 341 às 23h00', ferramenta: true },
  { hora: '11:42:17', etapa: 'consultar_historico', detalhe: '2026-04-06 → salto de 96 para 412 às 14h', ferramenta: true },
  { hora: '11:42:17', etapa: 'consultar_historico', detalhe: '2026-06-15 → 300+ das 9h às 11h', ferramenta: true },
  { hora: '11:42:18', etapa: 'consultar_historico', detalhe: '2025-11-10 → pico 337 às 22h30', ferramenta: true },
  { hora: '11:42:18', etapa: 'consultar_historico', detalhe: '2025-12-14 → abertura de rematrícula', ferramenta: true },
  { hora: '11:42:19', etapa: 'consultar_historico', detalhe: '2026-06-22 → notas finais', ferramenta: true },
  { hora: '11:42:21', etapa: 'formatar_riscos', detalhe: 'response_schema list[DiaRisco] · 7 dias', tokens: 2310, tempo: '1,9 s' },
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

// ---------- Evitar: plano + tentativas de validação (só 10/03 na prévia) ----------

export const PLANOS = {
  '2027-03-10': {
    calendario: [
      { titulo: 'Notas do Simulado em 4 lotes no dia seguinte', detalhe: '11/03: Gestão às 9h, Economia às 10h30, Direito às 12h e Engenharia às 13h30. Nenhum lote encosta na AV1 de Cálculo das 19h.' },
    ],
    comunicacao: [
      { titulo: 'Grupo A · 2.700 alunos', detalhe: 'Lembrete de pagamento em 05/03 às 10h (quem costuma pagar cedo).' },
      { titulo: 'Grupo B · 2.700 alunos', detalhe: 'Lembrete em 08/03 às 12h, com Pix e boleto no corpo da mensagem.' },
      { titulo: 'Grupo C · 2.600 alunos', detalhe: 'Lembrete em 09/03 às 9h para quem paga no dia. O vencimento continua 10/03.' },
      { titulo: 'Turmas da AV1', detalhe: 'Aviso em 09/03: a prova abre às 19h, não recarregue a página e use a fila se ela aparecer.' },
    ],
    infra_checklist: [
      { titulo: 'Escalar o portal até 17h de 10/03', detalhe: 'Pico previsto às 19h. Escala desfeita às 0h30.' },
      { titulo: 'Congelar deploys e manutenções', detalhe: 'De 08/03 a 12/03.' },
      { titulo: 'Fila virtual de login', detalhe: 'Ligada das 18h às 23h59 de 10/03.' },
      { titulo: 'Plantão de TI e atendimento', detalhe: 'Das 18h às 0h, com o comunicado de crise pré-aprovado.' },
    ],
  },
}

export const TENTATIVAS = {
  '2027-03-10': [
    {
      numero: 1,
      ok: false,
      proposta: 'Liberar as notas às 22h de 10/03, depois da prova.',
      erro: 'A carga recalculada às 22h fica em 739, acima da capacidade de 500: o horário coincide com a reta final dos pagamentos.',
    },
    {
      numero: 2,
      ok: false,
      proposta: 'Notas em lotes no dia 11/03, último lote às 19h.',
      erro: 'O lote das 19h de 11/03 conflita com a AV1 online de Cálculo I (ENG-1A, ENG-1B).',
    },
    {
      numero: 3,
      ok: true,
      proposta: 'Notas em 4 lotes em 11/03 entre 9h e 13h30, lembretes de pagamento em 3 grupos e checklist de TI.',
      checagens: [
        'Nenhuma ação cai em feriado',
        'Nenhuma ação conflita com prova online',
        'Nenhuma carga foi empurrada para outro dia crítico',
        'Pico recalculado 483 às 19h (97% da capacidade)',
      ],
    },
  ],
}

// ---------- Reagir: comunicado de crise ----------

export const FALHA_EXEMPLO = 'Portal do aluno fora do ar das 19h05 às 19h50 de 10/03, durante a AV1 online e no dia do vencimento.'

export const COMUNICADO = {
  titulo: 'Instabilidade no portal em 10/03: prazos estendidos',
  mensagem:
    'Entre 19h05 e 19h50 de hoje, o portal do aluno ficou instável. Sabemos que isso aconteceu num momento importante, com a AV1 online e o vencimento da mensalidade no mesmo dia. Ninguém será prejudicado: as respostas já enviadas estão salvas e os prazos abaixo foram ajustados.',
  nova_data_prazo: '2027-03-12',
  regras_tolerancia: [
    'Mensalidades de março pagas até 12/03 não terão multa nem juros.',
    'Quem não conseguiu concluir a AV1 online fará a prova em nova janela em 11/03, das 19h às 21h.',
    'Respostas enviadas antes da falha foram salvas e não precisam ser refeitas.',
    'Não é preciso abrir chamado: a tolerância é aplicada automaticamente.',
  ],
}

// ---------- Prova de carga (forma da saída de carga/comparar.py) ----------

const BASE_MS = 120

function ruido(i) {
  return 1 + 0.05 * Math.sin(i * 1.7) + 0.03 * Math.cos(i * 0.6)
}

export function seriesLatencia() {
  const antes = curvaDoDia('2027-03-10')
  const depois = curvaDoDia('2027-03-10', { notasMovidas: true, lembretesEscalonados: true })
  const controle = curvaDoDia('2027-03-03')
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
    { chave: 'antes', nome: 'Antes', sub: '10/03 · perfil original · sem fila', p95: pico('antes'), p50: Math.round(pico('antes') * 0.46), erros: erroPico },
    { chave: 'depois', nome: 'Depois', sub: '10/03 · plano aplicado · fila ligada', p95: pico('depois'), p50: Math.round(pico('depois') * 0.55), erros: 0 },
    { chave: 'controle', nome: 'Controle', sub: '03/03 · dia tranquilo · sem plano', p95: pico('controle'), p50: Math.round(pico('controle') * 0.6), erros: 0 },
  ]
}
