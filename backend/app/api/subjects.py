# Routes Subjects V4 — Subject Registry exposé en lecture + context
# preview (outil dev, §35).
# GET  /api/subjects                      → matières configurées
# GET  /api/subjects/{id}                 → une matière
# GET  /api/subjects/{id}/topics          → topics d'une matière
# POST /api/subjects/preview/context      → contexte + prompt SANS LLM
from fastapi import APIRouter, HTTPException

from app.services.agent.prompts import CORE_PROMPT
from app.schemas import (
    ContextPreviewRequest,
    ContextPreviewResponse,
    SubjectOut,
    TopicOut,
)
from app.services.context import build_context
from app.services.context.prompt_builder import build_system_prompt
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
    Alias canonique V5 : POST /api/context/preview (§44).
    """
    return build_context_preview(payload)


def build_context_preview(
    payload: ContextPreviewRequest,
) -> ContextPreviewResponse:
    """Handler partagé preview (utilisé par /api/context/preview
    et /api/subjects/preview/context)."""
    init_db()
    if get_user(payload.user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )

    # BuiltContext (pydantic V5) → dict pour la réponse API
    context = build_context(
        user_id=payload.user_id,
        thread_id=payload.thread_id or "",
        query=payload.query,
        subject=payload.subject,
    )
    ctx = context.model_dump()
    prompt = build_system_prompt(
        core_prompt=CORE_PROMPT,
        context=context,
        user_id=payload.user_id,
        thread_id=payload.thread_id or "",
    )

    # V7 §47 : le prompt_preview montre AUSSI le bloc stratégie
    # (ce que le LLM verra réellement au run — cohérence §31).
    preview_prompt = prompt
    try:
        from app.services.learning.engine import decide

        d = decide(
            context, user_id=payload.user_id, thread_id=""
        )
        from app.services.context.prompt_builder import (
            add_learning_strategy_block,
        )

        preview_prompt = add_learning_strategy_block(prompt, d)
        learning_strategy = {
            "action": d.action,
            "subject": d.subject,
            "topic": d.topic,
            "reason": d.reason,
            "confidence": d.confidence,
            "priority": d.priority,
            "recommended_tool": d.recommended_tool,
        }
    except Exception:
        learning_strategy = None
        preview_prompt = prompt

    # V6.8 §47 : budget (contrat frontend verrouillé) —
    # jamais exposé dans le chat étudiant, Context Inspector
    # uniquement (§32/§55).
    stats = ctx.get("stats") or {}
    budget = {
        "estimated_input_tokens": stats.get(
            "estimated_input_tokens"
        ),
        "context_window": stats.get("context_window"),
        "reserved_output_tokens": stats.get(
            "reserved_output_tokens", 0
        ),
        "available_input_tokens": stats.get(
            "available_input_tokens"
        ),
        "budget_status": stats.get("budget_status", "unknown"),
        "sources_used": stats.get("sources_used", 0),
        "sources_dropped": stats.get("sources_dropped", 0),
    }
    # V6.6 : décision de fallback (interface développeur)
    fb = ctx.get("fallback") or {}
    fallback = {
        "action": fb.get("action", ""),
        "reason": fb.get("reason", ""),
        "source_status": fb.get("source_status", ""),
        "confidence": fb.get("confidence", 0.0),
        "candidates": fb.get("candidates", []),
    }

    return ContextPreviewResponse(
        router=ctx["routing"],
        subject=ctx["subject"],
        knowledge=ctx["knowledge"],
        web=ctx.get("web"),
        fallback=fallback,
        tools=ctx["tools"],
        user=ctx["user"],
        thread=ctx["thread"],
        learning=ctx.get("learning"),
        budget=budget,
        prompt_preview=preview_prompt,
        stats=ctx["stats"],
        learning_strategy=learning_strategy,
    )
