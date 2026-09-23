# Agent Control Center — configuration centrale
import os
from dataclasses import dataclass
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


# ------------------------------------------------------------------
# Base de données — SQLAlchemy dual-dialect
# ------------------------------------------------------------------
# DATABASE_URL définie (Neon/PostgreSQL, déploiement Render) →
# PostgreSQL partout. Absente → SQLite local (développement).
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

# Origines CORS autorisées (backend) — séparées par virgules.
# Défaut : frontend dev Vite local (rien d'autre par défaut).
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
] or ["http://localhost:5173", "http://127.0.0.1:5173"]


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


# ------------------------------------------------------------------
# Clerk — authentification (mission Identité)
# ------------------------------------------------------------------
# AUTH_MODE :
#   clerk  → vérification RÉELLE des JWT Clerk via JWKS (production)
#   dev    → Bearer "dev:<name>" résolu en user interne (développement
#            local sans clés Clerk ; AUCUN secret)
# Le mode dev est un fallback d' intégration, PAS un second système
# d'authentification : la résolution passe par le même
# CurrentUserResolver et les mêmes règles d'ownership.
AUTH_MODE = os.getenv("AUTH_MODE", "clerk").strip().lower()

# Clé publique Clerk frontend ( publishable ) — injectée au frontend
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY", "")

# JWKS du backend : par défaut dérivé de l'instance Clerk
# ( <instance>.clerk.accounts.dev ou domaine custom ) via
# CLERK_JWKS_URL ; sinon construit depuis CLERK_ISSUER.
CLERK_ISSUER = os.getenv("CLERK_ISSUER", "")
CLERK_JWKS_URL = os.getenv(
    "CLERK_JWKS_URL",
    f"{CLERK_ISSUER}/.well-known/jwks.json" if CLERK_ISSUER else "",
)

# Audience acceptée ( optionnelle : Clerk utilise souvent
# "default" ; vide = pas de vérification d'audience )
CLERK_AUDIENCES = [
    a.strip()
    for a in os.getenv("CLERK_AUDIENCES", "").split(",")
    if a.strip()
]

# Tolérance d'horloge ( secondes ) pour la validation JWT Clerk.
# Les postes peuvent dériver ( horloge en retard ) : sans leeway, un
# token fraîchement émis a un "iat" perçu comme futur → 401
# ImmatureSignatureError. 60 s couvre ces dérives sans affaiblir la
# vérification ( signature/issuer/exp restent stricts ).
try:
    CLERK_JWT_LEEWAY = int(os.getenv("CLERK_JWT_LEEWAY", "60"))
except ValueError:
    CLERK_JWT_LEEWAY = 60

# Rôles admin — liste des clerk_user_id autorisés admin ( config ,
# PAS le frontend ) ; séparés par virgules. Le rôle par défaut est
# "user".
ADMIN_CLERK_IDS = [
    a.strip()
    for a in os.getenv("ADMIN_CLERK_IDS", "").split(",")
    if a.strip()
]


