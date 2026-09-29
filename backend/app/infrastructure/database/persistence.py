"""Persistance LangGraph ( checkpointer + store ) — PostgreSQL ( Neon ) UNIQUEMENT.

SQLite a été RETIRÉ ( décision 2026-09-29 ) : Neon est la seule source de
persistance — checkpointer, store mémoire longue durée, corpus knowledge,
monitoring. Un déploiement sans DATABASE_URL est une erreur de configuration
et doit échouer EXPLICITEMENT ( fail-closed, comme AUTH_MODE ) — un repli
silencieux sur des fichiers locaux éphémères faisait perdre checkpoints et
mémoire à chaque redéploiement Render.

API :
    get_checkpointer()      -> PostgresSaver
    get_persistent_store()  -> PostgresStore

Les deux exposent .setup() ( création idempotente des tables ) — les
callers n'ont aucune modification à faire.
"""
from __future__ import annotations

import threading

from app.config import DATABASE_URL
from app.logging.events import log_event


_lock = threading.RLock()
_checkpointer = None
_store = None

# Marqueur de la premiere initialisation ( log unique au demarrage ).
_initialized = False


def _require_database_url() -> str:
    """DATABASE_URL obligatoire — échec explicite sinon ( fail-closed )."""
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL absente : la persistance Neon ( PostgreSQL ) est "
            "la SEULE backend supporté — SQLite a été retiré. Renseigne "
            "DATABASE_URL ( render.yaml / dashboard Render / .env local )."
        )
    return DATABASE_URL


def _postgres_url() -> str:
    """DATABASE_URL normalisee pour SQLAlchemy / pgvector ( scheme psycopg3 ).

    Neon expose postgres:// ou postgresql:// ; SQLAlchemy et pgvector
    attendent postgresql+psycopg://. On reecrit seulement le scheme :
    le reste ( credentials, host, sslmode ) est preserve. Reflechit la
    logique de connections._postgres_url — pas de duplication des
    engines, juste la normalisation d'URL.
    """
    url = _require_database_url()
    scheme, rest = url.split("://", 1)
    if scheme in ("postgres", "postgresql"):
        return f"postgresql+psycopg://{rest}"
    return url


def _postgres_conninfo() -> str:
    """Conninfo psycopg BRUTE pour langgraph ( PostgresSaver/PostgresStore ).

    from_conn_string passe l'URL telle quelle a psycopg.Connection.connect
    — qui ne comprend NI "postgresql+psycopg://" ( SQLAlchemy ), NI les
    query params au format URL. Il faut donc un scheme postgresql:// pur,
    sans driver. Quelle que soit l'ecriture d'origine ( postgres:// ,
    postgresql:// , postgresql+psycopg:// ), on prend ce qui suit "://".
    """
    url = _require_database_url()
    _scheme, rest = url.split("://", 1)
    # Si l'URL d'origine etait deja "postgresql+psycopg://h", rest ne
    # contient PAS de "://" — on renvoie donc directement.
    if "://" in rest:
        rest = rest.split("://", 1)[1]
    return f"postgresql://{rest}"


