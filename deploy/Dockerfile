# deploy/Dockerfile — imagem da API do PicoZero (FastAPI) para o servidor do ERP da IBMEC Jr.
# Contexto do build: a raiz do projeto (requirements.txt + backend/picozero).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
# uvicorn fica fora do requirements.txt (lá é a lista da função da Vercel); mesma versão do backend/uv.lock.
RUN pip install -r requirements.txt uvicorn==0.54.0

COPY backend/picozero ./picozero

EXPOSE 8000
CMD ["uvicorn", "picozero.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
