// frontend/src/componentes/Gravidade.jsx
// Gravidade 1–5 escrita pelo Gemini, em barras.
import { nivelDaGravidade } from '../tema'

export default function Gravidade({ valor }) {
  const nivel = nivelDaGravidade(valor)
  const cor = `var(--${nivel.chave})`
  return (
    <span className="gravidade" title={`Gravidade ${valor} de 5, atribuída pelo Gemini`}>
      <span className="barras" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((i) => (
          <span key={i} style={i <= valor ? { background: cor } : undefined} />
        ))}
      </span>
      {valor} de 5 · {nivel.rotulo}
    </span>
  )
}
