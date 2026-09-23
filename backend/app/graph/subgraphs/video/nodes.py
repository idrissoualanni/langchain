# VideoSubgraph — NODES + graphe compilé (§28/§8).
#
# Pipeline (HORS chemin conversationnel, Cas F §74) :
#
#   START
#    ↓
#   validate_upload      → normalise l'entrée (payload/ids, video_id,
#                          working_dir) + validation VidéoUploadPayload
#    ↓                         (échec → finalize, jamais de boucle)
#   ingest ↺ RETRY       → video_ingest interne : localiser → matérialiser
#                          → transcrire → persister le transcript
#    ↓                         (transitoire → retry borné max_attempts ;
#                               définitif → finalize)
#   segment ↺ RETRY      → video_segment interne : segmentation
#                          pédagogique (timestamps) + validation Pydantic
#                          + persistance JSON
#    ↓
#   enrich               → métadonnées enrichies (langue, volumes, source)
#    ↓
#   index / persist      → la vidéo devient une SOURCE DE CONNAISSANCE
#                          (VideoKnowledgeStore, clés knowledge)
#    ↓
#   finalize             → VideoResult (§8) SANS exposer l'état interne
#    ↓
#   END
#
# Les retries ne portent QUE sur les erreurs TRANSITOIRES (réseau/
# provider) et sont BORNÉS par max_attempts (aucune boucle infinie).
# Le subgraph est AUTONOME (compile sans checkpointer, testable isolé)
# et n'est PAS câblé au Main (un autre agent câble).
#
# Sécurité : aucune exécution de code, aucun secret loggé.
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from app.schemas.workflow import VideoResult
from app.graph.subgraphs.video.ingest import (
    VideoFatalError,
    VideoTransientError,
    ingest_video,
)
from app.graph.subgraphs.video.metadata import enrich_video_metadata
from app.graph.subgraphs.video.persist import VideoKnowledgeStore
from app.schemas.video import VideoUploadPayload
from app.graph.subgraphs.video.segment import (
    SegmentationError,
    segment_parts,
)
from app.graph.subgraphs.video.state import VideoState
from app.logging.events import log_event

MAX_ATTEMPTS_DEFAULT = 3

# Progression par étape (monotone, partagée avec l'UI si câblée).
PROGRESS_VALIDATED = 0.10
PROGRESS_INGESTED = 0.45
PROGRESS_SEGMENTED = 0.70
PROGRESS_ENRICHED = 0.85
PROGRESS_INDEXED = 1.00


def _ids(state) -> tuple[str, str]:
    user_id = (state or {}).get("user_id") or ""
    thread_id = (state or {}).get("thread_id") or ""
    return user_id, thread_id


def _log(name: str, message: str, state, level: str = "INFO", extra: dict | None = None):
    user_id, thread_id = _ids(state)
    log_event(
        name,
        level=level,
        message=message,
        user_id=user_id,
        thread_id=thread_id,
        extra={"operation": "video_subgraph", **(extra or {})},
    )


def _errors(state) -> list:
    return list((state or {}).get("errors") or [])


def _meta(state) -> dict:
    return dict((state or {}).get("metadata") or {})


def _retry_or_fail(state, exc: Exception, *, node: str) -> dict:
    """Politique de retry BORNÉ : uniquement sur erreur transitoire."""
    if isinstance(exc, VideoTransientError):
        iteration = int((state or {}).get("iteration") or 0) + 1
        max_attempts = int((state or {}).get("max_attempts") or MAX_ATTEMPTS_DEFAULT)
        errors = _errors(state) + [f"{node}.transient: {exc}"]
        _log(
            "VIDEO_RETRY",
            f"Video retry | node={node} | iteration={iteration}/{max_attempts}",
            state,
            level="WARNING",
            extra={"node": node, "iteration": iteration, "max_attempts": max_attempts},
        )
        if iteration < max_attempts:
            return {
                "status": "retrying",
                "errors": errors,
                "iteration": iteration,
            }
        return {
            "status": "failed",
            "errors": errors,
            "iteration": iteration,
        }
    # Erreur NON transitoire → arrêt immédiat (jamais de boucle).
    errors = _errors(state) + [f"{node}.fatal: {exc}"]
    _log("VIDEO_ERROR", f"Video error | node={node}", state, level="ERROR")
    return {"status": "failed", "errors": errors}


