// frontend/src/telas/ProvaCarga.jsx
// Prova de carga: latência antes × depois × controle (saída de carga/comparar.py)
// e o que o aluno vê com a fila virtual. Sem ilustração: mock de produto em CSS.
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CircleCheck, Info, ShieldCheck, TriangleAlert } from 'lucide-react'
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
  const cores = { antes: t.semPlano, depois: t.comPlano, controle: t.controle }
  const [antes, depois] = resumo
  const picoAntes = series.reduce((a, b) => (b.antes > a.antes ? b : a))

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Prova de carga</h1>
          <p className="sub">
            O Locust reproduz a curva de 10/09 calculada pelo código (histórico + cálculo), nunca a saída do Gemini: a prova não é circular.
          </p>
        </div>
      </header>

      <section className="card aviso ok secao">
        <div className="aviso-icone"><CircleCheck size={20} strokeWidth={2} aria-hidden="true" /></div>
        <div className="aviso-corpo">
          <h3>Com o plano, o p95 cai de {numero(antes.p95)} ms para {numero(depois.p95)} ms</h3>
          <p>
            E os erros 503 vão de {pct(antes.erros)} para {pct(depois.erros)}. Mesmo servidor simulado, três perfis de carga.
          </p>
        </div>
      </section>

      <div className="grade g-3 secao">
        {resumo.map((c) => (
          <div key={c.chave} className="card metrica">
            <span className="perfil-cab"><i style={{ background: cores[c.chave] }} />{c.nome}</span>
            <span className="perfil-sub">{c.sub}</span>
            <div className="perfil-nums">
              <div>
                <div className="rot">p50</div>
                <div className="v">{numero(c.p50)}<small>ms</small></div>
              </div>
              <div>
                <div className="rot">p95</div>
                <div className="v">{numero(c.p95)}<small>ms</small></div>
              </div>
              <div>
                <div className="rot">Erros 503</div>
                <div className={`v ${c.erros > 0 ? 'critico' : ''}`}>{pct(c.erros)}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>Latência p95 ao longo do dia simulado</h2>
            <p>/sim/login e /sim/prova · base × (1 + (ativos ÷ {CONTEXTO.capacidade})³) · 503 acima de 1,5× a capacidade</p>
          </div>
          <div className="legenda">
            {resumo.map((c) => (
              <span key={c.chave}><i style={{ background: cores[c.chave], height: 3, width: 14 }} />{c.nome}</span>
            ))}
          </div>
        </div>
        <div className="card-corpo">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={series} margin={{ top: 26, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke={t.grade} />
              <XAxis dataKey="hora" interval={11} tick={{ fill: t.mudo, fontSize: 12 }} tickLine={false} axisLine={{ stroke: t.grade }} />
              <YAxis tick={{ fill: t.mudo, fontSize: 12 }} tickLine={false} axisLine={false} width={70} tickFormatter={(v) => `${numero(v)} ms`} />
              <Tooltip content={<Dica />} cursor={{ stroke: t.mudo, strokeDasharray: '3 3' }} />
              {resumo.map((c) => (
                <Line key={c.chave} type="monotone" dataKey={c.chave} name={c.nome} stroke={cores[c.chave]} strokeWidth={c.chave === 'depois' ? 2.5 : 2} dot={false} activeDot={{ r: 4, stroke: t.superficie, strokeWidth: 2 }} isAnimationActive={false} />
              ))}
              <ReferenceDot x={picoAntes.hora} y={picoAntes.antes} r={5} fill={cores.antes} stroke={t.superficie} strokeWidth={2} label={{ value: `sem plano: ${numero(picoAntes.antes)} ms`, position: 'top', fill: t.texto, fontSize: 12, fontWeight: 600 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>O que o aluno vê com a fila virtual</h2>
            <p>FILA_VIRTUAL=1 · asyncio.Semaphore({CONTEXTO.capacidade}) · quem entra navega com latência estável</p>
          </div>
        </div>
        <div className="card-corpo">
          <div className="grade g-2e">
            <div className="fila-mock" aria-label="Exemplo da tela de espera do portal">
              <div className="barra-nav">
                <span className="ponto" /><span className="ponto" /><span className="ponto" />
                <span className="url">portal.ibmec.br/login</span>
              </div>
              <div className="portal-topo">
                <b>Portal do aluno</b>
                <span>Sala de espera</span>
              </div>
              <div className="tela">
                <div className="rot">Sua posição na fila do Teste de Progresso</div>
                <div className="pos">132<small>º</small></div>
                <p>Sua vez chega em cerca de 40 segundos. Não feche nem recarregue esta página.</p>
                <div className="progresso"><span /></div>
                <div className="meta">posição estável · sem erro 503 · sessão garantida</div>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div className="explica">
                <h3><TriangleAlert size={16} style={{ color: 'var(--critico)' }} aria-hidden="true" />Sem fila</h3>
                <p>Acima de 1,5× a capacidade a rota devolve 503 e todo mundo recarrega, o que piora o pico. A latência cresce com o cubo da ocupação.</p>
              </div>
              <div className="explica">
                <h3><ShieldCheck size={16} style={{ color: 'var(--ok)' }} aria-hidden="true" />Com fila</h3>
                <p>O semáforo segura a concorrência na capacidade. Quem está dentro navega normal; quem espera vê a posição andar, em vez de erro.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <p className="nota-rodape">
        <Info size={15} aria-hidden="true" /> Prévia com números simulados. Na E8 estes valores vêm de carga/comparar.py.
      </p>
    </>
  )
}
