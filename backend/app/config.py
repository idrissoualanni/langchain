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
# Mémoire longue durée LangGraph ( PostgresStore sur Neon ; la MÊME
# base que le reste en PostgreSQL — voir persistence.py ).
LONG_TERM_DB_PATH = DATABASE_DIR / "long_term_memory.db"
# RAG documents + vecteurs ( SQLite local ; pgvector côté Neon ).
RAG_DB_PATH = DATABASE_DIR / "user_documents.db"
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
# Authentification (mission Identité)
# ------------------------------------------------------------------
# AUTH_MODE :
#   neon   → vérification RÉELLE des JWT Neon Managed Better Auth via
#            JWKS ( PRODUCTION — voir NEON_AUTH_JWKS_URL ci-dessous )
#   dev    → Bearer "dev:<name>" résolu en user interne ( développement
#            local sans aucune clé externe ; AUCUN secret )
#
# ⚠️ Le défaut est "neon" et DOIT le rester : un AUTH_MODE absent ou
# mal orthographié ne doit jamais retomber sur un fournisseur mort.
# Le resolver ÉCHOIT explicitement ( fail-closed ) sur un mode inconnu.
#
# Le mode dev est un fallback d' intégration, PAS un second système
# d'authentification : la résolution passe par le même
# CurrentUserResolver et les mêmes règles d'ownership.
AUTH_MODE = os.getenv("AUTH_MODE", "neon").strip().lower()


# ----------------------------------------------------------------------
# Garde-fou : le mode dev NE DOIT PAS écrire dans une base partagée
# ----------------------------------------------------------------------
# Constat ( 2026-09-29 ) : la table users de la base Neon de
# production contenait une ligne avec external_user_id NULL, dont
# l'email était un compte réel. Origine : api_create_user_dev, qui
# crée un utilisateur SANS identifiant externe. Le mode dev a donc
# pollué la base de production, sans rien signaler.
#
# Pourquoi une garde et pas un avertissement : le symptôme est
# invisible jusqu'au jour où quelqu'un nettoie la table, et le
# nettoyage destructif des données de rattachement d'un utilisateur
# réel est irréversible. Le coût du模式下 dev — un message d'erreur
# au démarrage — est nul ; le coût de l'absence de garde est une
# base de production corrompue, découverte des mois plus tard.
#
# On refuse au DEMARRAGE (import de config) et non au premier appel :
# un garde au point d'usage laisse démarrer un service qui échoue
# plus tard, au milieu d'une requête. Le coût du mode dev — un
# message d'erreur au démarrage — est nul ; le coût de l'absence de
# garde est une base de production corrompue.
def _is_remote_postgres(url: str) -> bool:
    """True si `url` pointe un PostgreSQL qui n'est pas local.

    "Local" = hôte absent, localhost, 127.0.0.1, ::1, ou un nom
    d'hôte sans point (socket Unix / résolution locale). Tout le
    reste est considéré comme partagé et interdit au mode dev.
    """
    if not url:
        return False
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False
    return "." in host or ":" in host


if AUTH_MODE == "dev" and _is_remote_postgres(DATABASE_URL):
    raise RuntimeError(
        "REFUS DE DÉMARRAGE : AUTH_MODE=dev alors que DATABASE_URL "
        f"pointe une base PostgreSQL distante ({DATABASE_URL.split('@')[-1]}).\n"
        "\n"
        "Le mode dev crée des utilisateurs sans identifiant externe et "
        "écrit dans la base cible : il a déjà pollué la base de "
        "production (ligne users.external_user_id NULL).\n"
        "\n"
        "Deux corrections possibles, selon ce que vous voulez faire :\n"
        "  - développer en local  → décommenter DATABASE_URL dans .env\n"
        "    (l'app bascule alors sur SQLite) et le laisser vide ici ;\n"
        "  - tester le mode dev   → viser une base PostgreSQL locale,\n"
        "    ou une branche de développement jetable, jamais la prod.\n"
    )

