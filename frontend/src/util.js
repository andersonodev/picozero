// frontend/src/util.js
// Datas sempre como 'AAAA-MM-DD' (igual ao backend), convertidas para data local.

export function paraData(iso) {
  const [a, m, d] = iso.split('-').map(Number)
  return new Date(a, m - 1, d)
}

export function paraIso(data) {
  const a = data.getFullYear()
  const m = String(data.getMonth() + 1).padStart(2, '0')
  const d = String(data.getDate()).padStart(2, '0')
  return `${a}-${m}-${d}`
}

export function curta(iso) {
  const [, m, d] = iso.split('-')
  return `${d}/${m}`
}

export function completa(iso) {
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

export function semana(iso) {
  return paraData(iso).toLocaleDateString('pt-BR', { weekday: 'long' })
}

export function longa(iso) {
  const texto = paraData(iso).toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

export function mesNome(iso) {
  return paraData(iso).toLocaleDateString('pt-BR', { month: 'long' })
}

export function numero(n) {
  return n.toLocaleString('pt-BR')
}

export function diasEntre(inicio, fim) {
  const dias = []
  const atual = paraData(inicio)
  const ultimo = paraData(fim)
  while (atual <= ultimo) {
    dias.push(paraIso(atual))
    atual.setDate(atual.getDate() + 1)
  }
  return dias
}
