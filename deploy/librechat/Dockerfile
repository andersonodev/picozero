# deploy/librechat/Dockerfile — LibreChat oficial com a marca do PicoZero: logo e ícones de marca/ e o nome
# trocado no cliente compilado (aplicar-marca.js), sem rodapé nem título do LibreChat.
FROM registry.librechat.ai/librechat-ai/librechat-dev:latest
COPY --chown=node:node marca/ /tmp/marca/
COPY --chown=node:node aplicar-marca.js /tmp/aplicar-marca.js
RUN node /tmp/aplicar-marca.js && rm -rf /tmp/marca /tmp/aplicar-marca.js
