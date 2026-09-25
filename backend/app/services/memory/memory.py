import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher

from langgraph.store.sqlite import SqliteStore

from app.config import DATABASE_DIR, log_safe
from app.infrastructure.cache.ttl import TTLCache
from app.logging.events import log_event

# Fichier store séparé du checkpointer — jamais partagé
LONG_TERM_DB_PATH = DATABASE_DIR / "long_term_memory.db"

# Champs autorisés du profil v2 — validation stricte, rien d'autre
PROFILE_FIELDS = ("name", "description")

# Catégories de MemoryFacts — extensibles : ajouter ici suffit
FACT_CATEGORIES = (
    "identity",
    "background",
    "personality",
    "preference",
    "interest",
)

# Sources possibles (v3 n'utilise que "user" — les autres sont réservées)
FACT_SOURCES = ("user", "inferred", "system", "teacher")

# Namespace racine commun à toute la mémoire utilisateur
NAMESPACE_LABEL = "users/profile"

# Seuil de similarité pour la déduplication (0..1)
DEDUP_THRESHOLD = 0.72

_store: SqliteStore | None = None
_store_lock = threading.RLock()

# Cache de la mémoire longue durée : le profil et les faits d'un
# utilisateur sont relus à chaque entrée de session vocale
# ( _build_instructions_async ) et à chaque message du chat. Ces
# données ne changent qu'en ÉCRITURE ( save_fact / update_fact /
# delete_fact / écriture profil ) — les fonctions qui écrivent
# invalident explicitement ( invalidate_memory_cache ), et la TTL de
# 5 min cicatrise toute invalidation oubliée.
#
# ⚠ Ne JAMAIS cacher des résultats LLM ( pédagogie adaptative ) ni les
# states de thread ( le checkpointer est la source de vérité ).
_memory_cache = TTLCache(ttl_seconds=300)


def _cache_key_profile(user_id: str) -> str:
    return f"mem:{user_id}:profile"


def _cache_key_facts(user_id: str) -> str:
    return f"mem:{user_id}:facts"


def invalidate_memory_cache(user_id: str) -> None:
    """Invalide profil + faits d'un utilisateur.

    À appeler à chaque écriture mémoire — déjà câblée sur les
    fonctions d'écriture publiques via _save_facts / l'écriture profil.
    """
    _memory_cache.invalidate(_cache_key_profile(user_id))
    _memory_cache.invalidate(_cache_key_facts(user_id))

# Stop-words français/anglais retirés avant comparaison de similarité
_STOP_WORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "d", "l",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "me", "moi", "ma", "mon", "mes", "te", "toi", "ta", "ton", "tes",
    "sa", "son", "ses", "notre", "nos", "votre", "vos", "leur", "leurs",
    "et", "ou", "en", "y", "a", "au", "aux", "avec", "sans", "dans",
    "pour", "par", "sur", "suis", "es", "est", "sont", "etre", "être",
    "j", "m", "t", "c", "s", "n", "ce", "cet", "cette", "que", "qui",
    "quoi", "aime", "aime", "les", "the", "is", "are", "am", "my",
    "i", "in", "of", "and", "me",
}


def _now() -> str:
    """Timestamp ISO 8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


def _fact_id() -> str:
    """Identifiant unique court d'un MemoryFact."""
    return uuid.uuid4().hex[:12]


def _profile_namespace(user_id: str) -> tuple[str, ...]:
    """Namespace de la mémoire : ("users", "profile", user_id)."""
    return ("users", "profile", user_id)


