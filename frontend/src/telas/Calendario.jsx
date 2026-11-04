// frontend/src/telas/Calendario.jsx
// Calendário acadêmico real do Ibmec RJ 2026.2: um mês por vez, eventos escritos na célula,
// períodos (rematrícula, AP1, AP2, AS…) como faixas que atravessam a semana e um painel
// com a curva de carga do dia escolhido. Os dias que o Gemini marcou abrem o plano.
import { Fragment, useMemo, useState } from 'react'
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowRight, CalendarDays, ChevronLeft, ChevronRight, List, MessageSquareText } from 'lucide-react'
import { CONTEXTO, DIAS_RISCO, EVENTOS, MARCOS, TIPOS, curvaDoDia } from '../dados/previa'
import { corDoTipo, nivelDaGravidade, situacaoDaCarga, useTema } from '../tema'
import { capitalizar, curta, diasEntre, longa, numero, paraData, paraIso, rotuloCurto, semana } from '../util'

const SEMANA = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
const MAX_EVENTOS_CELULA = 3
const risco = Object.fromEntries(DIAS_RISCO.map((r) => [r.data, r]))
const feriado = Object.fromEntries(CONTEXTO.feriados.map((f) => [f.data, f.nome]))
const eventosDoDia = EVENTOS.reduce((m, ev) => {
  ;(m[ev.data] = m[ev.data] || []).push(ev)
  return m
}, {})

const chaveMes = (ano, mes) => ano * 12 + mes
const MES_INICIO = (() => { const d = paraData(CONTEXTO.inicio); return chaveMes(d.getFullYear(), d.getMonth()) })()
const MES_FIM = (() => { const d = paraData(CONTEXTO.fim); return chaveMes(d.getFullYear(), d.getMonth()) })()
const limitarMes = (k) => Math.min(MES_FIM, Math.max(MES_INICIO, k))
const mesDoIso = (iso) => { const d = paraData(iso); return chaveMes(d.getFullYear(), d.getMonth()) }

function fimDeSemana(iso) {
  const d = paraData(iso).getDay()
  return d === 0 || d === 6
}

function horario(ev) {
  return ev.hora_inicio === '00:00' ? '' : ev.hora_inicio
}

// Semanas (seg→dom) que cobrem o mês, cada uma com as faixas de período em raias.
function semanasDoMes(k) {
  const ano = Math.floor(k / 12)
  const mes = k % 12
  const primeiro = new Date(ano, mes, 1)
  const ultimo = new Date(ano, mes + 1, 0)
  const inicio = new Date(ano, mes, 1 - ((primeiro.getDay() + 6) % 7))
  const fim = new Date(ano, mes, ultimo.getDate() + (6 - ((ultimo.getDay() + 6) % 7)))
  const dias = diasEntre(paraIso(inicio), paraIso(fim))
  const semanas = []
  for (let i = 0; i < dias.length; i += 7) {
    const sem = dias.slice(i, i + 7)
    const segmentos = MARCOS.flatMap((p) => {
      const ini = p.inicio > sem[0] ? p.inicio : sem[0]
      const fimSeg = p.fim < sem[6] ? p.fim : sem[6]
      if (ini > fimSeg) return []
      return [{ ...p, c0: sem.indexOf(ini), c1: sem.indexOf(fimSeg), contEsq: p.inicio < sem[0], contDir: p.fim > sem[6] }]
    }).sort((a, b) => a.c0 - b.c0 || b.c1 - b.c0 - (a.c1 - a.c0))
    const fimDaRaia = []
    for (const s of segmentos) {
      let raia = fimDaRaia.findIndex((f) => f < s.c0)
      if (raia === -1) raia = fimDaRaia.length
      fimDaRaia[raia] = s.c1
      s.raia = raia
    }
    semanas.push({ dias: sem, segmentos, raias: fimDaRaia.length })
  }
  return { semanas, ano, mes }
}

function DicaMini({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="dica-grafico" style={{ minWidth: 0 }}>
      <div className="cab">{label}</div>
      <div className="linha"><span>Acessos</span><b>{numero(payload[0].value)}</b></div>
    </div>
  )
}

