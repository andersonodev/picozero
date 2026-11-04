// frontend/src/telas/ProvaCarga.jsx
// Prova de carga: latência antes × depois × controle (saída do teste de carga do motor)
// e o que o aluno vê com a fila virtual. Sem ilustração: mock de produto em CSS.
import { CircleCheck, Info, ShieldCheck, TriangleAlert } from 'lucide-react'
import * as api from '../api/cliente'
import { usarApi } from '../api/usarApi'
import Latencia from '../graficos/Latencia'
import { useTema } from '../tema'
import { curta, numero } from '../util'

const pct = (x) => `${(x * 100).toFixed(1).replace('.', ',')}%`

export default function ProvaCarga({ unidade }) {
  const t = useTema()
  const prova = usarApi(() => api.provaCarga(unidade), [unidade])
  const d = prova.dados
  const cores = { antes: t.semPlano, depois: t.comPlano, controle: t.controle }

  if (!d) {
    return (
      <>
        <header className="cab-pagina"><div><h1>Prova de carga</h1></div></header>
        <div className="esq-bloco" style={{ height: 420 }} aria-busy="true" />
      </>
    )
  }

  const antes = d.resumo.find((r) => r.chave === 'antes')
  const depois = d.resumo.find((r) => r.chave === 'depois')
  const ganho = antes && depois ? Math.round((1 - depois.p95 / antes.p95) * 100) : null

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Prova de carga</h1>
          <p className="sub">
            O Locust reproduz a curva de {curta(d.data || '2026-09-10')} calculada pelo motor (histórico + cálculo), nunca a saída da IA: a prova não é circular.
          </p>
        </div>
      </header>

      {antes && depois && (
        <section className="card aviso ok secao">
          <div className="aviso-icone"><CircleCheck size={20} strokeWidth={2} aria-hidden="true" /></div>
          <div className="aviso-corpo">
            <h3>Com o plano, o p95 cai de {numero(antes.p95)} ms para {numero(depois.p95)} ms{ganho > 0 ? ` (−${ganho}%)` : ''}</h3>
            <p>E os erros 503 vão de {pct(antes.erros)} para {pct(depois.erros)}. Mesmo servidor simulado, três perfis de carga.</p>
          </div>
        </section>
      )}

      <div className="grade g-3 secao">
        {d.resumo.map((c) => (
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
            <p>/sim/login e /sim/prova · base × (1 + (ativos ÷ {d.capacidade})³) · 503 acima de 1,5× a capacidade · Ctrl + rolagem para dar zoom</p>
          </div>
          <div className="legenda">
            {d.resumo.map((c) => (
              <span key={c.chave}><i style={{ background: cores[c.chave], height: 3, width: 14 }} />{c.nome}</span>
            ))}
            <span><i className="linha" />meta p95</span>
          </div>
        </div>
        <div className="card-corpo">
          <Latencia series={d.series} resumo={d.resumo} cores={cores} />
        </div>
      </section>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>O que o aluno vê com a fila virtual</h2>
            <p>FILA_VIRTUAL=1 · asyncio.Semaphore({d.capacidade}) · quem entra navega com latência estável</p>
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
        <Info size={15} aria-hidden="true" />
        {prova.origem === 'api' ? 'Números do teste de carga do motor (servidor simulado, curva do código).' : 'Prévia com números simulados; com o motor no ar estes valores vêm do teste de carga.'}
      </p>
    </>
  )
}
