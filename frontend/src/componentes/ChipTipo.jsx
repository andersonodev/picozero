// frontend/src/componentes/ChipTipo.jsx
import { TIPOS } from '../dados/previa'
import { corDoTipo } from '../tema'

export default function ChipTipo({ tipo, texto, hora }) {
  return (
    <span className="chip-ev" style={{ '--cor-ev': corDoTipo(tipo) }}>
      {hora && <span className="h">{hora}</span>}
      <span>{texto || TIPOS[tipo]}</span>
    </span>
  )
}