def _ensure_vector_extension() -> None:
    """Active l'extension pgvector sur Neon ( idempotent ).

    pgvector est necessaire des qu'une colonne vector(dim) est utilisee
    ( RAG documents, segments video, corpus knowledge ). L'extension est
    inoffensive a activer.

    Si le role n'en a pas le droit, on echoue explicitement : un backend
    vectoriel sans pgvector est un backend casse, et se taire ferait
    croire que la recherche semantique marche ( elle renverrait des
    erreurs a la premiere requete ).
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    finally:
        engine.dispose()


def init_persistence() -> None:
    """Initialise checkpointer + store ( tables creees, idempotent ).

    A appeler au demarrage de l'application ( FastAPI lifespan ), une
    seule fois. .setup() cree les tables si absentes — sans toucher aux
    donnees existantes.
    """
    global _initialized, _checkpointer, _store
    with _lock:
        if _initialized:
            return

        _require_database_url()
        _ensure_vector_extension()
        _checkpointer = get_checkpointer()
        _store = get_persistent_store()
        log_event(
            "PERSISTENCE_INIT",
            message=(
                "Persistence LangGraph sur PostgreSQL (Neon) — "
                "checkpointer=PostgresSaver | store=PostgresStore | "
                "SQLite retiré"
            ),
        )
        _initialized = True


# ----------------------------------------------------------------------
# Wrappers async-compatibles.
#
# Le Main Graph contient des nodes async ( retrieve_context, agenda,
# coding, document — MCP + ainvoke de sous-agents ) : LangGraph exige
# alors .ainvoke(), qui appelle checkpointer.aget_tuple/aput/aput_writes
# et store.aget/aput/asearch. Les implémentations PostgresSaver /
# PostgresStore du paquet sont SYNC-ONLY ( les méthodes async de la
# classe de base lèvent NotImplementedError ).
#
# Au lieu de tout migrer en async ( AsyncPostgresSaver exige un pool
# async ET casserait les ~10 appels synchrones agent.get_state() du
# codebase ), on SOUS-CLASSE les implémentations sync et on délègue les
# méthodes async aux méthodes sync via asyncio.to_thread : le pool
# psycopg est thread-safe, chaque méthode prend sa propre connexion.
# L'héritage est OBLIGATOIRE — LangGraph fait isinstance(...,
# BaseCheckpointSaver) / isinstance(..., BaseStore) à l'invoke.
# Les deux API ( sync ET async ) fonctionnent sur le MÊME singleton.
# ----------------------------------------------------------------------
import asyncio

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore


class AsyncCompatPostgresSaver(PostgresSaver):
    """PostgresSaver + API async — double usage sync/async.

    L'API sync est HÉRITÉE inchangée ( agent.get_state() continue de
    marcher ). Seules les méthodes async sont surchargées pour
    déléguer aux sync via executor."""

    async def aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)

    async def aget(self, config):
        return await asyncio.to_thread(self.get, config)

    async def aput(self, config, checkpoint, metadata, new_config):
        return await asyncio.to_thread(
            self.put, config, checkpoint, metadata, new_config
        )

    async def aput_writes(self, config, writes, task_id, task_path=None):
        return await asyncio.to_thread(
            self.put_writes, config, writes, task_id, task_path
        )

    async def alist(self, config, *, filter=None, before=None, limit=None):
        # list() est un GENERATOR synchrone — on matérialise dans le
        # thread ( impossible de yield depuis to_thread ).
        def _collect():
            return list(
                self.list(config, filter=filter, before=before, limit=limit)
            )

        return await asyncio.to_thread(_collect)


class AsyncCompatPostgresStore(PostgresStore):
    """PostgresStore + API async — double usage sync/async."""

    async def aget(self, namespace, key):
        return await asyncio.to_thread(self.get, namespace, key)

    async def aput(self, namespace, key, value, index=None):
        await asyncio.to_thread(self.put, namespace, key, value, index)

    async def adelete(self, namespace, key):
        await asyncio.to_thread(self.delete, namespace, key)

    async def asearch(self, namespace_prefix, *, filter=None, limit=10, offset=0):
        return await asyncio.to_thread(
            self.search,
            namespace_prefix,
            filter=filter,
            limit=limit,
            offset=offset,
        )

    async def abatch(self, ops):
        return await asyncio.to_thread(self.batch, ops)

    async def alist_namespaces(
        self, *, prefix=None, suffix=None, max_depth=None, limit=100, offset=0
    ):
        return await asyncio.to_thread(
            self.list_namespaces,
            prefix=prefix,
            suffix=suffix,
            max_depth=max_depth,
            limit=limit,
            offset=offset,
        )


def get_checkpointer():
    """Checkpointer LangGraph ( singleton ) — PostgresSaver.

    Le graphe parent est le SEUL a detenir un checkpointer ; le
    sous-graphe create_agent en herite ( regle §26/§63 ).
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    with _lock:
        if _checkpointer is None:
            # from_conn_string est un CONTEXT MANAGER : hors d'un
            # `with`, la connexion sous-jacente est FERMEE des la
            # sortie de __enter__ ( "the connection is closed" au
            # premier put/get ). On construit donc le pool psycopg3
            # SOI-MEME et on le passe au constructeur — PostgresSaver
            # accepte un ConnectionPool en guise de conn et prend une
            # connexion par operation. Le pool vit aussi longtemps que
            # le singleton : exactement ce dont on a besoin au niveau
            # process. Conninfo psycopg BRUTE ( pas d'URL SQLAlchemy ).
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool

            _checkpoint_pool = ConnectionPool(
                _postgres_conninfo(),
                min_size=1,
                max_size=8,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                },
            )
            # open() avant setup() : le pool doit pouvoir servir une
            # connexion pour creer les tables.
            _checkpoint_pool.open()
            # Sous-classe de PostgresSaver : API sync héritée + méthodes
            # async ajoutées ( voir AsyncCompatPostgresSaver ).
            _checkpointer = AsyncCompatPostgresSaver(_checkpoint_pool)
            # setup() = creation idempotente des tables
            # checkpoints / checkpoint_blobs / checkpoint_writes.
            _checkpointer.setup()
    return _checkpointer


def get_persistent_store():
    """Store longue duree LangGraph ( singleton ) — PostgresStore.

    Utilise par la memoire utilisateur ( profils + MemoryFacts ), range par
    namespaces ( "users", "profile", <user_id> ).
    """
    global _store
    if _store is not None:
        return _store
    with _lock:
        if _store is None:
            # PostgresStore vit dans le paquet langgraph-checkpoint-
            # postgres ( pas de paquet separe ). Comme pour le
            # checkpointer, on construit le pool psycopg3 SOI-MEME et on
            # le passe au constructeur : from_conn_string est un context
            # manager, et hors d'un `with` la connexion est fermee.
            # setup() = creation idempotente de store_postgres.
            from psycopg_pool import ConnectionPool

            # ⚠️ psycopg décode jsonb → objets Python par défaut ;
            # langgraph._json_loads attend bytes / orjson.Fragment
            # ( orjson.loads(objet) → JSONDecodeError sur CHAQUE
            # lecture du store : faits mémoire, observations
            # learning… ). Loader IDENTITÉ : psycopg rend les bytes
            # JSON bruts, langgraph fait le orjson.loads lui-même —
            # insensible aux variations d'attributs Fragment entre
            # versions d'orjson.
            from psycopg.types.json import set_json_loads

            def _configure_conn(conn):
                set_json_loads(lambda raw: raw, context=conn)

            _store_pool = ConnectionPool(
                _postgres_conninfo(),
                min_size=1,
                max_size=8,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                },
                configure=_configure_conn,
            )
            _store_pool.open()
            _store = AsyncCompatPostgresStore(_store_pool)
            _store.setup()
    return _store


def is_postgres_persistence() -> bool:
    """Toujours True — SQLite retiré, Neon est la seule persistance.

    Conservé pour les callers ( logs de démarrage ) : la fonction
    disparaitra avec eux.
    """
    _require_database_url()
    return True


__all__ = [
    "get_checkpointer",
    "get_persistent_store",
    "init_persistence",
    "is_postgres_persistence",
]
