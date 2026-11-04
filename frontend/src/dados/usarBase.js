// frontend/src/dados/usarBase.js
// Dados-base de todas as telas (contexto, eventos, marcos, riscos e picos do semestre),
// carregados uma vez por unidade: da API do motor ou, sem ela, da prévia local.
import * as api from '../api/cliente'
import { usarApi } from '../api/usarApi'

async function carregarBase(unidade) {
  const rs = await Promise.all([api.contexto(unidade), api.eventos(unidade), api.marcos(unidade), api.riscos(unidade), api.picos(unidade)])
  const [contexto, eventos, marcos, riscos, picos] = rs.map((r) => r.dados)
  return { dados: { contexto, eventos, marcos, riscos, picos }, origem: rs.every((r) => r.origem === 'api') ? 'api' : 'previa' }
}

export function usarBase(unidade) {
  return usarApi(() => carregarBase(unidade), [unidade])
}

export function feriadosDe(contexto) {
  return Object.fromEntries((contexto?.feriados || []).map((f) => [f.data, f.nome]))
}

export function fimDeSemana(iso) {
  const d = new Date(`${iso}T12:00:00`).getDay()
  return d === 0 || d === 6
}