function PainelDia({ iso, abrirDia }) {
  const t = useTema()
  const cap = CONTEXTO.capacidade
  const r = risco[iso]
  const evs = eventosDoDia[iso] || []
  const curva = useMemo(() => curvaDoDia(iso), [iso])
  const pico = curva.reduce((a, b) => (b.carga > a.carga ? b : a))
  const s = situacaoDaCarga(pico.carga, cap)
  const dentro = iso >= CONTEXTO.inicio && iso <= CONTEXTO.fim
  const cor = s.chave === 'critico' ? t.critico : t.comPlano

  return (
    <aside className="card cal-painel" aria-live="polite">
      <div className="card-corpo">
        <div>
          <h2 className="painel-data">{longa(iso)}</h2>
          <div className="painel-tags">
            {r && <span className={`pill ${nivelDaGravidade(r.gravidade).chave}`}>Gravidade {r.gravidade} de 5</span>}
            {dentro && <span className={`pill ${s.chave}`}>{s.rotulo}</span>}
            {feriado[iso] && <span className="pill sem-ponto">{feriado[iso]}</span>}
            {!feriado[iso] && fimDeSemana(iso) && <span className="pill sem-ponto">fim de semana</span>}
          </div>
        </div>

        {dentro ? (
          <>
            <div className="painel-pico">
              <span className="rot">Pico projetado de acessos simultâneos</span>
              <span className={`val ${s.chave === 'critico' ? 'critico' : ''}`}>{numero(pico.carga)}</span>
              <span className="det">às {pico.hora} · {Math.round((pico.carga / cap) * 100)}% da capacidade de {cap}</span>
            </div>
            <div style={{ height: 128, margin: '-4px -6px 0' }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={curva} margin={{ top: 8, right: 14, bottom: 0, left: 14 }}>
                  <XAxis dataKey="hora" ticks={['06:00', '12:00', '18:00']} interval={0} tick={{ fill: t.mudo, fontSize: 11 }} tickLine={false} axisLine={{ stroke: t.grade }} />
                  <YAxis hide domain={[0, Math.max(cap, pico.carga) * 1.12]} />
                  <Tooltip content={<DicaMini />} cursor={{ stroke: t.mudo, strokeDasharray: '3 3' }} />
                  <ReferenceLine y={cap} stroke={t.critico} strokeDasharray="5 4" label={{ value: `capacidade ${cap}`, position: 'insideTopLeft', fill: t.critico, fontSize: 11 }} />
                  <Area type="monotone" dataKey="carga" stroke={cor} strokeWidth={2} fill={cor} fillOpacity={0.14} dot={false} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </>
        ) : (
          <p className="painel-vazio">Fora do período letivo 2026.2 ({curta(CONTEXTO.inicio)} a {curta(CONTEXTO.fim)}).</p>
        )}

        <div className="painel-secao">
          <h3>Eventos do dia</h3>
          {evs.length > 0 ? (
            <ul className="painel-evs">
              {evs.map((ev) => (
                <li key={ev.descricao} style={{ '--cor-ev': corDoTipo(ev.tipo) }}>
                  <div>
                    <b>{ev.descricao}</b>
                    <span>
                      {ev.hora_inicio === '00:00' ? 'o dia todo' : `${ev.hora_inicio} às ${ev.hora_fim}`} · {TIPOS[ev.tipo]}
                      {ev.turmas.length > 0 && ` · ${ev.turmas.length} turmas`}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="painel-vazio">Nenhum evento do calendário acadêmico neste dia.</p>
          )}
        </div>

        {r && (
          <>
            <p className="painel-motivo">
              <strong><MessageSquareText size={14} aria-hidden="true" /> Por que o Gemini marcou este dia</strong>
              {r.motivo}
            </p>
            <button className="botao primario bloco" onClick={() => abrirDia(iso)}>
              Abrir plano do dia <ArrowRight size={16} aria-hidden="true" />
            </button>
          </>
        )}
      </div>
    </aside>
  )
}

function GradeMes({ k, selecionado, selecionar, hoje }) {
  const { semanas, mes } = useMemo(() => semanasDoMes(k), [k])
  return (
    <div className="card cal-grade" role="grid" aria-label="Calendário do mês">
      <div className="cal-cab" role="row">
        {SEMANA.map((s, i) => <span key={s} role="columnheader" className={i >= 5 ? 'fds' : ''}>{s}</span>)}
      </div>
      {semanas.map((sem) => (
        <div key={sem.dias[0]} className="cal-semana" role="row" style={{ '--faixas': sem.raias }}>
          {sem.dias.map((iso) => {
            const d = paraData(iso)
            const r = risco[iso]
            const nivel = r ? nivelDaGravidade(r.gravidade) : null
            const evs = eventosDoDia[iso] || []
            const classes = [
              'cal-cel',
              d.getMonth() !== mes ? 'fora' : '',
              fimDeSemana(iso) ? 'fds' : '',
              feriado[iso] ? 'feriado' : '',
              nivel ? `r-${nivel.chave}` : '',
              iso === selecionado ? 'selecionado' : '',
              iso === hoje ? 'hoje' : '',
            ].join(' ')
            return (
              <div
                key={iso}
                className={classes}
                role="gridcell"
                tabIndex={0}
                aria-selected={iso === selecionado}
                aria-label={`${longa(iso)}${r ? `, dia de risco gravidade ${r.gravidade}` : ''}${evs.length ? `, ${evs.length} eventos` : ''}`}
                onClick={() => selecionar(iso)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    selecionar(iso)
                  }
                }}
              >
                <div className="cal-topo">
                  <span className="cal-num">{d.getDate()}</span>
                  {nivel && <span className={`cal-tag ${nivel.chave}`}>{nivel.rotulo}</span>}
                </div>
                {feriado[iso] && <span className="cal-feriado-nome">{feriado[iso].split(' (')[0]}</span>}
                {evs.slice(0, MAX_EVENTOS_CELULA).map((ev) => (
                  <span key={ev.descricao} className="cal-ev" style={{ '--cor-ev': corDoTipo(ev.tipo) }} title={`${ev.hora_inicio} ${ev.descricao}`}>
                    {horario(ev) && <span className="h">{horario(ev)}</span>}
                    <span>{rotuloCurto(ev.descricao)}</span>
                  </span>
                ))}
                {evs.length > MAX_EVENTOS_CELULA && <span className="cal-mais">+{evs.length - MAX_EVENTOS_CELULA} eventos</span>}
              </div>
            )
          })}
          {sem.segmentos.map((s) => (
            <span
              key={`${s.nome}-${s.c0}`}
              className={`cal-faixa ${s.contEsq ? 'cont-esq' : ''} ${s.contDir ? 'cont-dir' : ''}`}
              style={{
                '--cor-ev': corDoTipo(s.tipo),
                '--lane': s.raia,
                left: `calc(${(s.c0 / 7) * 100}% + ${s.contEsq ? 0 : 5}px)`,
                width: `calc(${((s.c1 - s.c0 + 1) / 7) * 100}% - ${(s.contEsq ? 0 : 5) + (s.contDir ? 0 : 5)}px)`,
              }}
              title={`${s.nome} · ${curta(s.inicio)} a ${curta(s.fim)}`}
            >
              {s.nome}
            </span>
          ))}
        </div>
      ))}
    </div>
  )
}

function Agenda({ irParaDia }) {
  const linhas = [
    ...EVENTOS.map((ev) => ({ ...ev, chave: `${ev.data}-${ev.descricao}` })),
    ...CONTEXTO.feriados.map((f) => ({ data: f.data, hora_inicio: '00:00', hora_fim: '23:59', tipo: 'feriado', descricao: f.nome, turmas: [], chave: `f-${f.data}` })),
  ].sort((a, b) => a.data.localeCompare(b.data) || a.hora_inicio.localeCompare(b.hora_inicio))
  const grupos = []
  for (const l of linhas) {
    const mes = l.data.slice(0, 7)
    let g = grupos.find((x) => x.mes === mes)
    if (!g) {
      g = { mes, nome: capitalizar(paraData(l.data).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })), linhas: [] }
      grupos.push(g)
    }
    g.linhas.push(l)
  }
  return (
    <div className="card">
      {grupos.map((g) => (
        <Fragment key={g.mes}>
          <div className="agenda-mes">{g.nome}</div>
          {g.linhas.map((l) => {
            const r = risco[l.data]
            const nivel = r ? nivelDaGravidade(r.gravidade) : null
            const cor = l.tipo === 'feriado' ? 'var(--borda-forte)' : corDoTipo(l.tipo)
            return (
              <button key={l.chave} className="agenda-linha" style={{ '--cor-ev': cor }} onClick={() => irParaDia(l.data)}>
                <span className="agenda-dia">
                  <b>{paraData(l.data).getDate()}</b>
                  <span>{semana(l.data).slice(0, 3)}</span>
                </span>
                <span className="agenda-hora">{l.hora_inicio === '00:00' ? 'dia todo' : `${l.hora_inicio}–${l.hora_fim}`}</span>
                <span className="agenda-desc">
                  <b>{l.descricao}</b>
                  <span>
                    {l.tipo === 'feriado' ? 'Feriado' : TIPOS[l.tipo]}
                    {l.turmas.length > 0 && ` · ${l.turmas.join(', ')}`}
                  </span>
                </span>
                {nivel ? <span className={`pill ${nivel.chave}`}>risco {nivel.rotulo}</span> : <span />}
              </button>
            )
          })}
        </Fragment>
      ))}
    </div>
  )
}

