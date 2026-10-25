# ---- frontend: compila web/dist ------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- app: FastAPI + motor de imagen (diffusers, CUDA) -----------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/cache/huggingface \
    U2NET_HOME=/cache/u2net \
    MODELS_DIR=/models
WORKDIR /app

# PyTorch con CUDA 12.8 (trae sus propias librerías CUDA; basta el driver del host)
RUN pip install torch --index-url https://download.pytorch.org/whl/cu128
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY main.py ./
COPY app/ app/
COPY referencias/ referencias/
COPY --from=web /web/dist web/dist

EXPOSE 8765
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8765"]
