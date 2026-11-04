// frontend/src/telas/Alertas.jsx
// Alertas antes do pico: próximos 7 dias, alertas antecipados em tempo real (SSE do motor) e a
// demonstração "dia ao vivo", em que a carga real foge da previsão e o motor avisa antes do pico.
import { useEffect, useMemo, useRef, useState } from 'react'
import { BellRing, CircleCheck, Info, Play, Radio, Square } from 'lucide-react'
import * as api from '../api/cliente'
import { usarApi } from '../api/usarApi'
import Grafico from '../graficos/Grafico'
import { alfa } from '../graficos/echarts'
import { useTema } from '../tema'
import { curta, esc, numero, semana } from '../util'

const PILL = { critico: 'critico', serio: 'alto', alerta: 'atencao', ok: 'ok' }
const ROTULO = { critico: 'crítico', serio: 'alto', alerta: 'atenção', ok: 'folga' }
const ESTAGIO = {
  planejamento: 'Planejamento',
  preparacao: 'Preparação',
  vespera: 'Véspera',
  iminente: 'Iminente',
  em_curso: 'Em curso',
  ao_vivo: 'Ao vivo',
}
const ORDEM = { critico: 3, serio: 2, alerta: 1, ok: 0 }

function quando(min) {
  if (min <= 0) return 'agora'
  if (min < 120) return `em ${min} min`
  if (min < 48 * 60) return `em ${Math.round(min / 60)} h`
  return `em ${Math.round(min / 1440)} dias`
}

