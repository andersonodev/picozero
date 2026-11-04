// frontend/src/telas/Entrada.jsx
// Entrada de dados: qualquer arquivo (CSV, Excel, JSON, logs, ICS, PDF, imagem…), texto livre,
// webhook ao vivo e MCP. Cada envio devolve o relatório: formato detectado, o que entrou e os avisos.
import { useRef, useState } from 'react'
import { Cable, FileUp, Info, Sparkles, Type, Webhook } from 'lucide-react'
import * as api from '../api/cliente'
import { usarApi } from '../api/usarApi'
import { numero } from '../util'

const FERRAMENTAS_MCP = [
  'previsao_dia', 'proximos_picos', 'alertas', 'dicas_manutencao', 'dias_de_risco', 'consultar_historico',
  'desempenho_modelo', 'validacao_publica', 'ingerir_metricas', 'ingerir_eventos', 'ingerir_texto',
  'ingerir_arquivo', 'ingerir_trafego_mensal', 'perguntar',
]

const EXEMPLO_TEXTO =
  'Prezados, a Secretaria informa: as notas da AP2 serão divulgadas em 20/11 às 18h e a rematrícula 2027.1 abre dia 01/12 às 9h. O vencimento da 6ª parcela segue em 10/12.'

function Relatorio({ r }) {
  if (!r) return null
  return (
    <div className="card" style={{ marginTop: 14, padding: '14px 16px' }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
        <span className="pill ok">{r.formato}</span>
        <span className={`pill sem-ponto ${r.origem_parse === 'gemini' ? 'alto' : ''}`}>
          {r.origem_parse === 'gemini' ? 'lido pelo Gemini' : 'lido por regras'}
        </span>
        <span className="mono" style={{ fontSize: 12.5, color: 'var(--texto-2)' }}>{r.duracao_ms} ms · {r.arquivo || r.canal}</span>
      </div>
      <div className="grade g-4" style={{ gap: 10 }}>
        {[['Linhas lidas', r.linhas_lidas], ['Pontos de carga', r.pontos_inseridos], ['Eventos', r.eventos_inseridos], ['Ignorados', r.ignorados]].map(([rot, v]) => (
          <div key={rot}>
            <div style={{ fontSize: 12.5, color: 'var(--texto-2)' }}>{rot}</div>
            <b style={{ fontSize: 20 }}>{numero(v)}</b>
          </div>
        ))}
      </div>
      {r.periodo && <p style={{ margin: '10px 0 0', fontSize: 13 }}>Período: <span className="mono">{r.periodo[0]} → {r.periodo[1]}</span></p>}
      {Object.keys(r.mapeamento || {}).length > 0 && (
        <p className="mono" style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--texto-2)' }}>
          {Object.entries(r.mapeamento).map(([k, v]) => `${k}: ${v}`).join(' · ')}
        </p>
      )}
      {r.avisos?.length > 0 && (
        <ul style={{ margin: '10px 0 0', paddingLeft: 18, fontSize: 13 }}>
          {r.avisos.map((a) => <li key={a}>{a}</li>)}
        </ul>
      )}
    </div>
  )
}

