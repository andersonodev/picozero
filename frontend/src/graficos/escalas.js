// frontend/src/graficos/escalas.js
// Escalas de cor compartilhadas pelos gráficos (níveis do motor e % da capacidade).

export const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

// Nível do motor (ok | alerta | serio | critico) → cor concreta do tema.
export function corDoNivel(t, nivel) {
  return { ok: t.folga, alerta: t.atencao, serio: t.alto, critico: t.critico }[nivel] || t.folga
}

// Faixas do mapa de calor em % da capacidade (visualMap piecewise).
export function faixasDeCalor(t) {
  return [
    { lt: 20, color: t.calor[0] },
    { gte: 20, lt: 40, color: t.calor[1] },
    { gte: 40, lt: 60, color: t.calor[2] },
    { gte: 60, lt: 85, color: t.atencao },
    { gte: 85, lte: 100, color: t.alto },
    { gt: 100, color: t.critico },
  ]
}

export const LEGENDA_CALOR = [
  ['calor0', '< 20%'],
  ['calor2', '20–60%'],
  ['atencao', '60–85%'],
  ['alto', '85–100%'],
  ['critico', '> 100%'],
]

// Hora 'HH:MM' arredondada para baixo na janela de 15 min ('23:59' → '23:45').
export function janela15(hhmm) {
  const [h, m] = hhmm.split(':').map(Number)
  return `${String(h).padStart(2, '0')}:${String(Math.floor(m / 15) * 15).padStart(2, '0')}`
}
