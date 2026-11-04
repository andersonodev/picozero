// frontend/src/telas/Overview.jsx
// Visão geral: abre com a fita de capacidade do semestre (a assinatura do produto),
// os indicadores de operação/SLO, os eventos, o registro do modelo e a fonte dos dados.
import { Fragment, useMemo, useState } from 'react'
import ChipTipo from '../componentes/ChipTipo'
import { CONTEXTO, DIAS_RISCO, EVENTOS, TRILHA_GEMINI, picoDoDia } from '../dados/previa'
import { FONTES } from '../dados/fontes'
import { nivelDaGravidade } from '../tema'
import { curta, diasEntre, mesNome, numero, paraData, semana } from '../util'

const risco = Object.fromEntries(DIAS_RISCO.map((r) => [r.data, r]))
const feriado = Object.fromEntries(CONTEXTO.feriados.map((f) => [f.data, f.nome]))
const FITA_PX = 76

function fds(iso) {
  const d = paraData(iso).getDay()
  return d === 0 || d === 6
}

function corDia(iso, pico, cap) {
  const r = risco[iso]
  if (r) return `var(--${nivelDaGravidade(r.gravidade).chave})`
  if (feriado[iso]) return 'var(--borda-forte)'
  if (pico >= cap) return 'var(--critico)'
  if (pico >= cap * 0.8) return 'var(--serio)'
  if (pico >= cap * 0.6) return 'var(--alerta)'
  return 'color-mix(in srgb, var(--serie3) 40%, var(--superficie-3))'
}

function Fita({ unidade, abrirDia }) {
  const [dica, setDica] = useState(null)
  const { dias, pontos, escala, cap } = useMemo(() => {
    const fator = unidade.alunos / CONTEXTO.alunos
    const cap = unidade.capacidade
    const dias = diasEntre(CONTEXTO.inicio, CONTEXTO.fim)
    const pontos = dias.map((iso) => ({ iso, pico: Math.round(picoDoDia(iso).carga * fator) }))
    const maxPico = Math.max(...pontos.map((p) => p.pico))
    const escala = Math.max(cap * 1.7, maxPico * 1.08)
    return { dias, pontos, escala, cap }
  }, [unidade])

  const meses = []
  dias.forEach((d, i) => {
    if (i === 0 || d.endsWith('-01')) meses.push({ i, nome: mesNome(d).slice(0, 3) })
  })
  const capPx = Math.round((cap / escala) * FITA_PX)

  return (
    <div className="fita" onMouseLeave={() => setDica(null)}>
      <div className="fita-grade">
        <div className="fita-linha-cap" style={{ bottom: capPx }}>
          <b>cap {cap}</b>
        </div>
        {pontos.map((p, i) => {
          const r = risco[p.iso]
          const alt = Math.max(3, Math.round((p.pico / escala) * FITA_PX))
          return (
            <div
              key={p.iso}
              className={`fita-col ${r ? 'risco' : ''}`}
              onMouseEnter={() => setDica({ ...p, x: Math.min(94, Math.max(6, ((i + 0.5) / dias.length) * 100)), r })}
              onClick={() => r && abrirDia(p.iso)}
              role={r ? 'button' : undefined}
              aria-label={r ? `${curta(p.iso)}: pico ${p.pico}, abrir plano` : undefined}
            >
              <div className="haste" style={{ height: alt, background: corDia(p.iso, p.pico, cap) }} />
            </div>
          )
        })}
      </div>
      <div className="fita-eixo">
        {meses.map((m) => (
          <span key={m.i} style={{ left: `${(m.i / dias.length) * 100}%` }}>{m.nome}</span>
        ))}
      </div>
      {dica && (
        <div className="fita-dica" style={{ left: `${dica.x}%` }}>
          <b className="mono">{curta(dica.iso)}</b> · {semana(dica.iso).slice(0, 3)} · pico <b className="mono">{numero(dica.pico)}</b>
          {dica.r && <span className="mono"> · g{dica.r.gravidade} — clique</span>}
        </div>
      )}
    </div>
  )
}

function agruparMes(eventos) {
  const grupos = []
  for (const ev of eventos) {
    const mes = ev.data.slice(0, 7)
    let g = grupos.find((x) => x.mes === mes)
    if (!g) { g = { mes, nome: mesNome(ev.data), eventos: [] }; grupos.push(g) }
    g.eventos.push(ev)
  }
  return grupos
}