export default function Entrada({ unidade }) {
  const historico = usarApi(() => api.historicoIngestao(unidade), [unidade])
  const [arrastando, setArrastando] = useState(false)
  const [dica, setDica] = useState('')
  const [texto, setTexto] = useState(EXEMPLO_TEXTO)
  const [ocupado, setOcupado] = useState(null)
  const [relatorio, setRelatorio] = useState(null)
  const [erro, setErro] = useState(null)
  const entrada = useRef(null)
  const base = api.BASE || window.location.origin

  async function enviar(promessa, qual) {
    setOcupado(qual)
    setErro(null)
    const r = await promessa
    setOcupado(null)
    if (r.dados) {
      setRelatorio(r.dados)
      api.limparCache() // dado novo: telas recalculam com a próxima leitura
      historico.recarregar()
    } else {
      setErro(r.erro || 'O motor não respondeu.')
    }
  }

  function enviarArquivo(arquivo) {
    if (arquivo) enviar(api.enviarArquivo(arquivo, { unidade, dica: dica || undefined }), 'arquivo')
  }

  return (
    <>
      <header className="cab-pagina">
        <div>
          <h1>Entrada de dados</h1>
          <p className="sub">
            Qualquer formato entra no mesmo motor. O formato é detectado pelo conteúdo, colunas desconhecidas e
            documentos vão ao Gemini, e reenviar o mesmo dado não duplica nada. O histórico novo recalibra a previsão.
          </p>
        </div>
      </header>

      <div className="grade g-2 secao">
        <section className="card">
          <div className="card-cab">
            <div>
              <h2><FileUp size={16} aria-hidden="true" /> Arquivo</h2>
              <p>CSV/TSV (export do Kibana), Excel, JSON do Elastic, Prometheus ou Datadog, NDJSON de APM, log nginx, ICS, PDF, DOCX, imagem</p>
            </div>
          </div>
          <div className="card-corpo">
            <div
              role="button"
              tabIndex={0}
              onClick={() => entrada.current?.click()}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && entrada.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setArrastando(true)
              }}
              onDragLeave={() => setArrastando(false)}
              onDrop={(e) => {
                e.preventDefault()
                setArrastando(false)
                enviarArquivo(e.dataTransfer.files?.[0])
              }}
              style={{
                border: `2px dashed var(--${arrastando ? 'primario' : 'borda-forte'})`,
                borderRadius: 12,
                padding: '28px 16px',
                textAlign: 'center',
                cursor: 'pointer',
                background: arrastando ? 'var(--superficie-2)' : 'transparent',
              }}
            >
              <FileUp size={26} aria-hidden="true" style={{ color: 'var(--texto-2)' }} />
              <p style={{ margin: '8px 0 0', fontWeight: 600 }}>{ocupado === 'arquivo' ? 'Lendo arquivo…' : 'Arraste um arquivo ou clique para escolher'}</p>
              <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--texto-2)' }}>até 25 MB · o relatório aparece abaixo</p>
              <input ref={entrada} type="file" hidden onChange={(e) => enviarArquivo(e.target.files?.[0])} />
            </div>
            <label htmlFor="dica" style={{ display: 'block', marginTop: 12, fontSize: 13, color: 'var(--texto-2)' }}>Dica para o motor (opcional)</label>
            <input
              id="dica"
              value={dica}
              onChange={(e) => setDica(e.target.value)}
              placeholder="ex.: a coluna Count é sessões ativas; horário em UTC"
              style={{ width: '100%', marginTop: 6, height: 34, padding: '0 10px', borderRadius: 8, border: '1px solid var(--borda)', background: 'var(--superficie)', color: 'var(--texto)' }}
            />
          </div>
        </section>

        <section className="card">
          <div className="card-cab">
            <div>
              <h2><Type size={16} aria-hidden="true" /> Texto livre</h2>
              <p>Cole um e-mail da secretaria, um aviso ou uma ata; o Gemini extrai os eventos do calendário</p>
            </div>
          </div>
          <div className="card-corpo">
            <textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              rows={6}
              style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid var(--borda)', background: 'var(--superficie)', color: 'var(--texto)', font: 'inherit', resize: 'vertical' }}
            />
            <button
              className="botao primario"
              style={{ marginTop: 10 }}
              disabled={!texto.trim() || ocupado === 'texto'}
              onClick={() => enviar(api.enviarTexto(texto, { unidade }), 'texto')}
            >
              <Sparkles size={14} aria-hidden="true" />
              {ocupado === 'texto' ? 'Extraindo eventos…' : 'Extrair eventos'}
            </button>
          </div>
        </section>
      </div>

      {erro && <div className="card aviso secao" style={{ padding: '12px 16px' }}><div className="aviso-corpo"><p style={{ margin: 0 }}>{erro}</p></div></div>}
      <Relatorio r={relatorio} />

      <div className="grade g-2 secao" style={{ marginTop: 18 }}>
        <section className="card">
          <div className="card-cab">
            <div>
              <h2><Cable size={16} aria-hidden="true" /> Conectar por MCP</h2>
              <p>Claude, Gemini CLI, Cursor ou LibreChat consultam o motor e enviam dados pelo protocolo</p>
            </div>
          </div>
          <div className="card-corpo">
            <p style={{ margin: 0, fontSize: 13 }}>Endereço (streamable HTTP, sem estado):</p>
            <pre className="mono" style={{ margin: '6px 0 10px', padding: 10, borderRadius: 8, background: 'var(--superficie-2)', overflowX: 'auto', fontSize: 12.5 }}>{`${base}/mcp`}</pre>
            <p style={{ margin: 0, fontSize: 13 }}>LibreChat (librechat.yaml):</p>
            <pre className="mono" style={{ margin: '6px 0 10px', padding: 10, borderRadius: 8, background: 'var(--superficie-2)', overflowX: 'auto', fontSize: 12.5 }}>{`mcpServers:\n  picozero:\n    type: streamable-http\n    url: ${base}/mcp`}</pre>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--texto-2)' }}>{FERRAMENTAS_MCP.length} ferramentas: {FERRAMENTAS_MCP.join(', ')}.</p>
          </div>
        </section>

        <section className="card">
          <div className="card-cab">
            <div>
              <h2><Webhook size={16} aria-hidden="true" /> Métricas ao vivo (webhook)</h2>
              <p>O APM, o Grafana ou um script mandam a carga atual; o motor corrige o resto do dia e alerta</p>
            </div>
          </div>
          <div className="card-corpo">
            <pre className="mono" style={{ margin: 0, padding: 10, borderRadius: 8, background: 'var(--superficie-2)', overflowX: 'auto', fontSize: 12.5 }}>{`curl -X POST "${base}/api/ingestao/metricas?unidade=${unidade}" \\\n  -H 'content-type: application/json' \\\n  -d '[{"ts": "2026-11-12T18:15:00-03:00", "valor": 420}]'`}</pre>
            <p style={{ margin: '10px 0 0', fontSize: 13, color: 'var(--texto-2)' }}>
              Também aceita qualquer JSON em <span className="mono">/api/ingestao/json</span> e eventos em <span className="mono">/api/ingestao/eventos</span>. Documentação em <a href={`${base}/docs`} target="_blank" rel="noreferrer">/docs</a>.
            </p>
          </div>
        </section>
      </div>

      <section className="card secao">
        <div className="card-cab">
          <div>
            <h2>Histórico de ingestões</h2>
            <p>tudo o que entrou no motor, por qualquer canal (arquivo, texto, webhook, MCP)</p>
          </div>
        </div>
        <div className="card-corpo">
          {historico.dados?.length ? (
            <table className="tabela">
              <thead>
                <tr><th>Quando</th><th>Canal</th><th>Formato</th><th>Leitura</th><th className="dir">Pontos</th><th className="dir">Eventos</th><th>Avisos</th></tr>
              </thead>
              <tbody>
                {historico.dados.map((r) => (
                  <tr key={r.id}>
                    <td className="mono">{r.quando.replace('T', ' ').slice(0, 16)}</td>
                    <td>{r.canal}</td>
                    <td>{r.formato}{r.arquivo ? <div className="fraco" style={{ fontSize: 12 }}>{r.arquivo}</div> : null}</td>
                    <td>{r.origem_parse === 'gemini' ? 'Gemini' : 'regras'}</td>
                    <td className="dir">{numero(r.pontos_inseridos)}</td>
                    <td className="dir">{numero(r.eventos_inseridos)}</td>
                    <td style={{ fontSize: 12.5, color: 'var(--texto-2)' }}>{r.avisos?.[0] || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="vazio" style={{ padding: 18 }}>
              {historico.origem === 'previa' ? 'Motor fora do ar: a entrada de dados precisa da API.' : 'Nenhuma ingestão ainda nesta instância. Envie um arquivo ou um texto acima.'}
            </div>
          )}
        </div>
      </section>

      <p className="nota-rodape">
        <Info size={15} aria-hidden="true" />
        Dados enviados aqui entram como origem "real" e substituem o histórico modelado nos mesmos horários. Na URL pública cada instância do servidor guarda os dados em memória temporária.
      </p>
    </>
  )
}
