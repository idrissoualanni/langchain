# Document Subgraph — DocumentState typé (§30).
#
# State INTERNE du subgraph : jamais exposé au Main Graph (§5).
# L'action documentaire (upload/search/list/delete) arrive par
# `payload.action` ; la sortie (DocumentResult §8) est produite via le
# canal `workflow_result`. Le pipeline est DÉTERMINISTE : il appelle la
# couche RAG existante (services/documents) sans aucun LLM.
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph.message import add_messages


class DocumentState(TypedDict, total=False):
    """État interne du DocumentSubgraph (§30).

    Champs publics partagés (entrée/sortie) :
      user_id / thread_id / query        : entrée run
      workflow_result                    : sortie (DocumentResult §8)
      messages                           : history (optionnelle)

    Champs INTERNES (jamais propagés au Main Graph) :
      action / filename / content / doc_id / search_query / top_k /
      chunk_count / data / error
    """

    # --- Entrée (partagée) ---
    user_id: str
    thread_id: str
    query: str

    # --- Sortie (partagée) : DocumentResult.model_dump() (§8) ---
    workflow_result: dict

    # --- History (partagée, optionnelle) ---
    messages: Annotated[list, add_messages]

    # --- Interne : pilotage de l'action ---
    action: str            # upload | search | list | delete
    payload: dict          # payload brut depuis le Main State

    # --- Interne : paramètres de l'opération ---
    filename: str
    content: str
    doc_id: str
    search_query: str
    top_k: int

    # --- Interne : résultat de l'opération RAG ---
    chunk_count: int
    data: Any              # sortie brute (record, hits, liste…)
    error: str             # message d'échec fail-safe (§15)


__all__ = ["DocumentState"]