def _normalize(text: str) -> str:
    """Normalise un contenu pour la comparaison de dédup.

    Minuscules, sans accents, sans ponctuation, sans stop-words,
    trié (l'ordre des mots n'a pas d'importance pour la similarité).
    """
    s = text.lower()
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[àâä]", "a", s)
    s = re.sub(r"[îï]", "i", s)
    s = re.sub(r"[ôö]", "o", s)
    s = re.sub(r"[ùûü]", "u", s)
    s = re.sub(r"[ç]", "c", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    words = [w for w in s.split() if w and w not in _STOP_WORDS]
    return " ".join(sorted(words))


def _similarity(a: str, b: str) -> float:
    """Similarité entre deux contenus (0..1).

    Combine deux vues complémentaires sur les contenus normalisés :
    1. Overlap coefficient des mots-clé (≥5 chars, hors stop-words) :
       |A∩B| / min(|A|,|B|) — détecte les reformulations du même fait
       ("Aime la robotique" ≈ "S'intéresse à la robotique") et les
       enrichissements ("Aime la robotique" ≈ "Aime la robotique et
       l'IA embarquée"), dans les deux sens.
    2. Ratio SequenceMatcher sur la chaîne triée — reformulations proches.
    Le max des deux est retourné. Conservateur par défaut : deux faits
    partageant un seul mot-clé générique sur plusieurs ne dédupent pas.
    """
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    # --- Vue 1 : overlap coefficient des mots signifiants (≥5 chars) ---
    ka = {w for w in na.split() if len(w) >= 5}
    kb = {w for w in nb.split() if len(w) >= 5}
    overlap = 0.0
    if ka and kb:
        shared = ka & kb
        if shared:
            overlap = len(shared) / min(len(ka), len(kb))

    # --- Vue 2 : ratio SequenceMatcher (ordre trié) ---
    ratio = SequenceMatcher(None, na, nb).ratio()

    return max(overlap, ratio)


def _fact_relevance(fact_content: str, query: str) -> float:
    """Pertinence d'un fait pour une requête (scoring de recherche).

    V10 — HYBRIDE : combine la vue lexicale (containment mots +
    reformulation SequenceMatcher) ET la vue sémantique (cosine
    sur le provider embeddings partagé), comme le hybrid_ranker
    V7.1 (§10) avec une pondération documentée :
       final = 0.60 * lexical + 0.40 * sémantique
    La part sémantique est FACULTATIVE : si le provider est
    indisponible (erreur), on retombe sur le seul lexical —
    jamais d'exception (§15 fail-safe).

    - Containment des mots signifiants (≥3 chars, hors stop-words)
      de la requête présents dans le fait : 1.0 si tous y sont.
    - À défaut, reformulation complète : similarité globale ≥ 0.5
      (évite le bruit SequenceMatcher sur chaînes courtes).
    """
    nq = _normalize(query)
    nc = _normalize(fact_content)
    if not nq or not nc:
        return 0.0
    qw = {w for w in nq.split() if len(w) >= 3}
    if not qw:
        return 0.0
    cw = set(nc.split())
    containment = len(qw & cw) / len(qw)
    if containment > 0:
        lex = containment
    else:
        sim = _similarity(fact_content, query)
        lex = sim if sim >= 0.5 else 0.0

    sem = _semantic_relevance(fact_content, query)
    if sem is None:
        return lex
    return 0.60 * lex + 0.40 * sem


def _semantic_relevance(
    fact_content: str, query: str
) -> float | None:
    """Vue sémantique (cosine provider embeddings) — None si KO.

    Import lazy : évite le cycle app.services.agent → app.services.context → memory.
    Échec → None (fallback lexical, jamais d'exception).
    """
    try:
        from app.services.context.semantic.provider import (
            cosine_similarity,
            get_embedding_provider,
        )

        provider = get_embedding_provider()
        qv = provider.embed_text(query)
        fv = provider.embed_text(fact_content)
        return cosine_similarity(qv, fv)
    except Exception:
        return None


def get_store() -> SqliteStore:
    """Singleton SqliteStore — initialisé au startup, thread-safe.

    Tous les accès (get/put) passent par _store_lock : la connexion
    sqlite3 partagée ne supporte pas les transactions concurrentes
    depuis plusieurs threads executor ("cannot start a transaction
    within a transaction").
    """
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            conn = sqlite3.connect(
                LONG_TERM_DB_PATH, check_same_thread=False
            )
            # CRITIQUE : le SqliteStore gère ses propres BEGIN/COMMIT
            # explicites. Le mode auto-transaction par défaut de Python
            # (isolation_level="") laisse une transaction ouverte après
            # setup() → "cannot start a transaction within a transaction"
            # sur chaque put/get. Mode autocommit = fix.
            conn.isolation_level = None
            _store = SqliteStore(conn)
            # setup() = migrations (tables/index) — requis avant usage
            _store.setup()
            log_event(
                "MEMORY_STORE_INIT",
                message=(
                    f"SqliteStore long-term memory on "
                    f"{LONG_TERM_DB_PATH} | namespace={NAMESPACE_LABEL}"
                ),
            )
    return _store


# ------------------------------------------------------------------
# Lecture / écriture brutes (toujours sous _store_lock)
# ------------------------------------------------------------------


def _load_facts(user_id: str) -> list[dict]:
    """Charge la liste brute des MemoryFacts (sans validation)."""
    store = get_store()
    item = store.get(_profile_namespace(user_id), "facts")
    if item is None or not item.value:
        return []
    facts = item.value
    if isinstance(facts, list):
        return [f for f in facts if isinstance(f, dict)]
    return []


def _save_facts(user_id: str, facts: list[dict]) -> None:
    store = get_store()
    store.put(_profile_namespace(user_id), "facts", facts)
    # Invalide le cache : list_facts/memory_overview serviraient des
    # données périmées sinon ( une écriture sans invalidation = bug sourd ).
    invalidate_memory_cache(user_id)


# ------------------------------------------------------------------
# Profil v2 (conservé — rétro-compatibilité)
# ------------------------------------------------------------------


def read_profile(user_id: str) -> dict:
    """Lit le profil v2 (name/description) depuis le store.

    Retourne TOUJOURS {"name": ..., "description": ...} —
    valeurs None si aucun profil n'existe encore.
    Émet MEMORY_READ (ou MEMORY_READ_ERROR).
    """
    thread_id = _current_thread_id()
    try:
        with _store_lock:
            store = get_store()
            item = store.get(_profile_namespace(user_id), "profile")

        if item is None:
            profile = {"name": None, "description": None}
            log_event(
                "MEMORY_READ",
                message=f"Profile not found | user={user_id}",
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "namespace": NAMESPACE_LABEL,
                    "operation": "read",
                    "result": "not_found",
                },
            )
        else:
            value = item.value or {}
            profile = {
                "name": value.get("name"),
                "description": value.get("description"),
            }
            log_event(
                "MEMORY_READ",
                message=(
                    f"Profile read | user={user_id} | "
                    f"name={log_safe(value.get('name'))}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "namespace": NAMESPACE_LABEL,
                "operation": "read",
                "result": "found",
            },
        )
        _memory_cache.set(_cache_key_profile(user_id), profile)
        return profile

    except Exception as exc:
        log_event(
            "MEMORY_READ_ERROR",
            level="ERROR",
            message=f"Profile read failed | user={user_id} | {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "read",
                "error": str(exc)[:300],
            },
        )
        raise


