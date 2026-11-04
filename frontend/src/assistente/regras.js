// frontend/src/assistente/regras.js
// Respostas locais do Assistente PicoZero quando /api/chat não responde (prévia estática, rede
// fora, timeout). Roteador por palavras-chave sobre dados/previa.js, no mesmo formato da resposta
// do backend ({ resposta, ferramentas, origem }). Os números saem das mesmas funções das telas.
import {
  CONTEXTO,
  DIAS_RISCO,
  EVENTOS,
  MARCOS,
  PLANOS,
  TENTATIVAS,
  curvaDoDia,
  picoDoDia,
  resumoLatencia,
} from '../dados/previa'

const ANO = 2026
const CAP = CONTEXTO.capacidade
const DIA_PLANO_PADRAO = '2026-09-10'
const NOMES_MES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
const MESES = NOMES_MES.map(normalizar)

// ---------- Texto e formatação ----------

export function normalizar(texto) {
  return String(texto ?? '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

const num = (n) => Number(n).toLocaleString('pt-BR')
const pct = (carga) => `${Math.round((carga / CAP) * 100).toLocaleString('pt-BR')}%`

function montarIso(a, m, d) {
  const dt = new Date(a, m - 1, d)
  if (dt.getFullYear() !== a || dt.getMonth() !== m - 1 || dt.getDate() !== d) return null
  return `${a}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

const isoDe = (dt) => montarIso(dt.getFullYear(), dt.getMonth() + 1, dt.getDate())

// DD/MM nas datas de 2026 (o painel transforma em link para o dia); ano explícito nas demais.
function rotulo(iso) {
  const [a, m, d] = iso.split('-')
  return Number(a) === ANO ? `${d}/${m}` : `${d}/${m}/${a}`
}

function diaSemana(iso, curto = false) {
  const [a, m, d] = iso.split('-').map(Number)
  const nome = new Date(a, m - 1, d).toLocaleDateString('pt-BR', { weekday: 'long' })
  return curto ? nome.replace('-feira', '') : nome
}

// '09:00' → '9h' · '23:45' → '23h45'
function hora(hhmm) {
  const [h, m] = hhmm.split(':')
  return `${Number(h)}h${m === '00' ? '' : m}`
}

function janela(ev) {
  if (ev.hora_inicio === '00:00' && ev.hora_fim === '23:59') return 'dia todo'
  return `${hora(ev.hora_inicio)}–${hora(ev.hora_fim)}`
}

function duracao(min) {
  const h = Math.floor(min / 60)
  const m = min % 60
  if (!h) return `${m} min`
  return m ? `${h}h${String(m).padStart(2, '0')}` : `${h}h`
}

function juntar(itens) {
  if (itens.length <= 1) return itens.join('')
  return `${itens.slice(0, -1).join(', ')} e ${itens[itens.length - 1]}`
}

const plural = (n, um, varios) => `${num(n)} ${n === 1 ? um : varios}`

function ferramenta(etapa, detalhe) {
  return { hora: new Date().toTimeString().slice(0, 8), etapa, detalhe, ferramenta: true, ok: true }
}

const comPico = (r) => ({ ...r, pico: picoDoDia(r.data) })
const porData = (a, b) => a.data.localeCompare(b.data)
const doMes = (mes) => (r) => Number(r.data.slice(5, 7)) === mes + 1
const dentroDoSemestre = (iso) => iso >= CONTEXTO.inicio && iso <= CONTEXTO.fim

// ---------- Entendendo a pergunta ----------

// '10/09', '10/09/2026', 'dia 12/11', '10 de setembro', 'hoje', 'amanhã'
function dataCitada(t, agora) {
  let m = t.match(/\b(\d{1,2})\/(\d{1,2})(?:\/(\d{4}|\d{2}))?\b/)
  if (m) {
    const ano = !m[3] ? ANO : m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3])
    return montarIso(ano, Number(m[2]), Number(m[1]))
  }
  m = t.match(new RegExp(`\\b(\\d{1,2})[oº°]? de (${MESES.join('|')})\\b`))
  if (m) return montarIso(ANO, MESES.indexOf(m[2]) + 1, Number(m[1]))
  if (/\bamanha\b/.test(t)) {
    const d = new Date(agora)
    d.setDate(d.getDate() + 1)
    return isoDe(d)
  }
  if (/\bhoje\b/.test(t)) return isoDe(agora)
  return null
}

function mesCitado(t) {
  return MESES.findIndex((nome) => new RegExp(`\\b${nome}\\b`).test(t))
}

const RE_PLANO = /\bplanos?\b|o que fazer|que (devo|devemos|posso|podemos) fazer|\bacoes\b|\bevitar\b|\bprevenir\b/
const RE_FILA = /\bfila|latencia|prova de carga|\bp95\b|\bp50\b|\b503\b|lentid|tempo de resposta/
const RE_PIOR = /\bpior|maior pico|mais critic|mais cheio|mais pesado|mais carregado|maior carga|pico do semestre/
const RE_LISTA = /critic|risco|\bproxim|\balerta/
const RE_PROXIMOS = /\bproxim|\bseguinte|\bfutur|\bdaqui|a seguir|\bvem\b/
const RE_CAPACIDADE = /capacidade|\blimite\b|suporta|aguenta/
const RE_FONTE = /\breal\b|\breais\b|modelad|\bdados\b|\bfontes?\b|historico|simulad|inventad|confiav|verdadeir/
const RE_SAUDACAO = /^(oi|ola|bom dia|boa tarde|boa noite|e ai|hey|hello|tudo bem)\b/

/**
 * Responde uma pergunta com os dados da prévia, sem backend.
 * @param {string} texto pergunta do usuário
 * @param {{agora?: Date, unidade?: string}} [opcoes] agora = referência de "hoje"/"próximos"; unidade do seletor
 * @returns {{resposta: string, ferramentas: object[], origem: 'previa', modelo: null}}
 */
export function responderLocal(texto, { agora = new Date(), unidade = 'rj' } = {}) {
  const t = normalizar(texto)
  const data = dataCitada(t, agora)
  const mes = data ? -1 : mesCitado(t)
  let r
  if (RE_PLANO.test(t)) r = plano(data || DIA_PLANO_PADRAO)
  else if (RE_FILA.test(t)) r = latencia()
  else if (!data && RE_PIOR.test(t)) r = piorDia(mes)
  else if (!data && RE_LISTA.test(t)) r = diasCriticos({ proximos: RE_PROXIMOS.test(t), mes, agora })
  else if (data) r = dia(data)
  else if (mes >= 0) r = diasCriticos({ proximos: false, mes, agora })
  else if (RE_CAPACIDADE.test(t)) r = capacidade()
  else if (RE_FONTE.test(t)) r = fonteDados()
  else if (RE_SAUDACAO.test(t)) r = ajuda(true)
  else r = semResposta(agora)
  // Só o RJ está modelado na prévia: em outra unidade, diz de onde vêm os números.
  const sigla = String(unidade || 'rj').toUpperCase()
  const nota = sigla !== 'RJ'
    ? `A prévia local só tem o Ibmec RJ modelado; os números abaixo são do RJ. Com o backend conectado, a resposta sai para o Ibmec ${sigla}.\n\n`
    : ''
  return { resposta: nota + r.resposta, ferramentas: r.ferramentas, origem: 'previa', modelo: null }
}

// ---------- Respostas ----------

function piorDia(mes) {
  const base = mes >= 0 ? DIAS_RISCO.filter(doMes(mes)) : DIAS_RISCO
  const ranking = base.map(comPico).sort((a, b) => b.pico.carga - a.pico.carga)
  const ferramentas = [
    ferramenta('previa.dias_risco', `${plural(base.length, 'dia', 'dias')}${mes >= 0 ? ` em ${NOMES_MES[mes]}` : ''}`),
    ferramenta('previa.pico_do_dia', plural(ranking.length, 'curva calculada', 'curvas calculadas')),
  ]
  if (!ranking.length) {
    return { resposta: `Nenhum dia de risco em ${NOMES_MES[mes]} na análise do semestre ${CONTEXTO.semestre}.`, ferramentas }
  }
  const [topo, segundo] = ranking
  const evs = EVENTOS.filter((e) => e.data === topo.data)
  const linhas = [
    `O pior dia ${mes >= 0 ? `de ${NOMES_MES[mes]}` : 'do semestre'} é **${rotulo(topo.data)}, ${diaSemana(topo.data)}**: ` +
      `pico de **${num(topo.pico.carga)} acessos simultâneos às ${hora(topo.pico.hora)}**, ${pct(topo.pico.carga)} da capacidade de ${num(CAP)}.`,
    '',
    'Eventos do dia:',
    ...(evs.length ? evs.map((e) => `- ${janela(e)} · ${e.descricao}`) : topo.eventos.map((e) => `- ${e}`)),
    '',
    `Gravidade ${topo.gravidade} de 5 na análise do Gemini.` +
      (segundo
        ? ` Em seguida vem ${rotulo(segundo.data)}, com pico de ${num(segundo.pico.carga)} às ${hora(segundo.pico.hora)} (${pct(segundo.pico.carga)}).`
        : ''),
  ]
  return { resposta: linhas.join('\n'), ferramentas }
}

function diasCriticos({ proximos, mes, agora }) {
  const hoje = isoDe(agora)
  let dias = DIAS_RISCO.map(comPico).sort(porData)
  if (mes >= 0) dias = dias.filter(doMes(mes))
  if (proximos) dias = dias.filter((r) => r.data >= hoje)
  const filtros = [proximos && `a partir de ${rotulo(hoje)}`, mes >= 0 && NOMES_MES[mes]].filter(Boolean)
  const ferramentas = [
    ferramenta('previa.dias_risco', [plural(DIAS_RISCO.length, 'dia', 'dias'), ...filtros].join(' · ')),
    ferramenta('previa.pico_do_dia', plural(dias.length, 'curva calculada', 'curvas calculadas')),
  ]
  const onde = mes >= 0 ? ` em ${NOMES_MES[mes]}` : ''
  if (!dias.length) {
    return {
      resposta: proximos
        ? `Não há mais dias críticos${onde} pela frente no semestre ${CONTEXTO.semestre}.`
        : `Nenhum dia crítico${onde} no semestre ${CONTEXTO.semestre}.`,
      ferramentas,
    }
  }
  const acima = dias.filter((r) => r.pico.carga > CAP).length
  const titulo = proximos
    ? `Próximos dias críticos${onde}, a partir de hoje (${rotulo(hoje)}):`
    : `Dias críticos${mes >= 0 ? ` de ${NOMES_MES[mes]}` : ` do semestre ${CONTEXTO.semestre}`}, por data:`
  const linhas = [
    titulo,
    ...dias.map(
      (r) =>
        `- **${rotulo(r.data)}** (${diaSemana(r.data, true)}): pico de ${num(r.pico.carga)} às ${hora(r.pico.hora)}, ` +
        `${pct(r.pico.carga)} da capacidade${r.pico.carga > CAP ? ' · **acima da capacidade**' : ''}${PLANOS[r.data] ? ' · com plano' : ''}`,
    ),
    '',
    acima
      ? `${acima} de ${dias.length} ${acima === 1 ? 'passa' : 'passam'} da capacidade de ${num(CAP)} acessos simultâneos.`
      : `Nenhum passa da capacidade de ${num(CAP)} acessos simultâneos.`,
  ]
  return { resposta: linhas.join('\n'), ferramentas }
}

function dia(d) {
  if (!dentroDoSemestre(d)) {
    return {
      resposta: `${rotulo(d)} fica fora do semestre ${CONTEXTO.semestre} (${rotulo(CONTEXTO.inicio)} a ${rotulo(CONTEXTO.fim)}). A prévia só cobre esse período.`,
      ferramentas: [ferramenta('previa.contexto', `semestre ${CONTEXTO.semestre}: ${CONTEXTO.inicio} a ${CONTEXTO.fim}`)],
    }
  }
  const evs = EVENTOS.filter((e) => e.data === d)
  const feriado = CONTEXTO.feriados.find((f) => f.data === d)
  const periodos = MARCOS.filter((m) => m.inicio <= d && d <= m.fim)
  const curva = curvaDoDia(d)
  const pico = curva.reduce((a, b) => (b.carga > a.carga ? b : a))
  const minutosAcima = curva.filter((p) => p.carga > CAP).length * 15
  const risco = DIAS_RISCO.find((r) => r.data === d)

  const linhas = [`**${rotulo(d)}, ${diaSemana(d)}**${feriado ? ` · feriado (${feriado.nome})` : ''}`, '']
  if (evs.length) {
    linhas.push(
      'Eventos do calendário:',
      ...evs.map((e) => `- ${janela(e)} · ${e.descricao}${e.turmas.length ? ` (${e.turmas.length} turmas)` : ''}`),
    )
  } else {
    linhas.push('Nenhum evento do calendário neste dia.')
  }
  if (periodos.length) {
    linhas.push('', `Dentro do período: ${juntar(periodos.map((p) => `${p.nome} (${rotulo(p.inicio)} a ${rotulo(p.fim)})`))}.`)
  }
  linhas.push(
    '',
    `Pico previsto: **${num(pico.carga)} acessos simultâneos às ${hora(pico.hora)}**, ${pct(pico.carga)} da capacidade de ${num(CAP)}.` +
      (minutosAcima ? ` Fica acima da capacidade por cerca de ${duracao(minutosAcima)} no total.` : ''),
  )
  if (risco) linhas.push('', `Dia crítico, gravidade ${risco.gravidade} de 5. Motivo apontado pelo Gemini: ${risco.motivo}`)
  if (PLANOS[d]) linhas.push('', `Há um plano validado para este dia. Pergunte "o que fazer em ${rotulo(d)}?".`)
  else if (risco) linhas.push('', 'Ainda não há plano gerado para este dia na prévia.')

  const ferramentas = [
    ferramenta('previa.eventos', `${rotulo(d)} → ${plural(evs.length, 'evento', 'eventos')}`),
    ferramenta('previa.curva_do_dia', `pico ${num(pico.carga)} às ${pico.hora}`),
  ]
  if (risco) ferramentas.push(ferramenta('previa.dias_risco', `gravidade ${risco.gravidade}`))
  if (PLANOS[d]) ferramentas.push(ferramenta('previa.planos', 'plano validado'))
  return { resposta: linhas.join('\n'), ferramentas }
}

function plano(d) {
  const p = PLANOS[d]
  if (!p) return semPlano(d)
  const tentativas = TENTATIVAS[d] || []
  const aprovada = tentativas.find((x) => x.ok)
  const recalculo = aprovada?.checagens?.find((c) => /^pico recalculado/i.test(c))
  const pico = picoDoDia(d)
  const itens = (lista = []) => lista.map((i) => `- ${i.titulo}`)
  const acoes = (p.calendario?.length || 0) + (p.comunicacao?.length || 0) + (p.infra_checklist?.length || 0)

  const linhas = [
    `**Plano para ${rotulo(d)}, ${diaSemana(d)}**`,
    '',
    `Sem plano, o pico previsto é de ${num(pico.carga)} acessos simultâneos às ${hora(pico.hora)} (${pct(pico.carga)} da capacidade).` +
      (aprovada
        ? ` O motor aprovou o plano na tentativa ${aprovada.numero} de ${tentativas.length}` +
          (recalculo ? `: ${recalculo.charAt(0).toLowerCase()}${recalculo.slice(1)}.` : '.')
        : ''),
    '',
    '**Calendário**',
    ...itens(p.calendario),
    '',
    '**Comunicação**',
    ...itens(p.comunicacao),
    '',
    '**Infraestrutura**',
    ...itens(p.infra_checklist),
    '',
    'O detalhe de cada ação está na tela Plano do dia.',
  ]
  const ferramentas = [
    ferramenta('previa.planos', `${rotulo(d)} → ${plural(acoes, 'ação', 'ações')} em 3 níveis`),
    ferramenta('previa.pico_do_dia', `${rotulo(d)} → ${num(pico.carga)} às ${pico.hora}`),
  ]
  if (tentativas.length) {
    ferramentas.push(
      ferramenta('previa.tentativas', `${plural(tentativas.length, 'tentativa', 'tentativas')}${aprovada ? ` · aprovada na ${aprovada.numero}ª` : ' · nenhuma aprovada'}`),
    )
  }
  return { resposta: linhas.join('\n'), ferramentas }
}

function semPlano(d) {
  const comPlano = Object.keys(PLANOS).sort()
  const linhas = [`Ainda não há plano gerado para ${rotulo(d)} na prévia.`]
  const ferramentas = [ferramenta('previa.planos', `nenhum plano para ${rotulo(d)}`)]
  if (dentroDoSemestre(d)) {
    const pico = picoDoDia(d)
    const risco = DIAS_RISCO.find((r) => r.data === d)
    ferramentas.push(ferramenta('previa.pico_do_dia', `${rotulo(d)} → ${num(pico.carga)} às ${pico.hora}`))
    linhas.push(
      `O pico previsto é de ${num(pico.carga)} acessos simultâneos às ${hora(pico.hora)} (${pct(pico.carga)} da capacidade)` +
        (risco ? `, e o dia está na lista de risco com gravidade ${risco.gravidade} de 5.` : pico.carga <= CAP ? ', dentro da capacidade.' : '.'),
    )
  }
  if (comPlano.length) {
    linhas.push('', `Na prévia, o plano validado é o de ${juntar(comPlano.map(rotulo))}. Pergunte "o que fazer em ${rotulo(comPlano[0])}?" para ver as ações.`)
  }
  return { resposta: linhas.join('\n'), ferramentas }
}

function latencia() {
  const resumo = Object.fromEntries(resumoLatencia().map((r) => [r.chave, r]))
  const { antes, depois, controle } = resumo
  const diaPico = antes.sub.split(' · ')[0]
  const queda = Math.round((1 - depois.p95 / antes.p95) * 100)
  const taxa = (x) => `${(x * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
  const linha = (r) =>
    `- **${r.nome}** (${r.sub}): p95 de ${num(r.p95)} ms, p50 de ${num(r.p50)} ms${r.erros ? `, ${taxa(r.erros)} de erros 503 no pico` : ', sem 503'}`
  const linhas = [
    `Na prova de carga com o perfil de ${diaPico}, o plano com a fila virtual levou o p95 de **${num(antes.p95)} ms para ${num(depois.p95)} ms** (${queda}% menor). ` +
      `Os erros 503 no pico caíram de **${taxa(antes.erros)} para ${taxa(depois.erros)}**.`,
    '',
    linha(antes),
    linha(depois),
    linha(controle),
    '',
    `A fila segura o login na capacidade de ${num(CAP)} acessos simultâneos: quem entra é atendido rápido, em vez de todos ficarem lentos ao mesmo tempo. ` +
      'São números da simulação da prévia, sobre o histórico modelado.',
  ]
  return {
    resposta: linhas.join('\n'),
    ferramentas: [ferramenta('previa.resumo_latencia', `p95 ${num(antes.p95)} → ${num(depois.p95)} ms · controle ${num(controle.p95)} ms`)],
  }
}

function capacidade() {
  const acima = DIAS_RISCO.map(comPico).filter((r) => r.pico.carga > CAP).sort(porData)
  const linhas = [
    `A capacidade de referência do portal do aluno é de **${num(CAP)} acessos simultâneos**, para ${num(CONTEXTO.alunos)} alunos do ${CONTEXTO.instituicao}. ` +
      'Acima disso a latência cresce rápido e, nos picos maiores, aparecem erros 503.',
  ]
  if (acima.length) {
    linhas.push(
      '',
      `${acima.length} dos ${DIAS_RISCO.length} dias críticos de ${CONTEXTO.semestre} passam desse limite: ` +
        `${juntar(acima.map((r) => `${rotulo(r.data)} (${pct(r.pico.carga)})`))}.`,
    )
  }
  return {
    resposta: linhas.join('\n'),
    ferramentas: [
      ferramenta('previa.contexto', `capacidade ${num(CAP)} · ${num(CONTEXTO.alunos)} alunos`),
      ferramenta('previa.pico_do_dia', plural(DIAS_RISCO.length, 'dia de risco', 'dias de risco')),
    ],
  }
}

function fonteDados() {
  const linhas = [
    'Parte é real e parte é modelada:',
    `- **Real:** o calendário acadêmico oficial do ${CONTEXTO.instituicao} ${CONTEXTO.semestre}: feriados, AP1, AP2 e AS, Teste de Progresso, rematrícula e vencimentos (sempre no dia 10).`,
    '- **Modelado:** o histórico de acessos e as curvas de carga. Os picos são estimativas do motor do PicoZero, não medições do portal.',
    '',
    'Esta resposta veio da prévia local, sem backend. A tela Fonte de dados mostra cada origem em detalhe.',
  ]
  return {
    resposta: linhas.join('\n'),
    ferramentas: [
      ferramenta('previa.contexto', `${plural(EVENTOS.length, 'evento', 'eventos')} · ${plural(CONTEXTO.feriados.length, 'feriado', 'feriados')} · ${plural(MARCOS.length, 'período', 'períodos')}`),
    ],
  }
}

// Pergunta fora do roteiro: nunca volta sem dados. Mostra os dias críticos do semestre e o que dá para perguntar.
function semResposta(agora) {
  const base = diasCriticos({ proximos: false, mes: -1, agora })
  const sugestoes = ajuda(false).resposta.split('\n').slice(1)
  return {
    resposta: [
      'Não achei uma resposta exata para isso na prévia local (sem backend). Estes são os dias críticos do semestre:',
      '',
      base.resposta,
      '',
      'Também posso dizer:',
      ...sugestoes,
    ].join('\n'),
    ferramentas: base.ferramentas,
  }
}

function ajuda(saudacao) {
  const linhas = [
    saudacao
      ? `Olá! Sem backend, eu respondo com os dados da prévia do ${CONTEXTO.instituicao} ${CONTEXTO.semestre}. Pergunte, por exemplo:`
      : 'Não sei responder isso na prévia local (sem backend). Por aqui eu consigo dizer:',
    '- qual é o pior dia do semestre',
    '- quais são os dias críticos, todos ou só os próximos',
    '- como fica um dia específico, como 10/09 ou 12 de novembro',
    '- o que fazer em um dia: "o que fazer em 10/09?"',
    '- quanto a fila virtual reduz a latência',
    '- qual é a capacidade do portal e de onde vêm os dados',
  ]
  return { resposta: linhas.join('\n'), ferramentas: [] }
}