function CartaoAlerta({ a, aoReconhecer, abrirDia }) {
  return (
    <article className="card secao" style={{ padding: '16px 18px', borderLeft: `4px solid var(--${PILL[a.nivel] === 'atencao' ? 'atencao' : PILL[a.nivel]})` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className={`pill ${PILL[a.nivel]}`}>{ROTULO[a.nivel]}</span>
          <span className="pill sem-ponto">{a.origem === 'ao_vivo' ? 'ao vivo' : ESTAGIO[a.estagio]}</span>
          <span className="mono" style={{ fontSize: 12.5, color: 'var(--texto-2)' }}>{quando(a.antecedencia_min)}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="botao" onClick={() => abrirDia?.(a.data)}>Plano do dia</button>
          {a.reconhecido_em ? (
            <span className="pill ok sem-ponto"><CircleCheck size={13} aria-hidden="true" />reconhecido</span>
          ) : (
            <button className="botao primario" onClick={() => aoReconhecer(a.id)}>Reconhecer</button>
          )}
        </div>
      </div>
      <h3 style={{ margin: '10px 0 4px', fontSize: 16 }}>{a.titulo}</h3>
      <p style={{ margin: 0, color: 'var(--texto-2)', fontSize: 14 }}>{a.mensagem}</p>
      {a.acoes?.length > 0 && (
        <ul style={{ margin: '10px 0 0', paddingLeft: 18, fontSize: 13.5 }}>
          {a.acoes.slice(0, 5).map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      )}
    </article>
  )
}

function ProximosDias({ dados, abrirDia }) {
  if (!dados) return <div className="esq-bloco" style={{ height: 112 }} aria-busy="true" />
  return (
    <div className="grade g-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))' }}>
      {dados.dias.map((d) => (
        <button
          key={d.data}
          className="card metrica"
          style={{ textAlign: 'left', cursor: 'pointer', borderTop: `3px solid var(--${PILL[d.nivel] === 'ok' ? 'borda' : PILL[d.nivel]})` }}
          onClick={() => abrirDia?.(d.data)}
          title={d.eventos.join(' · ') || 'sem eventos'}
        >
          <span className="rot">{semana(d.data).slice(0, 3)} · {curta(d.data)}</span>
          <span className="val" style={{ fontSize: 26 }}>{numero(d.pico)}</span>
          <span className="det">às {d.hora} · <span className={`prioridade ${d.nivel === 'critico' ? 'alta' : d.nivel === 'ok' ? 'baixa' : 'media'}`}>{ROTULO[d.nivel]}</span></span>
        </button>
      ))}
    </div>
  )
}

function DiaAoVivo({ unidade }) {
  const t = useTema()
  const [estado, setEstado] = useState('parado') // parado | rodando | fim | erro
  const [inicio, setInicio] = useState(null)
  const [pontos, setPontos] = useState([])
  const [corrigida, setCorrigida] = useState(null)
  const [noAlerta, setNoAlerta] = useState(null) // {hora, serie}: previsão corrigida quando o alerta ao vivo saiu
  const [disparos, setDisparos] = useState([])
  const [fim, setFim] = useState(null)
  const [passo, setPasso] = useState(1200)
  const cancelar = useRef(null)

  useEffect(() => () => cancelar.current?.(), [])

  function rodar() {
    cancelar.current?.()
    setEstado('rodando')
    setInicio(null)
    setPontos([])
    setCorrigida(null)
    setNoAlerta(null)
    setDisparos([])
    setFim(null)
    cancelar.current = api.simularAoVivo(
      {
        inicio: (d) => setInicio(d),
        ponto: (p) => {
          setPontos((xs) => [...xs, p])
          setCorrigida(p.previsao_corrigida)
        },
        alerta: (a) => {
          setDisparos((xs) => [...xs, { ...a, hora_disparo: null }])
          if (a.origem === 'ao_vivo') setNoAlerta((x) => x || { pendente: true })
        },
        fim: (f) => {
          setFim(f)
          setEstado('fim')
        },
        erro: () => setEstado((e) => (e === 'fim' ? e : 'erro')),
      },
      { unidade, data: '2026-11-12', inicio: '16:00', fim: '22:00', passoMs: passo, surpresa: 1.35, surpresaDesde: '17:30' },
    )
  }

  function parar() {
    cancelar.current?.()
    setEstado('parado')
  }

  // hora em que cada alerta disparou = último ponto recebido antes dele
  const horaAtual = pontos.length ? pontos[pontos.length - 1].hora : null
  useEffect(() => {
    setDisparos((xs) => xs.map((x) => (x.hora_disparo ? x : { ...x, hora_disparo: horaAtual })))
    setNoAlerta((x) => (x?.pendente ? { hora: horaAtual, serie: corrigida } : x))
  }, [disparos.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const opcao = useMemo(() => {
    if (!inicio) return null
    const horas = Array.from({ length: 96 }, (_, i) => `${String(Math.floor(i / 4)).padStart(2, '0')}:${String((i % 4) * 15).padStart(2, '0')}`)
    const ini = horas.indexOf('16:00')
    const fimI = horas.indexOf('22:00')
    const fatia = (arr) => arr.slice(ini, fimI + 1)
    const real = Object.fromEntries(pontos.map((p) => [p.hora, p.real]))
    const cap = inicio.capacidade
    const marcados = disparos.filter((d) => d.hora_disparo && (d.origem === 'ao_vivo' || d.estagio === 'iminente'))
    return {
      grid: { left: 52, right: 18, top: 30, bottom: 28 },
      xAxis: { type: 'category', data: fatia(horas), boundaryGap: false, axisLabel: { interval: 3 } },
      yAxis: { type: 'value', axisLabel: { formatter: (v) => numero(v) } },
      tooltip: {
        trigger: 'axis',
        confine: true,
        formatter: (ps) =>
          [`<b>${ps[0].axisValue}</b>`, ...ps.filter((p) => p.value != null).map((p) => `${esc(p.seriesName)} <b style="float:right;margin-left:14px">${numero(p.value)}</b>`)].join('<br/>'),
      },
      series: [
        {
          name: 'Previsão original',
          type: 'line',
          data: fatia(inicio.previsao_original),
          symbol: 'none',
          lineStyle: { color: t.controle, width: 1.6, type: [5, 4] },
          itemStyle: { color: t.controle },
          markLine: {
            symbol: 'none',
            silent: true,
            data: [{ yAxis: cap, lineStyle: { color: t.critico, type: [6, 4], width: 1.5 }, label: { formatter: `capacidade ${cap}`, position: 'insideEndTop', color: t.critico, fontSize: 11 } }],
          },
        },
        {
          // Só o futuro: durante a reprodução, a previsão corrigida do resto do dia; no fim, a projeção
          // congelada no momento do alerta ao vivo (mostra o que o motor já sabia antes do pico).
          name: noAlerta?.serie && estado === 'fim' ? `Previsão corrigida às ${noAlerta.hora}` : 'Previsão corrigida ao vivo',
          type: 'line',
          data: (() => {
            const base = estado === 'fim' && noAlerta?.serie ? noAlerta.serie : corrigida
            const corte = estado === 'fim' && noAlerta?.hora ? noAlerta.hora : horaAtual
            if (!base) return []
            return fatia(horas).map((h, i) => (corte && h < corte ? null : fatia(base)[i]))
          })(),
          symbol: 'none',
          lineStyle: { color: t.comPlano, width: 2.4 },
          itemStyle: { color: t.comPlano },
          areaStyle: { color: alfa(t.comPlano, 0.08) },
        },
        {
          name: 'Carga real',
          type: 'line',
          data: fatia(horas).map((h) => real[h] ?? null),
          symbol: 'circle',
          symbolSize: 5,
          lineStyle: { color: t.semPlano, width: 2.4 },
          itemStyle: { color: t.semPlano },
          markLine: horaAtual
            ? { symbol: 'none', silent: true, data: [{ xAxis: horaAtual, lineStyle: { color: t.mudo, type: 'solid', width: 1 }, label: { formatter: 'agora', color: t.texto2, fontSize: 11 } }] }
            : undefined,
          markPoint: {
            data: marcados.map((d) => ({
              coord: [d.hora_disparo, real[d.hora_disparo] ?? 0],
              symbol: 'pin',
              symbolSize: 34,
              itemStyle: { color: d.origem === 'ao_vivo' ? t.critico : t.alto },
              label: { formatter: '!', color: '#fff', fontWeight: 700 },
            })),
          },
        },
      ],
    }
  }, [inicio, pontos, corrigida, disparos, horaAtual, noAlerta, estado, t])

  return (
    <section className="card secao">
      <div className="card-cab">
        <div>
          <h2>Dia ao vivo · 12/11, abertura da AP2</h2>
          <p>
            O motor recebe a carga real a cada 15 min, corrige a previsão do resto do dia (nowcast) e dispara o alerta
            antes do pico. Na simulação, a carga real fica 35% acima do previsto a partir das 17h30.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <div className="segmentado" role="group" aria-label="Velocidade">
            {[[1200, '1×'], [500, '2×']].map(([ms, rot]) => (
              <button key={ms} className={passo === ms ? 'ativo' : ''} onClick={() => setPasso(ms)} disabled={estado === 'rodando'}>{rot}</button>
            ))}
          </div>
          {estado === 'rodando' ? (
            <button className="botao" onClick={parar}><Square size={14} aria-hidden="true" />Parar</button>
          ) : (
            <button className="botao primario" onClick={rodar}><Play size={14} aria-hidden="true" />Rodar dia ao vivo</button>
          )}
        </div>
      </div>
      <div className="card-corpo">
        {opcao ? (
          <Grafico opcao={opcao} altura={300} rotulo="Carga real, previsão original e previsão corrigida ao vivo" />
        ) : (
          <div className="vazio" style={{ padding: 28 }}>
            {estado === 'erro' ? 'Motor indisponível: a simulação ao vivo precisa da API no ar.' : 'Clique em "Rodar dia ao vivo" para reproduzir 16h–22h de 12/11 com métricas chegando em tempo real.'}
          </div>
        )}
        {disparos.length > 0 && (
          <ul className="log" style={{ marginTop: 14 }}>
            {disparos.map((d, i) => (
              <li key={`${d.id}-${i}`}>
                <span className="mono">{d.hora_disparo || '—'}</span>
                <div>
                  <b>{d.origem === 'ao_vivo' ? 'Alerta ao vivo' : `Alerta · ${ESTAGIO[d.estagio]}`}</b> · {d.titulo}
                  <div style={{ color: 'var(--texto-2)', fontSize: 13 }}>{d.mensagem}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
        {fim && (
          <div className="card aviso ok" style={{ marginTop: 14 }}>
            <div className="aviso-icone"><BellRing size={20} aria-hidden="true" /></div>
            <div className="aviso-corpo">
              <h3>
                Pico real de {numero(fim.pico_real.carga)} às {fim.pico_real.hora}
                {fim.antecedencia_ao_vivo_min != null ? `: o alerta ao vivo saiu ${fim.antecedencia_ao_vivo_min} min antes` : ''}
              </h3>
              <p>
                Previsão original: {numero(fim.pico_previsto_original.carga)} às {fim.pico_previsto_original.hora}.
                {fim.primeiro_alerta_serio && ` Primeiro alerta da previsão às ${fim.primeiro_alerta_serio} (${fim.antecedencia_min} min antes).`}
                {fim.primeiro_alerta_ao_vivo && ` Às ${fim.primeiro_alerta_ao_vivo.hora} o motor já projetava ${numero(fim.primeiro_alerta_ao_vivo.pico_previsto)} às ${fim.primeiro_alerta_ao_vivo.hora_pico}.`}
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

export default function Alertas({ unidade, abrirDia }) {
  const prev = usarApi(() => api.previsao(unidade, 6), [unidade])
  const inicial = usarApi(() => api.alertas(unidade), [unidade])
  const [alertas, setAlertas] = useState(null)
  const [conexao, setConexao] = useState('conectando')

  useEffect(() => {
    if (inicial.dados) setAlertas(inicial.dados)
  }, [inicial.dados])

  useEffect(() => {
    setConexao('conectando')
    const cancelar = api.assinarAlertas(
      {
        snapshot: (lista) => {
          setAlertas(lista)
          setConexao('ao vivo')
        },
        alerta: (a) => {
          if (a.unidade !== unidade || a.origem === 'ao_vivo') return
          setAlertas((xs) => {
            const lista = xs || []
            const i = lista.findIndex((x) => x.id === a.id)
            return i >= 0 ? lista.map((x, j) => (j === i ? a : x)) : [a, ...lista]
          })
        },
        erro: () => setConexao('reconectando'),
      },
      unidade,
    )
    return cancelar
  }, [unidade])

  async function reconhecer(id) {
    const r = await api.reconhecerAlerta(id)
    if (r.dados) setAlertas((xs) => xs.map((x) => (x.id === id ? r.dados : x)))
  }

  const ordenados = [...(alertas || [])].sort(
    (a, b) => (a.antecedencia_min > 0 ? a.antecedencia_min : -1) - (b.antecedencia_min > 0 ? b.antecedencia_min : -1) || ORDEM[b.nivel] - ORDEM[a.nivel],
  )
  const conta = (n) => ordenados.filter((a) => a.nivel === n).length
  const prox = prev.dados?.proximo_risco

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Alertas antes do pico</h1>
          <p className="sub">
            O motor varre a previsão dos próximos 14 dias e avisa em estágios: planejamento (mais de 72 h),
            preparação, véspera, iminente (menos de 2 h) e ao vivo, quando a carga real foge da previsão.
          </p>
        </div>
        <span className={`pill ${conexao === 'ao vivo' ? 'ok' : 'atencao'}`} title="Stream de alertas (SSE)">
          <Radio size={13} aria-hidden="true" />
          {conexao === 'ao vivo' ? 'conectado ao motor' : conexao === 'conectando' ? 'conectando…' : 'reconectando…'}
        </span>
      </header>

      <div className="grade g-4 secao">
        <div className="card metrica critico">
          <span className="rot">Críticos</span>
          <span className="val">{alertas ? conta('critico') : '—'}</span>
          <span className="det">acima da capacidade</span>
        </div>
        <div className="card metrica">
          <span className="rot">Altos e de atenção</span>
          <span className="val">{alertas ? conta('serio') + conta('alerta') : '—'}</span>
          <span className="det">60% a 100% da capacidade</span>
        </div>
        <div className="card metrica">
          <span className="rot">Próximo dia de risco</span>
          <span className="val" style={{ fontSize: 28 }}>{prox ? curta(prox.data) : '—'}</span>
          <span className="det">{prox ? `pico ${numero(prox.pico)} às ${prox.hora} · ${ROTULO[prox.nivel]}` : 'nada nos próximos 7 dias'}</span>
        </div>
        <div className="card metrica">
          <span className="rot">Pior dos próximos 7 dias</span>
          <span className="val" style={{ fontSize: 28 }}>{prev.dados?.pior ? numero(prev.dados.pior.pico) : '—'}</span>
          <span className="det">{prev.dados?.pior ? `${curta(prev.dados.pior.data)} às ${prev.dados.pior.hora} · ${String(prev.dados.pior.razao).replace('.', ',')}× a capacidade` : ''}</span>
        </div>
      </div>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>Próximos 7 dias</h2>
            <p>pico previsto de cada dia · clique para abrir o plano do dia</p>
          </div>
        </div>
        <div className="card-corpo">
          <ProximosDias dados={prev.dados} abrirDia={abrirDia} />
        </div>
      </section>

      <div className="secao">
        <h2 style={{ fontSize: 17, margin: '6px 0 12px' }}>Alertas ativos</h2>
        {alertas === null && <div className="esq-bloco" style={{ height: 140 }} aria-busy="true" />}
        {alertas && ordenados.length === 0 && (
          <div className="card vazio" style={{ padding: 22 }}>Nenhum alerta: a previsão dos próximos 14 dias fica abaixo de 60% da capacidade.</div>
        )}
        {ordenados.map((a) => (
          <CartaoAlerta key={a.id} a={a} aoReconhecer={reconhecer} abrirDia={abrirDia} />
        ))}
      </div>

      <DiaAoVivo unidade={unidade} />

      <p className="nota-rodape">
        <Info size={15} aria-hidden="true" />
        {inicial.origem === 'api'
          ? 'Alertas calculados pelo motor sobre a previsão (histórico + calendário) e atualizados em tempo real por SSE. Com ALERTA_WEBHOOK_URL, os altos e críticos também vão para Slack/Google Chat/Teams.'
          : 'Motor fora do ar: sem alertas em tempo real nesta prévia.'}
      </p>
    </>
  )
}
