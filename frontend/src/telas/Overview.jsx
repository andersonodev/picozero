// frontend/src/telas/Overview.jsx
// Visão geral: o alerta do semestre, os números da operação, a faixa de capacidade
// dia a dia (no estilo de status page), os dias de risco e o registro do Gemini.
import { useMemo, useState } from 'react'
import { ArrowRight, CalendarDays, ChevronDown, TriangleAlert } from 'lucide-react'
import { CONTEXTO, DIAS_RISCO, TRILHA_GEMINI, picoDoDia } from '../dados/previa'
import { UNIDADES } from '../dados/unidades'
import { situacaoDaCarga } from '../tema'
import { curta, diasEntre, mesNome, numero, paraData, paraIso, rotuloCurto, semana } from '../util'

const risco = Object.fromEntries(DIAS_RISCO.map((r) => [r.data, r]))
const feriado = Object.fromEntries(CONTEXTO.feriados.map((f) => [f.data, f.nome]))
const vezes = (x) => `${x.toFixed(1).replace('.', ',')}×`
const sem3 = (iso) => semana(iso).slice(0, 3)

function fimDeSemana(iso) {
  const d = paraData(iso).getDay()
  return d === 0 || d === 6
}

function FaixaCapacidade({ unidade, abrirDia }) {
  const [dica, setDica] = useState(null)
  const cap = unidade.capacidade
  const dias = useMemo(() => {
    const fator = unidade.alunos / CONTEXTO.alunos
    return diasEntre(CONTEXTO.inicio, CONTEXTO.fim).map((iso) => {
      const p = picoDoDia(iso)
      return { iso, pico: Math.round(p.carga * fator), hora: p.hora }
    })
  }, [unidade])

  const meses = dias.flatMap((d, i) => (i === 0 || d.iso.endsWith('-01') ? [{ i, nome: mesNome(d.iso).slice(0, 3) }] : []))
  const hoje = paraIso(new Date())
  const iHoje = dias.findIndex((d) => d.iso === hoje)
  const pos = (i) => ((i + 0.5) / dias.length) * 100

  return (
    <div className="faixa" onMouseLeave={() => setDica(null)}>
      {iHoje >= 0 && (
        <div className="faixa-hoje" style={{ left: `${pos(iHoje)}%` }}>
          <span>hoje</span>
        </div>
      )}
      <div className="faixa-dias">
        {dias.map((d, i) => {
          const s = situacaoDaCarga(d.pico, cap)
          const r = risco[d.iso]
          const classes = [
            'faixa-dia',
            feriado[d.iso] ? 'feriado' : s.chave !== 'folga' ? s.chave : fimDeSemana(d.iso) ? 'fds' : '',
            r ? 'sinalizado clicavel' : '',
          ].join(' ')
          return (
            <button
              key={d.iso}
              type="button"
              className={classes}
              onMouseEnter={() => setDica({ ...d, s, r, x: Math.min(93, Math.max(7, pos(i))) })}
              onFocus={() => setDica({ ...d, s, r, x: Math.min(93, Math.max(7, pos(i))) })}
              onClick={() => r && abrirDia(d.iso)}
              tabIndex={r ? 0 : -1}
              aria-label={`${curta(d.iso)}: pico ${d.pico}, ${s.rotulo}${r ? ', abrir plano do dia' : ''}`}
            />
          )
        })}
      </div>
      <div className="faixa-eixo">
        {meses.map((m) => (
          <span key={m.i} style={{ left: `${(m.i / dias.length) * 100}%` }}>{m.nome}</span>
        ))}
      </div>
      {dica && (
        <div className="faixa-dica" style={{ left: `${dica.x}%` }}>
          <b>{sem3(dica.iso)}, {curta(dica.iso)}</b>
          {feriado[dica.iso] && <span className="fraco"> · {feriado[dica.iso]}</span>}
          <div>
            Pico de <b>{numero(dica.pico)}</b> às {dica.hora} <span className="fraco">· {Math.round((dica.pico / cap) * 100)}% da capacidade</span>
          </div>
          {dica.r && <div className="fraco">Gemini: gravidade {dica.r.gravidade} de 5 · clique para abrir o plano</div>}
        </div>
      )}
    </div>
  )
}