def write_profile(
    user_id: str,
    fields: dict,
    thread_id: str = "",
) -> dict:
    """Crée ou met à jour le profil v2 — champs name/description uniquement.

    - Fusion avec le profil existant (update partiel possible)
    - Validation stricte : tout champ hors PROFILE_FIELDS → ValueError
    - Émet MEMORY_WRITE (ou MEMORY_WRITE_ERROR)
    """
    # --- Validation stricte AVANT toute écriture ---
    invalid = [k for k in fields if k not in PROFILE_FIELDS]
    if invalid:
        raise ValueError(
            f"Champs non autorisés : {invalid}. "
            f"Champs autorisés : {list(PROFILE_FIELDS)}"
        )

    for key, value in fields.items():
        if value is not None and not isinstance(value, str):
            raise ValueError(
                f"Le champ '{key}' doit être une chaîne de caractères"
            )

    if thread_id == "":
        thread_id = _current_thread_id()

    try:
        with _store_lock:
            store = get_store()

            # Fusion avec l'existant (update partiel)
            existing = store.get(
                _profile_namespace(user_id), "profile"
            )
            profile: dict = {"name": None, "description": None}
            if existing is not None and existing.value:
                profile = {
                    "name": existing.value.get("name"),
                    "description": existing.value.get("description"),
                }

            written = [k for k in PROFILE_FIELDS if k in fields]
            profile.update(
                {k: v for k, v in fields.items() if v is not None}
            )

            store.put(
                _profile_namespace(user_id),
                "profile",
                {
                    "name": profile["name"],
                    "description": profile["description"],
                },
            )
            # Invalide le cache : read_profile/memory_overview liraient
            # un profil périmé sinon.
            invalidate_memory_cache(user_id)

        log_event(
            "MEMORY_WRITE",
            message=(
                f"Profile written | user={user_id} | "
                f"fields={','.join(written)}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "write",
                "fields": written,
            },
        )
        return profile

    except Exception as exc:
        log_event(
            "MEMORY_WRITE_ERROR",
            level="ERROR",
            message=f"Profile write failed | user={user_id} | {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "write",
                "error": str(exc)[:300],
            },
        )
        raise


