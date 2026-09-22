# CODING node du Main Graph — délègue au CodingSubgraph (§22-§25).
#
# Quand WORKFLOW_ROUTER décide "coding" (hint @code du composer), CE
# node invoque le sous-graphe coding
# (ANALYZE → EXECUTE ↺ → EVALUATE → LEARNING_SIGNALS → FINALIZE) et
# persiste un CodingResult (§8) dans workflow_result pour la chaîne
# suivante (CONTEXT → agent).
#
# ADAPTATION DE CONTRAT : run_coding_workflow renvoie un CodingResult
# PROPRE au sous-graphe (champs success/status/observations/…), qui ne
# concorde pas avec le contrat §8 (tested/tests/analysis/security/…).
# Le node traduit l'un vers l'autre — le Main Graph ne consomme QUE le
# contrat §8 (frontière nette, §5/§8).
from __future__ import annotations

from typing import Any

from app.logging.events import log_event

_compiled_coding = None


def _coding_subgraph():
    """Lazy-init du CodingSubgraph compilé (cache module)."""
    global _compiled_coding
    if _compiled_coding is None:
        from app.graph.subgraphs.coding.graph import create_coding_subgraph

        _compiled_coding = create_coding_subgraph()
    return _compiled_coding


def _to_contract_result(local_result) -> dict:
    """Traduit le CodingResult interne du sous-graphe vers le contrat §8.

    run_coding_workflow renvoie {success, status, result, observations,
    errors, code, test_results, learning_signals} — le contrat §8 attend
    {workflow, status, message, tested, tests, analysis, security,
    code_summary}. La traduction est EXPLICITE et défensive (un champ
    manquant ne casse jamais le run).
    """
    from app.schemas.workflow import CodingResult

    if local_result is None:
        return CodingResult(
            workflow="coding",
            status="error",
            message="CodingSubgraph : aucun résultat produit",
        ).model_dump()

    # local_result peut être un objet CodingResult du sous-graphe ou un
    # dict (défensif — les deux chemins sont supportés).
    if isinstance(local_result, dict):
        data = local_result
    else:
        data = getattr(local_result, "model_dump", lambda: {})() or {}

    test_results = list(data.get("test_results") or [])
    errors = list(data.get("errors") or [])
    observations = list(data.get("observations") or [])

    passed = sum(1 for t in test_results if t.get("success"))
    status = str(data.get("status") or ("ok" if data.get("success") else "failed"))

    # Statut JobStatus §8 : ok / error / partial / cancelled / pending.
    if status in ("ok", "success"):
        job_status = "ok" if not errors else "partial"
    elif status == "max_iterations":
        job_status = "partial"
    else:
        job_status = "error"

    analysis = {}
    for obs in observations:
        if isinstance(obs, dict) and obs.get("type") == "code_analysis":
            analysis = obs.get("data") or {}
            break

    security = {
        "issues": [
            e for e in errors
            if isinstance(e, dict) and e.get("type") == "security_violation"
        ],
    }

    return CodingResult(
        workflow="coding",
        status=job_status,
        message=(
            f"Session de codage {status} "
            f"({passed}/{len(test_results)} tests validés)"
        ),
        tested=bool(test_results),
        tests={
            "passed": passed,
            "failed": len(test_results) - passed,
            "total": len(test_results),
        },
        analysis=analysis,
        security=security,
        code_summary=str(data.get("code") or "")[:2000],
    ).model_dump()


async def coding_node(state, config=None) -> dict[str, Any]:
    """CODING — exécute le CodingSubgraph pour la requête courante.

    Entrée : la demande vient du canal `intake.query` (ou du dernier
    message humain). Le code éventuel fourni par l'utilisateur vient
    du canal `payload.code`.

    Sortie : workflow_result (CodingResult §8). Le sous-graphe est
    async (run_coding_workflow) — le node est async également.
    """
    from app.graph.subgraphs.coding.graph import run_coding_workflow

    intake = (state or {}).get("intake") or {}
    query = intake.get("query") if isinstance(intake, dict) else ""
    if not query and isinstance(state, dict):
        query = state.get("query") or ""

    user_id = (state or {}).get("user_id") or ""
    thread_id = ""
    if config:
        thread_id = (
            config.get("configurable") or {}
        ).get("thread_id") or ""

    payload = (state or {}).get("payload") or {} if isinstance(state, dict) else {}
    language = str(payload.get("language") or "python")

    log_event(
        "CODING_NODE_START",
        message=f"Coding subgraph start | query_chars={len(query)}",
        user_id=user_id,
        thread_id=thread_id,
        extra={"operation": "coding_node", "language": language},
    )

    try:
        local = await run_coding_workflow(
            request=query,
            user_id=user_id,
            thread_id=thread_id,
            language=language,
            code=payload.get("code"),
        )
    except Exception as exc:  # noqa: BLE001 — isolation du run
        from app.schemas.workflow import CodingResult

        log_event(
            "CODING_NODE_ERROR",
            level="ERROR",
            message=f"Coding subgraph failed: {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={"operation": "coding_node"},
        )
        return {
            "workflow_result": CodingResult(
                workflow="coding",
                status="error",
                message=f"Session de codage en échec : {exc}",
            ).model_dump()
        }

    workflow_result = _to_contract_result(local)

    log_event(
        "CODING_NODE",
        message=(
            f"Coding subgraph run | status={workflow_result.get('status')} "
            f"| tests={workflow_result.get('tests')}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "coding_node",
            "status": workflow_result.get("status"),
            "tests": workflow_result.get("tests"),
        },
    )

    return {"workflow_result": workflow_result}


def route_after_coding(state) -> str:
    """Après CODING : retour TOUJOURS sur la chaîne principale."""
    return "context"


__all__ = ["coding_node", "route_after_coding"]
