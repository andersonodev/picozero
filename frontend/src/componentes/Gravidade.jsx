// frontend/src/componentes/Gravidade.jsx
import { nivelDaGravidade } from '../tema'

export default function Gravidade({ valor }) {
  const nivel = nivelDaGravidade(valor)
  const cor = `var(--${nivel.chave})`
  return (
    <span className="gravidade" title={`Gravidade ${valor} de 5`}>
      <span className="barras" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((i) => (
          <span key={i} style={i <= valor ? { background: cor } : undefined} />
        ))}
      </span>
      {valor}/5 · {nivel.rotulo}
    </span>
  )
}
