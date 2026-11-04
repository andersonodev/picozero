// frontend/src/telas/Calendario.jsx
// Calendário acadêmico real do Ibmec RJ 2026.2 em três vistas: Mês (eventos escritos na célula,
// períodos como faixas, carga do dia no topo da célula), Semestre (mapa de calor ECharts) e Lista.
// O painel à direita mostra a curva do dia vinda do motor. Teclado: setas, PageUp/PageDown, Enter.
import { Fragment, useMemo, useRef, useState } from 'react'
import { ArrowRight, CalendarDays, CalendarRange, ChevronLeft, ChevronRight, List, MessageSquareText } from 'lucide-react'
import * as api from '../api/cliente'
import { usarApi } from '../api/usarApi'
import AvisoIA from '../componentes/AvisoIA'
import { TIPOS } from '../dados/previa'
import { feriadosDe, fimDeSemana } from '../dados/usarBase'
import CalendarioCalor from '../graficos/CalendarioCalor'
import CurvaDia from '../graficos/CurvaDia'
import { corDoTipo, nivelDaGravidade, situacaoDoNivel } from '../tema'
import { capitalizar, curta, diasEntre, longa, numero, paraData, paraIso, rotuloCurto, semana } from '../util'

const SEMANA = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
const MAX_EVENTOS_CELULA = 3
const chaveMes = (ano, mes) => ano * 12 + mes
const mesDoIso = (iso) => { const d = paraData(iso); return chaveMes(d.getFullYear(), d.getMonth()) }
const somarDias = (iso, n) => { const d = paraData(iso); d.setDate(d.getDate() + n); return paraIso(d) }

function horario(ev) {
  return ev.hora_inicio === '00:00' ? '' : ev.hora_inicio
}

