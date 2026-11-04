// frontend/src/tema.js
// O tema vive numa classe (.tema-escuro) no <html>. Recharts precisa de hex,
// então os tokens de gráfico são resolvidos aqui a partir do tema ativo.
import { useEffect, useState } from 'react'

const CLARO = {
  superficie: '#ffffff',
  texto: '#0b1220',
  texto2: '#566072',
  mudo: '#8893a3',
  grade: '#e7ebf1',
  serie1: '#2a78d6',
  serie2: '#eb6834',
  serie3: '#1baf7a',
  critico: '#d03b3b',
  bom: '#0ca30c',
}

const ESCURO = {
  superficie: '#12161d',
  texto: '#eef2f7',
  texto2: '#9aa5b4',
  mudo: '#6b7686',
  grade: '#20262f',
  serie1: '#4f97ec',
  serie2: '#ec7a4b',
  serie3: '#2bc08a',
  critico: '#e05a5a',
  bom: '#2bbf2b',
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

export function nivelDaGravidade(g) {
  if (g >= 4) return { chave: 'critico', rotulo: 'crítico' }
  if (g === 3) return { chave: 'serio', rotulo: 'alto' }
  return { chave: 'alerta', rotulo: 'atenção' }
}
