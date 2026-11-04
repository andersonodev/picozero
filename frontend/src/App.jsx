// frontend/src/App.jsx
// Shell do console: menu lateral (identidade Yduqs) com a unidade, o estado da conexão com o
// motor e o assistente; a tela ativa recebe os dados-base da API (ou da prévia, sem backend).
import { useEffect, useState } from 'react'
import {
  BellRing,
  Bot,
  CalendarDays,
  ChevronsUpDown,
  ClipboardCheck,
  Database,
  Gauge,
  LayoutGrid,
  MessageSquareText,
  Moon,
  Sun,
  TriangleAlert,
  Upload,
} from 'lucide-react'
import { UNIDADE_PADRAO, UNIDADES, unidadePorId } from './dados/unidades'
import { usarBase } from './dados/usarBase'
import { temaEscuroAtivo } from './tema'
import { numero } from './util'
import Overview from './telas/Overview'
import Calendario from './telas/Calendario'
import DiasRisco from './telas/DiasRisco'
import DetalheDia from './telas/DetalheDia'
import ProvaCarga from './telas/ProvaCarga'
import Fontes from './telas/Fontes'
import Alertas from './telas/Alertas'
import Entrada from './telas/Entrada'
import Assistente from './componentes/Assistente'

const GRUPOS = [
  {
    nome: 'Operação',
    itens: [
      { chave: 'visao', nome: 'Visão geral', Icone: LayoutGrid },
      { chave: 'calendario', nome: 'Calendário', Icone: CalendarDays },
      { chave: 'riscos', nome: 'Dias críticos', Icone: TriangleAlert, contador: true },
      { chave: 'alertas', nome: 'Alertas ao vivo', Icone: BellRing },
    ],
  },
  {
    nome: 'Ação',
    itens: [
      { chave: 'dia', nome: 'Plano do dia', Icone: ClipboardCheck },
      { chave: 'carga', nome: 'Prova de carga', Icone: Gauge },
    ],
  },
  {
    nome: 'Dados',
    itens: [
      { chave: 'fontes', nome: 'Fonte de dados', Icone: Database },
      { chave: 'entrada', nome: 'Entrada de dados', Icone: Upload },
    ],
  },
]
const TELAS = GRUPOS.flatMap((g) => g.itens.map((i) => i.chave))

// Tema persistido; começa claro (melhor em projetor), respeita escolha anterior.
try {
  if (localStorage.getItem('picozero-tema') === 'escuro') document.documentElement.classList.add('tema-escuro')
} catch { /* sem storage */ }

function telaDoHash() {
  const c = window.location.hash.slice(1)
  return TELAS.includes(c) ? c : 'visao'
}

function Carregando() {
  return (
    <div className="esqueleto" aria-busy="true" aria-label="Carregando dados do motor">
      <div className="esq-linha" style={{ width: 260, height: 30 }} />
      <div className="esq-linha" style={{ width: 420, height: 14, marginTop: 10 }} />
      <div className="grade g-4" style={{ marginTop: 24 }}>
        {[0, 1, 2, 3].map((i) => <div key={i} className="esq-bloco" style={{ height: 112 }} />)}
      </div>
      <div className="esq-bloco" style={{ height: 380, marginTop: 16 }} />
    </div>
  )
}

