// frontend/src/telas/Fontes.jsx
// Fonte de dados: o que é medido e o que é modelado (os jurados vão perguntar "isso é real?"),
// a validação com dado público real e o backtest do motor.
import { FlaskConical, Radio } from 'lucide-react'
import * as api from '../api/cliente'
import { usarApi } from '../api/usarApi'
import { FONTES, SONDA } from '../dados/fontes'
import Validacao from '../graficos/Validacao'
import { numero } from '../util'

const virgula = (x, casas = 2) => (x == null ? '—' : x.toFixed(casas).replace('.', ','))

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

export default function Fontes({ unidade }) {
  const fontes = usarApi(() => api.fontes(unidade), [unidade])
  const validacao = usarApi(() => api.validacaoPublica(unidade), [unidade])
  const modelo = usarApi(() => api.modelo(unidade), [unidade])
  const cartoes = fontes.dados?.cartoes || FONTES
  const reais = cartoes.filter((f) => f.tipo === 'real')
  const modelos = cartoes.filter((f) => f.tipo !== 'real')
  const v = validacao.dados
  const bt = modelo.dados?.backtest
  const ia = fontes.dados?.bruto?.ia

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Fonte de dados</h1>
          <p className="sub">O que é medido e o que é modelado. O calendário acadêmico é o oficial do Ibmec RJ 2026.2; a carga vem do motor, nunca da IA.</p>
        </div>
        {ia && (
          <div className="cab-acoes">
            <span className={`pill ${ia.modo === 'gemini' || ia.configurado ? 'ok' : 'atencao'}`}>
              IA: {ia.configurado ? `Gemini (${ia.modelo})` : 'modo regras'} · {ia.chamadas_hoje}/{ia.limite_diario} chamadas hoje
            </span>
          </div>
        )}
      </header>

      {(v || bt) && (
        <div className="grade g-2 secao">
          {v ? (
            <section className="card">
              <div className="card-cab">
                <div>
                  <h2>Validação com dado público real</h2>
                  <p>{v.dominio} · {v.fonte} · coletado em {v.coletado_em?.split('-').reverse().join('/')}</p>
                </div>
                <span className="pill ok">real</span>
              </div>
              <div className="card-corpo">
                <div className="numeros-linha">
                  <div><span>Correlação mensal</span><b>{virgula(v.correlacao)}</b></div>
                  <div><span>Com tendência de adoção</span><b>{virgula(v.correlacao_com_tendencia)}</b></div>
                  <div><span>Erro médio (MAPE)</span><b>{virgula(v.mape, 1)}%</b></div>
                  <div><span>Meses comparados</span><b>{v.meses?.length || 0}</b></div>
                </div>
                {v.meses?.length > 0 && <Validacao meses={v.meses} />}
                {v.leitura && <p className="leitura">{v.leitura}</p>}
              </div>
            </section>
          ) : <div />}
          {bt ? (
            <section className="card">
              <div className="card-cab">
                <div>
                  <h2>Backtest do motor</h2>
                  <p>Treino até {bt.treino_ate?.split('-').reverse().join('/')} · {bt.dias_avaliados} dias avaliados fora da amostra</p>
                </div>
              </div>
              <div className="card-corpo">
                <dl className="spec">
                  <dt>Erro no pico (MAPE)</dt><dd>{virgula(bt.mape_pico, 1)}%</dd>
                  <dt>Erro médio no pico</dt><dd>{numero(bt.erro_medio_pico)} acessos</dd>
                  <dt>Erro na hora do pico</dt><dd>± {bt.erro_mediano_hora_min} min</dd>
                  <dt>Dias críticos acertados</dt><dd>{bt.dias_criticos?.acertos}</dd>
                  <dt>Falsos alarmes</dt><dd>{bt.dias_criticos?.falsos_alarmes}</dd>
                  <dt>Dias críticos perdidos</dt><dd>{bt.dias_criticos?.perdidos}</dd>
                </dl>
                {bt.observacao && <p className="leitura">{bt.observacao}</p>}
              </div>
            </section>
          ) : <div />}
        </div>
      )}

      <div className="grade g-2e secao">
        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Medido</h2>
              <p>Observado de fora, sem carga e sem acesso interno</p>
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
              <li>O arquivo entra pela ingestão do motor (/api/ingestao ou MCP ingerir_arquivo); o restante do fluxo não muda.</li>
              <li>As curvas passam a ser calibradas com o dado medido, e esta tela troca “modelo” por “real”.</li>
            </ol>
          </div>
        </section>
      </div>
    </>
  )
}
