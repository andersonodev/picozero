// frontend/src/api/cliente.js
// Cliente do backend PicoZero (FastAPI). Cada função devolve { dados, origem } com
// origem 'api' (motor real) ou 'previa' (fallback local de dados/previa.js quando a API não responde).
// Base: VITE_API_URL (vazio = mesma origem; no dev o proxy do vite manda /api para 127.0.0.1:8000).
import {
  COMUNICADO,
  CONTEXTO,
  DIAS_RISCO,
  EVENTOS,
  MARCOS,
  PLANOS,
  TENTATIVAS,
  TRILHA_GEMINI,
  curvaDoDia,
  resumoLatencia,
  seriesLatencia,
} from '../dados/previa'
import { FONTES, SONDA } from '../dados/fontes'
import { unidadePorId } from '../dados/unidades'

export const BASE = (import.meta.env?.VITE_API_URL || globalThis.PICOZERO_API_URL || '').replace(/\/$/, '')
const TIMEOUT_MS = 3000
const TIMEOUT_IA_MS = 60000
const COM_PLANO = { notasMovidas: true, lembretesEscalonados: true }
// Fila virtual do plano simulado da prévia (teto na capacidade dentro destas janelas).
const FILA_PREVIA = { '2026-09-10': [['08:30', '18:00'], ['20:00', '23:59']] }

// Escala da prévia para outras unidades: a mesma conta da Visão geral (alunos ÷ alunos do RJ).
const fator = (unidade) => unidadePorId(unidade).alunos / CONTEXTO.alunos
const capacidadeDe = (unidade) => unidadePorId(unidade).capacidade
const nivelDe = (carga, cap) => (carga >= cap ? 'critico' : carga >= 0.8 * cap ? 'serio' : carga >= 0.6 * cap ? 'alerta' : 'ok')

// ---------- compatível com frontend/src/dados/api.js (absorvido aqui) ----------

export class ApiIndisponivel extends Error {}

/** api(caminho, {metodo, corpo, tempo}) → JSON; lança ApiIndisponivel em erro, timeout ou resposta sem JSON. */
export async function api(caminho, { metodo = 'GET', corpo, tempo = 6000 } = {}) {
  try {
    return await pedir(caminho, { metodo, corpo, timeout: tempo, semCache: metodo !== 'GET' })
  } catch (e) {
    throw e instanceof ApiIndisponivel ? e : new ApiIndisponivel(e?.message || String(e))
  }
}

// ---------- transporte ----------

const cache = new Map() // GET: 30 s, para trocar de aba sem refazer tudo

async function pedir(caminho, { metodo = 'GET', corpo, form, timeout = TIMEOUT_MS, semCache = false } = {}) {
  const url = `${BASE}${caminho}`
  if (metodo === 'GET' && !semCache) {
    const c = cache.get(url)
    if (c && Date.now() - c.t < 30000) return c.v
  }
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeout)
  try {
    const resp = await fetch(url, {
      method: metodo,
      signal: ctrl.signal,
      headers: corpo !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: form || (corpo !== undefined ? JSON.stringify(corpo) : undefined),
    })
    const tipo = resp.headers.get('content-type') || ''
    if (!tipo.includes('application/json')) throw new Error(`resposta não-JSON (${resp.status})`)
    const json = await resp.json()
    if (!resp.ok) throw new Error(json?.detail ? String(json.detail) : `HTTP ${resp.status}`)
    if (metodo === 'GET') cache.set(url, { t: Date.now(), v: json })
    return json
  } finally {
    clearTimeout(timer)
  }
}

async function comFallback(fnApi, fnPrevia) {
  try {
    return { dados: await fnApi(), origem: 'api' }
  } catch (erro) {
    return { dados: fnPrevia ? fnPrevia() : null, origem: 'previa', erro: String(erro?.message || erro) }
  }
}

export function limparCache() {
  cache.clear()
}

const q = (params) => {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
  const t = s.toString()
  return t ? `?${t}` : ''
}

// ---------- fallbacks (mesmas formas da API, montadas a partir da prévia) ----------

