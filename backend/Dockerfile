# Agent-Tutor backend — FastAPI + worker LiveKit
# Image unique : Render lance soit le serveur web, soit le worker LiveKit
# selon la commande du service ( voir render.yaml ).
#
# Base : slim pour réduire la taille. Les wheels de torch/onnxruntime
# ( dépendances de livekit-plugins-silero ) existent pour linux/x86_64.

FROM python:3.11-slim AS builder

# Dépendances système pour la compilation des wheels manquantes et
# pour pymupdf / cryptography.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copie d'abord les dépendances : cache Docker préservé tant que
# requirements.txt ne change pas.
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ------------------------------------------------------------------
# Runtime
# ------------------------------------------------------------------
FROM python:3.11-slim

# libssl nécessaire aux wheels cryptography / aiohttp déjà compilés.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances Python installées en --user dans le builder.
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Code applicatif.
COPY app ./app
COPY langgraph.json .

# Render injecte PORT. uvicorn doit écouter sur 0.0.0.0:$PORT.
ENV PORT=8000
EXPOSE 8000

# Healthcheck : l'endpoint /api/health répond 200 quand l'API est prête.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

# Par défaut : le serveur web. Le worker LiveKit surcharge la commande
# ( voir render.yaml ) avec : python -m app.infrastructure.livekit.agent start
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
