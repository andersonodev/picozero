// frontend/src/graficos/GraficoSemestre.jsx
// Visão geral: pico diário (barras) e mapa de calor hora × dia no MESMO eixo de tempo,
// com zoom compartilhado (como um timeboard). Clique em qualquer dia abre o plano.
import { useCallback, useMemo } from 'react'
import Grafico from './Grafico'
import { alfa } from './echarts'
import { MESES, corDoNivel, faixasDeCalor } from './escalas'
import { useTema } from '../tema'
import { curta, esc, numero, paraData, rotuloCurto, semana } from '../util'

const HORAS = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, '0')}h`)

export default function GraficoSemestre({ picos, mapa, riscos, marcos, feriados, cap, hoje, aoAbrir }) {
  const t = useTema()
  const dias = useMemo(() => picos.map((p) => p.data), [picos])

  const opcao = useMemo(() => {
    const idx = Object.fromEntries(dias.map((d, i) => [d, i]))
    const risco = Object.fromEntries(riscos.map((r) => [r.data, r]))
    const barras = picos.map((p) => {
      const fds = [0, 6].includes(paraData(p.data).getDay())
      return {
        value: Math.round((p.pico / cap) * 100),
        itemStyle: { color: corDoNivel(t, p.nivel), opacity: fds && p.nivel === 'ok' ? 0.45 : 1 },
      }
    })
    const calor = []
    for (const m of mapa || []) {
      const i = idx[m.data]
      if (i === undefined) continue
      m.horas.forEach((v, h) => calor.push([i, h, Math.round((v / cap) * 100), v]))
    }
    const periodos = marcos
      .filter((m) => idx[m.inicio] !== undefined || idx[m.fim] !== undefined)
      .map((m) => [
        { name: m.nome, xAxis: idx[m.inicio] !== undefined ? m.inicio : dias[0] },
        { xAxis: idx[m.fim] !== undefined ? m.fim : dias[dias.length - 1] },
      ])
    const marcas = [
      {
        yAxis: 100,
        lineStyle: { color: t.critico, type: [6, 4], width: 1.5 },
        label: { formatter: 'capacidade', position: 'insideEndTop', color: t.critico, fontSize: 11 },
      },
    ]
    if (idx[hoje] !== undefined) {
      marcas.push({
        xAxis: hoje,
        lineStyle: { color: t.teal, type: 'solid', width: 1.5 },
        label: { formatter: 'hoje', position: 'end', color: t.teal, fontWeight: 600, fontSize: 11 },
      })
    }

    function dica(p) {
      if (p.componentType !== 'series') return ''
      if (p.seriesIndex === 0) {
        const d = picos[p.dataIndex]
        const r = risco[d.data]
        const fer = feriados[d.data]
        const per = marcos.filter((m) => m.inicio <= d.data && d.data <= m.fim).map((m) => esc(m.nome)).join(' · ')
        const evs = (d.eventos || []).slice(0, 3).map((e) => esc(rotuloCurto(e))).join(' · ')
        return [
          `<b>${semana(d.data).slice(0, 3)}, ${curta(d.data)}</b>${fer ? ` · ${esc(fer)}` : ''}`,
          `Pico ${numero(d.pico)} às ${d.hora} · ${Math.round((d.pico / cap) * 100)}% da capacidade`,
          evs && `<span style="opacity:.7">${evs}</span>`,
          per && `<span style="opacity:.55">Período: ${per}</span>`,
          r && `<span style="color:${t.teal}">Gemini: gravidade ${r.gravidade} de 5 · clique para abrir</span>`,
        ].filter(Boolean).join('<br/>')
      }
      const [i, h, pct, v] = p.value
      return `<b>${semana(dias[i]).slice(0, 3)}, ${curta(dias[i])}</b> · ${h}h às ${h + 1}h<br/>${numero(v)} acessos · ${pct}% da capacidade`
    }

    return {
      aria: { enabled: true, label: { description: 'Pico diário e mapa de calor por hora do semestre' } },
      grid: [
        { left: 46, right: 16, top: 24, height: 112 },
        { left: 46, right: 16, top: 158, height: 216 },
      ],
      xAxis: [
        { type: 'category', data: dias, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: t.grade } } },
        {
          type: 'category',
          data: dias,
          gridIndex: 1,
          axisLine: { show: false },
          axisLabel: {
            interval: (i, v) => i === 0 || v.endsWith('-01'),
            formatter: (v) => MESES[Number(v.slice(5, 7)) - 1],
            color: t.texto2,
            fontWeight: 500,
          },
        },
      ],
      yAxis: [
        { type: 'value', gridIndex: 0, splitNumber: 2, axisLabel: { formatter: '{value}%' } },
        { type: 'category', gridIndex: 1, data: HORAS, inverse: true, axisLabel: { interval: 5 }, axisLine: { show: false } },
      ],
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false, moveOnMouseMove: true },
        { type: 'slider', xAxisIndex: [0, 1], height: 18, bottom: 8, showDetail: false },
      ],
      visualMap: { type: 'piecewise', seriesIndex: 1, dimension: 2, pieces: faixasDeCalor(t), show: false },
      tooltip: { trigger: 'item', confine: true, formatter: dica },
      series: [
        {
          type: 'bar',
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: barras,
          barCategoryGap: '22%',
          markLine: { symbol: 'none', silent: true, data: marcas },
          markArea: {
            silent: true,
            itemStyle: { color: alfa(t.teal, t.escuro ? 0.1 : 0.06) },
            label: { show: false },
            data: periodos,
          },
        },
        {
          type: 'heatmap',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: calor,
          itemStyle: { borderColor: t.superficie, borderWidth: 0.6 },
          emphasis: { itemStyle: { borderColor: t.texto, borderWidth: 1 } },
        },
      ],
    }
  }, [t, dias, picos, mapa, riscos, marcos, feriados, cap, hoje])

  const clicar = useCallback(
    (p) => {
      if (p.componentType !== 'series') return
      const iso = p.seriesIndex === 0 ? dias[p.dataIndex] : dias[p.value[0]]
      if (iso) aoAbrir(iso)
    },
    [dias, aoAbrir],
  )

  return <Grafico opcao={opcao} altura={420} aoClicar={clicar} rotulo="Pico diário e mapa de calor por hora do semestre" />
}
