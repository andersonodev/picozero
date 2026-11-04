# PicoZero · backend

Motor de previsão de picos de acesso do portal acadêmico. Ele avisa **antes** do pico e diz à equipe o que fazer no dia. Usa FastAPI, Gemini (com fallback por regras) e MCP.

- **Produção:** https://frontend-delta-seven-37.vercel.app (front, `/api`, `/docs` e `/mcp` na mesma origem)
- **Local:** `uv run uvicorn picozero.api:app --port 8000` (o proxy `/api` do Vite já aponta para cá)
- **Testes:** `uv run pytest` (82 testes, sem rede e sem chave)

## Como o motor prevê

```
carga(dia, 15 min) = perfil orgânico aprendido (por tipo de dia: útil, sexta, sábado, domingo, feriado, férias)
                     × (1 + fator_período)                     ← semanas de rematrícula/provas
                   + Σ fator[tipo] × forma do evento           ← vencimento, prova online, notas, rematrícula, outro
                   → nowcast: com métricas ao vivo, corrige o resto do dia (real ÷ previsto, com encolhimento)
```

- **Fatores aprendidos:** os fatores de cada tipo saem de mínimos quadrados com prior sobre o histórico. As bandas p10–p90 saem do erro observado.
- **Backtest fora da amostra:** o motor treina com o histórico até o início de 2026.2 e mede o erro nos dias já ocorridos do semestre. Erro médio de 7,5% no pico, nenhum dia crítico perdido (`GET /api/modelo`).
- **Validação com dado real público:** visitas mensais do `estudante.ibmec.br` no Domsilo (set/2025 a set/2026). Correlação mensal de 0,78, ou 0,92 com a tendência de adoção (`GET /api/validacao/publica`). Esse teste revelou o efeito de período, que virou componente do modelo.
- **Divisão de papéis:** o Gemini **nunca** escreve números de carga. Ele lê documentos, classifica, consulta o histórico por function calling, explica e redige. Picos, horários e janelas vêm do código.

O histórico de acesso é **modelado**, com seed fixa e marcado `origem=modelo`. Um export real (CSV do Kibana ou API read-only) sobrescreve os mesmos horários e o motor recalibra sozinho.

## Entradas de dados (todas geram relatório auditável em `/api/ingestao/historico`)

| Canal | Rota / ferramenta | Formatos |
|---|---|---|
| Arquivo | `POST /api/ingestao/arquivo` (multipart) | Ver lista abaixo |
| Webhook | `POST /api/ingestao/json` | Qualquer JSON (Grafana, Elastic Watcher, Datadog, script) |
| Ao vivo | `POST /api/ingestao/metricas` | `[{ts, valor}]` (ISO ou epoch); máximo por janela de 15 min |
| Calendário | `POST /api/ingestao/eventos` | Formato do front (`data, hora_inicio, hora_fim, tipo, descricao, turmas`) |
| Texto livre | `POST /api/ingestao/texto` | E-mail ou aviso da secretaria → eventos |
| Tráfego público | `POST /api/ingestao/trafego` | Visitas mensais (Domsilo, Similarweb, GA4) |
| MCP | `ingerir_metricas`, `ingerir_eventos`, `ingerir_texto`, `ingerir_arquivo` (base64), `ingerir_trafego_mensal` | Os mesmos acima |

Formatos aceitos em `POST /api/ingestao/arquivo` (lista completa em `/api/ingestao/formatos`):
- CSV/TSV, inclusive export do Kibana, `;` e vírgula decimal;
- XLSX;
- JSON de Elasticsearch, Prometheus, Datadog e Grafana;
- NDJSON de APM/RUM (usuários distintos por janela);
- access log nginx/apache;
- texto do Prometheus;
- ICS;
- PDF, DOCX e imagem, lidos pelo Gemini.

O formato é detectado pelo conteúdo. Colunas desconhecidas vão ao Gemini (`mapear_colunas`). Reenviar o mesmo dado não duplica nada.

## Saídas principais

- `GET /api/carga/{data}`: 96 pontos `{hora, carga, p10, p90, real, base}`, com pico, janelas de pico (≥ 60% da capacidade) e nível.
- `GET /api/picos` (fita do semestre), `GET /api/mapa` (calor hora × dia), `GET /api/previsao?dias=7`.
- `GET /api/alertas` e `GET /api/alertas/stream` (SSE): estágios planejamento > 72 h, preparação, véspera, iminente < 2 h, em curso e ao vivo. Cada alerta traz ações por estágio e por tipo de evento. Com `ALERTA_WEBHOOK_URL`, alertas altos e críticos também vão para Slack, Google Chat ou Teams.
- `GET /api/manutencao/{data}`: dicas para a equipe. Inclui janela de manutenção (menor carga), congelamento de deploys, até quando escalar, tarefas com prioridade e responsável, e o que não fazer. `POST …/gerar` pede ao Gemini para reescrever.
- `GET /api/riscos` / `POST /api/riscos/analisar`: dias de risco com gravidade e motivo. O Gemini consulta o histórico por ferramenta.
- `GET /api/plano/{data}` / `POST …/gerar`: plano em 3 níveis com ações executáveis. O validador recalcula a curva em até 3 tentativas.
- `POST /api/crise`: comunicado aos alunos.
- `POST /api/chat`: copiloto (Gemini com function calling sobre o motor).
- `GET /api/simulacao/ao-vivo` (SSE): replay de um dia com carga acima do previsto. O alerta ao vivo dispara antes do pico.
- `GET /api/trilha`: registro de cada chamada ao Gemini, de cada ferramenta usada e de cada fallback.

## MCP

- **HTTP (stateless, JSON):** `https://picozeroday.vercel.app/mcp`. Em clientes que pedem o tipo, use `streamable-http`.
- **stdio** (Gemini CLI, Cursor e outros clientes MCP):
  ```json
  { "mcpServers": { "picozero": { "command": "uv", "args": ["--directory", "/caminho/para/backend", "run", "python", "-m", "picozero.mcp_servidor"] } } }
  ```

Ferramentas:
- consulta: `previsao_dia`, `proximos_picos`, `alertas`, `dicas_manutencao`, `dias_de_risco`, `consultar_historico`, `desempenho_modelo`, `validacao_publica`;
- ingestão: os 5 `ingerir_*`;
- conversa: `perguntar`;
- recurso: `picozero://contexto`.

## Configuração (`.env` local ou variáveis da Vercel)

Veja `.env.example`. A única variável necessária para usar a IA é `VERTEX_API_KEY`. Sem ela, tudo responde por regras (`origem: "regras"`).

A cadeia de modelos (`GEMINI_MODEL`) troca de modelo na hora quando recebe 404, 429 ou 503. Cada chamada tem prazo total de 45 s. As respostas estruturadas ficam em cache e não há teto diário, a não ser que `PICOZERO_IA_LIMITE_DIARIO` seja definido.

## White label

As outras marcas e unidades entram trocando `picozero/dados/contexto.json` (unidades, capacidades, semestre, feriados) e o calendário. Unidades sem histórico próprio usam a calibração da unidade de referência, escalada por número de alunos. A partir de 14 dias de dados próprios, a unidade é calibrada separadamente.