# Tolérance d'horloge ( secondes ) pour la validation JWT.
# Les postes peuvent dériver ( horloge en retard ) : sans leeway, un
# token fraîchement émis a un "iat" perçu comme futur → 401
# ImmatureSignatureError. 60 s couvre ces dérives sans affaiblir la
# vérification ( signature/issuer/exp restent stricts ).
try:
    JWT_LEEWAY = int(os.getenv("JWT_LEEWAY", "60"))
except ValueError:
    JWT_LEEWAY = 60

# Rôles admin — liste des identités EXTERNES ( claim `sub` émis par le
# fournisseur d'identité, Neon Auth en mode neon ) autorisées admin ;
# séparés par virgules. Le rôle par défaut est "user".
#
# ⚠️ DOUBLE LECTURE VOLONTAIRE ET TEMPORAIRE.
# ADMIN_CLERK_IDS est l'ancien nom, conservé en repli pendant la
# migration. Renommer une variable d'env d'un coup est un piège
# silencieux : la nouvelle est ignorée, l'ancienne reste lue ou
# l'inverse, et AUCUNE erreur n'est émise — les rôles admin
# disparaissent sans trace. Le `or` rend la bascule sûre dans les
# deux sens : la nouvelle gagne si elle est présente ET non vide,
# sinon on retombe sur l'ancienne.
#
#   - env var mis à jour AVANT le déploiement  → nouvelle lue
#   - code déployé AVANT l'env var             → ancienne lue
#   → aucun scénario ne peut retirer un admin.
#
# Une fois ADMIN_EXTERNAL_IDS présente sur TOUS les environnements
# ( local, Render ), ADMIN_CLERK_IDS et ce repli peuvent être
# supprimés. Ne pas le faire avant — c'est le seul garde-fou.
ADMIN_EXTERNAL_IDS = [
    a.strip()
    for a in (
        os.getenv("ADMIN_EXTERNAL_IDS")
        or os.getenv("ADMIN_CLERK_IDS", "")
    ).split(",")
    if a.strip()
]


# ------------------------------------------------------------------
# Neon Managed Better Auth — authentification ( mode AUTH_MODE=neon )
# ------------------------------------------------------------------
# Neon Auth émet ses propres JWT ( Better Auth ) signés avec les clés
# publiques exposées au well-known endpoint du projet. Le backend les
# vérifie via PyJWKClient ( JWKS réel, jamais verify_signature=False ).
# L'URL JWKS est PUBLIQUE ( well-known ) : aucun secret ici.
NEON_AUTH_JWKS_URL = os.getenv("NEON_AUTH_JWKS_URL", "").strip()

# Base d'auth Neon ( optionnelle — pour l'affichage/observabilité ).
NEON_AUTH_BASE_URL = os.getenv("NEON_AUTH_BASE_URL", "").strip()


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


# ------------------------------------------------------------------
# Langfuse — observabilité des traces de l'agent (auto-hébergé, v4)
# ------------------------------------------------------------------
# Activé uniquement si LANGFUSE_ENABLED=true ET que les clés + l'URL sont
# renseignées (le module app.observability.langfuse se désactive tout seul
# sinon). LANGFUSE_BASE_URL est le nom canonique du SDK Python ; l'ancien
# alias LANGFUSE_HOST est encore lu en fallback.
@dataclass(frozen=True)
class LangfuseSettings:
    enabled: bool
    public_key: str
    secret_key: str
    base_url: str


def langfuse_settings() -> LangfuseSettings:
    """Config Langfuse — lecture fraîche à chaque appel (testable)."""
    return LangfuseSettings(
        enabled=os.getenv("LANGFUSE_ENABLED", "false").strip().lower() == "true",
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "").strip(),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", "").strip(),
        base_url=_env_or_default(
            "LANGFUSE_BASE_URL", _env_or_default("LANGFUSE_HOST", "")
        ),
    )


# ------------------------------------------------------------------
# Utilitaire d'env (déclaré ICI, avant tout usage module-level )
# ------------------------------------------------------------------
def _env_or_default(name: str, default: str) -> str:
    """Valeur d'env non vide, sinon le défaut.

    Une variable présente mais VIDE ( ``LIVEKIT_WS_URL=`` ) ne doit pas
    court-circuiter le défaut : os.getenv renvoie "" dans ce cas, ce qui
    donnerait des tokens signés avec une clé vide.
    """
    value = os.getenv(name, "")
    return value.strip() if value.strip() else default