function curvaPrevia(data, unidade = 'rj', opcoes, janelasFila) {
  const f = fator(unidade)
  const cap = capacidadeDe(unidade)
  const dentroDaFila = (hora) => (janelasFila || []).some(([a, b]) => hora >= a && hora < b)
  const pontos = curvaDoDia(data, opcoes).map((p) => {
    const carga = Math.round(p.carga * f)
    return { hora: p.hora, carga: dentroDaFila(p.hora) ? Math.min(carga, cap) : carga, p10: null, p90: null, real: null, base: null }
  })
  const topo = pontos.reduce((a, b) => (b.carga > a.carga ? b : a))
  const pico = { hora: topo.hora, carga: topo.carga }
  const janelas = []
  let atual = null
  for (const p of [...pontos, null]) {
    if (p && p.carga >= 0.6 * cap) {
      if (!atual) atual = { inicio: p.hora, fim: p.hora, max: p.carga, hora_max: p.hora }
      atual.fim = p.hora
      if (p.carga > atual.max) Object.assign(atual, { max: p.carga, hora_max: p.hora })
    } else if (atual) {
      janelas.push({ ...atual, nivel: nivelDe(atual.max, cap) })
      atual = null
    }
  }
  return {
    data, unidade, capacidade: cap, pontos, pico, pico_real: null, janelas,
    nivel: nivelDe(pico.carga, cap),
    razao: Math.round((pico.carga / cap) * 100) / 100,
    eventos: EVENTOS.filter((e) => e.data === data),
  }
}

function diasDoSemestre() {
  const dias = []
  const d = new Date(`${CONTEXTO.inicio}T12:00:00`)
  const fim = new Date(`${CONTEXTO.fim}T12:00:00`)
  while (d <= fim) {
    dias.push(d.toISOString().slice(0, 10))
    d.setDate(d.getDate() + 1)
  }
  return dias
}

// ---------- leitura ----------

export const saude = (_unidade = 'rj') => comFallback(() => pedir('/api/saude', { semCache: true }), null)

export const contexto = (unidade = 'rj') =>
  comFallback(
    () => pedir(`/api/contexto${q({ unidade })}`),
    () => ({ ...CONTEXTO, alunos: unidadePorId(unidade).alunos, capacidade: capacidadeDe(unidade), unidade, ia: 'fallback' }),
  )

export const unidades = () => comFallback(() => pedir('/api/unidades'), () => null)

export const eventos = (unidade = 'rj') => comFallback(() => pedir(`/api/eventos${q({ unidade })}`), () => EVENTOS)

export const marcos = (_unidade = 'rj') => comFallback(() => pedir('/api/marcos'), () => MARCOS)

/** Curva do dia: { pontos:[{hora,carga,p10,p90,real,base}], pico, janelas, nivel, razao, eventos, ... } */
export const curva = (data, unidade = 'rj', agora) =>
  comFallback(() => pedir(`/api/carga/${data}${q({ unidade, agora })}`), () => curvaPrevia(data, unidade))

/** Pico diário do semestre (fita de capacidade): [{data, pico, hora, p90, nivel, razao, eventos, feriado, real}] */
export const picos = (unidade = 'rj', inicio, fim) =>
  comFallback(
    () => pedir(`/api/picos${q({ unidade, inicio, fim })}`),
    () => diasDoSemestre().map((d) => {
      const c = curvaPrevia(d, unidade)
      return { data: d, pico: c.pico.carga, hora: c.pico.hora, p90: c.pico.carga, nivel: c.nivel, razao: c.razao, eventos: c.eventos.map((e) => e.descricao), feriado: null, real: null }
    }),
  )

/** Mapa de calor hora × dia: [{data, horas:[24], nivel}] */
export const mapa = (unidade = 'rj') =>
  comFallback(
    () => pedir(`/api/mapa${q({ unidade })}`),
    () => diasDoSemestre().map((d) => {
      const c = curvaPrevia(d, unidade)
      const cargas = c.pontos.map((p) => p.carga)
      return { data: d, horas: Array.from({ length: 24 }, (_, h) => Math.max(...cargas.slice(h * 4, h * 4 + 4))), nivel: c.nivel }
    }),
  )

export const mapaCalor = mapa

/** Próximos dias a partir de agora: { dias:[ResumoDia], proximo_risco, pior } */
export const previsao = (unidade = 'rj', dias = 7, agora) =>
  comFallback(() => pedir(`/api/previsao${q({ unidade, dias, agora })}`), null)

/** DIAS_RISCO (gravidade/motivo do Gemini ou regras; pico do código) */
export const riscos = (unidade = 'rj') =>
  comFallback(
    () => pedir(`/api/riscos${q({ unidade })}`),
    () => DIAS_RISCO.map((r) => {
      const c = curvaPrevia(r.data, unidade)
      return { ...r, pico: c.pico, nivel: c.nivel, origem: 'previa' }
    }),
  )

