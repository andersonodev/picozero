// frontend/src/componentes/Assistente.jsx
// Assistente PicoZero: gaveta de chat à direita (layout inspirado no LibreChat).
// Pergunta ao POST /api/chat (Gemini com as ferramentas do motor ou, sem chave, regras do backend).
// Sem backend (prévia estática, rede fora, timeout, HTML no lugar de JSON) responde com
// assistente/regras.js sobre os dados da prévia. O texto do modelo nunca vira HTML: o markdown
// mínimo é montado como elementos React, e datas DD/MM de 2026 viram links para o dia.
import { Fragment, memo, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import {
  ArrowUp,
  Bot,
  Check,
  ChevronRight,
  ClipboardCheck,
  Copy,
  ExternalLink,
  Gauge,
  SquarePen,
  TrendingUp,
  TriangleAlert,
  Wrench,
  X,
} from 'lucide-react'
import { responderLocal } from '../assistente/regras'
import '../assistente/assistente.css'

// Mesma base do api/cliente.js: VITE_API_URL (build) ou PICOZERO_API_URL (runtime); vazio = mesma origem.
const API = (import.meta.env.VITE_API_URL || globalThis.PICOZERO_API_URL || '').replace(/\/$/, '')
const URL_LIBRECHAT = import.meta.env.VITE_LIBRECHAT_URL || ''
const LIBRECHAT = /^https?:\/\//i.test(URL_LIBRECHAT) ? URL_LIBRECHAT : null
// O backend usa o Gemini Pro com raciocínio alto e confere os números (até 50 s com uma correção).
// 75 s dá folga sobre os 50 s do backend; antes, com 60 s, a resposta às vezes chegava depois do corte.
const TEMPO_LIMITE_MS = 75000
const MAX_MENSAGENS = 20
const MAX_TEXTO = 4000
const LINHA_PX = 20
const MAX_LINHAS = 6
const RESPIRO_CAMPO_PX = 12 // padding vertical do textarea (6 + 6)
const ANO_LINKS = 2026
const AVISO_LIMITE = 'Muitas perguntas seguidas; tente de novo em alguns segundos.'
const AVISO_FALHA = {
  tempo: 'O backend está conectado, mas o Gemini demorou demais para responder. Tente de novo.',
  erro: 'O backend está conectado, mas falhou ao responder esta pergunta. Tente de novo.',
}

const SUGESTOES = [
  { texto: 'Qual é o pior dia do semestre?', Icone: TrendingUp },
  { texto: 'O que fazer em 10/09?', Icone: ClipboardCheck },
  { texto: 'Quais os próximos dias críticos?', Icone: TriangleAlert },
  { texto: 'Quanto a fila virtual reduz a latência?', Icone: Gauge },
]

const SUBTITULO = {
  gemini: 'Gemini · conectado ao motor',
  regras: 'Motor do PicoZero · respostas por regras',
  previa: 'Prévia local · sem backend',
}

let sequencia = 0
const novoId = () => `msg-${++sequencia}`

// ---------- Backend ----------

// Últimas ≤ 20 mensagens válidas, começando por uma do usuário (o Gemini espera essa ordem).
function montarHistorico(lista) {
  const hist = lista
    .filter((m) => !m.aviso && !m.falhou && m.texto && m.texto.trim())
    .slice(-MAX_MENSAGENS)
    .map((m) => ({ papel: m.papel, texto: m.texto.slice(0, MAX_TEXTO) }))
  while (hist.length && hist[0].papel !== 'usuario') hist.shift()
  return hist
}

// O backend responde? (/api/saude em até 3 s). Distingue "desligado" de "ligado, mas falhou".
async function backendNoAr() {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 3000)
  try {
    const res = await fetch(`${API}/api/saude`, { signal: ctrl.signal, headers: { Accept: 'application/json' } })
    return res.ok && (res.headers.get('content-type') || '').includes('json')
  } catch {
    return false
  } finally {
    clearTimeout(timer)
  }
}

