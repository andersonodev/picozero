// frontend/src/tema.js
// O tema vive numa classe (.tema-escuro) no <html>. Recharts precisa de hex,
// então os tokens de gráfico são resolvidos aqui a partir do tema ativo.
// Paleta: identidade Yduqs (navy #12284C, teal #00ADBB, cinza #F2F2F2).
import { useEffect, useState } from 'react'

const CLARO = {
  superficie: '#ffffff',
  texto: '#12284c',
  texto2: '#5a6578',
  mudo: '#8b95a5',
  grade: '#ebeef2',
  semPlano: '#e5792e',
  comPlano: '#00adbb',
  controle: '#8b95a5',
  critico: '#d64541',
  ok: '#1e9e6a',
}

const ESCURO = {
  superficie: '#0f1e36',
  texto: '#eef3fa',
  texto2: '#a3b1c6',
  mudo: '#71839e',
  grade: '#1c3050',
  semPlano: '#f08a45',
  comPlano: '#2cc3cf',
  controle: '#8798b3',
  critico: '#ef5f5a',
  ok: '#34c285',
}

export function temaEscuroAtivo() {
  return document.documentElement.classList.contains('tema-escuro')
}

export function useTema() {
  const [escuro, setEscuro] = useState(temaEscuroAtivo)
  useEffect(() => {
    const obs = new MutationObserver(() => setEscuro(temaEscuroAtivo()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])
  return escuro ? ESCURO : CLARO
}

// Gravidade escrita pelo Gemini (1–5).
export function nivelDaGravidade(g) {
  if (g >= 4) return { chave: 'critico', rotulo: 'crítico' }
  if (g === 3) return { chave: 'alto', rotulo: 'alto' }
  return { chave: 'atencao', rotulo: 'atenção' }
}

// Situação da carga calculada pelo código em relação à capacidade.
export function situacaoDaCarga(pico, cap) {
  if (pico > cap) return { chave: 'critico', rotulo: 'acima da capacidade' }
  if (pico >= cap * 0.85) return { chave: 'alto', rotulo: 'perto do limite' }
  if (pico >= cap * 0.65) return { chave: 'atencao', rotulo: 'atenção' }
  return { chave: 'folga', rotulo: 'com folga' }
}

// Cor de cada tipo de evento do calendário (tokens --ev-* no CSS).
const TIPOS_COM_COR = ['prova_online', 'vencimento', 'notas', 'rematricula', 'outro']
export function corDoTipo(tipo) {
  return `var(--ev-${TIPOS_COM_COR.includes(tipo) ? tipo : 'outro'})`
}
