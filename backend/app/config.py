# Agent Control Center — configuration centrale
import os
from pathlib import Path

from dotenv import load_dotenv

# .env du backend, sinon .env racine
BACKEND_DIR = Path(__file__).resolve().parents[1]
BASE_DIR = BACKEND_DIR.parent

if (BACKEND_DIR / ".env").exists():
    load_dotenv(BACKEND_DIR / ".env")
else:
    load_dotenv(BASE_DIR / ".env")

# ------------------------------------------------------------------
# Chemins
# ------------------------------------------------------------------

DATABASE_DIR = BACKEND_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

APP_DB_PATH = DATABASE_DIR / "app.db"
CHECKPOINTS_DB_PATH = DATABASE_DIR / "checkpoints.db"
LOG_PATH = LOG_DIR / "agent.log"


def log_safe(value) -> str:
    """Version tronquée/sécurisée d'une valeur pour les logs — jamais de secret."""
    if value is None:
        return "(none)"
    s = str(value)
    return s[:80] if len(s) <= 80 else s[:80] + "…"


# ------------------------------------------------------------------
# Ollama
# ------------------------------------------------------------------

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_OLLAMA", "qwen2.5")


def ollama_headers() -> dict | None:
    """Headers d'authentification pour Ollama cloud (jamais exposés au frontend)."""
    if OLLAMA_API_KEY:
        return {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
    return None


# ------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------


def check_ollama_health() -> bool:
    """Vérifie qu'Ollama répond (local ou cloud)."""
    try:
        import ollama

        client = ollama.Client(host=OLLAMA_HOST, headers=ollama_headers() or {})
        client.list()
        return True
    except Exception:
        return False


def check_sqlite_health() -> bool:
    """Vérifie l'accès aux bases SQLite (app.db + checkpoints.db)."""
    import sqlite3

    try:
        conn = sqlite3.connect(APP_DB_PATH, timeout=2)
        conn.execute("SELECT 1")
        conn.close()
        conn = sqlite3.connect(CHECKPOINTS_DB_PATH, timeout=2)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False


def check_langgraph_health() -> bool:
    """Vérifie que l'agent LangGraph est initialisé et le checkpointer actif."""
    try:
        from app.agent.graph import get_agent

        return get_agent() is not None
    except Exception:
        return False
