# Connexions base de données — SQLAlchemy dual-dialect.
#
# Deux backends, un SEUL code :
#   - PostgreSQL (Neon) si DATABASE_URL est définie (déploiement) ;
#   - SQLite local (backend/database/app.db) sinon (développement).
#
# L'API exposée aux callers est conservée (thread-local, rows à la
# sqlite3.Row : accès par clé ET par index, dict(row) fonctionne),
# mais les requêtes utilisent les paramètres NOMÉS (:name) portables,
# jamais « ? » (désormais interdit au profit de text() SQLAlchemy).
import threading

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine, Result

from app.config import (
    APP_DB_PATH,
    CHECKPOINTS_DB_PATH,
    DATABASE_URL,
    USE_POSTGRES,
)

_local = threading.local()
_init_lock = threading.RLock()
_initialized = False

_engine: Engine | None = None
_checkpoint_engine: Engine | None = None

# Schéma portable (types TEXT/INTEGER/DEFAULT valides en SQLite et
# PostgreSQL). Chaque statement est indépendant : text() SQLAlchemy
# n'accepte PAS plusieurs instructions en un seul execute().
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS threads (
        thread_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        name TEXT NOT NULL DEFAULT 'New Thread',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_id)",
    # --------------------------------------------------------------
    # VideoSubgraph v2 — ingestion + persistance vidéo (Neon).
    # videos : une ligne par vidéo ingérée ( transcript whisper, et
    # optionnellement la description visuelle de l'agent ReAct ).
    # video_segments : segments pédagogiques issus de la segmentation
    # du transcript ( title/summary/start/end/topics ).
    # --------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        filename TEXT NOT NULL,
        source_url TEXT NOT NULL DEFAULT '',
        duration REAL NOT NULL DEFAULT 0.0,
        origin TEXT NOT NULL DEFAULT '',
        format TEXT NOT NULL DEFAULT '',
        language TEXT NOT NULL DEFAULT '',
        transcript TEXT NOT NULL DEFAULT '',
        visual_description TEXT NOT NULL DEFAULT '',
        knowledge_key TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_videos_user ON videos(user_id)",
    """
    CREATE TABLE IF NOT EXISTS video_segments (
        id TEXT PRIMARY KEY,
        video_id TEXT NOT NULL REFERENCES videos(video_id),
        user_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        start REAL NOT NULL DEFAULT 0.0,
        "end" REAL NOT NULL DEFAULT 0.0,
        topics TEXT NOT NULL DEFAULT '',
        segment_text TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_video_segments_video ON video_segments(video_id)",
    # NB : idx_video_segments_user supprimé — video_segments n'a pas de
    # colonne user_id ( cf. schema.py : l'isolation se fait via
    # videos.user_id en jointure ). Tentative de création sur une
    # colonne absente → ProgrammingError au startup.
]

# Mission Identité — migrations ADDITIVES idempotentes (§6/§7) :
#   + users.clerk_user_id TEXT UNIQUE  (liaison identité externe)
#   + users.role TEXT DEFAULT 'user'    (rôles user/admin)
# AUCUNE donnée existante n'est modifiée ou supprimée : les users
# actuels gardent clerk_user_id NULL (jamais rattachés arbitrairement)
# et role NULL → résolu en 'user' par le resolver.
MIGRATIONS = [
    (
        "ALTER TABLE users ADD COLUMN clerk_user_id TEXT",
        "clerk_user_id",
    ),
    (
        "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'",
        "role",
    ),
]

# Index unique PARTIEL sur clerk_user_id : syntaxe WHERE acceptée par
# SQLite ET PostgreSQL ; multiples NULL autorisés (users non reliés).
UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk
ON users(clerk_user_id) WHERE clerk_user_id IS NOT NULL;
"""


# ----------------------------------------------------------------------
# Engines
# ----------------------------------------------------------------------


