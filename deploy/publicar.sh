#!/usr/bin/env bash
# deploy/publicar.sh — publica o PicoZero (painel, API e LibreChat em /chat) no servidor do ERP da IBMEC Jr.
# Uso, na raiz do projeto:  ./deploy/publicar.sh
# Precisa da chave SSH do Lightsail (caminho em PICOZERO_SSH_KEY). As credenciais do backend/.env vão pelo
# próprio SSH direto para um arquivo 600 no servidor: nada passa por linha de comando, tela ou log.
set -euo pipefail
cd "$(dirname "$0")/.."

SERVIDOR="${PICOZERO_SERVIDOR:-ubuntu@56.125.204.35}"
CHAVE="${PICOZERO_SSH_KEY:-$HOME/my_folders/producao/orgs/ibmecjrsolucoes/erpnext/LightsailDefaultKey-sa-east-1 (2).pem}"
DESTINO=/home/ubuntu/picozero
# O painel mostra o botão "Abrir no LibreChat" quando esta variável existe no build.
export VITE_LIBRECHAT_URL="${VITE_LIBRECHAT_URL:-https://picozeroday.vercel.app/chat/}"
ssh_srv() { ssh -i "$CHAVE" -o BatchMode=yes -o ConnectTimeout=15 "$SERVIDOR" "$@"; }

echo "1/5 build do painel (botão do LibreChat: $VITE_LIBRECHAT_URL)"
[ -d frontend/node_modules ] || (cd frontend && npm ci --silent)
(cd frontend && npm run build >/dev/null)

echo "2/5 envio do código"
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude='__pycache__' -czf - \
  requirements.txt backend/picozero frontend/dist \
  deploy/compose.yaml deploy/Dockerfile deploy/Dockerfile.dockerignore deploy/nginx.conf deploy/librechat/librechat.yaml deploy/librechat/Dockerfile deploy/librechat/marca deploy/librechat/chat-entrar.html \
  | ssh_srv "mkdir -p $DESTINO && cd $DESTINO && rm -rf backend/picozero frontend/dist && tar --warning=no-unknown-keyword -xzf - && cp deploy/librechat/librechat.yaml deploy/librechat.yaml"

echo "3/5 envio das credenciais (backend/.env -> $DESTINO/deploy/picozero.env, modo 600)"
python3 deploy/env_servidor.py | ssh_srv "umask 077 && cat > $DESTINO/deploy/picozero.env && chmod 600 $DESTINO/deploy/picozero.env"

echo "3b/5 segredos do LibreChat (criados no servidor só se ainda não existirem)"
# O script vai pelo stdin do SSH: os segredos nascem no servidor (openssl) e vão direto para o arquivo 600,
# sem passar por argumento de comando, tela ou log. Se o arquivo já existe, não é tocado.
ssh_srv "bash -s" <<'REMOTO'
set -euo pipefail
cd /home/ubuntu/picozero/deploy
if [ -f librechat.env ]; then
  echo "librechat.env já existe: mantido"
else
  umask 077
  {
    echo "# librechat.env — gerado no servidor pelo deploy/publicar.sh; os segredos nunca saem daqui. Não vai para o Git."
    echo "CREDS_KEY=$(openssl rand -hex 32)"
    echo "CREDS_IV=$(openssl rand -hex 16)"
    echo "JWT_SECRET=$(openssl rand -hex 32)"
    echo "JWT_REFRESH_SECRET=$(openssl rand -hex 32)"
    echo "DOMAIN_CLIENT=https://picozeroday.vercel.app/chat"
    echo "DOMAIN_SERVER=https://picozeroday.vercel.app/chat"
    echo "APP_TITLE=PicoZero · Assistente"
    echo "ENDPOINTS=custom"
    echo "SEARCH=false"
    echo "ALLOW_EMAIL_LOGIN=true"
    echo "ALLOW_REGISTRATION=true"
    echo "ALLOW_SOCIAL_LOGIN=false"
    echo "ALLOW_UNVERIFIED_EMAIL_LOGIN=true"
    echo "NO_INDEX=true"
  } > librechat.env
  chmod 600 librechat.env
  echo "librechat.env criado (modo 600)"
