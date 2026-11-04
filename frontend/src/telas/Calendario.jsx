// frontend/src/telas/Calendario.jsx
// Tela 1: o PDF do calendário e os eventos que o Gemini extraiu.
import { Fragment } from 'react'
import ChipTipo from '../componentes/ChipTipo'
import { CONTEXTO, EVENTOS, TRILHA_GEMINI } from '../dados/previa'
import { curta, mesNome, numero, semana } from '../util'

function agruparPorMes(eventos) {
  const grupos = []
  for (const ev of eventos) {
    const mes = ev.data.slice(0, 7)
    let grupo = grupos.find((g) => g.mes === mes)
    if (!grupo) {
      grupo = { mes, nome: mesNome(ev.data), eventos: [] }
      grupos.push(grupo)
    }
    grupo.eventos.push(ev)
  }
  return grupos
}

export default function Calendario({ irPara }) {
  const grupos = agruparPorMes(EVENTOS)
  const tokens = TRILHA_GEMINI.reduce((soma, t) => soma + (t.tokens || 0), 0)
  const consultas = TRILHA_GEMINI.filter((t) => t.ferramenta).length

  return (
    <>
      <section className="heroi">
        <div>
          <span className="rotulo">1 · Prever · ler o calendário</span>
          <h1 className="titulo-tela" style={{ marginTop: 10 }}>
            O calendário avisa <em>antes</em> do servidor cair.
          </h1>
          <p className="lide">
            O Gemini lê o PDF do calendário acadêmico, consulta o histórico de acessos e aponta os dias em que prova
            online, vencimento, notas e rematrícula se encontram. O código calcula a carga e valida o plano.
          </p>
          <div className="heroi-acoes">
            <button className="botao primario" onClick={() => irPara('riscos')}>Ver dias de risco →</button>
            <button className="botao" disabled title="Disponível com o backend (E2)">Enviar outro PDF</button>
          </div>
        </div>
        <img
          src="/img/heroi.jpg"
          alt="Ilustração: alunos saem de três dias marcados no calendário e chegam ao servidor em filas organizadas"
        />
      </section>

      <div className="grade-2">
        <section className="cartao">
          <div className="cartao-topo">
            <div>
              <h3>Eventos extraídos pelo Gemini</h3>
              <p>
                {EVENTOS.length} eventos · semestre {CONTEXTO.semestre} · response_schema list[Evento]
              </p>
            </div>
          </div>
          <table className="tabela">
            <thead>
              <tr>
                <th>Data</th>
                <th>Horário</th>
                <th>Tipo</th>
                <th>Descrição e turmas</th>
              </tr>
            </thead>
            <tbody>
              {grupos.map((g) => (
                <Fragment key={g.mes}>
                  <tr className="mes">
                    <td colSpan={4}>{g.nome}</td>
                  </tr>
                  {g.eventos.map((ev) => (
                    <tr key={`${ev.data}-${ev.descricao}`}>
                      <td>
                        <b className="mono">{curta(ev.data)}</b>
                        <div className="turmas">{semana(ev.data).slice(0, 3)}</div>
                      </td>
                      <td className="mono">
                        {ev.hora_inicio}–{ev.hora_fim}
                      </td>
                      <td>
                        <ChipTipo tipo={ev.tipo} />
                      </td>
                      <td>
                        {ev.descricao}
                        {ev.turmas.length > 0 && <div className="turmas">{ev.turmas.join(' · ')}</div>}
                      </td>
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </section>

        <aside className="pilha">
          <section className="cartao">
            <div className="cartao-topo">
              <h3>Calendário enviado</h3>
            </div>
            <div className="upload">
              <div className="upload-pdf">PDF</div>
              <div>
                <b>calendario_2027-1.pdf</b>
                <div className="meta">3 páginas · enviado pela Files API</div>
              </div>
            </div>
          </section>

          <section className="cartao">
            <div className="cartao-topo">
              <div>
                <h3>Trilha do Gemini</h3>
                <p>
                  {numero(tokens)} tokens · {consultas} consultas ao histórico · gravado por cliente.py
                </p>
              </div>
            </div>
            <ul className="trilha">
              {TRILHA_GEMINI.map((t, i) => (
                <li key={i}>
                  <span className="hora mono">{t.hora}</span>
                  <div className={t.ferramenta ? 'ferramenta' : ''}>
                    <div className="etapa">{t.etapa}</div>
                    <div className="meta">
                      {t.detalhe}
                      {t.tempo && ` · ${t.tempo}`}
                      {t.tokens && ` · ${numero(t.tokens)} tokens`}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </>
  )
}
