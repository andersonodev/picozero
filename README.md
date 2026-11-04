# PicoZero

Prevê os picos de acesso ao portal do aluno do Ibmec (semestre 2026.2), avisa antes que eles aconteçam e sugere o que fazer. Projeto do Innovation Day (Ibmec · Yduqs · Google).

O projeto tem duas partes no mesmo repositório:

| Pasta | O que é | Tecnologia |
|---|---|---|
| `backend/` | Motor de previsão, API REST, alertas ao vivo e servidor MCP | Python 3.12, FastAPI, Gemini, SQLite |
| `frontend/` | Painel de operações (visão geral, calendário, dias de risco, prova de carga, fontes) | React 19, Vite, ECharts |

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (ele instala o Python 3.12 sozinho se faltar)
- Node.js 20.19 ou mais novo, com npm
- Opcional: uma chave do Gemini ([Google AI Studio](https://aistudio.google.com/apikey)). Sem ela, tudo funciona com regras no lugar da IA.

## Rodar localmente

Use dois terminais, um para cada parte.

### 1. Backend (porta 8000)

```bash
cd backend
cp .env.example .env      # e coloque sua GEMINI_API_KEY (opcional)
uv sync
uv run fastapi dev        # http://127.0.0.1:8000
```

Na primeira execução o backend cria `backend/picozero.db` e preenche com o calendário 2026.2 e o histórico de acesso modelado. Para começar do zero, pare o servidor e apague `backend/picozero.db*`.

Endereços úteis:

- http://127.0.0.1:8000/docs: documentação interativa da API
- http://127.0.0.1:8000/api/saude: diz se a API está de pé e se o Gemini está configurado
- http://127.0.0.1:8000/mcp: servidor MCP (veja abaixo)

<details>
<summary>Sem uv (pip puro)</summary>

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt uvicorn
uvicorn picozero.api:app --reload --port 8000
```

</details>

### 2. Frontend (porta 5173)

```bash
cd frontend
npm install
npm run dev               # http://localhost:5173
```

O Vite repassa `/api` e `/sim` para o backend em `127.0.0.1:8000`, então não é preciso configurar nada.

Se o backend estiver desligado, o painel continua abrindo com os dados da prévia local (`frontend/src/dados/`) e mostra que está em modo prévia. Para apontar o front para outro backend, crie `frontend/.env.local` com `VITE_API_URL=https://endereco-do-backend`.

## Variáveis de ambiente do backend

Ficam em `backend/.env` (que não vai para o Git). Só a primeira importa no dia a dia.

| Variável | Para que serve | Padrão |
|---|---|---|
| `GEMINI_API_KEY` | Chave do Gemini. Sem ela, a IA usa regras. | vazio |
| `GEMINI_MODEL` | Lista de modelos separada por vírgula; se um falhar, tenta o próximo | `gemini-3-flash-preview,…` |
| `GEMINI_TIMEOUT_MS` | Tempo máximo por chamada ao Gemini | `30000` |
| `PICOZERO_IA_LIMITE_DIARIO` | Teto de chamadas ao Gemini por dia | `400` |
| `PICOZERO_IA_POR_MINUTO` | Teto de chamadas por minuto por IP | `12` |
| `PICOZERO_AGORA` | Fixa o "agora" do motor para demonstração (`2026-09-10T17:00`) | relógio real |
| `PICOZERO_DB` | Caminho do banco SQLite | `backend/picozero.db` |
| `PICOZERO_CORS` | Origens permitidas, separadas por vírgula | `*` |
| `PICOZERO_TOKEN` | Se definido, exige este token nas rotas de escrita (ingestão, reconhecer alerta) | vazio |
| `ALERTA_WEBHOOK_URL` | Webhook (Slack, Google Chat, Teams) que recebe alertas sério e crítico | vazio |
| `PICOZERO_INGESTAO_MAX_MB` | Tamanho máximo de arquivo na ingestão | `25` |

## Testes

```bash
cd backend
uv run pytest
```

## Servidor MCP

Agentes (Claude, Gemini CLI, Cursor) podem consultar a previsão e enviar dados pelo MCP. As ferramentas são as mesmas da API: `previsao_dia`, `proximos_picos`, `alertas`, `dias_de_risco`, `ingerir_metricas`, `ingerir_arquivo`, `perguntar` e outras.

Com o backend rodando, pelo HTTP:

```bash
claude mcp add --transport http picozero http://127.0.0.1:8000/mcp
```

Ou por stdio, sem subir a API:

```bash
cd backend
uv run python -m picozero.mcp_servidor
```

## Prova de carga

Teste de carga de verdade contra um portal simulado: reproduz a curva de um dia e mede latência (p50/p95) e erros 503, com e sem fila virtual.

```bash
cd backend
uv run python ferramentas/prova_carga.py servir --porta 8765    # terminal 1: sobe o portal simulado
uv run python ferramentas/prova_carga.py rodar --url http://127.0.0.1:8765 --data 2026-09-10    # terminal 2
```

O resultado fica em `backend/ferramentas/saida/`.

## Deploy na Vercel

O `vercel.json` da raiz publica o front e o backend juntos, no mesmo domínio:

- o front é construído a partir de `frontend/` e servido como site estático;
- `api/index.py` expõe o FastAPI como função Python, e `/api/*`, `/mcp`, `/sim/*` e `/docs` vão para ela.

```bash
vercel          # prévia
vercel --prod   # produção
```

Cadastre `GEMINI_API_KEY` nas variáveis de ambiente do projeto na Vercel. Lá o banco fica em `/tmp`, que é apagado de tempos em tempos; quando isso acontece, o backend recria o banco com os dados iniciais, e os dados enviados pela ingestão se perdem.

## Estrutura

```
backend/
  picozero/
    api/          rotas HTTP (painel, alertas, IA, plano, ingestão, simulação)
    motor/        cálculo de carga, previsão, alertas, plano, prova de carga
    ia/           Gemini: chat, análise de crise, tarefas
    ingestao/     leitores de CSV, XLSX, JSON, logs, ICS, PDF e texto
    dados/        calendário 2026.2, histórico de eventos, tráfego público
    mcp_servidor.py
  ferramentas/    prova de carga
  tests/
frontend/
  src/
    telas/        uma tela por aba do painel
    graficos/     gráficos em ECharts
    api/          cliente da API, com fallback para a prévia
    dados/        dados da prévia offline
api/index.py      entrada da função Python na Vercel
vercel.json       deploy de front e backend juntos
```
