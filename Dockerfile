# ---- frontend: builds web/dist ------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- app: FastAPI + image engine (diffusers, CUDA) -----------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data
WORKDIR /app

# PyTorch with CUDA 12.8 (ships its own CUDA libraries; the host driver is enough)
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY main.py ./
COPY app/ app/
COPY --from=web /web/dist web/dist

EXPOSE 8765
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8765"]
