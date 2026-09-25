"""Persistance LangGraph ( checkpointer + store ) — SQLite ou PostgreSQL.

UN SEUL ENDROIT decide du dialecte : ce module. Toute la couche LangGraph
( checkpointer du graphe parent, store de memoire longue duree ) y demande
son backend en fonction de DATABASE_URL, exactement comme
app.infrastructure.database.connections le fait pour users/threads.

Avant ce module, le grappe utilisait SqliteSaver et SqliteStore en DUR,
ignorant DATABASE_URL : en production ( Neon ), les checkpoints et la
memoire s'ecrivaient dans des fichiers locaux ephemeres du conteneur
Render — perdus a chaque redéploiement, et invisibles du dashboard admin
qui, lui, interrogeait Neon ( table absente → statistiques a zero ).

API :
    get_checkpointer()      -> SqliteSaver | PostgresSaver
    get_persistent_store()  -> SqliteStore  | PostgresStore

Les deux exposes .setup() ( creation idempotente des tables ) et la MEME
interface put/get/search : les callers n'ont aucune modification a faire.
"""
from __future__ import annotations

import sqlite3
import threading

from app.config import (
    CHECKPOINTS_DB_PATH,
    DATABASE_URL,
    LONG_TERM_DB_PATH,
    USE_POSTGRES,
)
from app.logging.events import log_event


_lock = threading.RLock()
_checkpointer = None
_store = None
# Connexions sqlite3 brutes : gardees en singleton pour etre fermees
# proprement ( les Savers/Stores ne les possedent pas ).
_sqlite_conn_checkpoint: sqlite3.Connection | None = None
_sqlite_conn_store: sqlite3.Connection | None = None

# Marqueur de la premiere initialisation ( log unique au demarrage ).
_initialized = False


def _postgres_url() -> str:
    """DATABASE_URL normalisee pour SQLAlchemy / pgvector ( scheme psycopg3 ).

    Neon expose postgres:// ou postgresql:// ; SQLAlchemy et pgvector
    attendent postgresql+psycopg://. On reecrit seulement le scheme :
    le reste ( credentials, host, sslmode ) est preserve. Reflechit la
    logique de connections._postgres_url — pas de duplication des
    engines, juste la normalisation d'URL.
    """
    scheme, rest = DATABASE_URL.split("://", 1)
    if scheme in ("postgres", "postgresql"):
        return f"postgresql+psycopg://{rest}"
    return DATABASE_URL


def _postgres_conninfo() -> str:
    """Conninfo psycopg BRUTE pour langgraph ( PostgresSaver/PostgresStore ).

    from_conn_string passe l'URL telle quelle a psycopg.Connection.connect
    — qui ne comprend NI "postgresql+psycopg://" ( SQLAlchemy ), NI les
    query params au format URL. Il faut donc un scheme postgresql:// pur,
    sans driver. Quelle que soit l'ecriture d'origine ( postgres:// ,
    postgresql:// , postgresql+psycopg:// ), on prend ce qui suit "://".
    """
    _scheme, rest = DATABASE_URL.split("://", 1)
    # Si l'URL d'origine etait deja "postgresql+psycopg://h", rest ne
    # contient PAS de "://" — on renvoie donc directement.
    if "://" in rest:
        rest = rest.split("://", 1)[1]
    return f"postgresql://{rest}"