fi
# Chat livre (sem senha): uma conta de convidado compartilhada por todos os visitantes.
umask 077
if [ ! -f convidado.env ]; then
  { echo "CONVIDADO_EMAIL=convidado@picozeroday.app"; echo "CONVIDADO_SENHA=$(openssl rand -hex 16)"; } > convidado.env
  echo "convidado.env criado (modo 600)"
fi
. ./convidado.env
# Conta compartilhada: cadastro fechado e sem limites por conta/IP que travariam todos juntos.
for par in ALLOW_REGISTRATION=false LOGIN_MAX=1000 LIMIT_CONCURRENT_MESSAGES=false LIMIT_MESSAGE_IP=false BAN_VIOLATIONS=false; do
  chave=${par%%=*}
  if grep -q "^$chave=" librechat.env; then sed -i "s|^$chave=.*|$par|" librechat.env; else echo "$par" >> librechat.env; fi
done
# Página que entra sozinha na conta de convidado. ">" reescreve no mesmo arquivo: o nginx continua com ele montado.
sed -e "s|__EMAIL__|$CONVIDADO_EMAIL|" -e "s|__SENHA__|$CONVIDADO_SENHA|" librechat/chat-entrar.html > chat-entrar.html
chmod 644 chat-entrar.html
REMOTO

echo "4/5 build e subida dos contêineres"
# O envio acima apaga e recria frontend/dist (e troca o nginx.conf): o nginx em execução ficaria com o diretório/arquivo
# antigos montados (403 ou configuração velha). Por isso o picozero-web é sempre recriado, para remontar o que acabou de subir.
ssh_srv "cd $DESTINO/deploy && sudo docker compose up -d --build --remove-orphans --wait && sudo docker compose up -d --force-recreate --no-deps --wait picozero-web"

echo "4b/5 contas do LibreChat (admin próprio e convidado do chat livre)"
ssh_srv "bash -s" <<'REMOTO'
set -euo pipefail
cd /home/ubuntu/picozero/deploy
. ./convidado.env
contar() { sudo docker exec picozero-librechat-mongo-1 mongosh LibreChat --quiet --eval "db.users.countDocuments($1)"; }
criar() { sudo docker exec picozero-librechat-1 npm run --silent create-user -- "$@" --email-verified=true >/dev/null; }
if [ "$(contar '{}')" = "0" ]; then
  # O primeiro usuário do LibreChat vira administrador: cria um admin próprio antes do convidado.
  umask 077
  SENHA_ADMIN=$(openssl rand -hex 16)
  printf 'LIBRECHAT_ADMIN_EMAIL=admin@picozeroday.app\nLIBRECHAT_ADMIN_SENHA=%s\n' "$SENHA_ADMIN" > librechat-admin.env
  criar admin@picozeroday.app "Administrador PicoZero" admin "$SENHA_ADMIN"
  echo "admin criado (senha só no servidor: $PWD/librechat-admin.env, modo 600)"
fi
if [ "$(contar "{email: '$CONVIDADO_EMAIL'}")" = "0" ]; then
  criar "$CONVIDADO_EMAIL" "Convidado PicoZero" convidado "$CONVIDADO_SENHA"
  echo "convidado criado"
fi
REMOTO

echo "5/5 conferência"
curl -fsS -m 30 https://picozeroday.vercel.app/api/saude | python3 -c "import sys, json; d = json.load(sys.stdin); print('API:', d['status'], '| IA:', d['ia']['modo'], '| chave configurada:', d['ia']['configurado'])"
curl -fsS -m 20 -o /dev/null -w "painel: HTTP %{http_code}\n" https://picozeroday.vercel.app/
curl -sS -m 30 -o /dev/null -w "LibreChat (/chat): HTTP %{http_code}\n" https://picozeroday.vercel.app/chat || true
curl -fsS -m 20 -o /dev/null https://erp.ibmecjr.com.br/api/method/ping && echo "ERP: respondendo normalmente"
echo "No ar: https://picozeroday.vercel.app e https://picozeroday.vercel.app/chat (proxy da Vercel para o servidor)"