// Semanas (seg→dom) que cobrem o mês, cada uma com as faixas de período em raias.
function semanasDoMes(k, marcos) {
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
    const segmentos = marcos.flatMap((p) => {
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
  return { semanas, mes }
}

function PainelDia({ iso, unidade, base, risco, eventos, feriados, abrirDia }) {
  const cap = base.contexto.capacidade
  const curva = usarApi(() => api.curva(iso, unidade), [iso, unidade])
  const c = curva.dados
  const dentro = iso >= base.contexto.inicio && iso <= base.contexto.fim
  const s = c ? situacaoDoNivel(c.nivel) : null
  const r = risco[iso]

  return (
    <aside className="card cal-painel" aria-live="polite">
      <div className="card-corpo">
        <div>
          <h2 className="painel-data">{longa(iso)}</h2>
          <div className="painel-tags">
            {r && <span className={`pill ${nivelDaGravidade(r.gravidade).chave}`}>Gravidade {r.gravidade} de 5</span>}
            {dentro && s && <span className={`pill ${s.chave}`}>{s.rotulo}</span>}
            {feriados[iso] && <span className="pill sem-ponto">{feriados[iso]}</span>}
            {!feriados[iso] && fimDeSemana(iso) && <span className="pill sem-ponto">fim de semana</span>}
          </div>
        </div>

        {!dentro ? (
          <p className="painel-vazio">Fora do período letivo {base.contexto.semestre} ({curta(base.contexto.inicio)} a {curta(base.contexto.fim)}).</p>
        ) : !c ? (
          <div className="esq-bloco" style={{ height: 196 }} aria-busy="true" />
        ) : (
          <>
            <div className="painel-pico">
              <span className="rot">Pico projetado de acessos simultâneos</span>
              <span className={`val ${c.pico.carga > cap ? 'critico' : ''}`}>{numero(c.pico.carga)}</span>
              <span className="det">às {c.pico.hora} · {Math.round((c.pico.carga / cap) * 100)}% da capacidade de {cap}</span>
            </div>
            <div style={{ margin: '-4px -6px 0' }}>
              <CurvaDia pontos={c.pontos} cap={cap} compacto altura={132} />
            </div>
          </>
        )}

        <div className="painel-secao">
          <h3>Eventos do dia</h3>
          {eventos.length > 0 ? (
            <ul className="painel-evs">
              {eventos.map((ev) => (
                <li key={ev.descricao} style={{ '--cor-ev': corDoTipo(ev.tipo) }}>
                  <div>
                    <b>{ev.descricao}</b>
                    <span>
                      {ev.hora_inicio === '00:00' ? 'o dia todo' : `${ev.hora_inicio} às ${ev.hora_fim}`} · {TIPOS[ev.tipo] || ev.tipo}
                      {ev.turmas?.length > 0 && ` · ${ev.turmas.length} turmas`}
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
            <div className="painel-motivo">
              <strong><MessageSquareText size={14} aria-hidden="true" /> Por que a IA marcou este dia</strong>
              <p>{r.motivo}</p>
              <AvisoIA origem={r.origem} />
            </div>
            <button className="botao primario bloco" onClick={() => abrirDia(iso)}>
              Abrir plano do dia <ArrowRight size={16} aria-hidden="true" />
            </button>
          </>
        )}
      </div>
    </aside>
  )
}

function GradeMes({ k, marcos, eventosDoDia, risco, picoDe, feriados, selecionado, selecionar, hoje, ocultos, aoTeclar }) {
  const { semanas, mes } = useMemo(() => semanasDoMes(k, ocultos.has('periodos') ? [] : marcos), [k, marcos, ocultos])
  return (
    <div className="card cal-grade" role="grid" aria-label="Calendário do mês" onKeyDown={aoTeclar}>
      <div className="cal-cab" role="row">
        {SEMANA.map((s, i) => <span key={s} role="columnheader" className={i >= 5 ? 'fds' : ''}>{s}</span>)}
      </div>
      {semanas.map((sem) => (
        <div key={sem.dias[0]} className="cal-semana" role="row" style={{ '--faixas': sem.raias }}>
          {sem.dias.map((iso) => {
            const d = paraData(iso)
            const r = risco[iso]
            const nivel = r ? nivelDaGravidade(r.gravidade) : null
            const evs = (eventosDoDia[iso] || []).filter((e) => !ocultos.has(e.tipo))
            const carga = picoDe[iso] ? situacaoDoNivel(picoDe[iso].nivel).chave : null
            const classes = [
              'cal-cel',
              d.getMonth() !== mes ? 'fora' : '',
              fimDeSemana(iso) ? 'fds' : '',
              feriados[iso] ? 'feriado' : '',
              nivel ? `r-${nivel.chave}` : '',
              carga && carga !== 'folga' ? `carga-${carga}` : '',
              iso === selecionado ? 'selecionado' : '',
              iso === hoje ? 'hoje' : '',
            ].join(' ')
            return (
              <div
                key={iso}
                className={classes}
                role="gridcell"
                tabIndex={iso === selecionado ? 0 : -1}
                data-iso={iso}
                aria-selected={iso === selecionado}
                aria-label={`${longa(iso)}${r ? `, dia de risco gravidade ${r.gravidade}` : ''}${evs.length ? `, ${evs.length} eventos` : ''}`}
                onClick={() => selecionar(iso)}
              >
                <div className="cal-topo">
                  <span className="cal-num">{d.getDate()}</span>
                  {nivel ? (
                    <span className={`cal-tag ${nivel.chave}`}>{nivel.rotulo}</span>
                  ) : picoDe[iso] && carga !== 'folga' ? (
                    <span className={`cal-pct ${carga}`}>{Math.round(picoDe[iso].razao * 100)}%</span>
                  ) : null}
                </div>
                {feriados[iso] && <span className="cal-feriado-nome">{feriados[iso].split(' (')[0]}</span>}
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

function Agenda({ eventos, feriadosLista, risco, irParaDia }) {
  const linhas = [
    ...eventos.map((ev) => ({ ...ev, chave: `${ev.data}-${ev.descricao}` })),
    ...feriadosLista.map((f) => ({ data: f.data, hora_inicio: '00:00', hora_fim: '23:59', tipo: 'feriado', descricao: f.nome, turmas: [], chave: `f-${f.data}` })),
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
                    {l.tipo === 'feriado' ? 'Feriado' : TIPOS[l.tipo] || l.tipo}
                    {l.turmas?.length > 0 && ` · ${l.turmas.join(', ')}`}
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

function Periodos({ marcos, inicio, fim }) {
  const t0 = paraData(inicio).getTime()
  const span = paraData(fim).getTime() - t0 || 1
  const pos = (iso) => Math.min(100, Math.max(0, ((paraData(iso).getTime() - t0) / span) * 100))
  const meses = diasEntre(inicio, fim).filter((iso, i) => i === 0 || iso.endsWith('-01'))
  return (
    <section className="card secao">
      <div className="card-cab">
        <div>
          <h2>Períodos do semestre</h2>
          <p>Janelas do calendário oficial · {curta(inicio)} a {curta(fim)}</p>
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
          {marcos.map((p) => (
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

const FILTROS = [
  ['prova_online', 'Prova online'],
  ['vencimento', 'Vencimento'],
  ['notas', 'Notas'],
  ['rematricula', 'Rematrícula'],
  ['outro', 'Acadêmico'],
  ['periodos', 'Períodos'],
]

export default function Calendario({ base, unidade, dia, abrirDia }) {
  const { contexto, eventos, marcos, riscos, picos } = base
  const hoje = paraIso(new Date())
  const mesInicio = mesDoIso(contexto.inicio)
  const mesFim = mesDoIso(contexto.fim)
  const limitar = (k) => Math.min(mesFim, Math.max(mesInicio, k))
  const [vista, setVista] = useState('mes')
  const [selecionado, setSelecionado] = useState(dia)
  const [k, setK] = useState(() => limitar(mesDoIso(dia)))
  const [ocultos, setOcultos] = useState(() => new Set())
  const gradeRef = useRef(null)

  const risco = useMemo(() => Object.fromEntries(riscos.map((r) => [r.data, r])), [riscos])
  const feriados = useMemo(() => feriadosDe(contexto), [contexto])
  const picoDe = useMemo(() => Object.fromEntries(picos.map((p) => [p.data, p])), [picos])
  const eventosDoDia = useMemo(() => {
    const m = {}
    for (const ev of eventos) (m[ev.data] = m[ev.data] || []).push(ev)
    return m
  }, [eventos])
  const contagem = useMemo(() => {
    const c = { folga: 0, atencao: 0, alto: 0, critico: 0 }
    for (const p of picos) c[situacaoDoNivel(p.nivel).chave] += 1
    return c
  }, [picos])
  const rotuloMes = capitalizar(new Date(Math.floor(k / 12), k % 12, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' }))

  function escolher(iso) {
    setSelecionado(iso)
    setK(limitar(mesDoIso(iso)))
  }

  function irParaDia(iso) {
    escolher(iso)
    setVista('mes')
  }

  function alternarFiltro(chave) {
    setOcultos((atual) => {
      const novo = new Set(atual)
      if (novo.has(chave)) novo.delete(chave)
      else novo.add(chave)
      return novo
    })
  }

  function teclar(e) {
    const passos = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
    if (e.key in passos) {
      e.preventDefault()
      const alvo = somarDias(selecionado, passos[e.key])
      escolher(alvo)
      requestAnimationFrame(() => gradeRef.current?.querySelector(`[data-iso="${alvo}"]`)?.focus())
    } else if (e.key === 'PageUp' || e.key === 'PageDown') {
      e.preventDefault()
      setK((x) => limitar(x + (e.key === 'PageUp' ? -1 : 1)))
    } else if (e.key === 'Enter' && risco[selecionado]) {
      abrirDia(selecionado)
    }
  }

  const painel = (
    <PainelDia
      iso={selecionado}
      unidade={unidade}
      base={base}
      risco={risco}
      eventos={eventosDoDia[selecionado] || []}
      feriados={feriados}
      abrirDia={abrirDia}
    />
  )

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Calendário acadêmico</h1>
          <p className="sub">
            Calendário oficial do {contexto.instituicao} {contexto.semestre} · {eventos.length} eventos · {contexto.feriados.length} feriados
          </p>
        </div>
        <div className="cab-acoes cal-toolbar">
          <div className="segmentado" role="group" aria-label="Vista">
            <button className={vista === 'mes' ? 'ativo' : ''} onClick={() => setVista('mes')}>
              <CalendarDays size={15} aria-hidden="true" /> Mês
            </button>
            <button className={vista === 'semestre' ? 'ativo' : ''} onClick={() => setVista('semestre')}>
              <CalendarRange size={15} aria-hidden="true" /> Semestre
            </button>
            <button className={vista === 'lista' ? 'ativo' : ''} onClick={() => setVista('lista')}>
              <List size={15} aria-hidden="true" /> Lista
            </button>
          </div>
          {vista === 'mes' && (
            <>
              <div className="grupo-botoes">
                <button onClick={() => setK((x) => limitar(x - 1))} disabled={k <= mesInicio} aria-label="Mês anterior">
                  <ChevronLeft size={17} aria-hidden="true" />
                </button>
                <button onClick={() => escolher(hoje)}>Hoje</button>
                <button onClick={() => setK((x) => limitar(x + 1))} disabled={k >= mesFim} aria-label="Próximo mês">
                  <ChevronRight size={17} aria-hidden="true" />
                </button>
              </div>
              <span className="cal-mes-rotulo">{rotuloMes}</span>
            </>
          )}
        </div>
      </header>

      {vista === 'mes' && (
        <div className="cal-layout">
          <div ref={gradeRef}>
            <div className="filtros" role="group" aria-label="Mostrar no calendário">
              {FILTROS.map(([chave, nome]) => (
                <button
                  key={chave}
                  className={`filtro ${ocultos.has(chave) ? 'desligado' : ''}`}
                  aria-pressed={!ocultos.has(chave)}
                  style={{ '--cor-ev': chave === 'periodos' ? 'var(--teal)' : corDoTipo(chave) }}
                  onClick={() => alternarFiltro(chave)}
                >
                  <i /> {nome}
                </button>
              ))}
              <span className="filtros-dica">setas movem o dia · Enter abre o plano</span>
            </div>
            <GradeMes
              k={k}
              marcos={marcos}
              eventosDoDia={eventosDoDia}
              risco={risco}
              picoDe={picoDe}
              feriados={feriados}
              selecionado={selecionado}
              selecionar={escolher}
              hoje={hoje}
              ocultos={ocultos}
              aoTeclar={teclar}
            />
            <div className="legenda" style={{ marginTop: 12 }}>
              <span><i className="topo" style={{ background: 'var(--atencao)' }} />carga em atenção</span>
              <span><i className="topo" style={{ background: 'var(--alto)' }} />perto do limite</span>
              <span><i className="topo" style={{ background: 'var(--critico)' }} />acima da capacidade</span>
              <span><i style={{ background: 'color-mix(in srgb, var(--critico) 22%, transparent)' }} />dia apontado pela IA</span>
              <span><i className="hachura" />feriado</span>
              <span><i className="redondo" style={{ background: 'var(--teal)' }} />hoje</span>
            </div>
          </div>
          {painel}
        </div>
      )}

      {vista === 'semestre' && (
        <div className="cal-layout">
          <div>
            <section className="card">
              <div className="card-cab">
                <div>
                  <h2>Semestre {contexto.semestre} em um olhar</h2>
                  <p>Cada dia pintado pelo pico projetado em % da capacidade · ponto = dia apontado pela IA · clique para ver o dia</p>
                </div>
              </div>
              <div className="card-corpo" style={{ paddingTop: 6 }}>
                <CalendarioCalor
                  picos={picos}
                  riscos={riscos}
                  feriados={feriados}
                  cap={contexto.capacidade}
                  inicio={contexto.inicio}
                  fim={contexto.fim}
                  selecionado={selecionado}
                  hoje={hoje}
                  aoEscolher={escolher}
                />
                <div className="legenda" style={{ marginTop: 6 }}>
                  <span><i style={{ background: 'var(--superficie-3)' }} />até 20%</span>
                  <span><i style={{ background: 'var(--folga)' }} />20–60%</span>
                  <span><i style={{ background: 'var(--atencao)' }} />60–85%</span>
                  <span><i style={{ background: 'var(--alto)' }} />85–100%</span>
                  <span><i style={{ background: 'var(--critico)' }} />acima de 100%</span>
                  <span><i className="redondo" style={{ background: 'var(--texto)' }} />apontado pela IA</span>
                </div>
              </div>
            </section>
            <div className="grade g-4 secao">
              <div className="card metrica"><span className="rot">Dias com folga</span><span className="val">{contagem.folga}</span></div>
              <div className="card metrica"><span className="rot">Em atenção</span><span className="val">{contagem.atencao}</span></div>
              <div className="card metrica"><span className="rot">Perto do limite</span><span className="val">{contagem.alto}</span></div>
              <div className="card metrica critico"><span className="rot">Acima da capacidade</span><span className="val">{contagem.critico}</span></div>
            </div>
          </div>
          {painel}
        </div>
      )}

      {vista === 'lista' && (
        <>
          <Periodos marcos={marcos} inicio={contexto.inicio} fim={contexto.fim} />
          <div className="secao">
            <Agenda eventos={eventos} feriadosLista={contexto.feriados} risco={risco} irParaDia={irParaDia} />
          </div>
        </>
      )}
    </>
  )
}