export default function Overview({ unidade, setUnidadeId, abrirDia, irPara }) {
  const fator = unidade.alunos / CONTEXTO.alunos
  const cap = unidade.capacidade
  const dias = DIAS_RISCO.map((r) => {
    const p = picoDoDia(r.data)
    return { ...r, pico: Math.round(p.carga * fator), hora: p.hora }
  }).sort((a, b) => a.data.localeCompare(b.data))
  const acima = dias.filter((d) => d.pico > cap)
  const pior = dias.reduce((a, b) => (b.pico > a.pico ? b : a))
  const letivos = diasEntre(CONTEXTO.inicio, CONTEXTO.fim).filter((iso) => !fimDeSemana(iso) && !feriado[iso]).length
  const tokens = TRILHA_GEMINI.reduce((s, t) => s + (t.tokens || 0), 0)
  const consultas = TRILHA_GEMINI.filter((t) => t.ferramenta).length

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Visão geral</h1>
          <p className="sub">
            {unidade.nome} · {numero(unidade.alunos)} alunos · capacidade de {cap} acessos simultâneos
            {!unidade.modelada && ' · projeção escalada a partir do modelo do Rio'}
          </p>
        </div>
        <div className="cab-acoes">
          <label className="campo-select" title="Edital: RJ, SP, BH e DF">
            <span className="rot">Unidade</span>
            <select value={unidade.id} onChange={(e) => setUnidadeId(e.target.value)}>
              {UNIDADES.map((u) => (
                <option key={u.id} value={u.id}>{u.nome}</option>
              ))}
            </select>
            <ChevronDown size={16} aria-hidden="true" />
          </label>
          <button className="botao primario" onClick={() => irPara('calendario')}>
            <CalendarDays size={16} aria-hidden="true" />
            Abrir calendário
          </button>
        </div>
      </header>

      <section className="card aviso secao">
        <div className="aviso-icone"><TriangleAlert size={20} strokeWidth={2} aria-hidden="true" /></div>
        <div className="aviso-corpo">
          <h3>{acima.length} {acima.length === 1 ? 'dia vai' : 'dias vão'} passar da capacidade neste semestre</h3>
          <p>
            O pior é {sem3(pior.data)}, {curta(pior.data)}: pico de {numero(pior.pico)} acessos às {pior.hora},{' '}
            {vezes(pior.pico / cap)} a capacidade. Fora desses dias, a infraestrutura atual dá conta.
          </p>
          <button className="link-seta" onClick={() => irPara('riscos')}>
            Ver dias críticos <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
      </section>

      <div className="grade g-4 secao">
        <div className="card metrica critico">
          <span className="rot">Dias acima da capacidade</span>
          <span className="val">{acima.length}<small>de {dias.length} em risco</small></span>
          <span className="det">apontados pelo Gemini, confirmados pelo cálculo</span>
        </div>
        <div className="card metrica">
          <span className="rot">Pior pico projetado</span>
          <span className="val">{numero(pior.pico)}<small>acessos</small></span>
          <span className="det">{curta(pior.data)} às {pior.hora} · {Math.round((pior.pico / cap) * 100)}% da capacidade</span>
        </div>
        <div className="card metrica">
          <span className="rot">Reforço de infraestrutura</span>
          <span className="val">{acima.length}<small>de {letivos} dias letivos</small></span>
          <span className="det">só nesses dias; no resto, a capacidade atual basta</span>
        </div>
        <div className="card metrica">
          <span className="rot">Orçamento de erro usado</span>
          <span className="val">18%</span>
          <div className="barra-progresso"><span style={{ width: '18%' }} /></div>
          <span className="det">SLO p95 &lt; 400 ms e 503 &lt; 0,5%, com o plano</span>
        </div>
      </div>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>Capacidade do semestre</h2>
            <p>Pico diário projetado contra a capacidade de {cap} acessos simultâneos · {curta(CONTEXTO.inicio)} a {curta(CONTEXTO.fim)}</p>
          </div>
          <div className="legenda">
            <span><i style={{ background: 'var(--folga)' }} />com folga</span>
            <span><i style={{ background: 'var(--atencao)' }} />atenção</span>
            <span><i style={{ background: 'var(--alto)' }} />perto do limite</span>
            <span><i style={{ background: 'var(--critico)' }} />acima da capacidade</span>
            <span><i className="hachura" />feriado</span>
            <span><i className="redondo" style={{ background: 'var(--texto)' }} />apontado pelo Gemini</span>
          </div>
        </div>
        <div className="card-corpo">
          <FaixaCapacidade unidade={unidade} abrirDia={abrirDia} />
        </div>
      </section>

      <div className="grade g-2 secao">
        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Dias de risco</h2>
              <p>{dias.length} dias apontados pelo Gemini · pico calculado pelo código · clique para abrir o plano</p>
            </div>
          </div>
          <div className="card-corpo">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Eventos</th>
                  <th className="dir">Pico</th>
                  <th className="dir">Capacidade</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {dias.map((d) => {
                  const s = situacaoDaCarga(d.pico, cap)
                  return (
                    <tr key={d.data} className="clicavel" onClick={() => abrirDia(d.data)}>
                      <td className="data-cel">
                        <b>{curta(d.data)}</b>
                        <span>{sem3(d.data)}</span>
                      </td>
                      <td className="fraco">{d.eventos.map(rotuloCurto).join(' · ')}</td>
                      <td className="dir data-cel">
                        <b>{numero(d.pico)}</b>
                        <span>às {d.hora}</span>
                      </td>
                      <td className="dir num">{Math.round((d.pico / cap) * 100)}%</td>
                      <td><span className={`pill ${s.chave}`}>{s.rotulo}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Registro do Gemini</h2>
              <p>{numero(tokens)} tokens · {consultas} consultas ao histórico · auditado por cliente.py</p>
            </div>
          </div>
          <div className="card-corpo">
            <ol className="log">
              {TRILHA_GEMINI.map((t, i) => (
                <li key={i} className={t.ferramenta ? 'ferramenta' : ''}>
                  <time>{t.hora}</time>
                  <div className="passo">
                    <b>{t.etapa}</b>
                    <p>
                      {t.detalhe}
                      {t.tempo && ` · ${t.tempo}`}
                      {t.tokens && ` · ${numero(t.tokens)} tokens`}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>
      </div>
    </>
  )
}