/** Plano do dia: { plano:{calendario,comunicacao,infra_checklist,acoes}, tentativas, pico_sem, pico_com, pontos_com, capacidade } */
export const plano = (data, unidade = 'rj') =>
  comFallback(
    () => pedir(`/api/plano/${data}${q({ unidade })}`),
    () => {
      const p = PLANOS[data] || null
      const sem = curvaPrevia(data, unidade)
      if (!p) {
        return { data, plano: null, tentativas: [], capacidade: sem.capacidade, pico_sem: sem.pico, pico_com: null, pontos_com: null, origem: 'previa' }
      }
      // Recalcula "com plano" de verdade: notas movidas + lembretes + fila virtual como teto nas janelas do plano.
      const com = curvaPrevia(data, unidade, COM_PLANO, FILA_PREVIA[data])
      const pct = Math.round((com.pico.carga / com.capacidade) * 100)
      const recalculado = `Pico recalculado ${com.pico.carga.toLocaleString('pt-BR')} às ${com.pico.hora} (${pct}% da capacidade)`
      const tentativas = (TENTATIVAS[data] || []).map((t) =>
        t.checagens ? { ...t, checagens: [...t.checagens.filter((c) => !c.startsWith('Pico recalculado')), recalculado] } : t,
      )
      return {
        data, plano: p, tentativas, capacidade: com.capacidade, pico_sem: sem.pico, pico_com: com.pico,
        pontos_com: com.pontos, origem: 'previa',
      }
    },
  )

/** Dicas de manutenção do dia para a equipe */
export const dicas = (data, unidade = 'rj') => comFallback(() => pedir(`/api/manutencao/${data}${q({ unidade })}`), null)

/** Alertas antecipados (do mais urgente ao mais distante) */
export const alertas = (unidade = 'rj', agora) =>
  comFallback(() => pedir(`/api/alertas${q({ unidade, agora })}`, { semCache: true }), () => [])

/** Registro do modelo (TRILHA_GEMINI) */
export const trilha = (_unidade = 'rj', limite = 120) =>
  comFallback(() => pedir(`/api/trilha${q({ limite })}`, { semCache: true }), () => TRILHA_GEMINI)

/** Prova de carga: { series:[{hora,antes,depois,controle,erroAntes}], resumo:[...] } */
export const provaCarga = (unidade = 'rj', data) =>
  comFallback(
    () => pedir(`/api/prova-carga${q({ unidade, data })}`),
    () => ({ series: seriesLatencia(), resumo: resumoLatencia(), capacidade: CONTEXTO.capacidade, data: '2026-09-10' }),
  )

/** Fontes de dados em formato de cartão [{tipo:'real'|'modelo', titulo, texto, mono}] (o mesmo de dados/fontes.js) */
export const fontes = (_unidade = 'rj') =>
  comFallback(async () => {
    const f = await pedir('/api/fontes')
    const cartoes = []
    for (const p of f.publico || []) {
      cartoes.push({
        tipo: 'real',
        titulo: `Tráfego público de ${p.dominio}`,
        texto: `${p.meses} meses de visitas estimadas (${p.fonte}). Último mês ${p.ultimo_mes}: ${p.visitas_ultimo_mes.toLocaleString('pt-BR')} visitas, duração média ${Math.round((p.duracao_media_s || 0) / 60)} min. Usado para validar a sazonalidade do motor.`,
        mono: `GET /api/validacao/publica · coletado ${p.coletado_em}`,
      })
    }
    cartoes.push(FONTES[0]) // sonda pública do site (medida hoje)
    const ingeridos = (f.metricas || []).filter((m) => m.origem !== 'modelo')
    if (ingeridos.length) {
      cartoes.push({
        tipo: 'real',
        titulo: 'Dados enviados ao motor',
        texto: ingeridos.map((m) => `${m.pontos.toLocaleString('pt-BR')} pontos (${m.origem}${m.fonte ? ` · ${m.fonte}` : ''}) de ${m.de} a ${m.ate}`).join('; '),
        mono: 'POST /api/ingestao/* · MCP ingerir_*',
      })
    }
    for (const m of (f.metricas || []).filter((x) => x.origem === 'modelo')) {
      cartoes.push({
        tipo: 'modelo',
        titulo: 'Histórico de acesso simultâneo',
        texto: `${m.pontos.toLocaleString('pt-BR')} janelas de 15 min de ${m.de.slice(0, 10)} a ${m.ate.slice(0, 10)}, geradas com seed fixa a partir do calendário. O export real do APM substitui pelos mesmos horários.`,
        mono: m.fonte || 'semente',
      })
    }
    cartoes.push(FONTES[FONTES.length - 1]) // curvas de carga e latência (modelo)
    return { cartoes, bruto: f }
  }, () => ({ cartoes: FONTES, bruto: null, sonda: SONDA }))

/** Teste com dado real público (Domsilo): correlação mensal, meses real × modelo, leitura */
export const validacaoPublica = (unidade = 'rj') => comFallback(() => pedir(`/api/validacao/publica${q({ unidade })}`), null)

