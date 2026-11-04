// frontend/src/graficos/CalendarioCalor.jsx
// O semestre inteiro num calendário de calor (ECharts calendar): cada dia pintado pelo pico
// projetado em % da capacidade; ponto nos dias que o Gemini apontou. Clique escolhe o dia.
import { useCallback, useMemo } from 'react'
import Grafico from './Grafico'
import { MESES, faixasDeCalor } from './escalas'
import { useTema } from '../tema'
import { curta, diasEntre, esc, numero, paraData, paraIso, rotuloCurto, semana } from '../util'

export default function CalendarioCalor({ picos, riscos, feriados, cap, inicio, fim, selecionado, hoje, aoEscolher }) {
  const t = useTema()

  const opcao = useMemo(() => {
    const a = paraData(inicio)
    const b = paraData(fim)
    const de = paraIso(new Date(a.getFullYear(), a.getMonth(), 1))
    const ate = paraIso(new Date(b.getFullYear(), b.getMonth() + 1, 0))
    const porData = Object.fromEntries(picos.map((p) => [p.data, p]))
    const risco = Object.fromEntries(riscos.map((r) => [r.data, r]))

    const calor = picos.map((p) => {
      const pct = Math.round((p.pico / cap) * 100)
      const marcado = p.data === selecionado
      return {
        value: [p.data, pct, p.pico],
        itemStyle: marcado ? { borderColor: t.teal, borderWidth: 3 } : undefined,
      }
    })
    const numeros = diasEntre(de, ate).map((iso) => {
      const pct = porData[iso] ? (porData[iso].pico / cap) * 100 : 0
      return {
        value: [iso, paraData(iso).getDate()],
        label: {
          color: pct > 85 ? '#ffffff' : iso === hoje ? t.teal : porData[iso] ? t.texto : t.mudo,
          fontWeight: iso === hoje ? 700 : 500,
        },
      }
    })

    function dica(p) {
      const iso = p.value[0]
      const d = porData[iso]
      const r = risco[iso]
      if (!d) return `<b>${semana(iso).slice(0, 3)}, ${curta(iso)}</b><br/><span style="opacity:.7">fora do período letivo</span>`
      return [
        `<b>${semana(iso).slice(0, 3)}, ${curta(iso)}</b>${feriados[iso] ? ` · ${esc(feriados[iso])}` : ''}`,
        `Pico ${numero(d.pico)} às ${d.hora} · ${Math.round((d.pico / cap) * 100)}% da capacidade`,
        (d.eventos || []).length > 0 && `<span style="opacity:.7">${d.eventos.slice(0, 3).map((e) => esc(rotuloCurto(e))).join(' · ')}</span>`,
        r && `<span style="color:${t.teal}">Gemini: gravidade ${r.gravidade} de 5</span>`,
      ].filter(Boolean).join('<br/>')
    }

    return {
      tooltip: { trigger: 'item', confine: true, formatter: dica },
      visualMap: { type: 'piecewise', seriesIndex: 0, dimension: 1, pieces: faixasDeCalor(t), show: false },
      calendar: {
        top: 34,
        left: 44,
        right: 8,
        bottom: 8,
        range: [de, ate],
        cellSize: ['auto', 40],
        orient: 'horizontal',
        splitLine: { show: true, lineStyle: { color: t.bordaForte, width: 1.5 } },
        itemStyle: { color: t.superficie2, borderColor: t.superficie, borderWidth: 3 },
        dayLabel: { firstDay: 1, nameMap: ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'], color: t.mudo, fontSize: 11 },
        monthLabel: { nameMap: MESES, color: t.texto, fontSize: 13, fontWeight: 600, margin: 10 },
        yearLabel: { show: false },
      },
      series: [
        { type: 'heatmap', coordinateSystem: 'calendar', data: calor },
        {
          type: 'scatter',
          coordinateSystem: 'calendar',
          symbolSize: 0,
          silent: true,
          data: numeros,
          label: { show: true, formatter: (p) => p.value[1], fontSize: 11 },
        },
        {
          type: 'scatter',
          coordinateSystem: 'calendar',
          symbol: 'circle',
          symbolSize: 6,
          symbolOffset: [12, -11],
          data: riscos.map((r) => [r.data, r.gravidade]),
          itemStyle: { color: t.texto, borderColor: t.superficie, borderWidth: 1 },
        },
      ],
    }
  }, [t, picos, riscos, feriados, cap, inicio, fim, selecionado, hoje])

  const clicar = useCallback((p) => p.value?.[0] && aoEscolher(p.value[0]), [aoEscolher])

  return <Grafico opcao={opcao} altura={340} aoClicar={clicar} rotulo="Calendário do semestre colorido pelo pico projetado de cada dia" />
}
