// frontend/src/componentes/FaixaSemestre.jsx
// Um traço por dia do semestre, no estilo das páginas de status (referência: Zendesk Status no Refero).
import { useState } from 'react'
import { CONTEXTO, DIAS_RISCO } from '../dados/previa'
import { nivelDaGravidade } from '../tema'
import { curta, diasEntre, mesNome, paraData, semana } from '../util'

const riscos = Object.fromEntries(DIAS_RISCO.map((r) => [r.data, r]))
const feriados = Object.fromEntries(CONTEXTO.feriados.map((f) => [f.data, f.nome]))

function fimDeSemana(iso) {
  const d = paraData(iso).getDay()
  return d === 0 || d === 6
}

function cor(iso) {
  const r = riscos[iso]
  if (r) return `var(--${nivelDaGravidade(r.gravidade).chave})`
  if (feriados[iso]) return 'var(--mudo)'
  if (fimDeSemana(iso)) return 'var(--superficie-2)'
  return 'color-mix(in srgb, var(--bom) 45%, var(--superficie))'
}

function descricao(iso) {
  const r = riscos[iso]
  if (r) return `Gravidade ${r.gravidade}/5 · ${r.eventos.length} evento${r.eventos.length > 1 ? 's' : ''}`
  if (feriados[iso]) return `Feriado: ${feriados[iso]}`
  if (fimDeSemana(iso)) return 'Fim de semana'
  return 'Sem risco'
}

export default function FaixaSemestre({ onEscolher }) {
  const [dica, setDica] = useState(null)
  const dias = diasEntre(CONTEXTO.inicio, CONTEXTO.fim)
  const meses = []
  dias.forEach((d, i) => {
    if (i === 0 || d.endsWith('-01')) meses.push({ i, nome: mesNome(d) })
  })

  function mostrar(iso, i) {
    const x = Math.min(92, Math.max(8, ((i + 0.5) / dias.length) * 100))
    setDica({ iso, x })
  }

  return (
    <div className="faixa" onMouseLeave={() => setDica(null)}>
      <div className="faixa-barras">
        {dias.map((iso, i) => (
          <button
            key={iso}
            className={riscos[iso] ? 'risco' : ''}
            style={{ background: cor(iso) }}
            onMouseEnter={() => mostrar(iso, i)}
            onFocus={() => mostrar(iso, i)}
            onBlur={() => setDica(null)}
            onClick={() => riscos[iso] && onEscolher(iso)}
            aria-label={`${curta(iso)}, ${descricao(iso)}`}
            tabIndex={riscos[iso] ? 0 : -1}
          />
        ))}
      </div>
      <div className="faixa-meses">
        {meses.map((m) => (
          <span key={m.i} style={{ left: `${(m.i / dias.length) * 100}%` }}>
            {m.nome}
          </span>
        ))}
      </div>
      {dica && (
        <div className="faixa-dica" style={{ left: `${dica.x}%` }}>
          <b>{curta(dica.iso)}</b> · {semana(dica.iso)}
          <div>{descricao(dica.iso)}</div>
          {riscos[dica.iso] && <div style={{ opacity: 0.75 }}>Clique para abrir o plano</div>}
        </div>
      )}
    </div>
  )
}
