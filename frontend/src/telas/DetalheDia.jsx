// frontend/src/telas/DetalheDia.jsx
// Plano do dia: curva de carga × capacidade (motor), plano em 3 níveis (IA, validado pelo motor),
// tentativas de validação, manutenção do dia para a TI e a simulação de crise.
import { useState } from 'react'
import { CalendarDays, Check, Clock, FileText, Megaphone, RefreshCw, Server, Siren, Wrench, X } from 'lucide-react'
import * as api from '../api/cliente'
import { usarApi } from '../api/usarApi'
import AvisoIA from '../componentes/AvisoIA'
import ChipTipo from '../componentes/ChipTipo'
import ModalCrise from '../componentes/ModalCrise'
import CurvaDia from '../graficos/CurvaDia'
import { nivelDaGravidade, situacaoDoNivel, useTema } from '../tema'
import { curta, longa, numero, rotuloCurto } from '../util'

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

function Manutencao({ dicas, reescrever, reescrevendo }) {
  return (
    <section className="card secao">
      <div className="card-cab">
        <div>
          <h2>Manutenção do dia</h2>
          <p>{dicas.resumo}</p>
        </div>
        <div className="cab-acoes">
          <AvisoIA origem={dicas.origem} compacto />
          <button className="botao" onClick={reescrever} disabled={reescrevendo}>
            {reescrevendo ? <span className="spinner" /> : <RefreshCw size={15} aria-hidden="true" />}
            {reescrevendo ? 'Reescrevendo…' : 'Reescrever com Gemini'}
          </button>
        </div>
      </div>
      <div className="card-corpo">
        <div className="manut-faixas">
          {dicas.janela_manutencao && (
            <div className="manut-faixa ok">
              <Wrench size={15} aria-hidden="true" />
              <span>Janela de manutenção <b>{dicas.janela_manutencao.inicio}–{dicas.janela_manutencao.fim}</b></span>
            </div>
          )}
          {dicas.escalar_ate && (
            <div className="manut-faixa">
              <Server size={15} aria-hidden="true" />
              <span>Escalar o portal até <b>{dicas.escalar_ate}</b></span>
            </div>
          )}
          {(dicas.congelamento || []).map((z) => (
            <div key={`${z.inicio}-${z.fim}`} className="manut-faixa critico">
              <Clock size={15} aria-hidden="true" />
              <span>Congelar deploys <b>{z.inicio}–{z.fim}</b> (máx. {numero(z.max)})</span>
            </div>
          ))}
        </div>
        <div className="grade g-2" style={{ marginTop: 16 }}>
          <table className="tabela">
            <thead>
              <tr><th>Quando</th><th>Tarefa</th><th>Quem</th></tr>
            </thead>
            <tbody>
              {(dicas.tarefas || []).map((tf) => (
                <tr key={`${tf.horario}-${tf.titulo}`}>
                  <td className="data-cel"><b>{tf.horario}</b><span className={`prioridade ${tf.prioridade}`}>{tf.prioridade}</span></td>
                  <td><b className="tarefa-titulo">{tf.titulo}</b><div className="fraco">{tf.detalhe}</div></td>
                  <td className="fraco">{tf.responsavel}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(dicas.nao_fazer || []).length > 0 && (
            <div className="nao-fazer">
              <h3><X size={15} aria-hidden="true" /> Não fazer neste dia</h3>
              <ul>{dicas.nao_fazer.map((n) => <li key={n}>{n}</li>)}</ul>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

export default function DetalheDia({ base, unidade, dia, setDia }) {
  const t = useTema()
  const [vista, setVista] = useState('ambos')
  const [crise, setCrise] = useState(false)
  const [gerado, setGerado] = useState({})
  const [gerando, setGerando] = useState(false)
  const [dicasNovas, setDicasNovas] = useState({})
  const [reescrevendo, setReescrevendo] = useState(false)
  const cap = base.contexto.capacidade

  const curva = usarApi(() => api.curva(dia, unidade), [dia, unidade])
  const planoApi = usarApi(() => api.plano(dia, unidade), [dia, unidade])
  const dicas = usarApi(() => api.dicas(dia, unidade), [dia, unidade])
  const p = gerado[dia] || planoApi.dados
  const c = curva.dados

  const risco = base.riscos.find((r) => r.data === dia)
  const diasOrdenados = [...base.riscos].sort((a, b) => a.data.localeCompare(b.data))
  const eventos = c?.eventos || base.eventos.filter((e) => e.data === dia)
  const temRematricula = eventos.some((e) => e.tipo === 'rematricula')
  const situacao = c ? situacaoDoNivel(c.nivel) : null
  const plano = p?.plano
  const tentativas = p?.tentativas || []

  async function reescreverDicas() {
    setReescrevendo(true)
    const r = await api.gerarDicas(dia, unidade)
    if (r.dados?.tarefas) setDicasNovas((d) => ({ ...d, [dia]: r.dados }))
    setReescrevendo(false)
  }

  async function gerarPlano() {
    setGerando(true)
    const r = await api.gerarPlano(dia, unidade)
    if (r.dados?.plano) setGerado((g) => ({ ...g, [dia]: r.dados }))
    setGerando(false)
  }

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
            {situacao && <span className={`pill ${situacao.chave}`}>{situacao.rotulo}</span>}
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
              Janelas de 15 minutos{c && ` · sem plano, pico de ${numero(c.pico.carga)} às ${c.pico.hora}`}
              {p?.pico_com && ` · com plano, ${numero(p.pico_com.carga)} às ${p.pico_com.hora}`} · capacidade {cap} · Ctrl + rolagem para dar zoom
            </p>
          </div>
          {p?.pontos_com && (
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
          <div className="legenda" style={{ marginBottom: 2 }}>
            {(!p?.pontos_com || vista !== 'com') && <span><i style={{ background: p?.pontos_com ? t.semPlano : t.teal, height: 3 }} />Sem plano</span>}
            {p?.pontos_com && vista !== 'sem' && <span><i style={{ background: t.comPlano, height: 3 }} />Com plano (fila virtual segura na capacidade)</span>}
            <span><i className="linha" />Capacidade</span>
            <span><i style={{ background: 'color-mix(in srgb, var(--ev-prova_online) 25%, transparent)' }} />janela de evento</span>
          </div>
          {c ? (
            <CurvaDia pontos={c.pontos} pontosCom={p?.pontos_com} cap={cap} eventos={eventos} vista={vista} altura={340} />
          ) : (
            <div className="esq-bloco" style={{ height: 340 }} aria-busy="true" />
          )}
        </div>
      </section>

      <div className="grade g-2 secao">
        <section className="card">
          <div className="card-cab">
            <div>
              <h2>Plano em 3 níveis</h2>
              <p>Só ações permitidas: vencimento e provas não mudam · cada ação é recalculada pelo motor</p>
            </div>
            {plano && <AvisoIA origem={p.origem || 'previa'} compacto />}
          </div>
          <div className="card-corpo">
            {planoApi.carregando && !p ? (
              <div className="esq-bloco" style={{ height: 180 }} aria-busy="true" />
            ) : plano ? (
              <div className="niveis">
                <Nivel Icone={CalendarDays} titulo="Calendário" itens={plano.calendario || []} />
                <Nivel Icone={Megaphone} titulo="Comunicação" itens={plano.comunicacao || []} />
                <Nivel Icone={Server} titulo="Infraestrutura" itens={plano.infra_checklist || []} />
              </div>
            ) : (
              <div className="vazio">
                <b>Plano ainda não gerado para {curta(dia)}</b>
                {temRematricula
                  ? 'As ações permitidas (notas, lembretes de pagamento e TI) não mexem na rematrícula. Esse caso depende de uma decisão de escopo.'
                  : 'Peça um plano: a IA propõe as ações e o motor recalcula a curva para validar.'}
                <div style={{ marginTop: 14 }}>
                  <button className="botao primario" onClick={gerarPlano} disabled={gerando}>
                    {gerando ? <span className="spinner claro" /> : <FileText size={16} aria-hidden="true" />}
                    {gerando ? 'Gerando…' : 'Gerar plano com Gemini'}
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
              <p>O motor recalcula a carga de cada proposta · até 3 tentativas</p>
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
                      Tentativa {tt.numero} <span>· {tt.ok ? 'aprovada' : 'reprovada e devolvida à IA'}</span>
                    </div>
                    <div className="proposta">{tt.proposta}</div>
                    {tt.erro && <div className="erro">{tt.erro}</div>}
                    {tt.checagens && (
                      <ul className="checagens">
                        {tt.checagens.map((ch) => (
                          <li key={ch}><Check size={14} strokeWidth={3} aria-hidden="true" />{ch}</li>
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

      {(dicasNovas[dia] || dicas.dados) && (
        <Manutencao dicas={dicasNovas[dia] || dicas.dados} reescrever={reescreverDicas} reescrevendo={reescrevendo} />
      )}

      {crise && <ModalCrise dia={dia} unidade={unidade} onFechar={() => setCrise(false)} />}
    </>
  )
}
