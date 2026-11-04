// frontend/src/componentes/ChipTipo.jsx
import { TIPOS } from '../dados/previa'

export default function ChipTipo({ tipo, texto }) {
  return (
    <span className={`chip ${tipo}`}>
      <i />
      {texto || TIPOS[tipo]}
    </span>
  )
}
