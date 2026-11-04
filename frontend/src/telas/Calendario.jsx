// frontend/src/telas/Calendario.jsx
// Calendário acadêmico real do Ibmec RJ 2026.2 (grade mensal) com os eventos sobre ele.
// Os dias que o Gemini marcou como risco ficam destacados e abrem o plano ao clicar.
import { useMemo } from 'react'
import ChipTipo from '../componentes/ChipTipo'
import { CONTEXTO, DIAS_RISCO, EVENTOS, MARCOS, TIPOS } from '../dados/previa'
import { nivelDaGravidade } from '../tema'
import { completa, curta, diasEntre, paraData, paraIso } from '../util'

const SEMANA = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S']
const CORES_TIPO = { prova_online: 'var(--serie1)', vencimento: 'var(--serie2)', notas: 'var(--serie3)', rematricula: '#7a5af0', outro: 'var(--mudo)' }

const risco = Object.fromEntries(DIAS_RISCO.map((r) => [r.data, r]))
const feriado = Object.fromEntries(CONTEXTO.feriados.map((f) => [f.data, f.nome]))

function eventosPorDia() {
  const m = {}
  for (const ev of EVENTOS) (m[ev.data] = m[ev.data] || []).push(ev)
  return m
}

function mesesDoSemestre() {
  const meses = []
  const d = paraData(CONTEXTO.inicio)
  d.setDate(1)
  const fim = paraData(CONTEXTO.fim)
  while (d <= fim) {
    meses.push({ ano: d.getFullYear(), mes: d.getMonth() })
    d.setMonth(d.getMonth() + 1)
  }
  return meses
}

function Mes({ ano, mes, eventos, abrirDia }) {
  const primeiro = new Date(ano, mes, 1)
  const nome = primeiro.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
  const diasNoMes = new Date(ano, mes + 1, 0).getDate()
  const offset = primeiro.getDay()
  const celulas = []
  for (let i = 0; i < offset; i++) celulas.push(null)
  for (let d = 1; d <= diasNoMes; d++) celulas.push(d)

  return (
    <div className="card mes">
      <h4>{nome}</h4>
      <div className="cal-head">{SEMANA.map((s, i) => <span key={i}>{s}</span>)}</div>
      <div className="cal-dias">
        {celulas.map((d, i) => {
          if (!d) return <div key={i} className="cal-dia fora" />
          const iso = paraIso(new Date(ano, mes, d))
          const dow = new Date(ano, mes, d).getDay()
          const fds = dow === 0 || dow === 6
          const r = risco[iso]
          const fer = feriado[iso]
          const evs = eventos[iso] || []
          const tipos = [...new Set(evs.map((e) => e.tipo))]
          const grav = r ? nivelDaGravidade(r.gravidade) : null
          const estilo = r
            ? { background: `color-mix(in srgb, var(--${grav.chave}) 13%, var(--superficie))`, borderColor: `color-mix(in srgb, var(--${grav.chave}) 45%, transparent)` }
            : undefined
          const titulo = [fer && `Feriado: ${fer}`, ...evs.map((e) => `${e.hora_inicio} ${e.descricao}`)].filter(Boolean).join('\n')
          return (
            <div
              key={i}
              className={`cal-dia ${fds ? 'fds' : ''} ${fer ? 'feriado' : ''} ${r ? 'risco' : ''}`}
              style={estilo}
              title={titulo || undefined}
              onClick={() => r && abrirDia(iso)}
              role={r ? 'button' : undefined}
              aria-label={r ? `${completa(iso)}, dia de risco gravidade ${r.gravidade}, abrir plano` : undefined}
            >
              <span className="d">{d}</span>
              {r && <span className="gsel" style={{ background: `var(--${grav.chave})` }}>{r.gravidade}</span>}
              {fer && <span className="ftag">{fer.split(' (')[0]}</span>}
              {tipos.length > 0 && (
                <div className="dots">
                  {tipos.slice(0, 4).map((t) => <i key={t} style={{ background: CORES_TIPO[t] }} />)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function Calendario({ abrirDia }) {
  const eventos = useMemo(eventosPorDia, [])
  const meses = mesesDoSemestre()
  const totalDias = diasEntre(CONTEXTO.inicio, CONTEXTO.fim)
  const t0 = paraData(CONTEXTO.inicio).getTime()
  const span = paraData(CONTEXTO.fim).getTime() - t0 || 1
  const faixa = (iso) => ((paraData(iso).getTime() - t0) / span) * 100

  return (
    <>
      <div className="secao" style={{ marginBottom: 16 }}>
        <div className="eyebrow">Calendário acadêmico · Ibmec RJ {CONTEXTO.semestre}</div>
        <h1 className="h-page">O calendário real, com os dias de risco marcados.</h1>
        <p className="lide">
          Base: o calendário acadêmico oficial do Ibmec RJ 2026.2 (feriados, Teste de Progresso, AP1/AP2/AS, rematrícula e
          vencimentos no dia 10). Os dias que o Gemini apontou como risco estão destacados — clique para abrir o plano.
        </p>
      </div>

      <div className="card secao card-pad">
        <div className="legenda" style={{ marginBottom: 2 }}>
          {Object.entries(TIPOS).map(([k, v]) => (<span key={k}><i style={{ background: CORES_TIPO[k] }} />{v}</span>))}
          <span><i style={{ background: 'color-mix(in srgb, var(--critico) 45%, transparent)' }} />dia de risco (nº = gravidade)</span>
          <span><i style={{ background: 'var(--mudo)', opacity: 0.4 }} />feriado</span>
        </div>
      </div>

      <div className="cal-wrap secao">
        {meses.map((m) => <Mes key={`${m.ano}-${m.mes}`} {...m} eventos={eventos} abrirDia={abrirDia} />)}
      </div>

      <div className="card secao">
        <div className="card-cab"><div><h3>Períodos do semestre</h3><div className="meta">janelas do calendário oficial · {totalDias.length} dias letivos</div></div></div>
        <div className="card-corpo">
          <div className="periodos">
            {MARCOS.map((p) => (
              <div key={p.nome} className="periodo">
                <div><ChipTipo tipo={p.tipo} texto={p.nome} /></div>
                <div>
                  <div className="faixa-p">
                    <span style={{ left: `${faixa(p.inicio)}%`, width: `${Math.max(1.5, faixa(p.fim) - faixa(p.inicio))}%`, background: CORES_TIPO[p.tipo] }} />
                  </div>
                  <div className="rng">{curta(p.inicio)} – {curta(p.fim)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