# ------------------------------------------------------------------
# MemoryFacts v3 — faits individuels indépendants
# ------------------------------------------------------------------


def list_facts(
    user_id: str,
    category: str | None = None,
    thread_id: str = "",
) -> list[dict]:
    """Liste les MemoryFacts d'un utilisateur, optionnellement filtrés.

    Émet MEMORY_READ.
    """
    if thread_id == "":
        thread_id = _current_thread_id()

    # Cache : hit → on évite le store ( les écritures invalident via
    # _save_facts → invalidate_memory_cache ). On ne met en cache QUE
    # la liste complète ; un appel avec category filtre ensuite sans
    # réécrire dans le cache ( sinon la catégorie deviendrait la
    # "vérité" cachée pour les autres appels ).
    if category is None:
        cached_facts = _memory_cache.get(_cache_key_facts(user_id))
        if cached_facts is not None:
            log_event(
                "MEMORY_READ",
                message=(
                    f"Facts read (cached) | user={user_id} | "
                    f"count={len(cached_facts)}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "namespace": NAMESPACE_LABEL,
                    "operation": "read_facts",
                    "category": "all",
                    "count": len(cached_facts),
                    "cached": True,
                },
            )
            return cached_facts

    try:
        with _store_lock:
            facts = _load_facts(user_id)

        if category is not None:
            if category not in FACT_CATEGORIES:
                raise ValueError(
                    f"Catégorie inconnue : {category}. "
                    f"Catégories autorisées : {list(FACT_CATEGORIES)}"
                )
            facts = [f for f in facts if f.get("category") == category]

        log_event(
            "MEMORY_READ",
            message=(
                f"Facts read | user={user_id} | "
                f"count={len(facts)}"
                + (f" | category={category}" if category else " | all")
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "read_facts",
                "category": category or "all",
                "count": len(facts),
            },
        )
        # Ne cacher QUE la liste complète ( category=None ) : un filtre
        # par catégorie ne doit pas devenir la "vérité" des autres appels.
        if category is None:
            _memory_cache.set(_cache_key_facts(user_id), facts)
        return facts

    except Exception as exc:
        log_event(
            "MEMORY_READ_ERROR",
            level="ERROR",
            message=f"Facts read failed | user={user_id} | {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "read_facts",
                "error": str(exc)[:300],
            },
        )
        raise


