# VIDEO node du Main Graph — délègue au VideoSubgraph (§28-§29).
#
# Quand WORKFLOW_ROUTER décide "video" (hint @video du composer), CE
# node invoque le sous-graphe vidéo
# (VALIDATE_UPLOAD → INGEST ↺ → SEGMENT ↺ → ENRICH → INDEX → FINALIZE)
# et persiste le VideoResult (§8) dans workflow_result.
#
# Le sous-graphe vidéo ingère un FICHIER (filename/source_url/duration)
# — pas un simple texte. En l'absence d'attachement, le node produit un
# résultat partial documenté (jamais d'ingestion bidon, jamais de crash).
from __future__ import annotations

from typing import Any

from app.logging.events import log_event

_compiled_video = None


def _video_subgraph():
    global _compiled_video
    if _compiled_video is None:
        from app.graph.subgraphs.video.nodes import compile_video_subgraph

        _compiled_video = compile_video_subgraph()
    return _compiled_video


def _video_payload(state) -> dict | None:
    """Extrait le payload vidéo de l'état (canal payload).

    Le composer transmet {filename, source_url, duration} via le canal
    payload quand l'utilisateur joint une vidéo. Sans attachement,
    retourne None — le node signale un résultat partial.
    """
    payload = (state or {}).get("payload") or {}
    if not isinstance(payload, dict):
        return None
    if not (payload.get("source_url") or payload.get("filename")):
        return None
    return payload


def video_node(state, config=None) -> dict[str, Any]:
    """VIDEO — exécute le VideoSubgraph pour la pièce jointe courante.

    Entrée : le payload vidéo vient du canal `payload`
    (filename/source_url/duration). La requête texte reste disponible
    pour le contexte.

    Sortie : workflow_result (VideoResult §8). Sans attachement, résultat
    partial explicite — le sous-graphe agentique explique à l'utilisateur
    qu'une vidéo doit être jointe.
    """
    from app.schemas.workflow import VideoResult

    intake = (state or {}).get("intake") or {}
    query = intake.get("query") if isinstance(intake, dict) else ""

    user_id = (state or {}).get("user_id") or ""
    thread_id = ""
    if config:
        thread_id = (
            config.get("configurable") or {}
        ).get("thread_id") or ""

    payload = _video_payload(state)
    if payload is None:
        no_attachment = VideoResult(
            workflow="video",
            status="partial",
            message=(
                "Aucune vidéo jointe à la requête — l'ingestion vidéo "
                "requiert un fichier ou une URL. Précisez la source et "
                "réessayez."
            ),
        ).model_dump()
        log_event(
            "VIDEO_NODE_NO_ATTACHMENT",
            level="WARNING",
            message="Video node without attachment — partial result",
            user_id=user_id,
            thread_id=thread_id,
            extra={"operation": "video_node"},
        )
        return {"workflow_result": no_attachment}

    sub = _video_subgraph()
    try:
        result = sub.invoke(
            {
                "user_id": user_id,
                "thread_id": thread_id,
                "payload": payload,
            }
        )
    except Exception as exc:  # noqa: BLE001 — isolation du run
        log_event(
            "VIDEO_NODE_ERROR",
            level="ERROR",
            message=f"Video subgraph failed: {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={"operation": "video_node"},
        )
        return {
            "workflow_result": VideoResult(
                workflow="video",
                status="error",
                message=f"Ingestion vidéo en échec : {exc}",
            ).model_dump()
        }

    # finalize_node écrit dans le canal `result` (VideoResult §8).
    workflow_result = result.get("result") or {}
    if not workflow_result:
        workflow_result = VideoResult(
            workflow="video",
            status="partial",
            message="Ingestion vidéo sans résultat exploitable.",
        ).model_dump()

    log_event(
        "VIDEO_NODE",
        message=(
            f"Video subgraph run | status={workflow_result.get('status')} "
            f"| segments={len(workflow_result.get('segments') or [])}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "video_node",
            "status": workflow_result.get("status"),
            "video_id": workflow_result.get("video_id"),
        },
    )

    return {"workflow_result": workflow_result}


def route_after_video(state) -> str:
    """Après VIDEO : retour TOUJOURS sur la chaîne principale."""
    return "context"


__all__ = ["video_node", "route_after_video"]