# ------------------------------------------------------------
# VALIDATE_UPLOAD node
# ------------------------------------------------------------
def validate_upload_node(state) -> dict:
    """VALIDATE_UPLOAD — normalise l'entrée et valide l'upload (§28).

    Représente la frontière d'entrée : rôle du SubgraphInput (payload)
    transformé en canaux VideoState. Les erreurs de validation sont
    NON retryables → routeur renvoie vers finalize (jamais de boucle).
    """
    s = dict(state or {})
    payload = dict(s.get("payload") or {})
    meta = _meta(s)
    options = dict(
        (payload.get("options") or {}) or (meta.get("options") or {})
    )

    user_id = str(s.get("user_id") or payload.get("user_id") or "")
    thread_id = str(s.get("thread_id") or payload.get("thread_id") or "")
    filename = str(s.get("filename") or payload.get("filename") or "")
    source_url = str(s.get("source_url") or payload.get("source_url") or "")
    duration = float(s.get("duration") or payload.get("duration") or 0.0)
    video_id = str(
        s.get("video_id") or payload.get("video_id") or f"vid-{uuid.uuid4().hex[:12]}"
    )
    max_attempts = int(
        s.get("max_attempts") or options.get("max_attempts") or MAX_ATTEMPTS_DEFAULT
    )

    meta["options"] = {"max_attempts": max_attempts, **options}

    errors = _errors(s)
    if not user_id:
        errors.append("user_id manquant")
    if not filename:
        errors.append("filename manquant")
    if not source_url:
        errors.append("source_url manquant")

    base = {
        "video_id": video_id,
        "user_id": user_id,
        "thread_id": thread_id,
        "filename": filename,
        "source_url": source_url,
        "duration": duration,
        "max_attempts": max_attempts,
        "iteration": int(s.get("iteration") or 0),
        "metadata": meta,
        "errors": errors,
        "local_path": str(s.get("local_path") or ""),
        "audio_path": str(s.get("audio_path") or ""),
        "transcript_path": str(s.get("transcript_path") or ""),
        "segments": list(s.get("segments") or []),
    }

    if errors:
        base["status"] = "failed"
        base["progress"] = float(s.get("progress") or 0.0)
        _log(
            "VIDEO_VALIDATE",
            f"Video validate KO | errors={len(errors)}",
            base,
            level="WARNING",
        )
        return base

    # Validation stricte du payload (extra=forbid) — échec = none retryable.
    try:
        VideoUploadPayload(
            video_id=video_id,
            filename=filename,
            source_url=source_url,
            duration=duration,
            options=options,
        )
    except Exception as exc:
        base["status"] = "failed"
        base["errors"] = errors + [f"validate: {exc}"]
        base["progress"] = float(s.get("progress") or 0.0)
        return base

    working_dir = Path(
        options.get("working_dir")
        or Path(tempfile.gettempdir()) / "video_subgraph" / user_id / video_id
    )
    meta["working_dir"] = str(working_dir)
    # Store PARTAGÉ par utilisateur (et non par vidéo) : le retrieval
    # (retrieval.py default_store_dir) doit retrouver les vidéos indexées
    # sans connaître le working_dir de chaque ingestion.
    meta["store_dir"] = str(
        options.get("store_dir")
        or Path(tempfile.gettempdir()) / "video_subgraph" / user_id / "store"
    )
    base["metadata"] = meta
    base["status"] = "validated"
    base["progress"] = PROGRESS_VALIDATED
    _log(
        "VIDEO_VALIDATE",
        f"Video validate OK | video_id={video_id}",
        base,
        extra={"video_id": video_id},
    )
    return base


