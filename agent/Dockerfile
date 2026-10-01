# Image de l'agent tuteur vocal — déploiement NATIF LiveKit Cloud.
#
# CONTEXTE DE BUILD = CE DOSSIER (`agent/`), pas la racine du dépôt :
#     cd C:\Users\hp\Desktop\langchain\agent
#     lk agent create --project live --region eu-central --secrets-file .env.local --yes
#
# Le contexte de build distant ne contient QUE les fichiers d'un seul
# dossier : impossible d'y faire référence `../backend/app`. L'agent est
# donc autonome (agent.py + config.py + session_factory.py).
#
# `livekit.toml` n'est PAS copié dans l'image : c'est de la métadonnée
# consommée et réécrite par le CLI LiveKit, pas du code applicatif.

FROM python:3.11-slim AS builder

# Wheels manquantes (cryptography, aiohttp, onnxruntime pour silero VAD).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ------------------------------------------------------------------
# Runtime
# ------------------------------------------------------------------
FROM python:3.11-slim

# ffmpeg : décode audio entrant. curl : probes de santé du runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    ca-certificates \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Code de l'agent (imports absolus `config` / `session_factory` → WORKDIR).
#
# Glob `*.py` volontairement : une liste explicite avait oublié
# `memory_tools.py` lors de son ajout, ce qui cassait le job en production
# (`ModuleNotFoundError` au démarrage). Le glob garantit qu'un nouveau module
# Python est toujours embarqué. `livekit.toml` reste exclu (pas du Python).
COPY *.py ./

ENV PORT=8080
EXPOSE 8080

# Protocole de démarrage du runner LiveKit : `python <fichier>.py start`.
# Slashes obliques obligatoires (des backslashes Windows cassent le build).
CMD ["python", "agent.py", "start"]