// null = backend desligado (rede fora, proxy sem backend, HTML da SPA): quem chama usa a prévia local.
// { falha: 'tempo' | 'erro' } = backend no ar, mas esta pergunta não teve resposta: quem chama mostra aviso.
async function perguntarApi(mensagens, unidade, sinal) {
  let res
  try {
    res = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ mensagens, unidade }),
      signal: sinal,
    })
  } catch (e) {
    if (e?.name === 'AbortError') return { falha: 'tempo' }
    return (await backendNoAr()) ? { falha: 'erro' } : null
  }
  try {
    if (res.status === 429) return { limitado: true }
    const ehJson = (res.headers.get('content-type') || '').includes('json')
    if (!res.ok || !ehJson) {
      // Erro em JSON vem do próprio backend; texto ou HTML pode ser o proxy do Vite sem backend.
      if (ehJson) return { falha: 'erro' }
      return (await backendNoAr()) ? { falha: 'erro' } : null
    }
    const dados = await res.json()
    if (!dados || typeof dados.resposta !== 'string' || !dados.resposta.trim()) return { falha: 'erro' }
    return {
      resposta: dados.resposta,
      ferramentas: Array.isArray(dados.ferramentas) ? dados.ferramentas.filter((f) => f && typeof f === 'object') : [],
      origem: dados.origem === 'gemini' ? 'gemini' : 'regras',
      modelo: typeof dados.modelo === 'string' ? dados.modelo : null,
      conferida: dados.dados?.conferencia?.ok === true,
    }
  } catch {
    return { falha: 'erro' } // o backend respondeu, mas o corpo não era o esperado
  }
}

function rotuloModelo(modelo) {
  const limpo = String(modelo || '').replace(/^models\//i, '').replace(/^gemini[-_ ]?/i, '')
  if (!limpo) return 'Gemini'
  const partes = limpo
    .split(/[-_ ]+/)
    .filter(Boolean)
    .map((p) => (/^[a-z]/.test(p) ? p[0].toUpperCase() + p.slice(1) : p))
  return `Gemini ${partes.join(' ')}`
}

function rotuloOrigem(m) {
  if (m.origem === 'gemini') return rotuloModelo(m.modelo)
  if (m.origem === 'previa') return 'prévia local'
  return 'regras do motor'
}

async function copiarTexto(texto) {
  try {
    await navigator.clipboard.writeText(texto)
    return
  } catch {
    /* sem Clipboard API (contexto inseguro ou permissão): método antigo */
  }
  const ativo = document.activeElement
  const area = document.createElement('textarea')
  area.value = texto
  area.setAttribute('readonly', '')
  area.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none'
  document.body.appendChild(area)
  area.select()
  const ok = document.execCommand('copy')
  area.remove()
  if (ativo instanceof HTMLElement) ativo.focus()
  if (!ok) throw new Error('cópia recusada')
}

// ---------- Markdown mínimo (sem HTML cru) ----------

const RE_INLINE = /(`[^`\n]+`|\*\*[^*\n]+?\*\*|\*[^*\s][^*\n]*?\*)/g
const RE_DATA = /\b(\d{2})\/(\d{2})(?:\/(\d{4}|\d{2}))?\b/g

function isoLinkavel(dd, mm, aa) {
  const ano = !aa ? ANO_LINKS : aa.length === 2 ? 2000 + Number(aa) : Number(aa)
  if (ano !== ANO_LINKS) return null
  const dt = new Date(ano, Number(mm) - 1, Number(dd))
  if (dt.getMonth() !== Number(mm) - 1 || dt.getDate() !== Number(dd)) return null
  return `${ano}-${mm}-${dd}`
}

function comDatas(texto, aoClicarData, chave) {
  if (!aoClicarData || !texto) return texto
  const partes = []
  let ultimo = 0
  for (const m of texto.matchAll(RE_DATA)) {
    const iso = isoLinkavel(m[1], m[2], m[3])
    if (!iso) continue
    if (m.index > ultimo) partes.push(texto.slice(ultimo, m.index))
    partes.push(
      <button
        key={`${chave}-${m.index}`}
        type="button"
        className="chat-data"
        onClick={() => aoClicarData(iso)}
        title={`Abrir ${m[1]}/${m[2]} no PicoZero`}
      >
        {m[0]}
      </button>,
    )
    ultimo = m.index + m[0].length
  }
  if (!partes.length) return texto
  if (ultimo < texto.length) partes.push(texto.slice(ultimo))
  return partes
}

function inline(texto, aoClicarData, chave) {
  const out = []
  let ultimo = 0
  const solto = (s) => {
    const k = `${chave}.${out.length}`
    out.push(<Fragment key={k}>{comDatas(s, aoClicarData, k)}</Fragment>)
  }
  for (const m of texto.matchAll(RE_INLINE)) {
    if (m.index > ultimo) solto(texto.slice(ultimo, m.index))
    const tok = m[0]
    const k = `${chave}.${out.length}`
    if (tok.startsWith('`')) out.push(<code key={k}>{tok.slice(1, -1)}</code>)
    else if (tok.startsWith('**')) out.push(<strong key={k}>{comDatas(tok.slice(2, -2), aoClicarData, k)}</strong>)
    else out.push(<em key={k}>{comDatas(tok.slice(1, -1), aoClicarData, k)}</em>)
    ultimo = m.index + tok.length
  }
  if (ultimo < texto.length) solto(texto.slice(ultimo))
  return out
}

