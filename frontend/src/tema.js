// frontend/src/tema.js
// O tema vive numa classe (.tema-escuro) no <html>. O ECharts precisa de cores concretas,
// então os tokens de gráfico são resolvidos aqui a partir do tema ativo.
// Paleta: identidade Yduqs (navy #12284C, teal #00ADBB, cinza #F2F2F2).
import { useEffect, useState } from 'react'

const CLARO = {
  escuro: false,
  superficie: '#ffffff',
  superficie2: '#f7f8fa',
  superficie3: '#eef0f4',
  texto: '#12284c',
  texto2: '#5a6578',
  mudo: '#8b95a5',
  grade: '#ebeef2',
  borda: '#e3e6eb',
  bordaForte: '#cdd3dc',
  navy: '#12284c',
  teal: '#00adbb',
  semPlano: '#e5792e',
  comPlano: '#00adbb',
  controle: '#8b95a5',
  critico: '#d64541',
  alto: '#e5792e',
  atencao: '#e0a614',
  ok: '#1e9e6a',
  folga: '#a7dce1',
  // escala do mapa de calor (% da capacidade), do vazio ao folgado
  calor: ['#f1f4f7', '#d9eff2', '#a7dce1', '#62c4ce'],
  dica: '#0c1b33',
  ev: { prova_online: '#00adbb', vencimento: '#3d6be0', notas: '#1e9e6a', rematricula: '#7357d9', outro: '#8b95a5' },
}

const ESCURO = {
  escuro: true,
  superficie: '#0f1e36',
  superficie2: '#132541',
  superficie3: '#182c4c',
  texto: '#eef3fa',
  texto2: '#a3b1c6',
  mudo: '#71839e',
  grade: '#1c3050',
  borda: '#21375a',
  bordaForte: '#2d4670',
  navy: '#12284c',
  teal: '#2cc3cf',
  semPlano: '#f08a45',
  comPlano: '#2cc3cf',
  controle: '#8798b3',
  critico: '#ef5f5a',
  alto: '#f08a45',
  atencao: '#e8b631',
  ok: '#34c285',
  folga: '#1f5f6c',
  calor: ['#132440', '#173a52', '#1f5f6c', '#2a8f9c'],
  dica: '#050d1a',
  ev: { prova_online: '#2cc3cf', vencimento: '#6b8fef', notas: '#34c285', rematricula: '#9a85ec', outro: '#8798b3' },
}

export function temaEscuroAtivo() {
  return document.documentElement.classList.contains('tema-escuro')
}

export function useEscuro() {
  const [escuro, setEscuro] = useState(temaEscuroAtivo)
  useEffect(() => {
    const obs = new MutationObserver(() => setEscuro(temaEscuroAtivo()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])
  return escuro
}

export function useTema() {
  return useEscuro() ? ESCURO : CLARO
}

export function tokensDoTema(escuro) {
  return escuro ? ESCURO : CLARO
}

// Gravidade escrita pelo Gemini (1–5).
export function nivelDaGravidade(g) {
  if (g >= 4) return { chave: 'critico', rotulo: 'crítico' }
  if (g === 3) return { chave: 'alto', rotulo: 'alto' }
  return { chave: 'atencao', rotulo: 'atenção' }
}

// Situação da carga em relação à capacidade (chaves da interface).
export function situacaoDaCarga(pico, cap) {
  if (pico > cap) return { chave: 'critico', rotulo: 'acima da capacidade' }
  if (pico >= cap * 0.85) return { chave: 'alto', rotulo: 'perto do limite' }
  if (pico >= cap * 0.65) return { chave: 'atencao', rotulo: 'atenção' }
  return { chave: 'folga', rotulo: 'com folga' }
}

// Nível no formato do backend (ok | alerta | serio | critico) → chaves da interface.
const DO_NIVEL = {
  ok: { chave: 'folga', rotulo: 'com folga' },
  alerta: { chave: 'atencao', rotulo: 'atenção' },
  serio: { chave: 'alto', rotulo: 'perto do limite' },
  critico: { chave: 'critico', rotulo: 'acima da capacidade' },
}
export function situacaoDoNivel(nivel) {
  return DO_NIVEL[nivel] || DO_NIVEL.ok
}

// Cor de cada tipo de evento do calendário (tokens --ev-* no CSS).
const TIPOS_COM_COR = ['prova_online', 'vencimento', 'notas', 'rematricula', 'outro']
export function corDoTipo(tipo) {
  return `var(--ev-${TIPOS_COM_COR.includes(tipo) ? tipo : 'outro'})`
}