def ollama_headers() -> dict | None:
    """Headers d'authentification pour Ollama cloud (jamais exposés au frontend)."""
    if OLLAMA_API_KEY:
        return {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
    return None


# ------------------------------------------------------------------
# LangSmith — observabilité (source unique de vérité)
# ------------------------------------------------------------------
# Une SEULE définition des défauts ici : avant, le client
# (langsmith_client.py) utilisait "true" par défaut et le health check
# (health.py) "false" par défaut — les deux répondaient "non configuré"
# l'un et "configuré" l'autre pour la même env absente. Désactivé par
# défaut : le tracing ne s'active que s'il est explicitement voulu ET
# qu'une clé API est présente (vérifiée côté client).
#
# La lecture se fait via une FONCTION (et non des constantes de module)
# pour rester testable : les tests patchent os.environ puis instancient
# LangSmithClient / appellent /api/health/langsmith — une constante
# lue à l'import ignorerait ces patches.


@dataclass(frozen=True)
class LangSmithSettings:
    enabled: bool
    project: str
    endpoint: str
    environment: str
    api_key: str


def langsmith_settings() -> LangSmithSettings:
    """Config LangSmith — lecture fraîche à chaque appel (testable)."""
    return LangSmithSettings(
        enabled=os.getenv("LANGSMITH_ENABLED", "false").strip().lower() == "true",
        project=os.getenv("LANGSMITH_PROJECT", "agent-tutor"),
        endpoint=os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        environment=os.getenv("LANGSMITH_ENVIRONMENT", "development"),
        api_key=os.getenv("LANGSMITH_API_KEY", "").strip(),
    )


def _env_or_default(name: str, default: str) -> str:
    """Valeur d'env non vide, sinon le défaut.

    Une variable présente mais VIDE ( ``LIVEKIT_WS_URL=`` ) ne doit pas
    court-circuiter le défaut : os.getenv renvoie "" dans ce cas, ce qui
    donnerait des tokens signés avec une clé vide.
    """
    value = os.getenv(name, "")
    return value.strip() if value.strip() else default


# ------------------------------------------------------------------
# LiveKit — temps réel vidéo/audio
# ------------------------------------------------------------------
# LIVEKIT_HOST est le point d'accès WebSocket (wss://…) du serveur ou du
# projet LiveKit Cloud. Deux noms d'env sont acceptés :
#   LIVEKIT_URL      — convention LiveKit Cloud (docs officielles)
#   LIVEKIT_WS_URL   — ancien nom du projet, conservé par compatibilité
# L'URL HTTP/HTTPS de l'API s'en déduit par conversion de schéma
# (voir app.infrastructure.livekit.token.livekit_api_url).
LIVEKIT_API_KEY = _env_or_default("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = _env_or_default("LIVEKIT_API_SECRET", "devsecret")
LIVEKIT_HOST = _env_or_default(
    "LIVEKIT_URL",
    _env_or_default("LIVEKIT_WS_URL", "wss://localhost:7880"),
)


def _looks_masked(value: str) -> bool:
    """Détecte un secret copié depuis un dashboard en mode masqué.

    LiveKit Cloud affiche le secret sous forme de points '••••' ; un
    copier-coller dans cet état met des U+2022 dans le .env, et l'API
    répond alors 401 sur TOUT appel — une erreur sourde qui se manifeste
    loin de sa cause. Le secret réel est en base64url ( ASCII pur ).
    """
    return bool(value) and any(ord(c) > 126 for c in value)


if _looks_masked(LIVEKIT_API_SECRET):
    print(
        "⚠️  LIVEKIT_API_SECRET contient des caractères masqués ( '••••' ) : "
        "il a été copié depuis le dashboard LiveKit sans être révélé. "
        "L'API LiveKit répondra 401 sur tous les appels. "
        "Revenez sur le dashboard, affichez le secret, puis recopiez-le."
    )


# ------------------------------------------------------------------
# LiveKit Agents — modèles du tuteur vocal ( worker app.infrastructure.livekit.agent )
# ------------------------------------------------------------------
# Tous via LiveKit Inference : mêmes LIVEKIT_API_KEY / SECRET que le
# reste du projet, aucune clé provider à gérer. Les noms doivent
# exister dans livekit.agents.inference ( STTModels / LLMModels /
# TTSModels ) — un nom invalide lève à la première inference.
LIVEKIT_AGENT_STT_MODEL = _env_or_default(
    "LIVEKIT_AGENT_STT_MODEL", "deepgram/nova-3"
)
LIVEKIT_AGENT_LLM_MODEL = _env_or_default(
    "LIVEKIT_AGENT_LLM_MODEL", "google/gemma-4-31b-it"
)
LIVEKIT_AGENT_TTS_MODEL = _env_or_default(
    "LIVEKIT_AGENT_TTS_MODEL", "rime/coda"
)
# Voice ID provider ( UUID Cartesia, nom Inworld… ). Vide = la voix par
# défaut côté Inference ; on ne transmet alors pas le paramètre — un ID
# inventé ferait échouer la première synthèse.
# "aurelie" : voix Rime testée en conditions réelles.
LIVEKIT_AGENT_TTS_VOICE = _env_or_default("LIVEKIT_AGENT_TTS_VOICE", "aurelie")
LIVEKIT_AGENT_LANGUAGE = _env_or_default("LIVEKIT_AGENT_LANGUAGE", "fr")


# ------------------------------------------------------------------
# Limites de la boucle agentique (mission §14 — configurables, jamais
# hardcodées dans le graphe)
# ------------------------------------------------------------------


def _as_int(name: str, default: int) -> int:
    """Entier d'env avec repli sûr (aucun crash si valeur invalide)."""
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


AGENT_MAX_ITERATIONS = _as_int("AGENT_MAX_ITERATIONS", 25)
AGENT_MAX_TOOL_CALLS = _as_int("AGENT_MAX_TOOL_CALLS", 20)
AGENT_TIMEOUT_SECONDS = _as_int("AGENT_TIMEOUT_SECONDS", 120)
AGENT_MAX_SUBGRAPH_CALLS = _as_int("AGENT_MAX_SUBGRAPH_CALLS", 10)
# LangGraph utilise DEFAULT_RECURSION_LIMIT=10007 — borné ici via la
# config d'invocation (paramètre runtime, pas compile).
AGENT_RECURSION_LIMIT = _as_int(
    "AGENT_RECURSION_LIMIT",
    max(AGENT_MAX_ITERATIONS, AGENT_MAX_TOOL_CALLS) * 3 + 40,
)
# Invocation LLM : timeout + retries BORNÉS (mission §14 — uniquement
# sur erreurs transitoires réseau/timeout/rate-limit temporaire, JAMAIS
# validation/authorization).
MODEL_REQUEST_TIMEOUT_SECONDS = _as_int("MODEL_REQUEST_TIMEOUT_SECONDS", 60)
MODEL_RETRY_ATTEMPTS = _as_int("MODEL_RETRY_ATTEMPTS", 2)
MODEL_PROVIDER_RETRIES = _as_int("MODEL_PROVIDER_RETRIES", 3)

# ---------------------------------------------------------------
# Vidéo — transcription réelle (faster-whisper).
#
# VIDEO_TRANSCRIPTION_MODE :
#   "auto"    → whisper si faster-whisper est installé, sinon bouchon
#               pédagogique hors-ligne (comportement historique) ;
#   "whisper" → whisper forcé (erreur si la lib est absente) ;
#   "offline" → bouchon forcé (tests/unitaires, aucun réseau).
# ---------------------------------------------------------------
VIDEO_TRANSCRIPTION_MODE = (
    os.getenv("VIDEO_TRANSCRIPTION_MODE", "auto").strip().lower()
)
VIDEO_WHISPER_MODEL = os.getenv(
    "VIDEO_WHISPER_MODEL", "tiny"
).strip().lower() or "tiny"
VIDEO_WHISPER_DEVICE = os.getenv(
    "VIDEO_WHISPER_DEVICE", "cpu"
).strip().lower() or "cpu"
VIDEO_WHISPER_COMPUTE = os.getenv(
    "VIDEO_WHISPER_COMPUTE", "int8"
).strip().lower() or "int8"
# Forcer la langue du transcript ("" = détection automatique).
VIDEO_WHISPER_LANGUAGE = os.getenv(
    "VIDEO_WHISPER_LANGUAGE", ""
).strip().lower()


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
    """Vérifie l'accès à la base de données (SQLite local ou PostgreSQL via DATABASE_URL)."""
    try:
        from sqlalchemy import text

        from app.infrastructure.database.connections import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def check_langgraph_health() -> bool:
    """Vérifie que l'agent LangGraph est initialisé et le checkpointer actif."""
    try:
        from app.graph.main import get_agent

        return get_agent() is not None
    except Exception:
        return False