# ------------------------------------------------------------------
# Cloudflare Workers AI — endpoint OpenAI-compatible
# ------------------------------------------------------------------
# NOMS DE VARIABLES : le projet renseigne CLOUDFLARE_ACCOUNT_ID /
# CLOUDFLARE_API_TOKEN (préfixe complet, celui du dashboard Cloudflare).
# CF_ACCOUNT_ID / CF_API_TOKEN sont acceptés en repli : le préfixe court
# est celui qu'on trouve dans la plupart des exemples et des templates,
# et lire un seul des deux noms rendait la feature silencieusement
# inerte selon le fichier .env utilisé (backend/.env vs .env racine).
#
# L'ordre de lecture est FIXE : nom complet d'abord, court ensuite.
#
# CF_AI_BASE_URL : chemin de BASE OpenAI-compatible (chat completions +
# embeddings). L'endpoint natif, lui, est
#   POST {CF_AI_API_ROOT}/run/{MODEL}
# où CF_AI_API_ROOT vaut « …/accounts/{id}/ai ». Les deux cohabitent : le
# premier sert aux clients LangChain, le second au health check et aux
# appels directs (embeddings).
#
# CF_AI_ENABLED n'est plus lu comme un simple booléen : absent, il
# s'auto-active dès que l'account ID ET le token sont présents. Une
# variable d'env vide reste « non configuré » (voir _env_or_default).

# Racine de l'API Workers AI (sans /v1) — base des deux formes d'appel.
CF_AI_API_ROOT_TEMPLATE = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai"
)
# Base OpenAI-compatible : la racine + /v1
CF_AI_OPENAI_BASE_URL_TEMPLATE = CF_AI_API_ROOT_TEMPLATE + "/v1"

CF_AI_DEFAULT_MODEL = _env_or_default(
    "CF_AI_DEFAULT_MODEL", "@cf/meta/llama-3.2-3b-instruct"
)
CF_AI_DEFAULT_EMBEDDING_MODEL = _env_or_default(
    "CF_AI_DEFAULT_EMBEDDING_MODEL", "@cf/baai/bge-base-en-v1.5"
)


@dataclass(frozen=True)
class CloudflareAISettings:
    """Config Cloudflare Workers AI — lecture fraîche (testable)."""

    enabled: bool
    account_id: str
    api_token: str
    api_root: str
    base_url: str


def cloudflare_ai_settings() -> CloudflareAISettings:
    """Config Workers AI — nom complet prioritaire, nom court en repli."""
    account_id = _env_or_default(
        "CLOUDFLARE_ACCOUNT_ID", _env_or_default("CF_ACCOUNT_ID", "")
    )
    api_token = _env_or_default(
        "CLOUDFLARE_API_TOKEN", _env_or_default("CF_API_TOKEN", "")
    )

    api_root = _env_or_default("CF_AI_API_ROOT", "")
    if not api_root and account_id:
        api_root = CF_AI_API_ROOT_TEMPLATE.format(account_id=account_id)

    # Base OpenAI-compatible : elle INCLUT /v1. Un caller qui fournit
    # une base SANS /v1 l'obtiendrait complète mais cassée (le SDK
    # OpenAI concatène « /chat/completions » sans rien ajouter).
    base_url = _env_or_default("CF_AI_BASE_URL", "")
    if not base_url and api_root:
        base_url = api_root.rstrip("/") + "/v1"

    # Auto-activation : CF_AI_ENABLED reste l'interrupteur explicite
    # (« false » désactive même avec des clés), mais son absence ne
    # doit pas laisser Workers AI mort alors que les clés sont là.
    explicit = os.getenv("CF_AI_ENABLED", "").strip().lower()
    if explicit in ("0", "false", "no", "off"):
        enabled = False
    else:
        # « true » explicite OU variable absente/vide : on exige dans
        # les deux cas que les DEUX credentials soient là, sinon on
        # activerait un provider qui ne peut pas s'authentifier.
        enabled = bool(account_id and api_token)

    return CloudflareAISettings(
        enabled=enabled,
        account_id=account_id,
        api_token=api_token,
        api_root=api_root,
        base_url=base_url,
    )