def save_fact(
    user_id: str,
    category: str,
    content: str,
    source: str = "user",
    confidence: float = 1.0,
    thread_id: str = "",
) -> dict:
    """Ajoute un MemoryFact AVEC déduplication automatique.

    - Recherche un fait similaire (même catégorie, similarité ≥ seuil)
    - Si trouvé : met à jour le contenu, bumps updated_at et confidence
      (MEMORY_DEDUP + MEMORY_UPDATE) — jamais de doublon
    - Sinon : crée un nouveau fait (MEMORY_WRITE)
    """
    if category not in FACT_CATEGORIES:
        raise ValueError(
            f"Catégorie inconnue : {category}. "
            f"Catégories autorisées : {list(FACT_CATEGORIES)}"
        )
    if source not in FACT_SOURCES:
        raise ValueError(
            f"Source inconnue : {source}. "
            f"Sources autorisées : {list(FACT_SOURCES)}"
        )
    content = (content or "").strip()
    if not content:
        raise ValueError("Le contenu du fait ne peut pas être vide")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence doit être entre 0.0 et 1.0")

    if thread_id == "":
        thread_id = _current_thread_id()

    try:
        with _store_lock:
            facts = _load_facts(user_id)

            # --- Déduplication : chercher un fait similaire ---
            best = None
            best_score = 0.0
            for f in facts:
                if f.get("category") != category:
                    continue
                score = _similarity(f.get("content", ""), content)
                if score > best_score:
                    best_score = score
                    best = f

            if best is not None and best_score >= DEDUP_THRESHOLD:
                # Fait similaire existant → mettre à jour
                old_content = best.get("content", "")
                best["content"] = content
                best["updated_at"] = _now()
                best["confidence"] = max(
                    float(best.get("confidence", 0.0)), confidence
                )
                best["source"] = source
                _save_facts(user_id, facts)

                log_event(
                    "MEMORY_DEDUP",
                    message=(
                        f"Fact deduplicated | user={user_id} | "
                        f"category={category} | "
                        f"similarity={best_score:.2f}"
                    ),
                    user_id=user_id,
                    thread_id=thread_id,
                    extra={
                        "namespace": NAMESPACE_LABEL,
                        "operation": "dedup",
                        "memory_id": best.get("id"),
                        "category": category,
                        "similarity": round(best_score, 2),
                    },
                )
                log_event(
                    "MEMORY_UPDATE",
                    message=(
                        f"Fact updated (dedup) | user={user_id} | "
                        f"id={best.get('id')} | "
                        f"old={log_safe(old_content)}"
                    ),
                    user_id=user_id,
                    thread_id=thread_id,
                    extra={
                        "namespace": NAMESPACE_LABEL,
                        "operation": "update",
                        "memory_id": best.get("id"),
                        "category": category,
                    },
                )
                return best

            # --- Nouveau fait ---
            fact = {
                "id": _fact_id(),
                "category": category,
                "content": content,
                "source": source,
                "confidence": confidence,
                "created_at": _now(),
                "updated_at": _now(),
            }
            facts.append(fact)
            _save_facts(user_id, facts)

        log_event(
            "MEMORY_WRITE",
            message=(
                f"Fact saved | user={user_id} | "
                f"category={category} | id={fact['id']} | "
                f"content={log_safe(content)}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "save_fact",
                "memory_id": fact["id"],
                "category": category,
                "source": source,
                "confidence": confidence,
            },
        )
        return fact

    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        log_event(
            "MEMORY_WRITE_ERROR",
            level="ERROR",
            message=f"Fact save failed | user={user_id} | {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "save_fact",
                "error": str(exc)[:300],
            },
        )
        raise


def update_fact(
    user_id: str,
    fact_id: str,
    content: str | None = None,
    category: str | None = None,
    confidence: float | None = None,
    thread_id: str = "",
) -> dict:
    """Met à jour UN fait précis par son id — jamais la mémoire entière."""
    if content is None and category is None and confidence is None:
        raise ValueError("Rien à mettre à jour")

    if category is not None and category not in FACT_CATEGORIES:
        raise ValueError(
            f"Catégorie inconnue : {category}. "
            f"Catégories autorisées : {list(FACT_CATEGORIES)}"
        )
    if confidence is not None and not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence doit être entre 0.0 et 1.0")

    if thread_id == "":
        thread_id = _current_thread_id()

    try:
        with _store_lock:
            facts = _load_facts(user_id)
            target = next(
                (f for f in facts if f.get("id") == fact_id), None
            )
            if target is None:
                raise ValueError(f"Fait introuvable : {fact_id}")

            if content is not None:
                content = content.strip()
                if not content:
                    raise ValueError("Le contenu ne peut pas être vide")
                target["content"] = content
            if category is not None:
                target["category"] = category
            if confidence is not None:
                target["confidence"] = confidence
            target["updated_at"] = _now()
            _save_facts(user_id, facts)

        log_event(
            "MEMORY_UPDATE",
            message=(
                f"Fact updated | user={user_id} | id={fact_id} | "
                f"fields="
                + ",".join(
                    k
                    for k, v in (
                        ("content", content),
                        ("category", category),
                        ("confidence", confidence),
                    )
                    if v is not None
                )
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "update",
                "memory_id": fact_id,
                "category": target.get("category"),
            },
        )
        return target

    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        log_event(
            "MEMORY_UPDATE_ERROR",
            level="ERROR",
            message=f"Fact update failed | user={user_id} | {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "update",
                "memory_id": fact_id,
                "error": str(exc)[:300],
            },
        )
        raise