# ------------------------------------------------------------
# INGEST node (↺ retry borné sur erreurs transitoires)
# ------------------------------------------------------------
def ingest_node(state) -> dict:
    """INGEST — localisation + matérialisation + transcription (§28).

    Appelle le service video_ingest interne (ingest_video). Toute
    erreur transitoire (réseau/provider) passe par la politique de
    retry borné ; une erreur définitive arrête par finalize.
    """
    s = dict(state or {})
    meta = _meta(s)
    working_dir = Path(
        meta.get("working_dir") or Path(tempfile.gettempdir()) / "video_subgraph"
    )
    _log(
        "VIDEO_START",
        "Video ingest | start",
        s,
        extra={"video_id": s.get("video_id", "")},
    )
    try:
        result = ingest_video(
            source_url=str(s.get("source_url") or ""),
            filename=str(s.get("filename") or ""),
            dest_dir=str(working_dir / "media"),
            duration=float(s.get("duration") or 0.0),
        )
    except (VideoTransientError, VideoFatalError) as exc:
        action = _retry_or_fail(s, exc, node="ingest")
        action["progress"] = float(s.get("progress") or PROGRESS_VALIDATED)
        return action
    except Exception as exc:  # pragma: no cover — défensif
        action = _retry_or_fail(s, exc, node="ingest")
        action["progress"] = float(s.get("progress") or PROGRESS_VALIDATED)
        return action

    new_meta = {
        **meta,
        "transcript": result["transcript"],
        "origin": result["origin"],
        "format": result["format"],
    }
    _log(
        "VIDEO_INGEST",
        f"Video ingested | {result['origin']} | words estimation",
        s,
        extra={
            "origin": result["origin"],
            "duration": result["duration"],
            "video_id": s.get("video_id", ""),
        },
    )
    return {
        "local_path": result["local_path"],
        "audio_path": result["audio_path"],
        "transcript_path": result["transcript_path"],
        "duration": result["duration"],
        "metadata": new_meta,
        "status": "ingested",
        "progress": PROGRESS_INGESTED,
        "errors": _errors(s),
        "iteration": 0,
    }


# ------------------------------------------------------------
# SEGMENT node (↺ retry borné sur erreurs transitoires)
# ------------------------------------------------------------
def segment_node(state) -> dict:
    """SEGMENT — segmentation PÉDAGOGIQUE du transcript + timestamps.

    Appelle le service video_segment interne (segment_transcript) puis
    valide chaque segment (PedagogicalSegment, extra=forbid) et le
    persiste en JSON. Un transcript vide est une erreur définitive
    (pas de segmentation possible) → finalize.
    """
    s = dict(state or {})
    meta = _meta(s)
    transcript = meta.get("transcript") or ""
    try:
        parts = segment_parts(
            transcript,
            duration=float(s.get("duration") or 0.0),
        )
    except SegmentationError as exc:
        _log(
            "VIDEO_SEGMENT",
            "Video segment impossible (transcript invalide)",
            s,
            level="ERROR",
        )
        return {
            "status": "failed",
            "errors": _errors(s) + [f"segment.fatal: {exc}"],
        }
    except Exception as exc:  # pragma: no cover — défensif
        action = _retry_or_fail(s, exc, node="segment")
        action["progress"] = float(s.get("progress") or PROGRESS_INGESTED)
        return action

    segments = [p["segment"] for p in parts]
    new_meta = {
        **meta,
        "segment_count": len(segments),
        "segment_texts": [p["text"] for p in parts],
    }
    _log(
        "VIDEO_SEGMENT",
        f"Video segmented | segments={len(segments)}",
        s,
        extra={"segments": len(segments), "video_id": s.get("video_id", "")},
    )
    return {
        "segments": segments,
        "metadata": new_meta,
        "status": "segmented",
        "progress": PROGRESS_SEGMENTED,
        "iteration": 0,
    }


# ------------------------------------------------------------
# ENRICH node
# ------------------------------------------------------------
def enrich_node(state) -> dict:
    """ENRICH — métadonnées enrichies (source, format, langue, volumes)."""
    s = dict(state or {})
    meta = _meta(s)
    enriched = enrich_video_metadata(
        video_id=str(s.get("video_id") or ""),
        user_id=str(s.get("user_id") or ""),
        filename=str(s.get("filename") or ""),
        origin=meta.get("origin", ""),
        duration=float(s.get("duration") or 0.0),
        fmt=meta.get("format", ""),
        transcript=meta.get("transcript", ""),
        segments=list(s.get("segments") or []),
    )
    new_meta = {**meta, **enriched, "knowledge_keys": []}
    _log(
        "VIDEO_ENRICH",
        f"Video metadata enriched | lang={enriched['language']}",
        s,
        extra={"language": enriched["language"]},
    )
    return {
        "metadata": new_meta,
        "status": "enriched",
        "progress": PROGRESS_ENRICHED,
    }


