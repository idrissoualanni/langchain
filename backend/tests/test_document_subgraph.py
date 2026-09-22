# Tests pour le DocumentSubgraph (§30) — pipeline déterministe.
#
# Couvre le cycle complet upload → search → list → delete avec la
# couche RAG réelle (SQLite temporaire) : statut DocumentResult §8,
# fail-safe (action invalide, doc absent, contenu vide), et le contrat
# workflow_result pour le Main Graph.
import uuid

import pytest
import pytest_asyncio

from app.graph.subgraphs.document import (
    ACTIONS,
    DocumentResult,
    compile_document_subgraph,
    run_document_workflow,
)
from app.services.documents.vector_store import get_rag_store


@pytest.fixture()
def user_id() -> str:
    """Identifiant unique par test — la base RAG persiste sur disque,
    l'isolation est donc garantie par user_id (jamais partagé)."""
    return f"u_doc_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def _purge(user_id):
    yield
    get_rag_store().delete_all(user_id)


def test_compile_document_subgraph():
    graph = compile_document_subgraph()
    nodes = set(graph.get_graph().nodes)
    assert {"validate_action", "dispatch", "finalize", "__start__", "__end__"} <= nodes


def test_actions_exposees():
    assert set(ACTIONS) == {"upload", "search", "list", "delete"}


@pytest.mark.asyncio
async def test_cycle_upload_search_list_delete(user_id, _purge):
    uploaded = await run_document_workflow(
        user_id=user_id,
        thread_id="t_doc",
        payload={
            "action": "upload",
            "filename": "cours-python.md",
            "content": "La boucle for en Python itère sur une séquence.",
        },
    )
    assert uploaded.status == "ok"
    assert uploaded.action == "upload"
    assert uploaded.doc_id
    assert uploaded.chunk_count >= 1

    found = await run_document_workflow(
        user_id=user_id,
        thread_id="t_doc",
        payload={"action": "search", "search_query": "boucle for"},
    )
    assert found.status == "ok"
    assert found.action == "search"
    assert found.chunk_count >= 1

    listed = await run_document_workflow(
        user_id=user_id,
        thread_id="t_doc",
        payload={"action": "list"},
    )
    assert listed.status == "ok"
    assert listed.action == "list"
    assert listed.chunk_count >= uploaded.chunk_count

    deleted = await run_document_workflow(
        user_id=user_id,
        thread_id="t_doc",
        payload={"action": "delete", "doc_id": uploaded.doc_id},
    )
    assert deleted.status == "ok"
    assert deleted.action == "delete"

    listed_after = await run_document_workflow(
        user_id=user_id,
        thread_id="t_doc",
        payload={"action": "list"},
    )
    assert listed_after.chunk_count == 0


@pytest.mark.asyncio
async def test_workflow_result_contrat_main_graph(user_id, _purge):
    """La sortie doit être consommable par le Main Graph (workflow+status)."""
    res = await run_document_workflow(
        user_id=user_id,
        thread_id="t_doc",
        payload={"action": "list"},
    )
    assert res.workflow == "document"
    assert res.status == "ok"
    assert isinstance(res, DocumentResult)


@pytest.mark.asyncio
async def test_fail_safe_action_invalide(user_id, _purge):
    res = await run_document_workflow(
        user_id=user_id,
        thread_id="t_doc",
        payload={"action": "explode", "filename": "x.txt", "content": "y"},
    )
    assert res.status == "error"
    assert res.workflow == "document"


@pytest.mark.asyncio
async def test_fail_safe_contenu_vide(user_id, _purge):
    res = await run_document_workflow(
        user_id=user_id,
        thread_id="t_doc",
        payload={"action": "upload", "filename": "vide.md", "content": "   "},
    )
    assert res.status == "error"
    assert "vide" in res.message.lower()


@pytest.mark.asyncio
async def test_fail_safe_doc_absent(user_id, _purge):
    res = await run_document_workflow(
        user_id=user_id,
        thread_id="t_doc",
        payload={"action": "delete", "doc_id": "absent-doc"},
    )
    assert res.status == "error"