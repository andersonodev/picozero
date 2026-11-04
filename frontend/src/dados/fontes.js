// frontend/src/dados/fontes.js
// Transparência de origem dos dados (os jurados vão perguntar "isso é real?").
// REAL = medido/observado hoje. MODELO = gerado pelo código, sem dado de produção.

// Sonda pública medida em 04/11/2026 contra o site público (uma requisição, sem carga).
export const SONDA = {
  alvo: 'ibmec.br',
  infra: 'Next.js · AWS CloudFront',
  home_kb: 252,
  ttfb_cache_ms: 52,
  ttfb_frio_ms: 840,
  cache: 's-maxage=1800 (30 min)',
  redirecionamento: 'ibmec.com.br → www.ibmec.br',
  medido_em: '04/11/2026',
}

export const FONTES = [
  {
    tipo: 'real',
    titulo: 'Sonda pública do site',
    texto: `Medição externa e sem carga de ${SONDA.alvo}: ${SONDA.infra}, home de ${SONDA.home_kb} KB, TTFB de ${SONDA.ttfb_cache_ms} ms em cache e ~${SONDA.ttfb_frio_ms} ms frio. Mostra que o front é cacheado na borda; o gargalo de pico é o portal autenticado, atrás do CDN.`,
    mono: `curl -w ttfb · ${SONDA.medido_em}`,
  },
  {
    tipo: 'real',
    titulo: 'Stack de observabilidade (mapeado)',
    texto: 'O portal emite RUM para o Elastic APM da Yduqs (Azure, East US). É o lugar certo para ler o histórico real de acesso — por acesso autorizado (API key read-only ou export do Kibana), não pelo endpoint de ingestão, que é só de escrita.',
    mono: 'Elastic APM · RUM intake',
  },
  {
    tipo: 'modelo',
    titulo: 'Histórico de acesso simultâneo',
    texto: 'Gerado por script com sazonalidade acadêmica (vencimento à noite, salto após notas, entrada em massa no início das provas). Substituível em minutos pelo histórico real quando a Yduqs liberar o export autenticado.',
    mono: 'dados/gerar_dados.py · seed fixa',
  },
  {
    tipo: 'modelo',
    titulo: 'Curvas de carga e latência',
    texto: 'Carga por janela de 15 min calculada pelo código a partir dos eventos; latência simulada pelo mini-sistema. A prova de carga usa a curva do código, nunca a saída do Gemini.',
    mono: 'calculo/carga.py · carga/comparar.py',
  },
]
