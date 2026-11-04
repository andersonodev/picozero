// frontend/src/graficos/Latencia.jsx
// Prova de carga: latência p95 antes × depois × controle ao longo do dia simulado,
// com a meta (SLO) marcada e a faixa acima dela sombreada.
import { useMemo } from 'react'
import Grafico from './Grafico'
import { alfa } from './echarts'
import { useTema } from '../tema'
import { esc, numero } from '../util'

const SLO_MS = 400

export default function Latencia({ series, resumo, cores }) {
  const t = useTema()

  const opcao = useMemo(() => {
    const horas = series.map((s) => s.hora)
    const maximo = Math.max(...series.flatMap((s) => resumo.map((c) => s[c.chave] || 0)))
    const picoAntes = series.reduce((a, b) => (b.antes > a.antes ? b : a))
    return {
      grid: { left: 64, right: 20, top: 34, bottom: 28 },
      xAxis: { type: 'category', data: horas, boundaryGap: false, axisLabel: { interval: 11 } },
      yAxis: { type: 'value', max: Math.ceil((maximo * 1.12) / 100) * 100, axisLabel: { formatter: (v) => `${numero(v)} ms` } },
      dataZoom: [{ type: 'inside' }],
      tooltip: {
        trigger: 'axis',
        confine: true,
        formatter: (ps) =>
          [`<b>${ps[0].axisValue}</b> · p95`, ...ps.map((p) => `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${p.color};margin-right:6px"></span>${esc(p.seriesName)} <b style="float:right;margin-left:14px">${numero(p.value)} ms</b>`)].join('<br/>'),
      },
      series: resumo.map((c, i) => ({
        name: c.nome,
        type: 'line',
        data: series.map((s) => s[c.chave]),
        smooth: 0.2,
        symbol: 'none',
        lineStyle: { color: cores[c.chave], width: c.chave === 'depois' ? 2.6 : 1.8 },
        itemStyle: { color: cores[c.chave] },
        z: c.chave === 'depois' ? 3 : 2,
        ...(i === 0
          ? {
              markLine: {
                symbol: 'none',
                silent: true,
                data: [
                  {
                    yAxis: SLO_MS,
                    lineStyle: { color: t.critico, type: [6, 4], width: 1.5 },
                    label: { formatter: `meta p95 ${SLO_MS} ms`, position: 'insideEndTop', color: t.critico, fontSize: 11 },
                  },
                ],
              },
              markArea: {
                silent: true,
                data: [[{ yAxis: SLO_MS, itemStyle: { color: alfa(t.critico, t.escuro ? 0.07 : 0.04) } }, { yAxis: 'max' }]],
              },
            }
          : {}),
        ...(c.chave === 'antes'
          ? {
              markPoint: {
                data: [
                  {
                    coord: [picoAntes.hora, picoAntes.antes],
                    symbol: 'circle',
                    symbolSize: 9,
                    itemStyle: { color: cores.antes, borderColor: t.superficie, borderWidth: 2 },
                    label: {
                      show: true,
                      position: 'top',
                      distance: 8,
                      formatter: `sem plano: ${numero(picoAntes.antes)} ms`,
                      color: t.texto,
                      fontWeight: 600,
                      backgroundColor: t.superficie,
                      borderColor: t.borda,
                      borderWidth: 1,
                      borderRadius: 5,
                      padding: [3, 7],
                    },
                  },
                ],
              },
            }
          : {}),
      })),
    }
  }, [t, series, resumo, cores])

  return <Grafico opcao={opcao} altura={320} rotulo="Latência p95 antes e depois do plano" />
}
