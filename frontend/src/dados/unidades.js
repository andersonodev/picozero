// frontend/src/dados/unidades.js
// Estrutura regional do edital (RJ, SP, BH, DF). Serve à história de escala/white-label:
// a mesma solução roda em qualquer unidade trocando só estes números.
// Capacidades são ilustrativas; só o Rio está totalmente modelado em previa.js.
export const UNIDADES = [
  { id: 'rj', nome: 'Rio de Janeiro · Barra', curto: 'RJ', alunos: 8000, capacidade: 500, modelada: true },
  { id: 'sp', nome: 'São Paulo', curto: 'SP', alunos: 6500, capacidade: 420, modelada: false },
  { id: 'bh', nome: 'Belo Horizonte', curto: 'BH', alunos: 4000, capacidade: 300, modelada: false },
  { id: 'df', nome: 'Brasília', curto: 'DF', alunos: 2500, capacidade: 200, modelada: false },
]

export const UNIDADE_PADRAO = UNIDADES[0]

export function unidadePorId(id) {
  return UNIDADES.find((u) => u.id === id) || UNIDADE_PADRAO
}