export default function App() {
  const [tela, setTela] = useState(telaDoHash)
  const [dia, setDia] = useState('2026-09-10')
  const [unidadeId, setUnidadeId] = useState(UNIDADE_PADRAO.id)
  const [escuro, setEscuro] = useState(temaEscuroAtivo)
  const [assistente, setAssistente] = useState(false)
  const unidade = unidadePorId(unidadeId)
  const base = usarBase(unidadeId)
  const dados = base.dados

  useEffect(() => {
    if (window.location.hash.slice(1) !== tela) window.location.hash = tela
    window.scrollTo(0, 0)
  }, [tela])

  useEffect(() => {
    const ir = () => setTela(telaDoHash())
    window.addEventListener('hashchange', ir)
    return () => window.removeEventListener('hashchange', ir)
  }, [])

  function alternarTema() {
    const alvo = !escuro
    document.documentElement.classList.toggle('tema-escuro', alvo)
    try { localStorage.setItem('picozero-tema', alvo ? 'escuro' : 'claro') } catch { /* */ }
    setEscuro(alvo)
  }

  function abrirDia(d) {
    setDia(d)
    setTela('dia')
  }

  const cap = dados?.contexto?.capacidade
  const criticos = dados ? dados.riscos.filter((r) => r.pico.carga > cap).length : 0
  const conectado = base.origem === 'api'
  const ia = dados?.contexto?.ia

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sb-marca">
          <span className="sb-logo" aria-hidden="true">
            <i style={{ height: 11 }} />
            <i style={{ height: 22 }} />
            <i style={{ height: 15 }} />
          </span>
          <span className="sb-nome">PicoZero</span>
        </div>

        <label className="sb-unidade" title="Unidade (edital: RJ, SP, BH e DF)">
          <span className="sb-unidade-txt">
            <b>Ibmec {unidade.curto} · {dados?.contexto?.semestre || '2026.2'}</b>
            <span>{unidade.nome} · {numero(unidade.alunos)} alunos</span>
          </span>
          <ChevronsUpDown size={16} aria-hidden="true" />
          <select value={unidadeId} onChange={(e) => setUnidadeId(e.target.value)} aria-label="Unidade">
            {UNIDADES.map((u) => (
              <option key={u.id} value={u.id}>Ibmec {u.curto} · {u.nome}</option>
            ))}
          </select>
        </label>

        <nav className="sb-nav" aria-label="Seções">
          {GRUPOS.map((g) => (
            <div key={g.nome} className="sb-grupo">
              <div className="sb-grupo-rot">{g.nome}</div>
              {g.itens.map(({ chave, nome, Icone, contador }) => (
                <button
                  key={chave}
                  className={`sb-item ${tela === chave ? 'ativo' : ''}`}
                  onClick={() => setTela(chave)}
                  aria-current={tela === chave ? 'page' : undefined}
                  title={nome}
                >
                  <Icone size={18} strokeWidth={1.8} aria-hidden="true" />
                  <span className="rotulo-item">{nome}</span>
                  {contador && criticos > 0 && (
                    <span className="sb-badge" aria-label={`${criticos} dias acima da capacidade`}>{criticos}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
          <div className="sb-grupo">
            <div className="sb-grupo-rot">IA</div>
            <button className={`sb-item ${assistente ? 'ativo' : ''}`} onClick={() => setAssistente((a) => !a)} title="Assistente">
              <MessageSquareText size={18} strokeWidth={1.8} aria-hidden="true" />
              <span className="rotulo-item">Assistente</span>
            </button>
          </div>
        </nav>

        <div className="sb-rodape">
          <button className="sb-status" onClick={() => setTela('fontes')} title="Ver a origem dos dados">
            <span className={`sb-ponto ${base.carregando && !dados ? 'carregando' : conectado ? 'ok' : 'previa'}`} />
            <span>
              <b>{base.carregando && !dados ? 'Conectando ao motor…' : conectado ? 'Motor conectado' : 'Prévia local'}</b>
              <span>
                {conectado
                  ? ia === 'gemini' ? 'IA: Gemini ativo' : 'IA: modo regras (sem chave)'
                  : 'calendário real · histórico modelado'}
              </span>
            </span>
          </button>
          <button className="sb-item" onClick={alternarTema} title="Alternar tema claro/escuro">
            {escuro ? <Sun size={18} strokeWidth={1.8} aria-hidden="true" /> : <Moon size={18} strokeWidth={1.8} aria-hidden="true" />}
            <span className="rotulo-item">{escuro ? 'Tema claro' : 'Tema escuro'}</span>
          </button>
        </div>
      </aside>

      <div className="conteudo">
        <main className="pagina">
          {!dados ? (
            <Carregando />
          ) : (
            <>
              {tela === 'visao' && <Overview base={dados} unidade={unidadeId} abrirDia={abrirDia} irPara={setTela} />}
              {tela === 'calendario' && <Calendario base={dados} unidade={unidadeId} dia={dia} abrirDia={abrirDia} />}
              {tela === 'riscos' && <DiasRisco base={dados} unidade={unidadeId} abrirDia={abrirDia} />}
              {tela === 'dia' && <DetalheDia base={dados} unidade={unidadeId} dia={dia} setDia={setDia} />}
              {tela === 'carga' && <ProvaCarga unidade={unidadeId} />}
              {tela === 'fontes' && <Fontes unidade={unidadeId} />}
              {tela === 'alertas' && <Alertas unidade={unidadeId} abrirDia={abrirDia} />}
              {tela === 'entrada' && <Entrada unidade={unidadeId} />}
            </>
          )}
        </main>
      </div>

      {!assistente && (
        <button className="fab-assistente" onClick={() => setAssistente(true)} aria-label="Abrir o assistente">
          <Bot size={18} aria-hidden="true" /> Perguntar ao assistente
        </button>
      )}
      <Assistente aberto={assistente} aoFechar={() => setAssistente(false)} unidade={unidadeId} irParaDia={abrirDia} />
    </div>
  )
}