/** Como o motor prevê: fatores aprendidos + backtest fora da amostra */
export const modelo = (unidade = 'rj') => comFallback(() => pedir(`/api/modelo${q({ unidade })}`), null)

export const historicoIngestao = (_unidade = 'rj') => comFallback(() => pedir('/api/ingestao/historico', { semCache: true }), () => [])

// ---------- ações (usam o Gemini; timeout maior; sem cache) ----------

const acao = (caminho, opcoes) => comFallback(() => pedir(caminho, { timeout: TIMEOUT_IA_MS, ...opcoes }), null)

export const analisarRiscos = (unidade = 'rj') => acao(`/api/riscos/analisar${q({ unidade })}`, { metodo: 'POST' })
export const gerarPlano = (data, unidade = 'rj') => acao(`/api/plano/${data}/gerar${q({ unidade })}`, { metodo: 'POST' })
export const gerarDicas = (data, unidade = 'rj') => acao(`/api/manutencao/${data}/gerar${q({ unidade })}`, { metodo: 'POST' })

export const crise = (data, falha, unidade = 'rj') =>
  comFallback(
    () => pedir('/api/crise', { metodo: 'POST', corpo: { data, falha, unidade }, timeout: TIMEOUT_IA_MS }),
    () => COMUNICADO,
  )

/** Copiloto: mensagens = [{papel:'usuario'|'assistente', texto}] → { resposta, ferramentas, origem, modelo } */
export const chat = (mensagens, unidade = 'rj', agora) =>
  comFallback(
    () => pedir('/api/chat', { metodo: 'POST', corpo: { mensagens, unidade, agora }, timeout: TIMEOUT_IA_MS }),
    () => ({ resposta: 'Sem conexão com o motor agora. Tente de novo em instantes.', ferramentas: [], origem: 'previa' }),
  )

export const reconhecerAlerta = (id) => acao(`/api/alertas/${id}/reconhecer`, { metodo: 'POST' })

/** Upload universal (CSV, XLSX, JSON, NDJSON, log, ICS, PDF, DOCX, imagem) → relatório de ingestão */
export function enviarArquivo(arquivo, { unidade = 'rj', dica } = {}) {
  const form = new FormData()
  form.append('arquivo', arquivo)
  form.append('unidade', unidade)
  if (dica) form.append('dica', dica)
  return acao('/api/ingestao/arquivo', { metodo: 'POST', form })
}

export const enviarTexto = (texto, { unidade = 'rj', dica } = {}) =>
  acao('/api/ingestao/texto', { metodo: 'POST', corpo: { texto, unidade, dica } })

export const enviarMetricas = (pontos, unidade = 'rj') =>
  acao(`/api/ingestao/metricas${q({ unidade })}`, { metodo: 'POST', corpo: pontos })

// ---------- tempo real (SSE) ----------

/** Assina alertas ao vivo. handlers: { snapshot(lista), alerta(a), ingestao(rel), erro() }. Devolve cancelar(). */
export function assinarAlertas(handlers, unidade = 'rj') {
  if (typeof EventSource === 'undefined') return () => {}
  const fonte = new EventSource(`${BASE}/api/alertas/stream${q({ unidade })}`)
  for (const tipo of ['snapshot', 'alerta', 'ingestao']) {
    fonte.addEventListener(tipo, (e) => handlers[tipo]?.(JSON.parse(e.data)))
  }
  fonte.onerror = () => handlers.erro?.()
  return () => fonte.close()
}

/** Replay ao vivo de um dia com surpresa de carga: handlers { inicio, ponto, alerta, fim, erro }. Devolve cancelar(). */
export function simularAoVivo(handlers, { unidade = 'rj', data = '2026-11-12', inicio = '16:00', fim = '22:00', passoMs = 1200, surpresa = 1.35, surpresaDesde = '17:30' } = {}) {
  if (typeof EventSource === 'undefined') return () => {}
  const fonte = new EventSource(
    `${BASE}/api/simulacao/ao-vivo${q({ unidade, data, inicio, fim, passo_ms: passoMs, surpresa, surpresa_desde: surpresaDesde })}`,
  )
  for (const tipo of ['inicio', 'ponto', 'alerta']) {
    fonte.addEventListener(tipo, (e) => handlers[tipo]?.(JSON.parse(e.data)))
  }
  fonte.addEventListener('fim', (e) => {
    handlers.fim?.(JSON.parse(e.data))
    fonte.close()
  })
  fonte.onerror = () => {
    handlers.erro?.()
    fonte.close()
  }
  return () => fonte.close()
}
