# Routes Subjects V4 — Subject Registry exposé en lecture + context
# preview (outil dev, §35).
# GET  /api/subjects                      → matières configurées
# GET  /api/subjects/{id}                 → une matière
# GET  /api/subjects/{id}/topics          → topics d'une matière
# POST /api/subjects/preview/context      → contexte + prompt SANS LLM
from fastapi import APIRouter, HTTPException

from app.agent.prompts import CORE_PROMPT
from app.api.schemas import (
    ContextPreviewRequest,
    ContextPreviewResponse,
    SubjectOut,
    TopicOut,
)
from app.context import build_context
from app.context.prompt_builder import build_system_prompt
from app.db.connections import init_db
from app.db.users import get_user
from app.subjects.registry import get_subject, list_subjects

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


def _to_subject_out(cfg) -> SubjectOut:
    return SubjectOut(
        id=cfg.id,
        name=cfg.name,
        domain=cfg.domain,
        description=cfg.description,
        teaching_style=cfg.teaching_style,
        pedagogical_guidelines=cfg.pedagogical_guidelines,
        capabilities=cfg.capabilities,
        topics=cfg.topics,
        knowledge_sources=cfg.knowledge.get("sources", []),
        tools_common=cfg.tools.get("common", []),
        tools_specialized=cfg.tools.get("specialized", []),
    )


@router.get("", response_model=list[SubjectOut])
def api_list_subjects() -> list[SubjectOut]:
    """Toutes les matières configurées (Subject Registry)."""
    return [_to_subject_out(cfg) for cfg in list_subjects()]


@router.get("/{subject_id}", response_model=SubjectOut)
def api_get_subject(subject_id: str) -> SubjectOut:
    cfg = get_subject(subject_id)
    if cfg is None:
        raise HTTPException(
            status_code=404, detail="Matière introuvable"
        )
    return _to_subject_out(cfg)


@router.get("/{subject_id}/topics", response_model=list[TopicOut])
def api_subject_topics(subject_id: str) -> list[TopicOut]:
    cfg = get_subject(subject_id)
    if cfg is None:
        raise HTTPException(
            status_code=404, detail="Matière introuvable"
        )
    return [
        TopicOut(id=t, subject_id=cfg.id, name=t)
        for t in cfg.topics
    ]


@router.post(
    "/preview/context", response_model=ContextPreviewResponse
)
def api_context_preview(
    payload: ContextPreviewRequest,
) -> ContextPreviewResponse:
    """Prévisualise le contexte + prompt SANS appeler le LLM.

    Route dev : expose la sélection interne (router, knowledge,
    mémoire). À protéger/limiter si exposée en production (§35).
    """
    init_db()
    if get_user(payload.user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )

    context = build_context(
        user_id=payload.user_id,
        thread_id=payload.thread_id or "",
        query=payload.query,
        subject=payload.subject,
    )
    prompt = build_system_prompt(
        core_prompt=CORE_PROMPT,
        context=context,
        user_id=payload.user_id,
        thread_id=payload.thread_id or "",
    )
    return ContextPreviewResponse(
        router=context["router"],
        subject=context["subject"],
        knowledge=context["knowledge"],
        tools=context["tools"],
        user=context["user"],
        thread=context["thread"],
        prompt_preview=prompt,
        stats=context["stats"],
    )