// Parágrafos (linha em branco), quebras de linha, listas "- " / "* " / "• " / "1. " e títulos "#".
function paraBlocos(texto) {
  const blocos = []
  let paragrafo = []
  let lista = null
  const fecharParagrafo = () => {
    if (paragrafo.length) blocos.push({ tipo: 'p', linhas: paragrafo })
    paragrafo = []
  }
  const fecharLista = () => {
    if (lista) blocos.push(lista)
    lista = null
  }
  for (const bruta of String(texto).replace(/\r\n?/g, '\n').split('\n')) {
    const linha = bruta.trimEnd()
    let m
    if (!linha.trim()) {
      fecharParagrafo()
      fecharLista()
    } else if ((m = linha.match(/^\s*[-*•]\s+(.*)$/))) {
      fecharParagrafo()
      if (lista?.tipo !== 'ul') {
        fecharLista()
        lista = { tipo: 'ul', itens: [] }
      }
      lista.itens.push(m[1])
    } else if ((m = linha.match(/^\s*(\d{1,3})[.)]\s+(.*)$/))) {
      fecharParagrafo()
      if (lista?.tipo !== 'ol') {
        fecharLista()
        lista = { tipo: 'ol', inicio: Number(m[1]), itens: [] }
      }
      lista.itens.push(m[2])
    } else if ((m = linha.match(/^\s*#{1,6}\s+(.*)$/))) {
      fecharParagrafo()
      fecharLista()
      blocos.push({ tipo: 'h', texto: m[1] })
    } else {
      fecharLista()
      paragrafo.push(linha.trim())
    }
  }
  fecharParagrafo()
  fecharLista()
  return blocos
}

function renderizar(texto, aoClicarData) {
  return paraBlocos(texto).map((b, i) => {
    const k = `b${i}`
    if (b.tipo === 'ul' || b.tipo === 'ol') {
      const Lista = b.tipo
      return (
        <Lista key={k} start={b.tipo === 'ol' && b.inicio !== 1 ? b.inicio : undefined}>
          {b.itens.map((item, j) => (
            <li key={j}>{inline(item, aoClicarData, `${k}.${j}`)}</li>
          ))}
        </Lista>
      )
    }
    if (b.tipo === 'h') {
      return (
        <p key={k} className="chat-h">
          {inline(b.texto, aoClicarData, k)}
        </p>
      )
    }
    return (
      <p key={k}>
        {b.linhas.map((linha, j) => (
          <Fragment key={j}>
            {j > 0 && <br />}
            {inline(linha, aoClicarData, `${k}.${j}`)}
          </Fragment>
        ))}
      </p>
    )
  })
}

// ---------- Peças ----------

function Avatar({ tamanho = 'p' }) {
  return (
    <span className={`chat-avatar ${tamanho}`} aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  )
}

function Vazio({ aoEscolher }) {
  return (
    <div className="chat-vazio">
      <Avatar tamanho="g" />
      <h3>Como posso ajudar?</h3>
      <p>Pergunte sobre picos, dias críticos e planos do semestre 2026.2.</p>
      <div className="chat-sugestoes">
        {SUGESTOES.map(({ texto, Icone }) => (
          <button key={texto} type="button" className="chat-sugestao" onClick={() => aoEscolher(texto)}>
            <Icone size={16} strokeWidth={1.9} aria-hidden="true" />
            <span>{texto}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

const MensagemUsuario = memo(function MensagemUsuario({ texto }) {
  return (
    <div className="chat-msg usuario">
      <span className="chat-sr">Você:</span>
      <div className="chat-bolha">{texto}</div>
    </div>
  )
})

function Ferramentas({ itens }) {
  const [aberto, setAberto] = useState(false)
  const id = useId()
  const n = itens.length
  return (
    <div className="chat-ferr">
      <button
        type="button"
        className="chat-ferr-botao"
        aria-expanded={aberto}
        aria-controls={id}
        onClick={() => setAberto((v) => !v)}
      >
        <Wrench size={13} strokeWidth={2} aria-hidden="true" />
        Consultou {n} {n === 1 ? 'ferramenta' : 'ferramentas'}
        <ChevronRight size={14} className="chat-seta" aria-hidden="true" />
      </button>
      <ul className="chat-ferr-lista" id={id} hidden={!aberto}>
        {itens.map((f, i) => (
          <li key={i}>
            <code>{String(f.etapa ?? 'ferramenta')}</code>
            {f.detalhe ? <span>{String(f.detalhe)}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function BotaoCopiar({ texto }) {
  const [copiado, setCopiado] = useState(false)
  const timer = useRef(0)
  useEffect(() => () => clearTimeout(timer.current), [])

  async function copiar() {
    try {
      await copiarTexto(texto)
      setCopiado(true)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopiado(false), 1500)
    } catch {
      /* sem permissão para a área de transferência */
    }
  }

  const rotulo = copiado ? 'Resposta copiada' : 'Copiar resposta'
  return (
    <button type="button" className="chat-icone p" onClick={copiar} aria-label={rotulo} title={rotulo}>
      {copiado ? <Check size={14} strokeWidth={2.2} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
    </button>
  )
}

const MensagemAssistente = memo(function MensagemAssistente({ m, aoClicarData }) {
  return (
    <div className="chat-msg ia">
      <Avatar />
      <div className="chat-corpo">
        <span className="chat-sr">Assistente:</span>
        <div className="chat-texto">{renderizar(m.texto, aoClicarData)}</div>
        {m.ferramentas?.length > 0 && <Ferramentas itens={m.ferramentas} />}
        <div className="chat-meta">
          {m.origem === 'gemini' && (
            <span className="chat-tag-ia">
              <Bot size={13} strokeWidth={2} aria-hidden="true" />
              Gerado por IA
            </span>
          )}
          {m.conferida && (
            <span className="chat-tag-ia" title="Cada número, data e horário da resposta foi conferido com o que as ferramentas devolveram">
              <Check size={13} strokeWidth={2} aria-hidden="true" />
              Conferido com os dados
            </span>
          )}
          <span className="chat-origem" title={m.modelo || undefined}>
            <i className={`chat-ponto ${m.origem}`} aria-hidden="true" />
            <span className="chat-sr">Origem: </span>
            {rotuloOrigem(m)}
          </span>
          <BotaoCopiar texto={m.texto} />
        </div>
      </div>
    </div>
  )
})

function Aviso({ texto, aoRepetir, desabilitado }) {
  return (
    <div className="chat-aviso">
      <span>{texto}</span>
      {aoRepetir && (
        <button type="button" onClick={aoRepetir} disabled={desabilitado}>
          Tentar de novo
        </button>
      )}
    </div>
  )
}

function Digitando() {
  return (
    <div className="chat-msg ia">
      <Avatar />
      <div className="chat-corpo">
        <span className="chat-digitando" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="chat-sr">O assistente está respondendo…</span>
      </div>
    </div>
  )
}

// ---------- Painel ----------

/**
 * @param {{ aberto: boolean, aoFechar?: () => void, unidade?: string, irParaDia?: (iso: string) => void }} props
 * Mantenha o componente montado e alterne `aberto`: a conversa sobrevive a fechar e abrir.
 */
export default function Assistente({ aberto, aoFechar, unidade = 'rj', irParaDia }) {
  const [mensagens, setMensagens] = useState([])
  const [rascunho, setRascunho] = useState('')
  const [carregando, setCarregando] = useState(false)
  const painelRef = useRef(null)
  const rolagemRef = useRef(null)
  const campoRef = useRef(null)
  const pedidoRef = useRef(null) // AbortController da pergunta em andamento
  const geracaoRef = useRef(0) // muda em "Nova conversa": respostas atrasadas são descartadas
  const ocupadoRef = useRef(false)

  // Ao abrir, foco no campo; ao fechar, o foco volta para quem abriu.
  useEffect(() => {
    if (!aberto) return undefined
    const anterior = document.activeElement
    const quadro = requestAnimationFrame(() => campoRef.current?.focus())
    return () => {
      cancelAnimationFrame(quadro)
      if (anterior instanceof HTMLElement && anterior.isConnected) anterior.focus()
    }
  }, [aberto])

  // Esc fecha (a menos que um modal esteja por cima).
  useEffect(() => {
    if (!aberto) return undefined
    function tecla(e) {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      const modal = document.querySelector('[aria-modal="true"]')
      if (modal && !painelRef.current?.contains(modal)) return
      aoFechar?.()
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [aberto, aoFechar])

  useEffect(() => {
    const el = rolagemRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [mensagens, carregando, aberto])

  // Textarea cresce de 1 a 6 linhas.
  useLayoutEffect(() => {
    const el = campoRef.current
    if (!el) return
    const max = LINHA_PX * MAX_LINHAS + RESPIRO_CAMPO_PX
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, max)}px`
    el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden'
  }, [rascunho, aberto])

  useEffect(
    () => () => {
      geracaoRef.current += 1
      pedidoRef.current?.abort()
    },
    [],
  )

  const abrirDia = useCallback(
    (iso) => {
      irParaDia?.(iso)
      // Em tela estreita a gaveta cobre o app: fecha para mostrar o dia (a conversa fica).
      if (window.matchMedia?.('(max-width: 640px)').matches) aoFechar?.()
    },
    [irParaDia, aoFechar],
  )
  const aoClicarData = irParaDia ? abrirDia : null

  async function enviar(bruto, base = mensagens) {
    const texto = String(bruto || '').trim().slice(0, MAX_TEXTO)
    if (!texto || ocupadoRef.current) return
    ocupadoRef.current = true
    const pergunta = { id: novoId(), papel: 'usuario', texto }
    const lista = [...base, pergunta]
    setMensagens(lista)
    setRascunho('')
    setCarregando(true)

    const geracao = geracaoRef.current
    const ctrl = new AbortController()
    pedidoRef.current = ctrl
    const prazo = setTimeout(() => ctrl.abort(), TEMPO_LIMITE_MS)
    const r = await perguntarApi(montarHistorico(lista), unidade || 'rj', ctrl.signal)
    clearTimeout(prazo)
    if (geracao !== geracaoRef.current) return // conversa reiniciada ou painel desmontado
    pedidoRef.current = null
    ocupadoRef.current = false

    if (r?.limitado || r?.falha) {
      const aviso = r.limitado ? AVISO_LIMITE : AVISO_FALHA[r.falha] || AVISO_FALHA.erro
      setMensagens((atual) => [
        ...atual.map((m) => (m.id === pergunta.id ? { ...m, falhou: true } : m)),
        { id: novoId(), papel: 'assistente', aviso: true, texto: aviso, repetir: texto, perguntaId: pergunta.id },
      ])
    } else {
      let resp = r
      if (!resp) {
        try {
          resp = responderLocal(texto, { unidade })
        } catch {
          resp = { resposta: 'Não consegui responder agora. Tente de novo.', ferramentas: [], origem: 'previa' }
        }
      }
      setMensagens((atual) => [
        ...atual,
        {
          id: novoId(),
          papel: 'assistente',
          texto: resp.resposta,
          ferramentas: resp.ferramentas || [],
          origem: resp.origem || 'previa',
          modelo: resp.modelo || null,
          conferida: resp.conferida === true,
        },
      ])
    }
    setCarregando(false)
  }

  function novaConversa() {
    geracaoRef.current += 1
    pedidoRef.current?.abort()
    pedidoRef.current = null
    ocupadoRef.current = false
    setMensagens([])
    setCarregando(false)
    setRascunho('')
    campoRef.current?.focus()
  }

  function tentarDeNovo(aviso) {
    enviar(
      aviso.repetir,
      mensagens.filter((m) => m.id !== aviso.id && m.id !== aviso.perguntaId),
    )
  }

  function aoTeclar(e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      enviar(rascunho)
    }
  }

  function escolherSugestao(texto) {
    enviar(texto)
    campoRef.current?.focus()
  }

  if (!aberto) return null

  const ultima = mensagens[mensagens.length - 1]
  const origemAtual = mensagens.findLast((m) => m.origem)?.origem
  const subtitulo = SUBTITULO[origemAtual] || 'Pronto para perguntas'
  const vazio = mensagens.length === 0 && !carregando

  return (
    <div ref={painelRef} className="chat-painel" role="dialog" aria-label="Assistente PicoZero">
      <header className="chat-cab">
        <Avatar tamanho="m" />
        <div className="chat-cab-texto">
          <h2 className="chat-titulo">Assistente PicoZero</h2>
          <p className="chat-sub">
            <i className={`chat-ponto ${origemAtual || ''}`} aria-hidden="true" />
            <span>{subtitulo}</span>
          </p>
        </div>
        <div className="chat-cab-acoes">
          {LIBRECHAT && (
            <a
              className="chat-icone"
              href={LIBRECHAT}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Abrir no LibreChat (nova aba)"
              title="Abrir no LibreChat"
            >
              <ExternalLink size={16} strokeWidth={1.9} aria-hidden="true" />
            </a>
          )}
          <button
            type="button"
            className="chat-icone"
            onClick={novaConversa}
            disabled={vazio}
            aria-label="Nova conversa"
            title="Nova conversa"
          >
            <SquarePen size={16} strokeWidth={1.9} aria-hidden="true" />
          </button>
          <button type="button" className="chat-icone" onClick={() => aoFechar?.()} aria-label="Fechar assistente" title="Fechar">
            <X size={18} strokeWidth={1.9} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div ref={rolagemRef} className="chat-rolagem">
        {vazio && <Vazio aoEscolher={escolherSugestao} />}
        <div className="chat-mensagens" role="log" aria-live="polite" aria-busy={carregando}>
          {mensagens.map((m) => {
            if (m.papel === 'usuario') return <MensagemUsuario key={m.id} texto={m.texto} />
            if (m.aviso) {
              return (
                <Aviso
                  key={m.id}
                  texto={m.texto}
                  aoRepetir={m === ultima && m.repetir ? () => tentarDeNovo(m) : null}
                  desabilitado={carregando}
                />
              )
            }
            return <MensagemAssistente key={m.id} m={m} aoClicarData={aoClicarData} />
          })}
          {carregando && <Digitando />}
        </div>
      </div>

      <form
        className="chat-compositor"
        onSubmit={(e) => {
          e.preventDefault()
          enviar(rascunho)
        }}
      >
        <div
          className="chat-caixa"
          onClick={(e) => {
            if (e.target === e.currentTarget) campoRef.current?.focus()
          }}
        >
          <textarea
            ref={campoRef}
            className="chat-campo"
            rows={1}
            value={rascunho}
            maxLength={MAX_TEXTO}
            placeholder="Pergunte ao assistente…"
            aria-label="Pergunta para o assistente"
            onChange={(e) => setRascunho(e.target.value)}
            onKeyDown={aoTeclar}
          />
          <button
            type="submit"
            className="chat-enviar"
            disabled={!rascunho.trim() || carregando}
            aria-label="Enviar pergunta"
            title="Enviar"
          >
            <ArrowUp size={17} strokeWidth={2.2} aria-hidden="true" />
          </button>
        </div>
        <p className="chat-nota">
          O assistente usa IA (Gemini) e pode errar. Os números vêm do motor de carga do PicoZero; confira antes de agir.
        </p>
      </form>
    </div>
  )
}
