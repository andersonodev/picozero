// frontend/src/telas/DetalheDia.jsx
// Plano do dia: curva de carga × capacidade, plano em 3 níveis, tentativas de validação e crise.
import { useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { CalendarDays, Check, FileText, Megaphone, Server, Siren, X } from 'lucide-react'
import ChipTipo from '../componentes/ChipTipo'
import ModalCrise from '../componentes/ModalCrise'
import { CONTEXTO, DIAS_RISCO, EVENTOS, PLANOS, TENTATIVAS, curvaDoDia, picoDoDia } from '../dados/previa'
import { nivelDaGravidade, situacaoDaCarga, useTema } from '../tema'
import { curta, longa, numero, rotuloCurto } from '../util'

const COM_PLANO = { notasMovidas: true, lembretesEscalonados: true }

function Dica({ active, payload, label, cap }) {
  if (!active || !payload?.length) return null
  return (
    <div className="dica-grafico">
      <div className="cab">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="linha">
          <span><i style={{ background: p.color || p.stroke }} />{p.name}</span>
          <b>{numero(p.value)}</b>
        </div>
      ))}
      <div className="linha" style={{ marginTop: 4 }}>
        <span>Capacidade</span>
        <b>{cap}</b>
      </div>
    </div>
  )
}

function Nivel({ Icone, titulo, itens }) {
  return (
    <div className="nivel">
      <h3><Icone size={16} strokeWidth={2} aria-hidden="true" />{titulo}</h3>
      <ul>
        {itens.map((item) => (
          <li key={item.titulo}>
            <b>{item.titulo}</b>
            <span>{item.detalhe}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function DetalheDia({ dia, setDia }) {
  const t = useTema()
  const [vista, setVista] = useState('ambos')
  const [crise, setCrise] = useState(false)
  const cap = CONTEXTO.capacidade

  const risco = DIAS_RISCO.find((r) => r.data === dia)
  const plano = PLANOS[dia]
  const tentativas = TENTATIVAS[dia] || []
  const eventos = EVENTOS.filter((e) => e.data === dia)
  const temRematricula = eventos.some((e) => e.tipo === 'rematricula')

  const dados = useMemo(() => {
    const sem = curvaDoDia(dia)
    const com = plano ? curvaDoDia(dia, COM_PLANO) : null
    return sem.map((p, i) => ({ hora: p.hora, sem: p.carga, com: com ? com[i].carga : null }))
  }, [dia, plano])

  const picoSem = picoDoDia(dia)
  const picoCom = plano ? picoDoDia(dia, COM_PLANO) : null
  const mostraSem = !plano || vista !== 'com'
  const mostraCom = Boolean(plano) && vista !== 'sem'
  const teto = Math.ceil((Math.max(picoSem.carga, cap) * 1.15) / 100) * 100
  const diasOrdenados = [...DIAS_RISCO].sort((a, b) => a.data.localeCompare(b.data))
  const situacao = situacaoDaCarga(picoSem.carga, cap)

  return (
    <>
      <div className="dias-abas" role="tablist" aria-label="Dias de risco">
        {diasOrdenados.map((r) => (
          <button
            key={r.data}
            role="tab"
            aria-selected={r.data === dia}
            className={r.data === dia ? 'ativo' : ''}
            onClick={() => setDia(r.data)}
            title={`Gravidade ${r.gravidade} de 5`}
          >
            <i style={{ background: `var(--${nivelDaGravidade(r.gravidade).chave})` }} />
            {curta(r.data)}
          </button>
        ))}
      </div>

      <header className="cab-pagina">
        <div>
          <h1>{longa(dia)}</h1>
          <div className="cab-dia-tags">
            {risco && <span className={`pill ${nivelDaGravidade(risco.gravidade).chave}`}>Gravidade {risco.gravidade} de 5</span>}
            <span className={`pill ${situacao.chave}`}>{situacao.rotulo}</span>
            {eventos.map((e) => (
              <ChipTipo key={e.descricao} tipo={e.tipo} hora={e.hora_inicio === '00:00' ? null : e.hora_inicio} texto={rotuloCurto(e.descricao)} />
            ))}
          </div>
        </div>
        <div className="cab-acoes">
          <button className="botao perigo" onClick={() => setCrise(true)}>
            <Siren size={16} aria-hidden="true" /> Simular crise
          </button>
        </div>
      </header>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>Carga simultânea esperada</h2>
            <p>
              Janelas de 15 minutos · sem plano, pico de {numero(picoSem.carga)} às {picoSem.hora}
              {picoCom && ` · com plano, ${numero(picoCom.carga)} às ${picoCom.hora}`} · capacidade {cap}
            </p>
          </div>
          {plano && (
            <div className="segmentado" role="group" aria-label="Curvas exibidas">
              {[
                ['sem', 'Sem plano'],
                ['com', 'Com plano'],
                ['ambos', 'Os dois'],
              ].map(([chave, nome]) => (
                <button key={chave} className={vista === chave ? 'ativo' : ''} onClick={() => setVista(chave)}>
                  {nome}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="card-corpo">
          <div className="legenda" style={{ marginBottom: 6 }}>
            {mostraSem && <span><i style={{ background: t.semPlano, height: 3 }} />Sem plano</span>}
            {mostraCom && <span><i style={{ background: t.comPlano, height: 3 }} />Com plano</span>}
            <span><i className="linha" />Capacidade</span>
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={dados} margin={{ top: 26, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke={t.grade} />
              <XAxis dataKey="hora" interval={11} tick={{ fill: t.mudo, fontSize: 12 }} tickLine={false} axisLine={{ stroke: t.grade }} />
              <YAxis domain={[0, teto]} tick={{ fill: t.mudo, fontSize: 12 }} tickLine={false} axisLine={false} width={44} />
              <Tooltip content={<Dica cap={cap} />} cursor={{ stroke: t.mudo, strokeDasharray: '3 3' }} />
              <ReferenceLine
                y={cap}
                stroke={t.critico}
                strokeDasharray="6 4"
                label={{ value: `capacidade ${cap}`, position: 'insideTopLeft', fill: t.critico, fontSize: 12 }}
              />
              {mostraSem && (
                <Area type="monotone" dataKey="sem" name="Sem plano" stroke={t.semPlano} strokeWidth={2} fill={t.semPlano} fillOpacity={0.12} dot={false} activeDot={{ r: 4, stroke: t.superficie, strokeWidth: 2 }} isAnimationActive={false} />
              )}
              {mostraCom && (
                <Line type="monotone" dataKey="com" name="Com plano" stroke={t.comPlano} strokeWidth={2.5} dot={false} activeDot={{ r: 4, stroke: t.superficie, strokeWidth: 2 }} isAnimationActive={false} />
              )}
              {mostraSem && picoSem.carga > cap && (
                <ReferenceDot
                  x={picoSem.hora}
                  y={picoSem.carga}
                  r={5}
                  fill={t.semPlano}
                  stroke={t.superficie}
                  strokeWidth={2}
                  label={{ value: `pico ${numero(picoSem.carga)}`, position: 'top', fill: t.texto, fontSize: 12, fontWeight: 600 }}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className="grade g-2 secao">
        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Plano em 3 níveis</h2>
              <p>Gerado pelo Gemini · só ações permitidas: vencimento e provas não mudam</p>
            </div>
          </div>
          <div className="card-corpo">
            {plano ? (
              <div className="niveis">
                <Nivel Icone={CalendarDays} titulo="Calendário" itens={plano.calendario} />
                <Nivel Icone={Megaphone} titulo="Comunicação" itens={plano.comunicacao} />
                <Nivel Icone={Server} titulo="Infraestrutura" itens={plano.infra_checklist} />
              </div>
            ) : (
              <div className="vazio">
                <b>Plano ainda não gerado para {curta(dia)}</b>
                {temRematricula
                  ? 'As ações permitidas (notas, lembretes de pagamento e TI) não mexem na rematrícula. Esse caso depende de uma decisão de escopo.'
                  : 'Na prévia, só 10/09 tem plano simulado. Com o backend, este botão chama evitar.gerar_plano.'}
                <div style={{ marginTop: 14 }}>
                  <button className="botao" disabled>
                    <FileText size={16} aria-hidden="true" /> Gerar plano com Gemini
                  </button>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Validação do plano</h2>
              <p>calculo/validacao.py · até 3 tentativas</p>
            </div>
          </div>
          <div className="card-corpo">
            {tentativas.length > 0 ? (
              <ol className="tentativas">
                {tentativas.map((tt) => (
                  <li key={tt.numero}>
                    <span className={`marcador ${tt.ok ? 'passou' : 'falhou'}`}>
                      {tt.ok ? <Check size={15} strokeWidth={3} aria-hidden="true" /> : <X size={15} strokeWidth={3} aria-hidden="true" />}
                    </span>
                    <div className="cabeca">
                      Tentativa {tt.numero} <span>· {tt.ok ? 'aprovada' : 'reprovada e devolvida ao Gemini'}</span>
                    </div>
                    <div className="proposta">{tt.proposta}</div>
                    {tt.erro && <div className="erro">{tt.erro}</div>}
                    {tt.checagens && (
                      <ul className="checagens">
                        {tt.checagens.map((c) => (
                          <li key={c}><Check size={14} strokeWidth={3} aria-hidden="true" />{c}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <div className="vazio">Sem tentativas registradas.</div>
            )}
          </div>
        </section>
      </div>

      {crise && <ModalCrise dia={dia} onFechar={() => setCrise(false)} />}
    </>
  )
}
