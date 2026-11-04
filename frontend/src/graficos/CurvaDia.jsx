// frontend/src/graficos/CurvaDia.jsx
// Carga simultânea de um dia em janelas de 15 min: área "sem plano", linha "com plano",
// faixa acima da capacidade, janelas dos eventos sombreadas e o pico marcado.
import { useMemo } from 'react'
import Grafico from './Grafico'
import { alfa } from './echarts'
import { janela15 } from './escalas'
import { useTema } from '../tema'
import { esc, numero, rotuloCurto } from '../util'

const maior = (pontos) => pontos.reduce((a, b) => (b.carga > a.carga ? b : a))

export default function CurvaDia({ pontos, pontosCom, cap, eventos = [], vista = 'ambos', compacto = false, altura = 320 }) {
  const t = useTema()

  const opcao = useMemo(() => {
    const horas = pontos.map((p) => p.hora)
    const picoSem = maior(pontos)
    const picoCom = pontosCom ? maior(pontosCom) : null
    const topo = Math.max(cap, picoSem.carga, picoCom?.carga || 0) * 1.12
    const passo = topo > 1200 ? 500 : topo > 600 ? 200 : 100
    const teto = Math.ceil(topo / passo) * passo
    const mostraSem = !pontosCom || vista !== 'com'
    const mostraCom = Boolean(pontosCom) && vista !== 'sem'
    const corSem = compacto && picoSem.carga <= cap ? t.teal : pontosCom ? t.semPlano : picoSem.carga > cap ? t.critico : t.teal

    const janelas = compacto
      ? []
      : eventos
          .filter((e) => e.hora_inicio !== '00:00')
          .map((e) => [
            {
              name: rotuloCurto(e.descricao),
              xAxis: janela15(e.hora_inicio),
              itemStyle: { color: alfa(t.ev[e.tipo] || t.ev.outro, t.escuro ? 0.14 : 0.08) },
              label: { color: t.texto2, fontSize: 11, position: 'insideTopLeft', distance: 6 },
            },
            { xAxis: janela15(e.hora_fim) },
          ])

    const marcas = {
      markLine: {
        symbol: 'none',
        silent: true,
        data: [
          {
            yAxis: cap,
            lineStyle: { color: t.critico, type: [6, 4], width: 1.5 },
            label: { formatter: `capacidade ${cap}`, position: 'insideStartTop', color: t.critico, fontSize: 11 },
          },
        ],
      },
      markArea: {
        silent: true,
        data: [[{ yAxis: cap, itemStyle: { color: alfa(t.critico, t.escuro ? 0.08 : 0.045) } }, { yAxis: teto }], ...janelas],
      },
    }

    const area = (cor) => ({
      color: {
        type: 'linear',
        x: 0,
        y: 0,
        x2: 0,
        y2: 1,
        colorStops: [
          { offset: 0, color: alfa(cor, 0.3) },
          { offset: 1, color: alfa(cor, 0.02) },
        ],
      },
    })
    const ponto = (p, cor, texto) => ({
      coord: [p.hora, p.carga],
      symbol: 'circle',
      symbolSize: 9,
      itemStyle: { color: cor, borderColor: t.superficie, borderWidth: 2 },
      label: {
        show: true,
        position: 'top',
        distance: 8,
        formatter: texto,
        color: t.texto,
        fontWeight: 600,
        fontSize: 12,
        backgroundColor: t.superficie,
        borderColor: t.borda,
        borderWidth: 1,
        borderRadius: 5,
        padding: [3, 7],
      },
    })

    const series = []
    if (mostraSem) {
      series.push({
        name: 'Sem plano',
        type: 'line',
        data: pontos.map((p) => p.carga),
        smooth: 0.25,
        symbol: 'none',
        lineStyle: { color: corSem, width: 2 },
        itemStyle: { color: corSem },
        areaStyle: area(corSem),
        markPoint: !compacto && picoSem.carga > cap * 0.6 ? { data: [ponto(picoSem, corSem, `pico ${numero(picoSem.carga)}`)] } : undefined,
      })
    }
    if (mostraCom) {
      series.push({
        name: 'Com plano',
        type: 'line',
        data: pontosCom.map((p) => p.carga),
        smooth: 0.25,
        symbol: 'none',
        lineStyle: { color: t.comPlano, width: 2.5 },
        itemStyle: { color: t.comPlano },
        areaStyle: mostraSem ? undefined : area(t.comPlano),
        markPoint: compacto ? undefined : { data: [ponto(picoCom, t.comPlano, `com plano ${numero(picoCom.carga)}`)] },
      })
    }
    Object.assign(series[0], marcas)

    return {
      grid: compacto ? { left: 8, right: 8, top: 10, bottom: 22 } : { left: 48, right: 20, top: 34, bottom: 28 },
      xAxis: {
        type: 'category',
        data: horas,
        boundaryGap: false,
        axisLabel: compacto
          ? { interval: (i, v) => ['06:00', '12:00', '18:00'].includes(v), fontSize: 11 }
          : { interval: 11 },
      },
      yAxis: { type: 'value', max: teto, interval: passo, show: !compacto, axisLabel: { formatter: (v) => numero(v) } },
      dataZoom: compacto ? [] : [{ type: 'inside', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false, moveOnMouseMove: true }],
      tooltip: {
        trigger: 'axis',
        confine: true,
        formatter: (ps) => {
          const linhas = ps.map((p) => `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${p.color};margin-right:6px"></span>${esc(p.seriesName)} <b style="float:right;margin-left:14px">${numero(p.value)}</b>`)
          return [`<b>${ps[0].axisValue}</b>`, ...linhas, `<span style="opacity:.7">capacidade ${cap}</span>`].join('<br/>')
        },
      },
      series,
    }
  }, [t, pontos, pontosCom, cap, eventos, vista, compacto])

  return <Grafico opcao={opcao} altura={altura} rotulo="Curva de carga do dia contra a capacidade" />
}
