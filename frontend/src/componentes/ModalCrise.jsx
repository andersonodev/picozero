// frontend/src/componentes/ModalCrise.jsx
// Reagir: descreve a falha e a IA escreve o comunicado aos alunos e as regras de tolerância.
// O texto sai como RASCUNHO com aviso de IA: alguém revisa antes de enviar.
import { useEffect, useState } from 'react'
import { FileText, X } from 'lucide-react'
import * as api from '../api/cliente'
import AvisoIA from './AvisoIA'
import { completa, curta } from '../util'

function falhaExemplo(dia) {
  return `Portal do aluno fora do ar das 10h05 às 10h50 de ${curta(dia)}, no meio do horário de maior acesso.`
}

export default function ModalCrise({ dia, unidade, onFechar }) {
  const [falha, setFalha] = useState(() => falhaExemplo(dia))
  const [estado, setEstado] = useState('editando') // editando | gerando | pronto
  const [comunicado, setComunicado] = useState(null)
  const [origem, setOrigem] = useState('previa')

  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onFechar()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onFechar])

  async function gerar() {
    setEstado('gerando')
    const r = await api.crise(dia, falha, unidade)
    setComunicado(r.dados)
    setOrigem(r.origem === 'api' ? r.dados?.origem || 'regras' : 'previa')
    setEstado('pronto')
  }

  return (
    <div className="fundo-modal" onClick={onFechar}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="titulo-crise" onClick={(e) => e.stopPropagation()}>
        <div className="modal-cab">
          <div>
            <h2 id="titulo-crise">Simular crise em {curta(dia)}</h2>
            <p>Reagir · a IA escreve o comunicado aos alunos e as regras de tolerância</p>
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
              <span className="gerando"><span className="spinner" /> escrevendo o comunicado…</span>
            )}
          </div>

          {estado === 'pronto' && comunicado && (
            <>
              <div style={{ marginTop: 16 }}>
                <AvisoIA origem={origem} texto={origem === 'regras' ? undefined : 'Rascunho gerado por IA · revise antes de enviar aos alunos'} />
              </div>
              <article className="comunicado">
                <header className="comunicado-topo">
                  <span>Comunicado aos alunos · rascunho</span>
                  <h3>{comunicado.titulo}</h3>
                </header>
                <div className="comunicado-corpo">
                  <p>{comunicado.mensagem}</p>
                  {comunicado.nova_data_prazo && (
                    <div className="prazo">
                      <span>Novo prazo</span>
                      <b>{completa(comunicado.nova_data_prazo)}</b>
                    </div>
                  )}
                  <ul>
                    {(comunicado.regras_tolerancia || []).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              </article>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
