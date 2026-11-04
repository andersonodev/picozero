// frontend/src/componentes/AvisoIA.jsx
// Aviso de IA: todo texto escrito por modelo leva este selo, dizendo se veio do Gemini,
// das regras do motor (IA fora do ar) ou da prévia. Números de carga nunca vêm do modelo.
import { Bot } from 'lucide-react'

const TEXTOS = {
  gemini: 'Gerado por IA (Gemini) · revise antes de agir',
  regras: 'Gerado pelas regras do motor (sem IA) · revise antes de agir',
  previa: 'Exemplo de saída da IA (prévia) · revise antes de agir',
}

export default function AvisoIA({ origem = 'previa', texto, compacto = false }) {
  const chave = TEXTOS[origem] ? origem : 'previa'
  return (
    <span
      className={`aviso-ia ${chave}`}
      title="Conteúdo gerado por IA pode conter erros. Os números de carga vêm do cálculo do motor, não do modelo."
    >
      <Bot size={13} strokeWidth={2} aria-hidden="true" />
      {compacto ? (chave === 'regras' ? 'Regras' : 'IA') : texto || TEXTOS[chave]}
    </span>
  )
}