export default function Overview({ unidade, abrirDia }) {
  const fator = unidade.alunos / CONTEXTO.alunos
  const cap = unidade.capacidade
  const comPico = DIAS_RISCO.map((r) => ({ ...r, pico: Math.round(picoDoDia(r.data).carga * fator) }))
  const acima = comPico.filter((d) => d.pico > cap)
  const pior = Math.max(...comPico.map((d) => d.pico))
  const letivos = diasEntre(CONTEXTO.inicio, CONTEXTO.fim).filter((iso) => {
    const d = paraData(iso).getDay()
    return d !== 0 && d !== 6 && !feriado[iso]
  }).length
  const tokens = TRILHA_GEMINI.reduce((s, t) => s + (t.tokens || 0), 0)
  const consultas = TRILHA_GEMINI.filter((t) => t.ferramenta).length
  const grupos = agruparMes(EVENTOS)

  return (
    <>
      <div className="secao" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
        <div>
          <div className="eyebrow">Operação do portal · {unidade.nome}</div>
          <h1 className="h-page">
            <span className="destaque">{acima.length} dias</span> vão estourar a capacidade neste semestre.
          </h1>
          <p className="lide">
            O Gemini lê o calendário acadêmico, consulta o histórico e aponta os dias de risco. O código calcula a
            carga por janela de 15 minutos, valida o plano e prova o ganho sob carga. {unidade.modelada ? '' : `Projeção de ${unidade.curto} escalada a partir do modelo do Rio.`}
          </p>
        </div>
        <div className="nota-flag" title="Como a demo foi preenchida">● prévia · histórico modelado · ver Fonte de dados</div>
      </div>

      <div className="grade-4 secao">
        <div className="card tile">
          <span className="k">Dias críticos</span>
          <span className="v">{acima.length}<small>/ {comPico.length} em risco</small></span>
          <span className="d">de {letivos} dias letivos no semestre</span>
        </div>
        <div className="card tile ruim">
          <span className="k">Pior pico projetado</span>
          <span className="v">{numero(pior)}<small>req</small></span>
          <span className="d">{(pior / cap).toFixed(1).replace('.', ',')}× a capacidade de {cap}</span>
        </div>
        <div className="card tile bom">
          <span className="k">Infra extra só em</span>
          <span className="v">{acima.length}<small>/ {letivos} dias</small></span>
          <span className="d">resto do semestre fica dentro da capacidade</span>
        </div>
        <div className="card tile">
          <span className="k">SLO de capacidade</span>
          <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span className="selo-slo"><b className="mono">p95 &lt; 400 ms</b> · 503 &lt; 0,5%</span>
            <div className="barra-budget"><span style={{ width: '18%', background: 'var(--bom)' }} /></div>
            <span className="d" style={{ fontSize: 11 }}>orçamento de erro: 18% usado (com plano)</span>
          </div>
        </div>
      </div>

      <div className="card secao">
        <div className="card-cab">
          <div>
            <h3>Capacidade do semestre · {unidade.curto}</h3>
            <div className="meta">pico diário projetado × capacidade de {cap} acessos simultâneos · {CONTEXTO.semestre}</div>
          </div>
          <div className="legenda">
            <span><i style={{ background: 'color-mix(in srgb, var(--serie3) 40%, var(--superficie-3))' }} />folga</span>
            <span><i style={{ background: 'var(--alerta)' }} />atenção</span>
            <span><i style={{ background: 'var(--serio)' }} />alto</span>
            <span><i style={{ background: 'var(--critico)' }} />crítico</span>
            <span><i className="linha" style={{ background: 'var(--critico)' }} />capacidade</span>
          </div>
        </div>
        <div className="card-corpo">
          <Fita unidade={unidade} abrirDia={abrirDia} />
        </div>
      </div>

      <div className="grade-2 secao">
        <div className="card">
          <div className="card-cab">
            <div>
              <h3>Eventos do semestre</h3>
              <div className="meta">{EVENTOS.length} eventos · extraídos pelo Gemini · response_schema list[Evento]</div>
            </div>
          </div>
          <div className="card-corpo" style={{ paddingTop: 6, maxHeight: 420, overflow: 'auto' }}>
            <table className="tabela">
              <tbody>
                {grupos.map((g) => (
                  <Fragment key={g.mes}>
                    <tr className="mes"><td colSpan={3}><span className="eyebrow">{g.nome}</span></td></tr>
                    {g.eventos.map((ev) => (
                      <tr key={`${ev.data}-${ev.descricao}`} className={risco[ev.data] ? 'linha-risco' : ''}>
                        <td style={{ width: 86 }}>
                          <b className="num">{curta(ev.data)}</b>
                          <div className="turmas">{ev.hora_inicio}</div>
                        </td>
                        <td style={{ width: 118 }}><ChipTipo tipo={ev.tipo} /></td>
                        <td>
                          {ev.descricao}
                          {ev.turmas.length > 0 && <div className="turmas">{ev.turmas.join(' · ')}</div>}
                        </td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-cab">
            <div>
              <h3>Registro do modelo</h3>
              <div className="meta">{numero(tokens)} tokens · {consultas} consultas · auditado por cliente.py</div>
            </div>
          </div>
          <div className="card-corpo" style={{ maxHeight: 420, overflow: 'auto' }}>
            <ul className="log">
              {TRILHA_GEMINI.map((t, i) => (
                <li key={i}>
                  <span className="t">{t.hora}</span>
                  <div className={t.ferramenta ? 'tool' : ''}>
                    <div className="etapa">{t.etapa}</div>
                    <div className="obs">
                      {t.detalhe}
                      {t.tempo && ` · ${t.tempo}`}
                      {t.tokens && ` · ${numero(t.tokens)} tok`}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <div className="card secao">
        <div className="card-cab">
          <div>
            <h3>Fonte de dados</h3>
            <div className="meta">o que é medido e o que é modelado · honesto para a banca</div>
          </div>
        </div>
        <div className="card-corpo" style={{ paddingTop: 2 }}>
          {FONTES.map((f) => (
            <div key={f.titulo} className="fonte">
              <span className={`tag ${f.tipo === 'real' ? 'real' : 'modelo'}`}>{f.tipo === 'real' ? 'real' : 'modelo'}</span>
              <div className="corpo">
                <b>{f.titulo}</b>
                <p>{f.texto}</p>
                <span className="mono">{f.mono}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
