// frontend/src/telas/Overview.jsx
// Visão geral: o alerta do semestre, os números da operação, o pico diário com o mapa de calor
// por hora (mesmo eixo, zoom compartilhado), os dias de risco e o registro da IA.
import { useMemo } from 'react'
import { ArrowRight, CalendarDays, TriangleAlert } from 'lucide-react'
import * as api from '../api/cliente'
import { usarApi } from '../api/usarApi'
import AvisoIA from '../componentes/AvisoIA'
import { feriadosDe, fimDeSemana } from '../dados/usarBase'
import { unidadePorId } from '../dados/unidades'
import GraficoSemestre from '../graficos/GraficoSemestre'
import { situacaoDoNivel } from '../tema'
import { curta, numero, paraData, paraIso, rotuloCurto, semana } from '../util'

const vezes = (x) => `${x.toFixed(1).replace('.', ',')}×`
const sem3 = (iso) => semana(iso).slice(0, 3)
const DIA_MS = 86400000

export default function Overview({ base, unidade, abrirDia, irPara }) {
  const { contexto, riscos, picos, marcos } = base
  const u = unidadePorId(unidade)
  const cap = contexto.capacidade
  const feriados = useMemo(() => feriadosDe(contexto), [contexto])
  const mapa = usarApi(() => api.mapaCalor(unidade), [unidade])
  const trilha = usarApi(() => api.trilha(unidade), [unidade])
  const hoje = paraIso(new Date())

  const dias = [...riscos].sort((a, b) => a.data.localeCompare(b.data))
  const acima = dias.filter((d) => d.pico.carga > cap)
  const pior = dias.reduce((a, b) => (b.pico.carga > a.pico.carga ? b : a), dias[0])
  const proximo = acima.find((d) => d.data >= hoje) || dias.find((d) => d.data >= hoje)
  const emDias = proximo ? Math.round((paraData(proximo.data) - paraData(hoje)) / DIA_MS) : null
  const letivos = picos.filter((p) => !fimDeSemana(p.data) && !feriados[p.data]).length
  const registros = (trilha.dados || []).slice(0, 12)
  const tokens = registros.reduce((s, t) => s + (t.tokens || 0), 0)
  const consultas = registros.filter((t) => t.ferramenta).length
  const origemIA = riscos[0]?.origem || 'previa'

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Visão geral</h1>
          <p className="sub">
            {u.nome} · {numero(contexto.alunos)} alunos · capacidade de {cap} acessos simultâneos
            {!u.modelada && ' · projeção escalada a partir do modelo do Rio'}
          </p>
        </div>
        <div className="cab-acoes">
          <button className="botao" onClick={() => irPara('calendario')}>
            <CalendarDays size={16} aria-hidden="true" /> Calendário
          </button>
          {proximo && (
            <button className="botao primario" onClick={() => abrirDia(proximo.data)}>
              Plano de {curta(proximo.data)} <ArrowRight size={16} aria-hidden="true" />
            </button>
          )}
        </div>
      </header>

      {acima.length > 0 && (
        <section className="card aviso secao">
          <div className="aviso-icone"><TriangleAlert size={20} strokeWidth={2} aria-hidden="true" /></div>
          <div className="aviso-corpo">
            <h3>{acima.length} {acima.length === 1 ? 'dia vai' : 'dias vão'} passar da capacidade neste semestre</h3>
            <p>
              O pior é {sem3(pior.data)}, {curta(pior.data)}: pico de {numero(pior.pico.carga)} acessos às {pior.pico.hora},{' '}
              {vezes(pior.pico.carga / cap)} a capacidade. Fora desses dias, a infraestrutura atual dá conta.
            </p>
            <button className="link-seta" onClick={() => irPara('riscos')}>
              Ver dias críticos <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </section>
      )}

      <div className="grade g-4 secao">
        <div className="card metrica critico">
          <span className="rot">Dias acima da capacidade</span>
          <span className="val">{acima.length}<small>de {dias.length} em risco</small></span>
          <span className="det">apontados pela IA, confirmados pelo cálculo</span>
        </div>
        <div className="card metrica">
          <span className="rot">Pior pico projetado</span>
          <span className="val">{numero(pior.pico.carga)}<small>acessos</small></span>
          <span className="det">{curta(pior.data)} às {pior.pico.hora} · {Math.round((pior.pico.carga / cap) * 100)}% da capacidade</span>
        </div>
        <div className="card metrica">
          <span className="rot">Reforço de infraestrutura</span>
          <span className="val">{acima.length}<small>de {letivos} dias letivos</small></span>
          <span className="det">só nesses dias; no resto, a capacidade atual basta</span>
        </div>
        <button className="card metrica clicavel" onClick={() => proximo && abrirDia(proximo.data)} disabled={!proximo}>
          <span className="rot">Próximo dia crítico</span>
          <span className="val">{proximo ? curta(proximo.data) : '—'}<small>{emDias === 0 ? 'hoje' : emDias === 1 ? 'amanhã' : emDias != null ? `em ${emDias} dias` : ''}</small></span>
          <span className="det">{proximo ? `${proximo.eventos.slice(0, 2).map(rotuloCurto).join(' + ')} · pico ${numero(proximo.pico.carga)}` : 'nenhum no resto do semestre'}</span>
        </button>
      </div>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>Capacidade do semestre</h2>
            <p>Pico diário em % da capacidade de {cap} e, embaixo, a carga hora a hora · arraste a barra de baixo ou use Ctrl + rolagem para dar zoom · clique num dia para abrir o plano</p>
          </div>
          <div className="legenda">
            <span><i style={{ background: 'var(--folga)' }} />com folga</span>
            <span><i style={{ background: 'var(--atencao)' }} />atenção</span>
            <span><i style={{ background: 'var(--alto)' }} />perto do limite</span>
            <span><i style={{ background: 'var(--critico)' }} />acima da capacidade</span>
            <span><i className="linha" />capacidade</span>
          </div>
        </div>
        <div className="card-corpo" style={{ paddingTop: 4 }}>
          <GraficoSemestre
            picos={picos}
            mapa={mapa.dados}
            riscos={riscos}
            marcos={marcos}
            feriados={feriados}
            cap={cap}
            hoje={hoje}
            aoAbrir={abrirDia}
          />
        </div>
      </section>

      <div className="grade g-2 secao">
        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Dias de risco</h2>
              <p>{dias.length} dias apontados pela IA · pico calculado pelo motor · clique para abrir o plano</p>
            </div>
            <AvisoIA origem={origemIA} compacto />
          </div>
          <div className="card-corpo">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Eventos</th>
                  <th className="dir">Pico</th>
                  <th className="dir">Capacidade</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {dias.map((d) => {
                  const s = situacaoDoNivel(d.nivel)
                  return (
                    <tr key={d.data} className={`clicavel ${d.data < hoje ? 'passado' : ''}`} onClick={() => abrirDia(d.data)}>
                      <td className="data-cel">
                        <b>{curta(d.data)}</b>
                        <span>{sem3(d.data)}{d.data === hoje ? ' · hoje' : ''}</span>
                      </td>
                      <td className="fraco">{d.eventos.map(rotuloCurto).join(' · ')}</td>
                      <td className="dir data-cel">
                        <b>{numero(d.pico.carga)}</b>
                        <span>às {d.pico.hora}</span>
                      </td>
                      <td className="dir num">{Math.round((d.pico.carga / cap) * 100)}%</td>
                      <td><span className={`pill ${s.chave}`}>{s.rotulo}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Registro da IA</h2>
              <p>{registros.length} chamadas recentes{tokens ? ` · ${numero(tokens)} tokens` : ''}{consultas ? ` · ${consultas} consultas ao histórico` : ''} · auditado pelo motor</p>
            </div>
          </div>
          <div className="card-corpo">
            {registros.length === 0 ? (
              <p className="painel-vazio">{trilha.carregando ? 'Carregando registro…' : 'Nenhuma chamada registrada ainda.'}</p>
            ) : (
              <ol className="log">
                {registros.map((t, i) => (
                  <li key={`${t.hora}-${i}`} className={t.ferramenta ? 'ferramenta' : ''}>
                    <time>{t.hora}</time>
                    <div className="passo">
                      <b>{t.etapa}</b>
                      <p>
                        {t.detalhe}
                        {t.tempo && ` · ${t.tempo}`}
                        {t.tokens ? ` · ${numero(t.tokens)} tokens` : ''}
                        {t.modelo && !t.ferramenta ? ` · ${t.modelo}` : ''}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>
      </div>
    </>
  )
}
