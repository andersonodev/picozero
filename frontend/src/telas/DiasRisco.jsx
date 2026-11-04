// frontend/src/telas/DiasRisco.jsx
// Os dias de risco com gravidade e motivo escritos pelo Gemini; o pico vem do cálculo.
import { ArrowRight } from 'lucide-react'
import ChipTipo from '../componentes/ChipTipo'
import Gravidade from '../componentes/Gravidade'
import { CONTEXTO, DIAS_RISCO, EVENTOS, picoDoDia } from '../dados/previa'
import { situacaoDaCarga } from '../tema'
import { completa, curta, numero, paraData, rotuloCurto, semana } from '../util'

function tipoDoEvento(data, descricao) {
  return EVENTOS.find((e) => e.data === data && e.descricao === descricao)?.tipo || 'outro'
}

export default function DiasRisco({ abrirDia }) {
  const cap = CONTEXTO.capacidade
  const dias = [...DIAS_RISCO]
    .sort((a, b) => b.gravidade - a.gravidade || a.data.localeCompare(b.data))
    .map((r) => ({ ...r, pico: picoDoDia(r.data) }))
  const acima = dias.filter((d) => d.pico.carga > cap)
  const pior = dias.reduce((a, b) => (b.pico.carga > a.pico.carga ? b : a))
  const consultas = new Set(DIAS_RISCO.flatMap((r) => r.consultados)).size

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Dias críticos</h1>
          <p className="sub">O Gemini escolhe quais dias do histórico consultar e escreve o motivo de cada alerta. A gravidade vem dele; a carga, do cálculo.</p>
        </div>
      </header>

      <div className="grade g-4 secao">
        <div className="card metrica">
          <span className="rot">Apontados pelo Gemini</span>
          <span className="val">{dias.length}<small>dias</small></span>
          <span className="det">de risco no semestre {CONTEXTO.semestre}</span>
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
          <span className="det">que o próprio Gemini pediu para ver</span>
        </div>
      </div>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>Por gravidade</h2>
            <p>list[DiaRisco] escrito pelo Gemini · pico calculado pelo código</p>
          </div>
        </div>
        <div style={{ marginTop: 8 }}>
          {dias.map((d) => {
            const s = situacaoDaCarga(d.pico.carga, cap)
            const dt = paraData(d.data)
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
                      <ChipTipo key={e} tipo={tipoDoEvento(d.data, e)} texto={rotuloCurto(e)} />
                    ))}
                  </div>
                  <p className="risco-motivo">{d.motivo}</p>
                  <div className="risco-meta">
                    <span>Pico calculado <b>{numero(d.pico.carga)}</b> às {d.pico.hora}</span>
                    <span><b>{Math.round((d.pico.carga / cap) * 100)}%</b> da capacidade</span>
                    {d.consultados.length > 0 && <span>Consultou {d.consultados.map(completa).join(', ')}</span>}
                  </div>
                </div>
                <div className="risco-acoes">
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
