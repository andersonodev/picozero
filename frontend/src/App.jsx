// frontend/src/App.jsx
// Shell do console: menu lateral (identidade Yduqs) + a tela ativa, com rota por hash.
import { useEffect, useState } from 'react'
import { CalendarDays, ClipboardCheck, Database, Gauge, Info, LayoutGrid, Moon, Sun, TriangleAlert } from 'lucide-react'
import { CONTEXTO, DIAS_RISCO, picoDoDia } from './dados/previa'
import { UNIDADE_PADRAO, unidadePorId } from './dados/unidades'
import { temaEscuroAtivo } from './tema'
import Overview from './telas/Overview'
import Calendario from './telas/Calendario'
import DiasRisco from './telas/DiasRisco'
import DetalheDia from './telas/DetalheDia'
import ProvaCarga from './telas/ProvaCarga'
import Fontes from './telas/Fontes'

const GRUPOS = [
  {
    nome: 'Operação',
    itens: [
      { chave: 'visao', nome: 'Visão geral', Icone: LayoutGrid },
      { chave: 'calendario', nome: 'Calendário', Icone: CalendarDays },
      { chave: 'riscos', nome: 'Dias críticos', Icone: TriangleAlert, contador: true },
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
    itens: [{ chave: 'fontes', nome: 'Fonte de dados', Icone: Database }],
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

// Dias de risco (RJ) cujo pico calculado passa da capacidade: o contador do menu.
const CRITICOS = DIAS_RISCO.filter((r) => picoDoDia(r.data).carga > CONTEXTO.capacidade).length

export default function App() {
  const [tela, setTela] = useState(telaDoHash)
  const [dia, setDia] = useState('2026-09-10')
  const [unidadeId, setUnidadeId] = useState(UNIDADE_PADRAO.id)
  const [escuro, setEscuro] = useState(temaEscuroAtivo)
  const unidade = unidadePorId(unidadeId)

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

        <div className="sb-contexto">
          <b>{CONTEXTO.instituicao} · {CONTEXTO.semestre}</b>
          <span>Portal do aluno · Yduqs</span>
        </div>

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
                  {contador && CRITICOS > 0 && (
                    <span className="sb-badge" aria-label={`${CRITICOS} dias acima da capacidade`}>{CRITICOS}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sb-rodape">
          <button className="sb-nota" onClick={() => setTela('fontes')}>
            <Info size={15} strokeWidth={2} aria-hidden="true" />
            <span>Prévia: calendário real do Ibmec RJ, histórico de acesso modelado.</span>
          </button>
          <button className="sb-item" onClick={alternarTema} title="Alternar tema claro/escuro">
            {escuro ? <Sun size={18} strokeWidth={1.8} aria-hidden="true" /> : <Moon size={18} strokeWidth={1.8} aria-hidden="true" />}
            <span className="rotulo-item">{escuro ? 'Tema claro' : 'Tema escuro'}</span>
          </button>
        </div>
      </aside>

      <div className="conteudo">
        <main className="pagina">
          {tela === 'visao' && <Overview unidade={unidade} setUnidadeId={setUnidadeId} abrirDia={abrirDia} irPara={setTela} />}
          {tela === 'calendario' && <Calendario dia={dia} abrirDia={abrirDia} />}
          {tela === 'riscos' && <DiasRisco abrirDia={abrirDia} />}
          {tela === 'dia' && <DetalheDia dia={dia} setDia={setDia} />}
          {tela === 'carga' && <ProvaCarga />}
          {tela === 'fontes' && <Fontes />}
        </main>
      </div>
    </div>
  )
}
