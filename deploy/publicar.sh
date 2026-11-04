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
  deploy/compose.yaml deploy/Dockerfile deploy/Dockerfile.dockerignore deploy/nginx.conf deploy/librechat/librechat.yaml deploy/librechat/Dockerfile deploy/librechat/marca \
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
REMOTO

echo "4/5 build e subida dos contêineres"
# O envio acima apaga e recria frontend/dist (e troca o nginx.conf): o nginx em execução ficaria com o diretório/arquivo
# antigos montados (403 ou configuração velha). Por isso o picozero-web é sempre recriado, para remontar o que acabou de subir.
ssh_srv "cd $DESTINO/deploy && sudo docker compose up -d --build --remove-orphans --wait && sudo docker compose up -d --force-recreate --no-deps --wait picozero-web"

echo "5/5 conferência"
curl -fsS -m 30 https://picozeroday.vercel.app/api/saude | python3 -c "import sys, json; d = json.load(sys.stdin); print('API:', d['status'], '| IA:', d['ia']['modo'], '| chave configurada:', d['ia']['configurado'])"
curl -fsS -m 20 -o /dev/null -w "painel: HTTP %{http_code}\n" https://picozeroday.vercel.app/
curl -sS -m 30 -o /dev/null -w "LibreChat (/chat): HTTP %{http_code}\n" https://picozeroday.vercel.app/chat || true
curl -fsS -m 20 -o /dev/null https://erp.ibmecjr.com.br/api/method/ping && echo "ERP: respondendo normalmente"
echo "No ar: https://picozeroday.vercel.app e https://picozeroday.vercel.app/chat (proxy da Vercel para o servidor)"