def _sqlite_url(path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _postgres_url(db_url: str) -> str:
    """Force le driver psycopg v3 ( binaire, pas de compilation ).

    SQLAlchemy choisit psycopg2 par défaut pour les URL postgres://… .
    psycopg2 nécessite pg_config + compilation ( lourd en CI / Render );
    psycopg 3 ( paquet psycopg[binary] ) est le driver moderne et se
    contente d'une wheel. On ne réécrit que le scheme, le reste de l'URL
    ( credentials, host, sslmode ) est préservé tel quel.
    """
    scheme, rest = db_url.split("://", 1)
    if scheme in ("postgres", "postgresql"):
        return f"postgresql+psycopg://{rest}"
    return db_url


def _build_engine(db_url: str | None, sqlite_path) -> Engine:
    """Construit l'engine portable (Postgres si DATABASE_URL, sinon SQLite)."""
    if USE_POSTGRES and db_url:
        return create_engine(
            _postgres_url(db_url),
            pool_pre_ping=True,
            # Neon coupe une session restée inactive en transaction
            # ( idle_in_transaction_session_timeout ). get_conn() garde la
            # connexion thread-local OUVERTE entre deux requêtes : la 1re
            # SELECT démarre implicitement une transaction qui reste
            # "idle in transaction" jusqu'au commit suivant — sous un
            # service Render peu sollicité, Neon la tue et la requête
            # d'après arrive sur une connexion morte → 500.
            # idle_in_transaction_session_timeout=0 : pas de limite de
            # côté serveur ( on s'appuie sur pool_pre_ping + le bail
            # ci-dessous pour la robustesse ).
            connect_args={
                "options": "-c idle_in_transaction_session_timeout=0",
            },
        )
    engine = create_engine(
        _sqlite_url(sqlite_path),
        connect_args={"check_same_thread": False},
    )

    # Foreign keys : PRAGMA par connexion (équivalent de l'ancien
    # get_conn() qui exécutait PRAGMA foreign_keys=ON).
    @event.listens_for(engine, "connect")
    def _fk_on_connect(dbapi_conn, _record):  # pragma: no cover — dialect-specific
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def get_engine() -> Engine:
    """Engine de l'application (users/threads) — singleton thread-safe."""
    global _engine
    if _engine is None:
        with _init_lock:
            if _engine is None:
                _engine = _build_engine(DATABASE_URL, APP_DB_PATH)
    return _engine


def get_checkpoint_engine() -> Engine:
    """Engine des checkpoints LangGraph (fichier dédié en SQLite,
    même base que l'app en PostgreSQL)."""
    global _checkpoint_engine
    if _checkpoint_engine is None:
        with _init_lock:
            if _checkpoint_engine is None:
                _checkpoint_engine = _build_engine(
                    DATABASE_URL, CHECKPOINTS_DB_PATH
                )
    return _checkpoint_engine


# ----------------------------------------------------------------------
# Rows compatibles sqlite3.Row (dict + accès par index + itération
# sur les VALEURS pour le tuple-unpacking — ex: for tag, blob in rows)
# ----------------------------------------------------------------------


class AppRow(dict):
    """Row hybride : clé ET index (compat sqlite3.Row).

    - dict(row)  → copie {colonne: valeur}
    - row["col"] → valeur par clé
    - row[0]     → valeur par position (COLUMN ORDER)
    - for a, b in row → itère les valeurs (tuple-unpacking)
    """

    def __init__(self, mapping):
        super().__init__(mapping)
        self._values = list(mapping.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return dict.__getitem__(self, key)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    @property
    def values_list(self):
        return self._values


class AppResult:
    """Résultat de requête compatible sqlite3 (fetchall/fetchone/rowcount)."""

    def __init__(self, result: Result):
        if result.returns_rows:
            self._rows = [AppRow(dict(r._mapping)) for r in result.fetchall()]
        else:
            self._rows = []
        self._rowcount = result.rowcount

    def fetchall(self) -> list[AppRow]:
        return self._rows

    def fetchone(self) -> AppRow | None:
        return self._rows[0] if self._rows else None

    @property
    def rowcount(self) -> int:
        return self._rowcount


def _is_connection_dead(exc: BaseException) -> bool:
    """True si le serveur a tué / perdu la session sous-jacente.

    Neon ferme les sessions restées inactives en transaction
    ( IdleInTransactionSessionTimeout ) ou inactives tout court. La
    connexion SQLAlchemy a l'air encore ouverte — la garder fait planter
    toutes les requêtes suivantes ( PendingRollbackError en cascade ).
    """
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "terminating connection",
            "idle in transaction",
            "connection reset by peer",
            "server closed the connection",
            "connection already closed",
            "could not receive data",
            "ssl connection has been closed unexpectedly",
        )
    )


