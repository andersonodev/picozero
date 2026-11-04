// frontend/src/telas/ProvaCarga.jsx
// Prova de carga: latência antes × depois × controle (saída de carga/comparar.py)
// e o que o aluno vê com a fila virtual. Sem ilustração: mock de produto em CSS.
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CONTEXTO, resumoLatencia, seriesLatencia } from '../dados/previa'
import { useTema } from '../tema'
import { numero } from '../util'

function Dica({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="dica-grafico">
      <div className="cab">{label} · p95</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="linha">
          <span><i style={{ background: p.color || p.stroke }} />{p.name}</span>
          <b>{numero(p.value)} ms</b>
        </div>
      ))}
    </div>
  )
}

const pct = (x) => `${(x * 100).toFixed(1).replace('.', ',')}%`

export default function ProvaCarga() {
  const t = useTema()
  const series = seriesLatencia()
  const resumo = resumoLatencia()
  const cores = { antes: t.serie2, depois: t.serie1, controle: t.serie3 }
  const [antes, depois] = resumo
  const picoAntes = series.reduce((a, b) => (b.antes > a.antes ? b : a))

  return (
    <>
      <div className="secao" style={{ marginBottom: 16 }}>
        <div className="eyebrow">Prova · teste de carga com Locust</div>
        <h1 className="h-page">
          Com o plano, o p95 cai de <span className="destaque">{numero(antes.p95)} ms</span> para {numero(depois.p95)} ms.
        </h1>
        <p className="lide">
          O Locust reproduz a curva do dia calculada pelo código (histórico + cálculo), nunca a saída do Gemini — assim a
          prova não é circular. Mesmo servidor simulado, três perfis de carga.
        </p>
      </div>

      <div className="grade-3 secao">
        {resumo.map((c) => (
          <div key={c.chave} className={`card tile ${c.erros > 0 ? 'ruim' : ''}`} style={{ minHeight: 0 }}>
            <span className="k" style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
              <i style={{ width: 12, height: 3, borderRadius: 2, background: cores[c.chave], display: 'inline-block' }} />
              {c.nome}
            </span>
            <span className="d" style={{ marginBottom: 10 }}>{c.sub}</span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
              <div><div className="k">p50</div><div className="num" style={{ fontSize: 22 }}>{numero(c.p50)}<small style={{ fontSize: 11, color: 'var(--mudo)' }}> ms</small></div></div>
              <div><div className="k">p95</div><div className="num" style={{ fontSize: 22 }}>{numero(c.p95)}<small style={{ fontSize: 11, color: 'var(--mudo)' }}> ms</small></div></div>
              <div><div className="k">503</div><div className="num" style={{ fontSize: 22, color: c.erros > 0 ? 'var(--critico)' : 'inherit' }}>{pct(c.erros)}</div></div>
            </div>
          </div>
        ))}
      </div>

      <div className="card secao">
        <div className="card-cab">
          <div>
            <h3>Latência p95 ao longo do dia simulado</h3>
            <div className="meta">/sim/login · /sim/prova · base × (1 + (ativos ÷ {CONTEXTO.capacidade})³) · 503 acima de 1,5× a capacidade</div>
          </div>
          <div className="legenda">
            {resumo.map((c) => (<span key={c.chave}><i className="linha" style={{ background: cores[c.chave] }} />{c.nome}</span>))}
          </div>
        </div>
        <div className="card-corpo">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={series} margin={{ top: 28, right: 28, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke={t.grade} />
              <XAxis dataKey="hora" interval={11} tick={{ fill: t.mudo, fontSize: 12 }} tickLine={false} axisLine={{ stroke: t.grade }} />
              <YAxis tick={{ fill: t.mudo, fontSize: 12 }} tickLine={false} axisLine={false} width={66} tickFormatter={(v) => `${numero(v)} ms`} />
              <Tooltip content={<Dica />} cursor={{ stroke: t.mudo, strokeDasharray: '3 3' }} />
              {resumo.map((c) => (
                <Line key={c.chave} type="monotone" dataKey={c.chave} name={c.nome} stroke={cores[c.chave]} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: t.superficie, strokeWidth: 2 }} isAnimationActive={false} />
              ))}
              <ReferenceDot x={picoAntes.hora} y={picoAntes.antes} r={5} fill={cores.antes} stroke={t.superficie} strokeWidth={2} label={{ value: `pico sem plano ${numero(picoAntes.antes)} ms`, position: 'top', fill: t.texto, fontSize: 12 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card secao">
        <div className="card-cab">
          <div>
            <h3>O que o aluno vê · FILA_VIRTUAL=1</h3>
            <div className="meta">asyncio.Semaphore({CONTEXTO.capacidade}) · quem entra tem latência estável</div>
          </div>
        </div>
        <div className="card-corpo">
          <div className="grade-2e">
            <div className="fila-mock">
              <div className="barra-nav">
                <span className="ponto" /><span className="ponto" /><span className="ponto" />
                <span className="url">portal.ibmec.br/login</span>
              </div>
              <div className="tela">
                <div className="eyebrow">Sala de espera · AV1 online</div>
                <div className="pos">132<small>º</small></div>
                <div style={{ color: 'var(--texto-2)', fontSize: 13 }}>Sua vez chega em cerca de 40 segundos. Não feche nem recarregue esta página.</div>
                <div className="progresso"><span /></div>
                <div className="meta">posição estável · sem 503 · sessão garantida</div>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 14 }}>
              <div>
                <div className="eyebrow">Sem fila</div>
                <p style={{ margin: '6px 0 0', color: 'var(--texto-2)', fontSize: 13 }}>Acima de 1,5× a capacidade a rota devolve 503 e todo mundo recarrega, o que piora o pico. A latência cresce com o cubo da ocupação.</p>
              </div>
              <div>
                <div className="eyebrow">Com fila</div>
                <p style={{ margin: '6px 0 0', color: 'var(--texto-2)', fontSize: 13 }}>O semáforo segura a concorrência na capacidade. Quem está dentro navega normal; quem espera vê a posição andar, em vez de erro.</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <p className="nota-previa">Prévia com números simulados. Na E8 estes valores vêm de carga/comparar.py.</p>
    </>
  )
}
