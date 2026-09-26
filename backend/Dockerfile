# Agent-Tutor backend — FastAPI + worker LiveKit
# Image unique : Render lance soit le serveur web, soit le worker LiveKit
# selon la commande du service ( voir render.yaml ).
#
# Base : slim pour réduire la taille. Les wheels de torch/onnxruntime
# ( dépendances de livekit-plugins-silero ) existent pour linux/x86_64.
#
# MCP ( §39–§41 ) : l'image embarque la couche Model Context Protocol
# ( mcp + langchain-mcp-adapters ) et le backend Google Calendar. Les
# SECRETS OAuth ( client_secret.json / token.json ) ne sont jamais dans
# l'image : ils viennent d'un volume persistant monté sur
# /app/data/mcp/google ( cf. .gitignore + .env.example ).

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
# ffmpeg : VideoSubgraph — faster-whisper décode l'audio du conteneur
# vidéo (MP4…) via libav/ffmpeg. Sans ffmpeg dans le PATH, toute
# ingestion vidéo lève "tuple index out of range" ( decode ) au lieu de
# transcrire — d'où la transcription désactivée de fait en production.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    ca-certificates \
    ffmpeg \
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

# Racine des données — créée à l'exécution ( pas de COPY : data/ est
# local et absent d'un checkout propre ; les backends le recréent ).
#  - data/mcp/calendar.json   : agenda mock ( fallback sans GCP )
#  - data/mcp/google/         : SECRETS OAuth — monter un VOLUME
#                               persistant Render dessus, sinon le
#                               consentement est perdu à chaque restart
#                               ( le token.json est éphémère sans volume )
#  - data/workspace/files/    : sandbox filesystem MCP
RUN mkdir -p /app/data/mcp/google /app/data/workspace/files

# Render injecte PORT. uvicorn doit écouter sur 0.0.0.0:$PORT.
ENV PORT=8000 \
    MCP_CALENDAR_STORE=/app/data/mcp/calendar.json \
    GOOGLE_CALENDAR_CREDENTIALS=/app/data/mcp/google/client_secret.json \
    GOOGLE_CALENDAR_TOKEN=/app/data/mcp/google/token.json
EXPOSE 8000

# Healthcheck : l'endpoint /api/health répond 200 quand l'API est prête.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

# Une seule image, deux rôles :
#   - RUN_AS_WORKER=1 → worker LiveKit ( connexion persistante,
#     aucun port web — Render le voit comme un service inactif,
#     c'est normal et voulu ) ;
#   - sinon → serveur web FastAPI ( port $PORT ).
# Le shell form permet l'expansion de $RUN_AS_WORKER et $PORT.
CMD if [ "$RUN_AS_WORKER" = "1" ]; then \
        exec python -m app.infrastructure.livekit.agent start; \
    else \
        exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}; \
    fi