# ------------------------------------------------------------
# INDEX node — la vidéo devient une SOURCE DE CONNAISSANCE
# ------------------------------------------------------------
def index_node(state) -> dict:
    """INDEX/PERSIST — enregistre la vidéo indexée (knowledge)."""
    s = dict(state or {})
    meta = _meta(s)
    try:
        store = VideoKnowledgeStore(meta.get("store_dir") or meta.get("working_dir"))
        keys = store.persist_video(
            video_id=str(s.get("video_id") or ""),
            user_id=str(s.get("user_id") or ""),
            filename=str(s.get("filename") or ""),
            source_url=str(s.get("source_url") or ""),
            duration=float(s.get("duration") or 0.0),
            transcript=meta.get("transcript", ""),
            segments=list(s.get("segments") or []),
            segment_texts=list(meta.get("segment_texts") or []),
            metadata=meta,
            created_at=meta.get("created_at", ""),
        )
    except Exception as exc:
        _log(
            "VIDEO_INDEX",
            f"Video index failed | {exc}",
            s,
            level="ERROR",
        )
        return {
            "status": "index_failed",
            "errors": _errors(s) + [f"index: {exc}"],
            "progress": float(s.get("progress") or PROGRESS_ENRICHED),
        }
    new_meta = {**meta, "knowledge_keys": keys}
    _log(
        "VIDEO_INDEX",
        "Video indexed | knowledge_keys=" + ",".join(keys),
        s,
        extra={"knowledge_keys": keys},
    )
    return {
        "metadata": new_meta,
        "status": "indexed",
        "progress": PROGRESS_INDEXED,
    }


# ------------------------------------------------------------
# FINALIZE node — VideoResult (§8), état interne jamais exposé
# ------------------------------------------------------------
def finalize_node(state) -> dict:
    """FINALIZE — construit la sortie structurée VideoResult (§8)."""
    existing = (state or {}).get("result")
    if isinstance(existing, dict) and existing:
        return {"status": "done"}

    s = dict(state or {})
    meta = _meta(s)
    internal_status = str(s.get("status") or "")

    transcript = meta.get("transcript") or ""
    if not transcript:
        transcript = _read_transcript_path(str(s.get("transcript_path") or ""))
    if not transcript:
        transcript = " ".join(
            seg.get("summary", "") for seg in (s.get("segments") or [])
        ).strip()

    status_map = {
        "indexed": ("ok", "Vidéo ingérée, segmentée et indexée en connaissance"),
        "index_failed": (
            "partial",
            "Vidéo ingérée et segmentée, mais index persistée en échec",
        ),
    }
    job_status, message = status_map.get(
        internal_status,
        (
            "error",
            (s.get("errors") or [""])[-1] or "Ingestion vidéo en échec",
        ),
    )

    result = VideoResult(
        workflow="video",
        status=job_status,
        message=message,
        video_id=str(s.get("video_id") or ""),
        transcript=transcript,
        segments=list(s.get("segments") or []),
        knowledge_keys=list(meta.get("knowledge_keys") or []),
    )
    _log(
        "VIDEO_END",
        f"Video end | status={job_status} | segments={len(result.segments)}",
        s,
        extra={"status": job_status, "segments": len(result.segments)},
    )
    return {
        "result": result.model_dump(),
        "status": "done",
        "progress": float(s.get("progress") or PROGRESS_INDEXED),
    }


def _read_transcript_path(path: str) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


# ------------------------------------------------------------
# Routeurs internes (bornes de la boucle)
# ------------------------------------------------------------
def route_after_validate(state) -> str:
    """Valide → ingest ; échec de validation → finalize (jamais de retry)."""
    return "ingest" if (state or {}).get("status") == "validated" else "finalize"