# Alias rétro-compatibles (le nom court reste exporté pour les appelants
# existants ; ce sont des CONSTANTES figées au'import, la source de
# vérité reste cloudflare_ai_settings() ).
_CF_SETTINGS = cloudflare_ai_settings()
CF_AI_ENABLED = _CF_SETTINGS.enabled
CF_ACCOUNT_ID = _CF_SETTINGS.account_id
CF_API_TOKEN = _CF_SETTINGS.api_token
CF_AI_BASE_URL = _CF_SETTINGS.base_url


# ------------------------------------------------------------------
# OpenAI — API officielle
# ------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()  # Optionnel, pour proxy


# ------------------------------------------------------------------
# Anthropic — API officielle
# ------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "").strip()  # Optionnel


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
# ⚠️ Le défaut a été corrigé : « google/gemma-4-31b-it » n'existe PAS
# dans le catalogue Inference (le worker démarre, s'enregistre, puis
# échoue silencieusement au premier tour de parole — visible seulement
# dans les logs du job). Liste vérifiée contre livekit-agents 1.8.x :
# openai/gpt-4o-mini, google/gemini-2.5-flash, moonshotai/kimi-k2.5…
LIVEKIT_AGENT_STT_MODEL = _env_or_default(
    "LIVEKIT_AGENT_STT_MODEL", "deepgram/nova-3"
)
LIVEKIT_AGENT_LLM_MODEL = _env_or_default(
    "LIVEKIT_AGENT_LLM_MODEL", "openai/gpt-4o-mini"
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
# Transcription STT — Deepgram (feature独立ée, hors LiveKit)
# ------------------------------------------------------------------
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "").strip()

# ------------------------------------------------------------------
# Chiffrement des données (Fernet AES)
# ------------------------------------------------------------------
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "").strip()


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

# ---------------------------------------------------------------
# VideoSubgraph v2 — analyse de frames (LLM vision).
#
# Le transcript ( whisper ) capte ce qui est DIT ; l'agent vision
# decrit ce qui est MONTRE ( slides, diagrammes, ecran de code ).
# VISION_MODEL_ID : assignment du purpose "vision" — le resolver lit
# l'env du meme nom ( app/services/models/resolver.py ). Defaut
# "vision-default" ( gpt-oss:20b — seul modele FREE de l'host Ollama
# acceptant les images ; les autres renvoient 402 Payment Required ).
# ---------------------------------------------------------------
VISION_MODEL_ID = os.getenv("VISION_MODEL_ID", "vision-default").strip()

# Frames : nombre extraites pour l'analyse (opencv), strategie
# d'echantillonnage ( uniform = equirarti ; scene = detection de
# coupures ) et plafond envoye au LLM vision ( cout tokens ; le compte
# free Ollama est rate-limite, d'ou un plafond bas ).
VIDEO_FRAME_COUNT = _as_int("VIDEO_FRAME_COUNT", 8)
VIDEO_FRAME_STRATEGY = (
    os.getenv("VIDEO_FRAME_STRATEGY", "uniform").strip().lower() or "uniform"
)
VIDEO_AGENT_MAX_FRAMES = _as_int("VIDEO_AGENT_MAX_FRAMES", 6)

# Agent ReAct d'analyse visuelle (opt-in). Exige EN PLUS que le modele
# "vision" se resolve — sinon repli silencieux sur le pipeline
# deterministe ( meme philosophie que resolve_transcriber() : jamais de
# contenu fabrique presente comme analyse ).
VIDEO_AGENT_ENABLED = os.getenv("VIDEO_AGENT_ENABLED", "0").strip() == "1"

# Profondeur max de la boucle ReAct — bornee, jamais infinie
# (anti-boucle, comme MAX_ATTEMPTS_DEFAULT).
VIDEO_AGENT_MAX_STEPS = _as_int("VIDEO_AGENT_MAX_STEPS", 6)


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


def check_database_health() -> bool:
    """Vérifie l'accès à Neon ( PostgreSQL via DATABASE_URL ).

    SQLite retiré — Neon est la seule base de l'application."""

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