def delete_fact(
    user_id: str,
    fact_id: str,
    thread_id: str = "",
) -> dict:
    """Supprime UN fait précis — les autres restent intacts."""
    if thread_id == "":
        thread_id = _current_thread_id()
    try:
        with _store_lock:
            facts = _load_facts(user_id)
            remaining = [f for f in facts if f.get("id") != fact_id]
            if len(remaining) == len(facts):
                raise ValueError(f"Fait introuvable : {fact_id}")
            _save_facts(user_id, remaining)

        log_event(
            "MEMORY_DELETE",
            message=f"Fact deleted | user={user_id} | id={fact_id}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "delete",
                "memory_id": fact_id,
            },
        )
        return {"deleted": fact_id}

    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        log_event(
            "MEMORY_DELETE_ERROR",
            level="ERROR",
            message=f"Fact delete failed | user={user_id} | {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "delete",
                "memory_id": fact_id,
                "error": str(exc)[:300],
            },
        )
        raise


def search_facts(
    user_id: str,
    query: str,
    category: str | None = None,
    limit: int = 10,
    thread_id: str = "",
) -> list[dict]:
    """Recherche les faits pertinents pour une requête.

    Score = similarité contenu/requête (normalisée). Émet MEMORY_SEARCH.
    """
    if thread_id == "":
        thread_id = _current_thread_id()
    try:
        with _store_lock:
            facts = _load_facts(user_id)

        if category is not None:
            if category not in FACT_CATEGORIES:
                raise ValueError(
                    f"Catégorie inconnue : {category}. "
                    f"Catégories autorisées : {list(FACT_CATEGORIES)}"
                )
            facts = [f for f in facts if f.get("category") == category]

        scored = []
        for f in facts:
            score = _fact_relevance(f.get("content", ""), query)
            if score >= 0.25:
                scored.append((score, f))

        scored.sort(key=lambda t: t[0], reverse=True)
        results = [f for _, f in scored[:limit]]

        log_event(
            "MEMORY_SEARCH",
            message=(
                f"Facts search | user={user_id} | "
                f"query={log_safe(query)} | results={len(results)}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "search",
                "query": query[:100],
                "results": len(results),
                "category": category or "all",
            },
        )
        return results

    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        log_event(
            "MEMORY_SEARCH_ERROR",
            level="ERROR",
            message=f"Facts search failed | user={user_id} | {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "namespace": NAMESPACE_LABEL,
                "operation": "search",
                "error": str(exc)[:300],
            },
        )
        raise


def _current_thread_id() -> str:
    """thread_id courant depuis la config LangGraph (si disponible)."""
    try:
        from langgraph.config import get_config

        cfg = get_config() or {}
        return (cfg.get("configurable") or {}).get("thread_id", "")
    except Exception:
        return ""


# ------------------------------------------------------------------
# Variantes API (ne lèvent jamais)
# ------------------------------------------------------------------


def read_profile_for_api(user_id: str) -> dict:
    """Variante API : ne lève jamais — retourne le dict complet."""
    try:
        profile = read_profile(user_id)
        return {
            "user_id": user_id,
            "name": profile["name"],
            "description": profile["description"],
            "exists": profile["name"] is not None
            or profile["description"] is not None,
        }
    except Exception:
        return {
            "user_id": user_id,
            "name": None,
            "description": None,
            "exists": False,
        }


def memory_overview_for_api(user_id: str) -> dict:
    """Vue complète pour le frontend : profil + faits groupés par catégorie."""
    try:
        profile = read_profile(user_id)
    except Exception:
        profile = {"name": None, "description": None}
    try:
        facts = list_facts(user_id)
    except Exception:
        facts = []

    by_category: dict[str, list[dict]] = {
        cat: [] for cat in FACT_CATEGORIES
    }
    for f in facts:
        cat = f.get("category")
        if cat in by_category:
            by_category[cat].append(f)

    return {
        "user_id": user_id,
        "identity": {
            "name": profile["name"],
            "description": profile["description"],
        },
        "facts_by_category": by_category,
        "total_facts": len(facts),
        "categories": list(FACT_CATEGORIES),
    }