def route_after_ingest(state) -> str:
    """Ingesté → segment ; transitoire → retry ingest ; sinon finalize."""
    status = (state or {}).get("status")
    if status == "ingested":
        return "segment"
    if status == "retrying":
        return "ingest"
    return "finalize"


def route_after_segment(state) -> str:
    """Segmenté → enrich ; transitoire → retry segment ; sinon finalize."""
    status = (state or {}).get("status")
    if status == "segmented":
        return "enrich"
    if status == "retrying":
        return "segment"
    return "finalize"


def route_after_index(state) -> str:
    """Indexé ou non → finalize (le résultat porte l'état contrôlé)."""
    return "finalize"


# ------------------------------------------------------------
# Compilation
# ------------------------------------------------------------
def compile_video_subgraph():
    """Compile le VideoSubgraph (§28) sur VideoState.

    AUTONOME : aucun checkpointer/store requis — le sous-graphe est
    déterministe et stateless (l'état transite par l'invocation). Il
    peut être ajouté au Main Graph par un autre agent via add_node(
    "video", compile_video_subgraph...) — les seuls canaux exposés sont
    l'entrée (user_id/thread_id/filename/source_url/payload) et la
    sortie `result` (VideoResult §8).
    """
    graph = StateGraph(VideoState)

    graph.add_node("validate_upload", validate_upload_node)
    graph.add_node("ingest", ingest_node)
    graph.add_node("segment", segment_node)
    graph.add_node("enrich", enrich_node)
    graph.add_node("index", index_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "validate_upload")
    graph.add_conditional_edges(
        "validate_upload",
        route_after_validate,
        {"ingest": "ingest", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "ingest",
        route_after_ingest,
        {"ingest": "ingest", "segment": "segment", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "segment",
        route_after_segment,
        {"segment": "segment", "enrich": "enrich", "finalize": "finalize"},
    )
    graph.add_edge("enrich", "index")
    graph.add_conditional_edges(
        "index",
        route_after_index,
        {"finalize": "finalize"},
    )
    graph.add_edge("finalize", END)

    return graph.compile()


# ------------------------------------------------------------
# Façade d'exécution (testable / pour le wiring)
# ------------------------------------------------------------
def run_video_subgraph(
    payload: dict,
    *,
    user_id: str = "",
    thread_id: str = "",
    max_attempts: int = MAX_ATTEMPTS_DEFAULT,
) -> VideoResult:
    """Exécute le subgraph vidéo et retourne le VideoResult (§8).

    payload : {video_id, filename, source_url, duration, options} —
    les options (max_attempts, working_dir, store_dir…) transitent par
    le canal `metadata` (seuls les canaux déclarés de VideoState
    survivent à l'invoke LangGraph ; `payload` lui-même est consommé en
    entrée par validate_upload).
    """
    p = dict(payload or {})
    init: dict = {
        "user_id": user_id,
        "thread_id": thread_id,
        "max_attempts": int(max_attempts or MAX_ATTEMPTS_DEFAULT),
        "video_id": str(p.get("video_id") or ""),
        "filename": str(p.get("filename") or ""),
        "source_url": str(p.get("source_url") or ""),
        "duration": float(p.get("duration") or 0.0),
        "metadata": {"options": dict(p.get("options") or {})},
    }
    final = compile_video_subgraph().invoke(init)
    raw = (final or {}).get("result")
    if isinstance(raw, dict) and raw:
        return VideoResult(**raw)
    return VideoResult(
        workflow="video",
        status="error",
        message="VideoSubgraph : aucun résultat produit",
    )


__all__ = [
    "MAX_ATTEMPTS_DEFAULT",
    "PROGRESS_ENRICHED",
    "PROGRESS_INDEXED",
    "PROGRESS_INGESTED",
    "PROGRESS_SEGMENTED",
    "PROGRESS_VALIDATED",
    "compile_video_subgraph",
    "enrich_node",
    "finalize_node",
    "index_node",
    "ingest_node",
    "route_after_index",
    "route_after_ingest",
    "route_after_segment",
    "route_after_validate",
    "run_video_subgraph",
    "segment_node",
    "validate_upload_node",
]