# Tools de l'agent — repris de ap.py, log_event structuré au lieu de logger brut
from langchain_core.tools import tool

from app.agent.memory import (
    delete_fact,
    list_facts,
    read_profile,
    save_fact,
    search_facts,
    update_fact,
    write_profile,
)
from app.logging.events import log_event


@tool
def additionner(
    a: float,
    b: float,
) -> float:
    """Additionne deux nombres."""

    log_event(
        "TOOL_CALL",
        message=f"additionner a={a} b={b}",
        tool_name="additionner",
    )

    result = a + b

    log_event(
        "TOOL_RESULT",
        message=f"additionner result={result}",
        tool_name="additionner",
    )

    return result


@tool
def calculer_longueur_texte(
    texte: str,
) -> int:
    """Calcule le nombre de caractères."""

    log_event(
        "TOOL_CALL",
        message="calculer_longueur_texte",
        tool_name="calculer_longueur_texte",
    )

    result = len(texte)

    log_event(
        "TOOL_RESULT",
        message=f"longueur={result}",
        tool_name="calculer_longueur_texte",
    )

    return result


@tool
def recherche_web(
    query: str,
    max_results: int = 3,
) -> str:
    """Effectue une recherche web structurée (V6.5) et renvoie
    les résultats pertinents : titre, URL, extrait et score de
    pertinence pour chacun — jamais une chaîne concaténée brute.
    Indique clairement si la recherche est indisponible ou
    sans résultat pertinent."""

    log_event(
        "TOOL_CALL",
        message=f"recherche_web query={query}",
        tool_name="recherche_web",
    )

    from app.context.web_search import web_search

    response = web_search(
        user_query=query,
        subject=None,
        topic=None,
        language="fr",
        top_k=max_results,
    )

    log_event(
        "TOOL_RESULT",
        message=(
            f"recherche_web status={response.status} "
            f"results={len(response.results)}"
        ),
        tool_name="recherche_web",
    )

    if response.status == "unavailable":
        return (
            "Recherche web indisponible (service ou clé absente). "
            "Réponds avec tes connaissances générales et signale-le."
        )
    if response.status == "error":
        return (
            "Erreur de recherche web. Réponds avec tes "
            "connaissances générales et signale-le."
        )
    if not response.results:
        return (
            "Recherche web : aucun résultat pertinent trouvé. "
            "Réponds avec tes connaissances générales et signale-le."
        )

    lines = []
    for i, r in enumerate(response.results, 1):
        lines.append(
            f"[{i}] {r.title}\n    URL : {r.url}\n"
            f"    Pertinence : {r.relevance:.2f}\n"
            f"    {r.snippet or r.content[:200]}"
        )
    return "\n\n".join(lines)


tools = [
    additionner,
    calculer_longueur_texte,
    recherche_web,
]


# ------------------------------------------------------------------
# Mémoire longue durée — profil utilisateur (cross-thread)
# ------------------------------------------------------------------


@tool
def get_user_profile(user_id: str) -> dict:
    """Récupère le profil longue durée de l'utilisateur.

    Retourne {"name": ..., "description": ...} — valeurs null
    si aucun profil n'a encore été enregistré pour cet utilisateur.
    Le profil est persistant : il est partagé entre tous les threads
    de cet utilisateur.
    """

    profile = read_profile(user_id)

    if profile["name"] is None and profile["description"] is None:
        return (
            "Aucun profil longue durée n'existe encore pour cet "
            "utilisateur (name=null, description=null)."
        )

    return profile


