// frontend/src/telas/DiasRisco.jsx
// Tela 2: os dias de risco com gravidade e motivo escritos pelo Gemini.
import Gravidade from '../componentes/Gravidade'
import { CONTEXTO, DIAS_RISCO, EVENTOS, picoDoDia } from '../dados/previa'
import { completa, curta, diasEntre, numero, paraData, semana } from '../util'

function Kpi({ valor, texto }) {
  return (
    <div className="cartao kpi">
      <div className="numero">{valor}</div>
      <p>{texto}</p>
    </div>
  )
}

function tipoDoEvento(data, descricao) {
  return EVENTOS.find((e) => e.data === data && e.descricao === descricao)?.tipo || 'outro'
}

export default function DiasRisco({ abrirDia }) {
  const cap = CONTEXTO.capacidade
  const dias = [...DIAS_RISCO]
    .sort((a, b) => b.gravidade - a.gravidade || a.data.localeCompare(b.data))
    .map((r) => ({ ...r, pico: picoDoDia(r.data) }))
  const acima = dias.filter((d) => d.pico.carga > cap)
  const pior = Math.max(...dias.map((d) => d.pico.carga))
  const letivos = diasEntre(CONTEXTO.inicio, CONTEXTO.fim).filter((iso) => {
    const semanaDia = paraData(iso).getDay()
    return semanaDia !== 0 && semanaDia !== 6 && !CONTEXTO.feriados.some((f) => f.data === iso)
  }).length
  const consultas = new Set(DIAS_RISCO.flatMap((r) => r.consultados)).size

  return (
    <>
      <header style={{ marginBottom: 24 }}>
        <div className="eyebrow">Dias críticos · análise do Gemini</div>
        <h1 className="h-page">
          {acima.length} dias passam da capacidade no semestre.
        </h1>
        <p className="lide">
          O Gemini decidiu sozinho quais dias do histórico consultar ({consultas} consultas) e escreveu o motivo de
          cada alerta. A gravidade vem dele; a carga vem do cálculo determinístico.
        </p>
      </header>

      <div className="grade-4" style={{ marginBottom: 20 }}>
        <Kpi valor={DIAS_RISCO.length} texto="dias de risco apontados pelo Gemini" />
        <Kpi valor={acima.length} texto={`passam da capacidade de ${cap} acessos simultâneos`} />
        <Kpi valor={`${(pior / cap).toFixed(1).replace('.', ',')}×`} texto="o pior pico em relação à capacidade" />
        <Kpi valor={`${acima.length}/${letivos}`} texto="dias letivos precisam de infraestrutura extra" />
      </div>


      <section className="cartao">
        <div className="cartao-topo">
          <div>
            <h3>Dias de risco por gravidade</h3>
            <p>list[DiaRisco] · gravidade, eventos e motivo escritos pelo Gemini · pico calculado pelo código</p>
          </div>
        </div>
        {dias.map((d) => (
          <article key={d.data} className="dia-risco">
            <div>
              <div className="dia-data">{curta(d.data)}</div>
              <div className="dia-semana">{semana(d.data)}</div>
              <div style={{ marginTop: 10 }}>
                <Gravidade valor={d.gravidade} />
              </div>
            </div>
            <div>
              <div className="dia-chips">
                {d.eventos.map((e) => (
                  <span key={e} className={`chip ${tipoDoEvento(d.data, e)}`}>
                    <i />
                    {e}
                  </span>
                ))}
              </div>
              <p className="dia-motivo">{d.motivo}</p>
              <div className="consultas">
                Pico calculado <b className="mono">{numero(d.pico.carga)}</b> às {d.pico.hora}
                {d.pico.carga > cap ? ` (${Math.round((d.pico.carga / cap) * 100)}% da capacidade)` : ''}
                {d.consultados.length > 0 && (
                  <>
                    {' · consultou no histórico: '}
                    {d.consultados.map((c, i) => (
                      <span key={c} className="mono">
                        {i > 0 && ', '}
                        {completa(c)}
                      </span>
                    ))}
                  </>
                )}
              </div>
            </div>
            <button className="botao" onClick={() => abrirDia(d.data)}>
              Abrir dia →
            </button>
          </article>
        ))}
      </section>
    </>
  )
}
