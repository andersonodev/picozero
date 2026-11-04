// frontend/src/App.jsx
import { useEffect, useState } from 'react'
import { CONTEXTO, DIAS_RISCO, picoDoDia } from './dados/previa'
import { UNIDADE_PADRAO, UNIDADES, unidadePorId } from './dados/unidades'
import { temaEscuroAtivo } from './tema'
import Overview from './telas/Overview'
import DiasRisco from './telas/DiasRisco'
import DetalheDia from './telas/DetalheDia'
import ProvaCarga from './telas/ProvaCarga'
import { numero } from './util'

const TABS = [
  { chave: 'visao', nome: 'Visão geral' },
  { chave: 'riscos', nome: 'Dias críticos' },
  { chave: 'dia', nome: 'Plano do dia' },
  { chave: 'carga', nome: 'Prova de carga' },
]

// Tema persistido; começa claro (melhor em projetor), respeita escolha anterior.
try {
  if (localStorage.getItem('picozero-tema') === 'escuro') document.documentElement.classList.add('tema-escuro')
} catch { /* sem storage */ }

function telaDoHash() {
  const c = window.location.hash.slice(1)
  return TABS.some((t) => t.chave === c) ? c : 'visao'
}

export default function App() {
  const [tela, setTela] = useState(telaDoHash)
  const [dia, setDia] = useState('2027-03-10')
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

  // Farol da operação: dias de risco (RJ) que passam da capacidade.
  const criticos = DIAS_RISCO.filter((r) => picoDoDia(r.data).carga > CONTEXTO.capacidade).length

  return (
    <>
      <header className="appbar">
        <div className="marca">
          <div className="marca-glifo" aria-hidden="true">
            <span>
              <i style={{ height: 5 }} />
              <i style={{ height: 9 }} />
              <i style={{ height: 14 }} />
              <i style={{ height: 7 }} />
            </span>
          </div>
          <div>
            <div className="marca-nome">PicoZero</div>
            <div className="marca-sub">Console de capacidade · Yduqs</div>
          </div>
        </div>

        <div className="appbar-sep" />

        <nav className="tabs" aria-label="Seções">
          {TABS.map((t, i) => (
            <button
              key={t.chave}
              className={`tab ${tela === t.chave ? 'ativo' : ''}`}
              onClick={() => setTela(t.chave)}
              aria-current={tela === t.chave ? 'page' : undefined}
            >
              <span className="ix">{String(i + 1).padStart(2, '0')}</span>
              <span>{t.nome}</span>
            </button>
          ))}
        </nav>

        <div className="appbar-dir">
          <span className={`status-pill ${criticos > 0 ? 'risco' : 'ok'}`}>
            <span className="farol" />
            {criticos > 0 ? `${criticos} dias críticos` : 'operação estável'}
          </span>
          <label className="select" title="Unidade (edital: RJ, SP, BH, DF)">
            <span className="mono" style={{ fontSize: 11, color: 'var(--mudo)' }}>unidade</span>
            <select value={unidadeId} onChange={(e) => setUnidadeId(e.target.value)}>
              {UNIDADES.map((u) => (
                <option key={u.id} value={u.id}>{u.curto} · {numero(u.alunos)} alunos</option>
              ))}
            </select>
          </label>
          <button className="icon-btn" onClick={alternarTema} aria-label="Alternar tema" title="Alternar tema claro/escuro">
            {escuro ? '☀' : '☾'}
          </button>
        </div>
      </header>

      <main className="pagina">
        {tela === 'visao' && <Overview unidade={unidade} abrirDia={abrirDia} />}
        {tela === 'riscos' && <DiasRisco abrirDia={abrirDia} />}
        {tela === 'dia' && <DetalheDia dia={dia} setDia={setDia} />}
        {tela === 'carga' && <ProvaCarga />}
      </main>
    </>
  )
}
