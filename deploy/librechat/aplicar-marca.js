// deploy/librechat/aplicar-marca.js — roda no build da imagem (deploy/librechat/Dockerfile) e tira o nome
// LibreChat do cliente já compilado: título, descrição, app instalável, rodapé padrão e textos das traduções
// passam a dizer PicoZero, e o logo e os ícones vêm de marca/.
// O servidor entrega cópias pré-comprimidas (.gz/.br) e o service worker guarda os arquivos em cache: cada
// arquivo alterado ganha cópias comprimidas novas e revisão nova no sw.js, senão o navegador seguiria com o antigo.
const fs = require('fs')
const path = require('path')
const zlib = require('zlib')
const crypto = require('crypto')

const DIST = '/app/client/dist'
const MARCA = '/tmp/marca'
const NOME = 'PicoZero'
const TITULO = 'PicoZero · Assistente'
const DESCRICAO = 'Assistente do PicoZero: previsão dos picos de acesso do portal do aluno.'
const alterados = new Set()

const ler = (rel) => fs.readFileSync(path.join(DIST, rel))

function gravar(rel, conteudo) {
  const arq = path.join(DIST, rel)
  const novo = Buffer.isBuffer(conteudo) ? conteudo : Buffer.from(conteudo, 'utf8')
  if (fs.existsSync(arq) && fs.readFileSync(arq).equals(novo)) return
  fs.writeFileSync(arq, novo)
  alterados.add(rel)
}

function comprimir(rel) {
  const arq = path.join(DIST, rel)
  const conteudo = fs.readFileSync(arq)
  if (fs.existsSync(`${arq}.gz`)) fs.writeFileSync(`${arq}.gz`, zlib.gzipSync(conteudo, { level: 9 }))
  if (fs.existsSync(`${arq}.br`)) {
    const params = { [zlib.constants.BROTLI_PARAM_QUALITY]: 9 }
    fs.writeFileSync(`${arq}.br`, zlib.brotliCompressSync(conteudo, { params }))
  }
}

// Logo e ícones do PicoZero no lugar dos originais.
for (const f of fs.readdirSync(MARCA)) gravar(`assets/${f}`, fs.readFileSync(path.join(MARCA, f)))

// Título e descrição da página: aparecem antes do app carregar e na prévia do link em apps de mensagem.
gravar(
  'index.html',
  ler('index.html')
    .toString('utf8')
    .replace(/<title>[^<]*<\/title>/, `<title>${TITULO}</title>`)
    .replace(/(name="description"\s+content=")[^"]*"/, `$1${DESCRICAO}"`),
)

// App instalável (PWA): nome e cores do PicoZero.
const manifesto = JSON.parse(ler('manifest.webmanifest'))
Object.assign(manifesto, {
  name: TITULO,
  short_name: NOME,
  description: DESCRICAO,
  lang: 'pt-BR',
  theme_color: '#12284C',
  background_color: '#0C1B33',
})
gravar('manifest.webmanifest', JSON.stringify(manifesto))

// Código e traduções: o rodapé padrão ("LibreChat vX - Toda IA para Todos") fica vazio e o nome vira PicoZero.
// Nas traduções (locale-*.js, só texto) troca tudo, inclusive "LibreChat-Instanz". No código, nome colado em
// hífen, barra ou ponto fica como está: é protocolo (o cabeçalho X-LibreChat-Generation-Protocol), não texto.
const RODAPE = /`\[LibreChat `\+[\w$.]+\+`\]\(https:\/\/librechat\.ai\) - `\+[\w$]+\(`com_ui_latest_footer`\)/g
let rodapes = 0
for (const f of fs.readdirSync(path.join(DIST, 'assets'))) {
  if (!f.endsWith('.js')) continue
  const rel = `assets/${f}`
  const js = ler(rel).toString('utf8')
  const nome = f.startsWith('locale-') ? /LibreChat/g : /(?<![-\w/.$])LibreChat(?![-\w])/g
  const novo = js
    .replace(RODAPE, () => {
      rodapes++
      return '``'
    })
    .replace(nome, NOME)
  gravar(rel, novo)
}
if (!rodapes) console.warn('aviso: rodapé padrão não encontrado; o CUSTOM_FOOTER vazio do librechat.env ainda o esconde')

// Cópias pré-comprimidas e revisões do service worker dos arquivos alterados.
let sw = ler('sw.js').toString('utf8')
let revisoes = 0
for (const rel of alterados) {
  comprimir(rel)
  const md5 = crypto.createHash('md5').update(ler(rel)).digest('hex')
  const url = rel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  sw = sw.replace(new RegExp(`(\\{url:"${url}",revision:)(?:null|"[0-9a-f]*")\\}`), (_, inicio) => {
    revisoes++
    return `${inicio}"${md5}"}`
  })
}
fs.writeFileSync(path.join(DIST, 'sw.js'), sw)
comprimir('sw.js')

console.log(`marca do PicoZero: ${alterados.size} arquivos alterados, ${rodapes} rodapé(s) removido(s), ${revisoes} revisões no service worker`)
