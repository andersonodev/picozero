// frontend/src/telas/DetalheDia.jsx
// Tela 3: curva de carga × capacidade, plano em 3 níveis, tentativas de validação e crise.
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
import ChipTipo from '../componentes/ChipTipo'
import Gravidade from '../componentes/Gravidade'
import ModalCrise from '../componentes/ModalCrise'
import { CONTEXTO, DIAS_RISCO, EVENTOS, PLANOS, TENTATIVAS, curvaDoDia, picoDoDia } from '../dados/previa'
import { useTema } from '../tema'
import { curta, longa, numero } from '../util'

const COM_PLANO = { notasMovidas: true, lembretesEscalonados: true }

function Dica({ active, payload, label, cap }) {
  if (!active || !payload?.length) return null
  return (
    <div className="dica-grafico">
      <div className="rotulo" style={{ marginBottom: 6 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="linha">
          <span>
            <i style={{ background: p.color || p.stroke }} />
            {p.name}
          </span>
          <b className="mono">{numero(p.value)}</b>
        </div>
      ))}
      <div className="linha" style={{ marginTop: 4 }}>
        <span>Capacidade</span>
        <b className="mono">{cap}</b>
      </div>
    </div>
  )
}

function Nivel({ num, titulo, itens }) {
  return (
    <div className="nivel">
      <h4>
        <span className="num">{num}</span>
        {titulo}
      </h4>
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

  return (
    <>
      <div className="seletor-dias" style={{ marginBottom: 20 }}>
        {diasOrdenados.map((r) => (
          <button key={r.data} className={r.data === dia ? 'ativo' : ''} onClick={() => setDia(r.data)}>
            {curta(r.data)} · {r.gravidade}/5
          </button>
        ))}
      </div>

      <header style={{ display: 'flex', justifyContent: 'space-between', gap: 20, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 20 }}>
        <div>
          <div className="eyebrow">Plano do dia · evitar e reagir</div>
          <h1 className="h-page">{longa(dia)}</h1>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
            {risco && <Gravidade valor={risco.gravidade} />}
            {eventos.map((e) => (
              <ChipTipo key={e.descricao} tipo={e.tipo} texto={`${e.hora_inicio} ${e.descricao}`} />
            ))}
          </div>
        </div>
        <button className="botao perigo" onClick={() => setCrise(true)}>Simular crise</button>
      </header>

      <section className="cartao" style={{ marginBottom: 20 }}>
        <div className="cartao-topo" style={{ flexWrap: 'wrap' }}>
          <div>
            <h3>Carga simultânea esperada · janelas de 15 minutos</h3>
            <p>
              Pico sem plano {numero(picoSem.carga)} às {picoSem.hora}
              {picoCom && ` · com plano ${numero(picoCom.carga)} às ${picoCom.hora}`} · capacidade {cap}
            </p>
          </div>
          {plano && (
            <div className="alternador" role="group" aria-label="Curvas exibidas">
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
        <div className="legenda" style={{ marginBottom: 8 }}>
          {mostraSem && (
            <span>
              <i style={{ background: t.serie2, height: 3 }} />
              Sem plano
            </span>
          )}
          {mostraCom && (
            <span>
              <i style={{ background: t.serie1, height: 3 }} />
              Com plano
            </span>
          )}
          <span>
            <i style={{ background: t.critico, height: 2 }} />
            Capacidade
          </span>
        </div>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={dados} margin={{ top: 28, right: 24, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke={t.grade} />
            <XAxis dataKey="hora" interval={11} tick={{ fill: t.mudo, fontSize: 12 }} tickLine={false} axisLine={{ stroke: t.grade }} />
            <YAxis domain={[0, teto]} tick={{ fill: t.mudo, fontSize: 12 }} tickLine={false} axisLine={false} width={44} />
            <Tooltip content={<Dica cap={cap} />} cursor={{ stroke: t.mudo, strokeDasharray: '3 3' }} />
            <ReferenceLine
              y={cap}
              stroke={t.critico}
              strokeDasharray="6 4"
              label={{ value: `capacidade ${cap}`, position: 'insideTopLeft', fill: t.texto2, fontSize: 12 }}
            />
            {mostraSem && (
              <Area
                type="monotone"
                dataKey="sem"
                name="Sem plano"
                stroke={t.serie2}
                strokeWidth={2}
                fill={t.serie2}
                fillOpacity={0.12}
                dot={false}
                activeDot={{ r: 4, stroke: t.superficie, strokeWidth: 2 }}
                isAnimationActive={false}
              />
            )}
            {mostraCom && (
              <Line
                type="monotone"
                dataKey="com"
                name="Com plano"
                stroke={t.serie1}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: t.superficie, strokeWidth: 2 }}
                isAnimationActive={false}
              />
            )}
            {mostraSem && picoSem.carga > cap && (
              <ReferenceDot
                x={picoSem.hora}
                y={picoSem.carga}
                r={5}
                fill={t.serie2}
                stroke={t.superficie}
                strokeWidth={2}
                label={{ value: `pico ${numero(picoSem.carga)}`, position: 'top', fill: t.texto, fontSize: 12 }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </section>

      <div className="grade-2">
        <section className="cartao">
          <div className="cartao-topo">
            <div>
              <h3>Plano em 3 níveis</h3>
              <p>Plano gerado pelo Gemini · só ações permitidas · vencimento e provas não mudam</p>
            </div>
          </div>
          {plano ? (
            <div className="grade-3">
              <Nivel num="01" titulo="Calendário" itens={plano.calendario} />
              <Nivel num="02" titulo="Comunicação" itens={plano.comunicacao} />
              <Nivel num="03" titulo="Infraestrutura" itens={plano.infra_checklist} />
            </div>
          ) : (
            <div className="vazio">
              <b>Plano ainda não gerado para {curta(dia)}</b>
              {temRematricula
                ? 'As ações permitidas (notas, lembretes de pagamento e TI) não mexem na rematrícula. Esse caso depende de uma decisão de escopo.'
                : 'Na prévia só 10/03 tem plano simulado. Com o backend, este botão chama evitar.gerar_plano.'}
              <div style={{ marginTop: 14 }}>
                <button className="botao" disabled>Gerar plano com Gemini</button>
              </div>
            </div>
          )}
        </section>

        <section className="cartao">
          <div className="cartao-topo">
            <div>
              <h3>Tentativas de validação</h3>
              <p>calculo/validacao.py · até 3 tentativas</p>
            </div>
          </div>
          {tentativas.length > 0 ? (
            <ol className="tentativas">
              {tentativas.map((tt) => (
                <li key={tt.numero}>
                  <span className={`marcador ${tt.ok ? 'passou' : 'falhou'}`}>{tt.ok ? '✓' : '✕'}</span>
                  <div className="cabeca">Tentativa {tt.numero} · {tt.ok ? 'aprovada' : 'reprovada e devolvida ao Gemini'}</div>
                  <div className="proposta">{tt.proposta}</div>
                  {tt.erro && <div className="erro">{tt.erro}</div>}
                  {tt.checagens && (
                    <ul className="checagens">
                      {tt.checagens.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ol>
          ) : (
            <div className="vazio">Sem tentativas registradas.</div>
          )}
        </section>
      </div>

      {crise && <ModalCrise dia={dia} onFechar={() => setCrise(false)} />}
    </>
  )
}