class AppConn:
    """Connexion compatible avec l'ancien get_conn() sqlite3.

    execute() accepte du SQL text() avec paramètres nommés PASSÉS EN
    dict ({"nom": valeur}) — les til et listes positionnels sont REJETÉS
    pour forcer la portabilité SQLite/PostgreSQL.
    """

    def __init__(self, sa_conn: Connection):
        self._sa = sa_conn

    @property
    def closed(self) -> bool:
        return self._sa.closed

    def execute(self, sql: str, params: dict | None = None) -> AppResult:
        # Une erreur SQL ( ex : coupure réseau vers Neon ) laisse la
        # transaction dans un état "invalid" : TOUTE requête suivante
        # sur cette même connexion lève PendingRollbackError. On rollback
        # donc avant de remonter l'erreur, pour que les requêtes
        # ultérieures puissent reprendre sur une transaction saine.
        try:
            if params is None:
                res = self._sa.execute(text(sql))
            elif isinstance(params, dict):
                res = self._sa.execute(text(sql), params)
            else:
                raise TypeError(
                    "get_conn().execute() exige des paramètres NOMÉS en dict "
                    f"(:name), reçu {type(params).__name__}. "
                    "Réécrivez la requête en style portable SQLite/PostgreSQL."
                )
        except Exception as exc:
            try:
                self._sa.rollback()
            except Exception:
                # rollback lui-même en échec → la connexion est morte,
                # on la déconnecte pour forcer une reconnexion propre au
                # prochain get_conn().
                self._dispose()
            # Neon ( ou le pool ) peut avoir TUÉ la session sous-jacente.
            # pool_pre_ping ne voit pas une connexion apparemment ouverte
            # mais serveur-mort : on la jette pour que le prochain appel
            # reparte sur une connexion fraîche.
            if _is_connection_dead(exc):
                self._dispose()
            raise
        return AppResult(res)

    def _dispose(self) -> None:
        """Déconnecte en silence — get_conn() recréera la connexion."""
        try:
            self._sa.close()
        except Exception:
            pass

    def executemany(self, sql: str, seq_params: list[dict]) -> None:
        """exécution en lot (INSERT/UPDATE multiples) — parametres nommés."""
        self._sa.execute(text(sql), seq_params)

    def commit(self) -> None:
        self._sa.commit()

    def rollback(self) -> None:
        self._sa.rollback()

    def close(self) -> None:
        if not self._sa.closed:
            self._sa.close()


# ----------------------------------------------------------------------
# get_conn — connexion thread-local (même sémantique qu'avant)
# ----------------------------------------------------------------------


def get_conn() -> AppConn:
    """Connexion app.db par thread (thread-safe pour FastAPI threadpool).

    La connexion SQLAlchemy est attachée au thread : appeler
    get_conn() deux fois dans le même handler retombe dessus, comme
    avec le sqlite3 thread-local d'origine (commit() partagé).
    """
    conn = getattr(_local, "conn", None)
    if conn is None or conn.closed:
        conn = AppConn(get_engine().connect())
        _local.conn = conn
    return conn


def get_checkpoint_conn() -> AppConn:
    """Connexion à la base checkpoints LangGraph (thread-local)."""
    key = "checkpoint_conn"
    conn = getattr(_local, key, None)
    if conn is None or conn.closed:
        conn = AppConn(get_checkpoint_engine().connect())
        setattr(_local, key, conn)
    return conn


def _existing_columns(engine: Engine) -> set[str]:
    """Colonnes existantes de la table users (introspection portable)."""
    from sqlalchemy import inspect

    insp = inspect(engine)
    if not insp.has_table("users"):
        return set()
    return {c["name"] for c in insp.get_columns("users")}


def init_db() -> None:
    """Crée le schema users/threads + migrations identité (idempotent)."""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        engine = get_engine()
        conn = get_conn()
        for stmt in SCHEMA_STATEMENTS:
            conn.execute(stmt)
        conn.commit()
        # Migrations additives — idempotentes et non destructives
        cols = _existing_columns(engine)
        for stmt, col in MIGRATIONS:
            if col not in cols:
                conn.execute(stmt)
                conn.commit()
        conn.execute(UNIQUE_INDEX)
        conn.commit()
        _initialized = True


__all__ = [
    "SCHEMA_STATEMENTS",
    "MIGRATIONS",
    "UNIQUE_INDEX",
    "get_engine",
    "get_checkpoint_engine",
    "get_conn",
    "get_checkpoint_conn",
    "init_db",
    "AppConn",
    "AppResult",
    "AppRow",
]