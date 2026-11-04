// frontend/src/graficos/echarts.js
// Apache ECharts com import enxuto (só o que o PicoZero usa) e os temas Yduqs claro/escuro.
import * as echarts from 'echarts/core'
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  AriaComponent,
  AxisPointerComponent,
  CalendarComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { LabelLayout, UniversalTransition } from 'echarts/features'
import { CanvasRenderer, SVGRenderer } from 'echarts/renderers'
import { tokensDoTema } from '../tema'

echarts.use([
  BarChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
  AriaComponent,
  AxisPointerComponent,
  CalendarComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
  VisualMapComponent,
  LabelLayout,
  UniversalTransition,
  CanvasRenderer,
  SVGRenderer,
])

export const FONTE = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif'

export function alfa(hex, a) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}

function tema(t) {
  const eixo = {
    axisLine: { show: true, lineStyle: { color: t.grade } },
    axisTick: { show: false },
    axisLabel: { color: t.mudo, fontSize: 11.5, fontFamily: FONTE },
    splitLine: { show: false },
    nameTextStyle: { color: t.mudo, fontFamily: FONTE },
  }
  return {
    color: [t.teal, t.semPlano, t.controle, t.navy, t.ok, t.critico],
    backgroundColor: 'transparent',
    textStyle: { fontFamily: FONTE, color: t.texto2, fontSize: 12 },
    animationDuration: 550,
    animationDurationUpdate: 450,
    animationEasing: 'cubicOut',
    tooltip: {
      backgroundColor: t.dica,
      borderWidth: 0,
      padding: [9, 11],
      textStyle: { color: '#ffffff', fontSize: 12, fontFamily: FONTE },
      extraCssText: 'border-radius:8px;box-shadow:0 14px 34px rgba(5,13,26,.28);',
    },
    axisPointer: { lineStyle: { color: t.mudo, type: 'dashed', width: 1 } },
    categoryAxis: eixo,
    timeAxis: eixo,
    valueAxis: { ...eixo, axisLine: { show: false }, splitLine: { show: true, lineStyle: { color: t.grade } } },
    legend: { textStyle: { color: t.texto2, fontFamily: FONTE }, itemWidth: 14, itemHeight: 4, icon: 'roundRect' },
    dataZoom: {
      borderColor: t.borda,
      backgroundColor: 'transparent',
      fillerColor: alfa(t.teal, 0.12),
      handleStyle: { color: t.superficie, borderColor: t.bordaForte },
      moveHandleStyle: { color: t.bordaForte },
      textStyle: { color: t.mudo, fontFamily: FONTE },
      dataBackground: { lineStyle: { color: t.bordaForte }, areaStyle: { color: t.superficie3 } },
      selectedDataBackground: { lineStyle: { color: t.teal }, areaStyle: { color: alfa(t.teal, 0.2) } },
      brushSelect: false,
    },
    visualMap: { textStyle: { color: t.texto2, fontFamily: FONTE } },
    line: { symbol: 'none', lineStyle: { width: 2 } },
    bar: { itemStyle: { borderRadius: [2, 2, 0, 0] } },
  }
}

echarts.registerTheme('yduqs-claro', tema(tokensDoTema(false)))
echarts.registerTheme('yduqs-escuro', tema(tokensDoTema(true)))

export default echarts
