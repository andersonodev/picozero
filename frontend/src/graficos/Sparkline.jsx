// frontend/src/graficos/Sparkline.jsx
// Mini curva de 24 horas com a linha da capacidade, para listas e cartões.
import { useMemo } from 'react'
import Grafico from './Grafico'
import { alfa } from './echarts'
import { useTema } from '../tema'

export default function Sparkline({ valores, cap, cor, altura = 52 }) {
  const t = useTema()
  const opcao = useMemo(() => {
    const c = cor || t.teal
    return {
      animation: false,
      grid: { left: 1, right: 1, top: 4, bottom: 1 },
      xAxis: { type: 'category', show: false, boundaryGap: false, data: valores.map((_, i) => i) },
      yAxis: { type: 'value', show: false, min: 0, max: Math.max(cap, ...valores) * 1.08 },
      series: [
        {
          type: 'line',
          data: valores,
          smooth: 0.3,
          symbol: 'none',
          lineStyle: { color: c, width: 1.6 },
          areaStyle: { color: alfa(c, 0.16) },
          markLine: {
            symbol: 'none',
            silent: true,
            label: { show: false },
            data: [{ yAxis: cap }],
            lineStyle: { color: t.critico, type: [3, 3], width: 1 },
          },
        },
      ],
    }
  }, [t, valores, cap, cor])
  return <Grafico opcao={opcao} altura={altura} renderer="svg" rotulo="Curva do dia por hora" />
}