function Periodos() {
  const t0 = paraData(CONTEXTO.inicio).getTime()
  const span = paraData(CONTEXTO.fim).getTime() - t0 || 1
  const pos = (iso) => ((paraData(iso).getTime() - t0) / span) * 100
  const meses = diasEntre(CONTEXTO.inicio, CONTEXTO.fim).filter((iso, i) => i === 0 || iso.endsWith('-01'))
  return (
    <section className="card secao">
      <div className="card-cab">
        <div>
          <h2>Períodos do semestre</h2>
          <p>Janelas do calendário oficial · {curta(CONTEXTO.inicio)} a {curta(CONTEXTO.fim)}</p>
        </div>
      </div>
      <div className="card-corpo">
        <div className="periodos">
          <div className="periodo-meses">
            <span />
            <div>
              {meses.map((iso) => (
                <span key={iso} style={{ left: `${pos(iso)}%` }}>
                  {paraData(iso).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')}
                </span>
              ))}
            </div>
          </div>
          {MARCOS.map((p) => (
            <div key={p.nome} className="periodo" style={{ '--cor-ev': corDoTipo(p.tipo) }}>
              <span className="periodo-nome">{p.nome}</span>
              <div>
                <div className="periodo-trilho">
                  <span style={{ left: `${pos(p.inicio)}%`, width: `${Math.max(1.2, pos(p.fim) - pos(p.inicio))}%` }} />
                </div>
                <div className="periodo-datas">{curta(p.inicio)} a {curta(p.fim)}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default function Calendario({ dia, abrirDia }) {
  const hoje = paraIso(new Date())
  const [vista, setVista] = useState('mes')
  const [selecionado, setSelecionado] = useState(dia)
  const [k, setK] = useState(() => limitarMes(mesDoIso(dia)))
  const rotuloMes = capitalizar(new Date(Math.floor(k / 12), k % 12, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' }))

  function irParaDia(iso) {
    setSelecionado(iso)
    setK(limitarMes(mesDoIso(iso)))
    setVista('mes')
  }

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Calendário acadêmico</h1>
          <p className="sub">
            Calendário oficial do {CONTEXTO.instituicao} {CONTEXTO.semestre} · {EVENTOS.length} eventos · {CONTEXTO.feriados.length} feriados
          </p>
        </div>
        <div className="cab-acoes cal-toolbar">
          <div className="segmentado" role="group" aria-label="Vista">
            <button className={vista === 'mes' ? 'ativo' : ''} onClick={() => setVista('mes')}>
              <CalendarDays size={15} aria-hidden="true" /> Mês
            </button>
            <button className={vista === 'lista' ? 'ativo' : ''} onClick={() => setVista('lista')}>
              <List size={15} aria-hidden="true" /> Lista
            </button>
          </div>
          {vista === 'mes' && (
            <>
              <div className="grupo-botoes">
                <button onClick={() => setK((x) => limitarMes(x - 1))} disabled={k <= MES_INICIO} aria-label="Mês anterior">
                  <ChevronLeft size={17} aria-hidden="true" />
                </button>
                <button onClick={() => irParaDia(hoje)}>Hoje</button>
                <button onClick={() => setK((x) => limitarMes(x + 1))} disabled={k >= MES_FIM} aria-label="Próximo mês">
                  <ChevronRight size={17} aria-hidden="true" />
                </button>
              </div>
              <span className="cal-mes-rotulo">{rotuloMes}</span>
            </>
          )}
        </div>
      </header>

      {vista === 'mes' ? (
        <>
          <div className="cal-layout">
            <div>
              <GradeMes k={k} selecionado={selecionado} selecionar={setSelecionado} hoje={hoje} />
              <div className="legenda" style={{ marginTop: 14 }}>
                {Object.entries(TIPOS).map(([chave, nome]) => (
                  <span key={chave}><i style={{ background: corDoTipo(chave) }} />{nome}</span>
                ))}
                <span><i style={{ background: 'var(--critico)' }} />dia de risco</span>
                <span><i className="hachura" />feriado</span>
                <span><i className="redondo" style={{ background: 'var(--teal)' }} />hoje</span>
              </div>
            </div>
            <PainelDia iso={selecionado} abrirDia={abrirDia} />
          </div>
        </>
      ) : (
        <>
          <Periodos />
          <div className="secao">
            <Agenda irParaDia={irParaDia} />
          </div>
        </>
      )}
    </>
  )
}
