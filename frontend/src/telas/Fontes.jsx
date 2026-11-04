// frontend/src/telas/Fontes.jsx
// Fonte de dados: o que é medido e o que é modelado (os jurados vão perguntar "isso é real?").
import { FlaskConical, Radio } from 'lucide-react'
import { FONTES, SONDA } from '../dados/fontes'

function Fonte({ f }) {
  const real = f.tipo === 'real'
  return (
    <div className="fonte-item">
      <span className={`fonte-icone ${real ? 'real' : 'modelo'}`}>
        {real ? <Radio size={17} aria-hidden="true" /> : <FlaskConical size={17} aria-hidden="true" />}
      </span>
      <div>
        <h3>{f.titulo}</h3>
        <p>{f.texto}</p>
        <code>{f.mono}</code>
      </div>
    </div>
  )
}

export default function Fontes() {
  const reais = FONTES.filter((f) => f.tipo === 'real')
  const modelos = FONTES.filter((f) => f.tipo !== 'real')

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Fonte de dados</h1>
          <p className="sub">O que é medido e o que é modelado nesta prévia. O calendário acadêmico é o oficial do Ibmec RJ 2026.2.</p>
        </div>
      </header>

      <div className="grade g-2e secao">
        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Medido</h2>
              <p>Observado hoje, de fora, sem carga e sem acesso interno</p>
            </div>
            <span className="pill ok">real</span>
          </div>
          <div className="card-corpo">
            {reais.map((f) => <Fonte key={f.titulo} f={f} />)}
          </div>
        </section>

        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Modelado</h2>
              <p>Gerado pelo código enquanto o histórico real não é liberado</p>
            </div>
            <span className="pill atencao">modelo</span>
          </div>
          <div className="card-corpo">
            {modelos.map((f) => <Fonte key={f.titulo} f={f} />)}
          </div>
        </section>
      </div>

      <div className="grade g-2e secao">
        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Sonda pública do site</h2>
              <p>Uma requisição contra {SONDA.alvo}, sem carga · {SONDA.medido_em}</p>
            </div>
          </div>
          <div className="card-corpo">
            <dl className="spec">
              <dt>Infraestrutura</dt><dd>{SONDA.infra}</dd>
              <dt>Peso da home</dt><dd>{SONDA.home_kb} KB</dd>
              <dt>TTFB em cache</dt><dd>{SONDA.ttfb_cache_ms} ms</dd>
              <dt>TTFB frio</dt><dd>~{SONDA.ttfb_frio_ms} ms</dd>
              <dt>Cache de borda</dt><dd>{SONDA.cache}</dd>
              <dt>Redirecionamento</dt><dd>{SONDA.redirecionamento}</dd>
            </dl>
          </div>
        </section>

        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Como trocar pelo histórico real</h2>
              <p>Só com acesso autorizado por escrito</p>
            </div>
          </div>
          <div className="card-corpo">
            <ol className="passos">
              <li>A Yduqs exporta o histórico de acessos do Elastic APM (CSV do Kibana) ou emite uma API key só de leitura.</li>
              <li>O PicoZero importa o arquivo no lugar do histórico modelado; o restante do fluxo não muda.</li>
              <li>As curvas passam a ser calibradas com o dado medido, e esta tela troca “modelo” por “real”.</li>
            </ol>
          </div>
        </section>
      </div>
    </>
  )
}
