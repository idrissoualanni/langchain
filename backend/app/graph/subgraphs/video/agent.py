# VideoSubgraph — AGENT ReAct d'ANALYSE VISUELLE (LLM vision).
#
# Le transcript ( faster-whisper ) capte ce qui est DIT dans la vidéo ;
# cet agent decrit ce qui est MONTRE : contenu des slides/diagrammes,
# ecran de code, gestes, decor, transitions. Les deux sont
# complementaires — la sortie du subgraph combine audio + image.
#
# Agent ReAct via langchain.agents.create_agent ( meme import que
# app/graph/main/graph.py:22 ), modele resolu par la Model Gateway
# ( purpose "vision" — JAMAIS de ChatOllama en dur, regle §1 du repo ).
#
# Tools LangChain exposes a l'agent ( ReAct = raisonner + agir ) :
#   - frame_lookup(index)      : recupere UNE frame precise ;
#   - transcript_lookup(debut, fin) : portion du transcript pour une
#     fenetre temporelle ( lit le STORE, jamais de re-transcription —
#     la mission du subgraph est de ne pas retranscrire a la demande ).
#
# ANTI-REGRESSION ( point cle, meme philosophie que transcribe.py ) :
#   - VIDEO_AGENT_ENABLED=0 ( defaut ) → pipeline deterministe seul ;
#   - modele "vision" non resolu → repli silencieux ( log WARNING,
#     pas d'exception : l'agent est une AMELIORATION, jamais une
#     dependance ) ;
#   - frames vides → analyse sautee, pas de description fabriquee ;
#   - boucle ReAct BORNEE par VIDEO_AGENT_MAX_STEPS ( jamais infinie ).
from __future__ import annotations

from typing import Any

from app.config import (
    VIDEO_AGENT_ENABLED,
    VIDEO_AGENT_MAX_FRAMES,
    VIDEO_AGENT_MAX_STEPS,
    VIDEO_FRAME_STRATEGY,
)
from app.logging.events import log_event

SYSTEM_PROMPT = """Tu es l'analyste visuel d'un cours vidéo pédagogique.

On te donne des frames extraites de la vidéo et le transcript de l'audio.
Ton travail : produire une description visuelle structurée qui COMPLÈTE
le transcript — décrire ce que l'ŒIL voit, pas ce que la bouche dit.

Structure ta description en points courts :
- supports visuels (slides, diagrammes, schémas, tableau) ;
- code ou IDE à l'écran (langage, éléments visibles) ;
- personne et gestes (présentateur, pointage, écriture) ;
- décor, texte incrusté, transitions marquantes.

Règles absolues :
1. INTERDICTION D'INVENTER. Tu décris UNIQUEMENT ce que les frames
   montrent. Une frame illisible, vide ou ambiguë → tu le dis
   explicitement ("frame 3 illisible").
2. Tu utilises les tools : frame_lookup pour examiner une frame,
   transcript_lookup pour recoller une image à ce qui est dit à ce
   moment. N'invente pas la correspondance.
3. Réponse en français, concrète, en points. Pas de remplissage.
4. Si RIEN n'est exploitable, réponds exactement :
   « Aucun contenu visuel exploitable. »"""


class VideoAgentUnavailable(RuntimeError):
    """L'agent vision n'est pas disponible (config / modèle / frames)."""


def _resolve_vision_llm():
    """Résout le LLM vision via la Model Gateway (§1 — gateway uniquement).

    Retourne None si aucun modele vision n'est resolu ( repli
    silencieux documente — l'agent est optionnel par design ).
    """
    from app.services.models.gateway import ModelGatewayError, get_llm_for_purpose

    try:
        return get_llm_for_purpose("vision")
    except ModelGatewayError as exc:
        log_event(
            "VIDEO_AGENT_NO_MODEL",
            level="WARNING",
            message=(
                "Agent vision désactivé — aucun modèle 'vision' résolu "
                "(repli sur le pipeline déterministe)"
            ),
            extra={
                "operation": "video_agent",
                "reason": str(exc)[:200],
            },
        )
        return None


