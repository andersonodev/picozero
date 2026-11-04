// frontend/src/graficos/Validacao.jsx
// Validação com dado público real: visitas mensais estimadas do portal (barras) contra o volume
// que o motor projeta para os mesmos meses (linha, eixo à direita). Escalas diferentes de propósito:
// o que se compara é a forma da série (correlação), não o valor absoluto.
import { useMemo } from 'react'
import Grafico from './Grafico'
import { alfa } from './echarts'
import { MESES } from './escalas'
import { useTema } from '../tema'
import { numero } from '../util'

const rotuloMes = (m) => `${MESES[Number(m.slice(5, 7)) - 1]}/${m.slice(2, 4)}`

export default function Validacao({ meses }) {
  const t = useTema()
  const opcao = useMemo(
    () => ({
      grid: { left: 64, right: 64, top: 30, bottom: 28 },
      legend: { top: 0, right: 0, data: ['Visitas reais (público)', 'Projeção do motor'] },
      tooltip: {
        trigger: 'axis',
        confine: true,
        formatter: (ps) => {
          const m = meses[ps[0].dataIndex]
          return [
            `<b>${rotuloMes(m.mes)}</b>`,
            `Visitas reais <b style="float:right;margin-left:14px">${numero(m.visitas_reais)}</b>`,
            `Motor <b style="float:right;margin-left:14px">${numero(m.visitas_modelo)}</b>`,
            m.erro_pct != null ? `<span style="opacity:.7">diferença de forma: ${m.erro_pct}%</span>` : '',
          ].filter(Boolean).join('<br/>')
        },
      },
      xAxis: { type: 'category', data: meses.map((m) => rotuloMes(m.mes)) },
      yAxis: [
        { type: 'value', name: 'reais', axisLabel: { formatter: (v) => numero(v) }, splitNumber: 3 },
        { type: 'value', name: 'motor', axisLabel: { formatter: (v) => numero(v) }, splitLine: { show: false }, splitNumber: 3 },
      ],
      series: [
        {
          name: 'Visitas reais (público)',
          type: 'bar',
          data: meses.map((m) => m.visitas_reais),
          barMaxWidth: 26,
          itemStyle: { color: alfa(t.teal, 0.55), borderRadius: [3, 3, 0, 0] },
        },
        {
          name: 'Projeção do motor',
          type: 'line',
          yAxisIndex: 1,
          data: meses.map((m) => m.visitas_modelo),
          smooth: 0.25,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { color: t.texto, width: 2 },
          itemStyle: { color: t.texto },
        },
      ],
    }),
    [t, meses],
  )
  return <Grafico opcao={opcao} altura={260} rotulo="Visitas mensais reais contra a projeção do motor" />
}
