// frontend/src/telas/DiasRisco.jsx
// Os dias de risco: gravidade e motivo escritos pela IA, pico calculado pelo motor, a curva do
// dia por hora (mapa do motor) e o botão que pede uma nova análise ao Gemini.
import { useMemo, useState } from 'react'
import { ArrowRight, RefreshCw } from 'lucide-react'
import * as api from '../api/cliente'
import { usarApi } from '../api/usarApi'
import AvisoIA from '../componentes/AvisoIA'
import ChipTipo from '../componentes/ChipTipo'
import Gravidade from '../componentes/Gravidade'
import Sparkline from '../graficos/Sparkline'
import { corDoNivel } from '../graficos/escalas'
import { situacaoDoNivel, useTema } from '../tema'
import { completa, curta, numero, paraData, rotuloCurto, semana } from '../util'

export default function DiasRisco({ base, unidade, abrirDia }) {
  const t = useTema()
  const { contexto, eventos } = base
  const cap = contexto.capacidade
  const [novos, setNovos] = useState(null)
  const [analise, setAnalise] = useState({ estado: 'parado', msg: '' })
  const mapa = usarApi(() => api.mapaCalor(unidade), [unidade])
  const horasDe = useMemo(() => Object.fromEntries((mapa.dados || []).map((m) => [m.data, m.horas])), [mapa.dados])

  const riscos = novos || base.riscos
  const dias = [...riscos].sort((a, b) => b.gravidade - a.gravidade || a.data.localeCompare(b.data))
  const acima = dias.filter((d) => d.pico.carga > cap)
  const pior = dias.reduce((a, b) => (b.pico.carga > a.pico.carga ? b : a), dias[0])
  const consultas = new Set(riscos.flatMap((r) => r.consultados || [])).size
  const tipoDe = (data, descricao) => eventos.find((e) => e.data === data && e.descricao === descricao)?.tipo || 'outro'

  async function analisar() {
    setAnalise({ estado: 'rodando', msg: '' })
    const r = await api.analisarRiscos(unidade)
    if (Array.isArray(r.dados) && r.dados.length) {
      setNovos(r.dados)
      const via = r.dados[0]?.origem === 'gemini' ? 'pelo Gemini' : 'pelas regras do motor (IA indisponível)'
      setAnalise({ estado: 'ok', msg: `Análise refeita ${via} agora há pouco.` })
    } else {
      setAnalise({ estado: 'erro', msg: 'O motor não respondeu; mantida a análise anterior.' })
    }
  }

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Dias críticos</h1>
          <p className="sub">A IA escolhe quais dias do histórico consultar e escreve o motivo de cada alerta. A gravidade vem dela; a carga, do motor.</p>
        </div>
        <div className="cab-acoes">
          <button className="botao primario" onClick={analisar} disabled={analise.estado === 'rodando'}>
            {analise.estado === 'rodando' ? <span className="spinner claro" /> : <RefreshCw size={16} aria-hidden="true" />}
            {analise.estado === 'rodando' ? 'Analisando…' : 'Analisar de novo com Gemini'}
          </button>
        </div>
      </header>

      {analise.msg && <p className={`nota-rodape ${analise.estado}`} style={{ marginTop: -8, marginBottom: 14 }}>{analise.msg}</p>}

      <div className="grade g-4 secao">
        <div className="card metrica">
          <span className="rot">Apontados pela IA</span>
          <span className="val">{dias.length}<small>dias</small></span>
          <span className="det">de risco no semestre {contexto.semestre}</span>
        </div>
        <div className="card metrica critico">
          <span className="rot">Acima da capacidade</span>
          <span className="val">{acima.length}<small>dias</small></span>
          <span className="det">passam de {cap} acessos simultâneos</span>
        </div>
        <div className="card metrica">
          <span className="rot">Pior pico</span>
          <span className="val">{(pior.pico.carga / cap).toFixed(1).replace('.', ',')}×<small>a capacidade</small></span>
          <span className="det">{curta(pior.data)} às {pior.pico.hora} · {numero(pior.pico.carga)} acessos</span>
        </div>
        <div className="card metrica">
          <span className="rot">Consultas ao histórico</span>
          <span className="val">{consultas}<small>dias</small></span>
          <span className="det">que a própria IA pediu para ver</span>
        </div>
      </div>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>Por gravidade</h2>
            <p>Gravidade e motivo escritos pela IA · pico e curva calculados pelo motor</p>
          </div>
          <AvisoIA origem={dias[0]?.origem} />
        </div>
        <div style={{ marginTop: 8 }}>
          {dias.map((d) => {
            const s = situacaoDoNivel(d.nivel)
            const dt = paraData(d.data)
            const horas = horasDe[d.data]
            return (
              <article key={d.data} className="risco-item">
                <div className={`risco-data ${s.chave === 'critico' ? 'critico' : ''}`}>
                  <b>{dt.getDate()}</b>
                  <span>{dt.toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')} · {semana(d.data).slice(0, 3)}</span>
                </div>
                <div className="risco-corpo">
                  <div className="risco-titulo">
                    <Gravidade valor={d.gravidade} />
                    <span className={`pill ${s.chave}`}>{s.rotulo}</span>
                  </div>
                  <div className="risco-chips">
                    {d.eventos.map((e) => (
                      <ChipTipo key={e} tipo={tipoDe(d.data, e)} texto={rotuloCurto(e)} />
                    ))}
                  </div>
                  <p className="risco-motivo">{d.motivo}</p>
                  <div className="risco-meta">
                    <span>Pico calculado <b>{numero(d.pico.carga)}</b> às {d.pico.hora}</span>
                    <span><b>{Math.round((d.pico.carga / cap) * 100)}%</b> da capacidade</span>
                    {d.consultados?.length > 0 && <span>Consultou {d.consultados.map(completa).join(', ')}</span>}
                  </div>
                </div>
                <div className="risco-acoes">
                  <div className="risco-curva" title="Carga do dia por hora contra a capacidade">
                    {horas ? <Sparkline valores={horas} cap={cap} cor={corDoNivel(t, d.nivel)} /> : <div className="esq-bloco" style={{ height: 52 }} />}
                    <span>00h</span><span>12h</span><span>23h</span>
                  </div>
                  <button className="botao" onClick={() => abrirDia(d.data)}>
                    Abrir plano <ArrowRight size={16} aria-hidden="true" />
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      </section>
    </>
  )
}
