// frontend/src/componentes/ModalCrise.jsx
// Reagir: descreve a falha e mostra o Comunicado gerado (referências: OpenSea Status e Slack no Refero).
import { useEffect, useState } from 'react'
import { FileText, X } from 'lucide-react'
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
        <div className="modal-cab">
          <div>
            <h2 id="titulo-crise">Simular crise em {curta(dia)}</h2>
            <p>Reagir · o Gemini escreve o comunicado aos alunos e as regras de tolerância</p>
          </div>
          <button className="icone-btn" onClick={onFechar} aria-label="Fechar">
            <X size={17} aria-hidden="true" />
          </button>
        </div>

        <div className="modal-corpo">
          <label htmlFor="falha">O que falhou</label>
          <textarea id="falha" value={falha} onChange={(e) => setFalha(e.target.value)} />

          <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
            <button className="botao perigo-cheio" onClick={gerar} disabled={estado === 'gerando' || !falha.trim()}>
              <FileText size={16} aria-hidden="true" /> Gerar comunicado com Gemini
            </button>
            {estado === 'gerando' && (
              <span className="gerando"><span className="spinner" /> response_schema Comunicado · temperature 0.2</span>
            )}
          </div>

          {estado === 'pronto' && (
            <article className="comunicado">
              <header className="comunicado-topo">
                <span>Comunicado aos alunos</span>
                <h3>{COMUNICADO.titulo}</h3>
              </header>
              <div className="comunicado-corpo">
                <p>{COMUNICADO.mensagem}</p>
                <div className="prazo">
                  <span>Novo prazo</span>
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
    </div>
  )
}