def _ensure_vector_extension() -> None:
    """Active l'extension pgvector sur Neon ( idempotent ).

    pgvector est necessaire des qu'une colonne vector(dim) est utilisee
    ( RAG documents, segments video, corpus knowledge ). L'extension est
    inoffensive a activer ; on ne l'active QU'EN MODE POSTGRES.

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

        if USE_POSTGRES and DATABASE_URL:
            _ensure_vector_extension()
            _checkpointer = get_checkpointer()
            _store = get_persistent_store()
            log_event(
                "PERSISTENCE_INIT",
                message=(
                    "Persistence LangGraph sur PostgreSQL (Neon) — "
                    "checkpointer=PostgresSaver | store=PostgresStore"
                ),
            )
        else:
            _checkpointer = get_checkpointer()
            _store = get_persistent_store()
            log_event(
                "PERSISTENCE_INIT",
                message=(
                    "Persistence LangGraph sur SQLite locale — "
                    f"checkpoints={CHECKPOINTS_DB_PATH} | "
                    f"store={LONG_TERM_DB_PATH}"
                ),
            )
        _initialized = True


def get_checkpointer():
    """Checkpointer LangGraph ( singleton ) — PostgresSaver ou SqliteSaver.

    Le graphe parent est le SEUL a detenir un checkpointer ; le
    sous-graphe create_agent en herite ( regle §26/§63 ).
    """
    global _checkpointer, _sqlite_conn_checkpoint
    if _checkpointer is not None:
        return _checkpointer
    with _lock:
        if _checkpointer is None:
            if USE_POSTGRES and DATABASE_URL:
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
                _checkpointer = PostgresSaver(_checkpoint_pool)
                # setup() = creation idempotente des tables
                # checkpoints / checkpoint_blobs / checkpoint_writes.
                _checkpointer.setup()
            else:
                from langgraph.checkpoint.sqlite import SqliteSaver

                # Connexion partagee entre instances ( une seule,
                # check_same_thread=False ) — le graphe peut etre instancie
                # plusieurs fois ( ModelSelector ) mais persiste dans le
                # meme fichier.
                _sqlite_conn_checkpoint = sqlite3.connect(
                    CHECKPOINTS_DB_PATH, check_same_thread=False
                )
                _checkpointer = SqliteSaver(_sqlite_conn_checkpoint)
    return _checkpointer


def get_persistent_store():
    """Store longue duree LangGraph ( singleton ) — PostgresStore ou SqliteStore.

    Utilise par la memoire utilisateur ( profils + MemoryFacts ), range par
    namespaces ( "users", "profile", <user_id> ). L'interface put/get est
    STRICTEMENT identique entre les deux backends — les callers de la
    memoire n'ont aucun changement a faire.
    """
    global _store, _sqlite_conn_store
    if _store is not None:
        return _store
    with _lock:
        if _store is None:
            if USE_POSTGRES and DATABASE_URL:
                # PostgresStore vit dans le paquet langgraph-checkpoint-
                # postgres ( pas de paquet separe ) et expose la meme API
                # que SqliteStore. Comme pour le checkpointer, on construit
                # le pool psycopg3 SOI-MEME et on le passe au constructeur :
                # from_conn_string est un context manager, et hors d'un
                # `with` la connexion est fermee. setup() = creation
                # idempotente de store_postgres.
                from langgraph.store.postgres import PostgresStore
                from psycopg_pool import ConnectionPool

                _store_pool = ConnectionPool(
                    _postgres_conninfo(),
                    min_size=1,
                    max_size=8,
                    kwargs={
                        "autocommit": True,
                        "prepare_threshold": 0,
                    },
                )
                _store_pool.open()
                _store = PostgresStore(_store_pool)
                _store.setup()
            else:
                from langgraph.store.sqlite import SqliteStore

                # SqliteStore gere ses propres BEGIN/COMMIT : le mode
                # auto-transaction de Python ( isolation_level="" ) laisse
                # une transaction ouverte apres setup() → "cannot start a
                # transaction within a transaction" au premier put/get.
                # Autocommit = fix (cf. memory.py avant refactor).
                _sqlite_conn_store = sqlite3.connect(
                    LONG_TERM_DB_PATH, check_same_thread=False
                )
                _sqlite_conn_store.isolation_level = None
                _store = SqliteStore(_sqlite_conn_store)
                _store.setup()
    return _store


def is_postgres_persistence() -> bool:
    """True si la persistance LangGraph s'ecrit sur Neon ( PostgreSQL )."""
    return bool(USE_POSTGRES and DATABASE_URL)


__all__ = [
    "get_checkpointer",
    "get_persistent_store",
    "init_persistence",
    "is_postgres_persistence",
]
