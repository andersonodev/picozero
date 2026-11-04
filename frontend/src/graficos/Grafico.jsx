// frontend/src/graficos/Grafico.jsx
// Envelope React do ECharts: inicia com o tema Yduqs do momento, acompanha o tamanho do
// contêiner, troca o tema junto com o app e repassa cliques.
import { useEffect, useRef } from 'react'
import echarts from './echarts'
import { useEscuro } from '../tema'

export default function Grafico({ opcao, altura = 300, aoClicar, renderer = 'canvas', rotulo, className }) {
  const el = useRef(null)
  const grafico = useRef(null)
  const escuro = useEscuro()

  useEffect(() => {
    const g = echarts.init(el.current, escuro ? 'yduqs-escuro' : 'yduqs-claro', { renderer })
    grafico.current = g
    const obs = new ResizeObserver(() => g.resize())
    obs.observe(el.current)
    return () => {
      obs.disconnect()
      g.dispose()
      grafico.current = null
    }
  }, [escuro, renderer])

  useEffect(() => {
    grafico.current?.setOption(opcao, { notMerge: true, lazyUpdate: true })
  }, [opcao, escuro, renderer])

  useEffect(() => {
    const g = grafico.current
    if (!g || !aoClicar) return undefined
    g.on('click', aoClicar)
    return () => g.off('click', aoClicar)
  }, [aoClicar, escuro, renderer])

  return <div ref={el} className={className} style={{ width: '100%', height: altura }} role="img" aria-label={rotulo} />
}