def _build_tools(frames, transcript: str):
    """Construit les tools ReAct : consultation frames + transcript.

    `frames` : liste de Frame ( frames.py ). Le store de frames est
    capture par closure — l'agent ne fait JAMAIS d'IO disque lui-meme.
    """
    from langchain_core.tools import tool

    index_map = {f.index: f for f in frames}

    @tool("frame_lookup")
    def frame_lookup(index: int) -> str:
        """Examine une frame vidéo précise par son index (int).

        Retourne la frame sous forme d'image pour analyse visuelle.
        Utilise-le pour décrire le contenu d'un instant précis.
        """
        frame = index_map.get(index)
        if frame is None:
            return f"frame {index} inexistante (indexes disponibles: {sorted(index_map)[:8]})"
        return frame.data_url

    @tool("transcript_lookup")
    def transcript_lookup(start: float, end: float) -> str:
        """Renvoie la portion de transcript entre start et end (secondes).

        Le transcript vient de la transcription whisper, déjà stockée —
        aucune re-transcription. Sert à recoller une image à la parole.
        """
        text = (transcript or "").strip()
        if not text:
            return "transcript vide pour cette vidéo"
        # Le transcript n'est pas timecodé par phrase : on renvoie le
        # texte intégral ( l'agent l'utilise pour le contexte global ).
        return f"[contexte transcript {start}s–{end}s]\n{text}"

    return [frame_lookup, transcript_lookup]


def agent_available() -> bool:
    """L'agent vision peut-il tourner ? ( gate avant d'extraire les frames )

    Vérifie l'opt-in ET la résolution du modèle — sans consommer de
    frames. Permet au pipeline de SAUTER l'extraction (opencv) quand
    l'agent de toute façon indisponible.
    """
    if not VIDEO_AGENT_ENABLED:
        return False
    from app.services.models.gateway import ModelGatewayError, get_llm_for_purpose

    try:
        get_llm_for_purpose("vision")
        return True
    except ModelGatewayError:
        return False


def _build_runnable_agent(llm, tools):
    """Instancie l'agent ReAct avec SES tools (frames de la vidéo courante).

    On reconstruit l'agent à chaque run : les tools ferment sur les
    frames de la vidéo en cours d'analyse (pas partageable globalement).
    """
    from langchain.agents import create_agent

    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )


def run_video_agent(
    frames,
    transcript: str,
    *,
    user_id: str = "",
    thread_id: str = "",
) -> str:
    """Exécute l'analyse visuelle sur les frames extraites.

    Retourne la description visuelle ( str ), ou "" si l'agent est
    indisponible / si aucune frame exploitable ( repli documente,
    JAMAIS de description fabriquee ).
    """
    if not frames:
        log_event(
            "VIDEO_AGENT_NO_FRAMES",
            level="WARNING",
            message="Agent vision sauté — aucune frame extraite",
            extra={"operation": "video_agent"},
        )
        return ""

    if not VIDEO_AGENT_ENABLED:
        return ""

    llm = _resolve_vision_llm()
    if llm is None:
        return ""

    # Plafond de frames envoyees au LLM ( cout tokens ; compte free
    # Ollama rate-limite ). On echantillonne regulierement les frames
    # extraites pour garder une couverture de la timeline.
    selected = frames[: max(1, int(VIDEO_AGENT_MAX_FRAMES or 1))]
    tools = _build_tools(selected, transcript)
    agent = _build_runnable_agent(llm, tools)

    from langchain_core.messages import HumanMessage

    indexes = [f.index for f in selected]
    prompt = (
        f"Analyse ces {len(selected)} frames (indexes {indexes}) de la "
        "vidéo. Utilise frame_lookup pour les examiner, "
        "transcript_lookup pour le contexte audio, puis donne ta "
        "description visuelle structurée en points."
    )
    payload: dict[str, Any] = {
        "messages": [HumanMessage(prompt)],
        "recursion_limit": VIDEO_AGENT_MAX_STEPS * 2,
    }
    if thread_id:
        payload["configurable"] = {"thread_id": thread_id}

    try:
        result = agent.invoke(payload, {"user_id": user_id} if user_id else None)
    except Exception as exc:  # noqa: BLE001 — l'agent n'est jamais fatal
        log_event(
            "VIDEO_AGENT_ERROR",
            level="ERROR",
            message=f"Agent vision en échec : {type(exc).__name__}",
            extra={
                "operation": "video_agent",
                "error": str(exc)[:300],
                "frames": len(selected),
            },
        )
        return ""

    messages = (result or {}).get("messages") or []
    description = ""
    for msg in reversed(messages):
        content = getattr(msg, "content", "")
        if isinstance(content, str) and content.strip():
            # On saute les messages de tool ( reponses frame/transcript ).
            if getattr(msg, "type", "") == "tool":
                continue
            description = content.strip()
            break

    log_event(
        "VIDEO_AGENT_OK",
        message=(
            f"Agent vision | frames={len(selected)} | "
            f"chars={len(description)}"
        ),
        extra={
            "operation": "video_agent",
            "frames": len(selected),
            "chars": len(description),
        },
    )
    return description


__all__ = [
    "SYSTEM_PROMPT",
    "VideoAgentUnavailable",
    "agent_available",
    "run_video_agent",
]