@tool
def update_user_profile(
    user_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict:
    """Crée ou met à jour le profil longue durée de l'utilisateur.

    Champs autorisés uniquement : name, description.
    Passer None (ou omettre) un champ le laisse inchangé.
    Le profil est persistant et partagé entre tous les threads
    de cet utilisateur.
    """

    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description

    if not fields:
        return "Aucun champ à mettre à jour (name et description vides)."

    return write_profile(user_id, fields)


# ------------------------------------------------------------------
# MemoryFacts v3 — faits individuels par catégorie
# ------------------------------------------------------------------


@tool
def get_user_memory(
    user_id: str,
    category: str | None = None,
) -> list:
    """Liste les faits mémorisés de l'utilisateur (mémoire longue durée).

    Args:
        user_id: identifiant persistant de l'utilisateur.
        category: filtrer par catégorie parmi
            identity, background, personality, preference, interest.
            None = toutes les catégories.

    Retourne la liste des faits (id, category, content, source,
    confidence, created_at, updated_at) — liste vide si aucune
    mémoire. Ces faits sont partagés entre tous les threads
    de l'utilisateur.
    """
    return list_facts(user_id, category)


@tool
def save_user_memory(
    user_id: str,
    category: str,
    content: str,
    confidence: float = 1.0,
) -> dict:
    """Enregistre UN nouveau fait durable sur l'utilisateur.

    À utiliser UNIQUEMENT quand l'utilisateur déclare explicitement
    une information durable sur lui-même (nom, formation, préférence
    d'apprentissage, centre d'intérêt, trait de caractère).
    Ne jamais enregistrer une question, un calcul ou une demande
    ponctuelle.

    Args:
        user_id: identifiant persistant de l'utilisateur.
        category: identity | background | personality |
            preference | interest.
        content: le fait en une phrase courte, à la 3e personne
            (ex: "Étudiant en mécatronique",
            "Préfère les explications avec des exemples").
        confidence: 1.0 pour une déclaration explicite de
            l'utilisateur (défaut), moins si déduit.

    La déduplication est automatique : un fait similaire existant
    sera mis à jour au lieu d'être dupliqué.
    """
    return save_fact(
        user_id, category, content, source="user", confidence=confidence
    )


@tool
def update_user_memory(
    user_id: str,
    memory_id: str,
    content: str | None = None,
    category: str | None = None,
) -> dict:
    """Modifie UN fait précis de la mémoire, ciblé par son id.

    Ne modifie QUE ce fait — les autres restent intacts.
    Args:
        user_id: identifiant persistant de l'utilisateur.
        memory_id: id du fait à modifier.
        content: nouveau contenu (None = inchangé).
        category: nouvelle catégorie (None = inchangée).
    """
    return update_fact(
        user_id, memory_id, content=content, category=category
    )


@tool
def delete_user_memory(user_id: str, memory_id: str) -> dict:
    """Supprime UN fait précis de la mémoire, ciblé par son id.

    Ne supprime QUE ce fait — les autres souvenirs et le profil
    de l'utilisateur restent intacts.
    Args:
        user_id: identifiant persistant de l'utilisateur.
        memory_id: id du fait à supprimer.
    """
    return delete_fact(user_id, memory_id)


@tool
def search_user_memory(
    user_id: str,
    query: str,
    category: str | None = None,
) -> list:
    """Recherche les faits mémorisés pertinents pour une requête.

    Args:
        user_id: identifiant persistant de l'utilisateur.
        query: requête en langage naturel
            (ex: "préférences d'apprentissage").
        category: filtrer en plus par catégorie (optionnel).

    Retourne les faits classés par pertinence (liste vide si
    aucun résultat).
    """
    return search_facts(user_id, query, category=category)


memory_tools = [
    get_user_profile,
    update_user_profile,
    get_user_memory,
    save_user_memory,
    update_user_memory,
    delete_user_memory,
    search_user_memory,
]

# ------------------------------------------------------------------
# V4.1 — Tools pédagogiques communs (implémentations RÉELLES
# branchées sur la base knowledge — pas des simulations)
# ------------------------------------------------------------------

from app.agent.learning_tools import learning_tools  # noqa: E402
from app.agent.pedagogical_tools import pedagogical_tools  # noqa: E402

# V5.2 — capability tools de pratique du code (execute_code /
# run_tests / analyze_code). Disponibles UNIQUEMENT si le
# SubjectConfig les déclare (garde interne, §37) — le modèle les
# voit, mais chaque appel vérifie l'autorisation du subject.
from app.agent.code_tools import code_tools  # noqa: E402

all_tools = (
    tools
    + memory_tools
    + pedagogical_tools
    + learning_tools
    + code_tools
)
