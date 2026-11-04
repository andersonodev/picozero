// frontend/src/componentes/ModalCrise.jsx
// Reagir: descreve a falha e mostra o Comunicado gerado (referências: OpenSea Status e Slack no Refero).
import { useEffect, useState } from 'react'
import { COMUNICADO, FALHA_EXEMPLO } from '../dados/previa'
import { completa, curta } from '../util'

export default function ModalCrise({ dia, onFechar }) {
  const [falha, setFalha] = useState(FALHA_EXEMPLO)
  const [estado, setEstado] = useState('editando') // editando | gerando | pronto

  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onFechar()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onFechar])

  function gerar() {
    setEstado('gerando')
    setTimeout(() => setEstado('pronto'), 1200)
  }

  return (
    <div className="fundo-modal" onClick={onFechar}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="titulo-crise" onClick={(e) => e.stopPropagation()}>
        <div className="cartao-topo">
          <div>
            <span className="rotulo">4 · Reagir · gerar_crise</span>
            <h3 id="titulo-crise" style={{ fontSize: 20, marginTop: 4 }}>Simular crise em {curta(dia)}</h3>
          </div>
          <button className="botao" onClick={onFechar}>Fechar</button>
        </div>

        <label className="rotulo" htmlFor="falha">O que falhou</label>
        <textarea id="falha" value={falha} onChange={(e) => setFalha(e.target.value)} />

        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12 }}>
          <button className="botao perigo" onClick={gerar} disabled={estado === 'gerando' || !falha.trim()}>
            Gerar comunicado com Gemini
          </button>
          {estado === 'gerando' && (
            <span className="meta" style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
              <span className="carregando" /> response_schema Comunicado · temperature 0.2
            </span>
          )}
        </div>

        {estado === 'pronto' && (
          <article className="comunicado">
            <header className="comunicado-topo">
              <span className="rotulo" style={{ color: 'inherit', opacity: 0.7 }}>Comunicado aos alunos</span>
              <h4>{COMUNICADO.titulo}</h4>
            </header>
            <div className="comunicado-corpo">
              <p style={{ margin: 0 }}>{COMUNICADO.mensagem}</p>
              <div className="prazo">
                <span className="rotulo">Novo prazo</span>
                <b>{completa(COMUNICADO.nova_data_prazo)}</b>
              </div>
              <ul>
                {COMUNICADO.regras_tolerancia.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          </article>
        )}
      </div>
    </div>
  )
}
