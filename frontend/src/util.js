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

// Rótulos curtos para caber nas células do calendário e nas tabelas.
// Só apresentação: descrição desconhecida (ex.: vinda da API) aparece inteira.
const CURTOS = {
  'Início do período letivo (veteranos)': 'Início das aulas (veteranos)',
  'Início do período letivo (calouros)': 'Início das aulas (calouros)',
  'Vencimento da 2ª parcela da semestralidade': 'Vencimento 2ª parcela',
  'Vencimento da 3ª parcela da semestralidade': 'Vencimento 3ª parcela',
  'Vencimento da 4ª parcela (10/10 cai no sábado)': 'Vencimento 4ª parcela',
  'Vencimento da 5ª parcela da semestralidade': 'Vencimento 5ª parcela',
  'Aplicação do Teste de Progresso': 'Teste de Progresso',
  'Divulgação de notas da Avaliação Contínua (AC)': 'Notas da AC',
  'Prazo final de notas da Avaliação Contínua (AC)': 'Prazo de notas da AC',
  'Fim da renovação de matrícula online 2026.2': 'Fim da rematrícula',
  'Fim dos prazos de ajuste de disciplinas pelo portal': 'Fim dos ajustes de disciplina',
  'AP1 online · início do período': 'AP1 online',
  'Abertura da AP2 online': 'Abertura da AP2 online',
  'Divulgação de notas das Avaliações Parciais AP1': 'Notas da AP1',
  'Divulgação de notas finais (AS e Teste de Progresso)': 'Notas finais',
  'Conclusão do período letivo 2026.2': 'Fim do período letivo',
}

export function rotuloCurto(descricao) {
  return CURTOS[descricao] || descricao
}

export function capitalizar(texto) {
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}
