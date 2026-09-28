# Tool diagramme V6.7 — création d'activités visuelles (Mermaid).
#
# Même mécanique que create_exercise/create_quiz : Command(update={...})
# natif LangGraph, l'activité vit dans CustomAgentState.learning_activity
# (persistée par le checkpointer §16). Le frontend rend l'activité via le
# contrat AgentResponse type="diagram" (data.chart = code mermaid BRUT,
# sans fence ```), et la carte DiagramCard applique le style du projet.
#
# GARDE-FOUS DE VALIDITÉ (§27-§30 des règles Mermaid) :
#   - blocs ```mermaid ... ``` retirés automatiquement si le LLM en
#     laisse (le contrat exige du code brut) ;
#   - mot-clé de diagramme obligatoire en première ligne (liste
#     blanche des types supportés par le renderer frontend) ;
#   - nombre de lignes borné (~15 nœuds max, règle pédagogique) ;
#   - repli contrôlé : chart invalide → message d'erreur à renvoyer à
#     l'étudiant avec un exemple valide, jamais de rendu cassé.
from __future__ import annotations

import re
import time
from typing import Annotated

from langchain.tools import InjectedToolCallId
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.config import RunnableConfig
from langgraph.types import Command

from app.logging.events import log_event

# Types acceptés par le renderer frontend (mermaid-diagram.aui.tsx) —
# cohérents avec la liste du prompt système §27.
DIAGRAM_KEYWORDS = {
    "graph", "flowchart", "sequenceDiagram", "classDiagram",
    "stateDiagram", "stateDiagram-v2", "erDiagram", "gantt",
    "pie", "mindmap", "timeline", "journey", "gitGraph",
}

MAX_DIAGRAM_LINES = 30


def _clean_chart(chart: str) -> tuple[str, str | None]:
    """Normalise le code mermaid fourni. Retour (chart, erreur)."""
    text = (chart or "").strip()
    if not text:
        return "", "Le paramètre 'chart' est vide."

    # Retire les fences markdown si le LLM en a laissé (```mermaid ... ```)
    fence = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```\s*$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "", "Le diagramme ne contient aucune ligne exploitable."

    first = lines[0].strip()
    keyword = re.split(r"[\s;]", first, maxsplit=1)[0]
    if keyword not in DIAGRAM_KEYWORDS:
        return "", (
            f"Première ligne invalide : « {first[:60]} ». La première "
            "ligne doit être un mot-clé de diagramme seul "
            "(graph TD, flowchart LR, sequenceDiagram, classDiagram, "
            "stateDiagram-v2, erDiagram, pie…)."
        )
    if len(lines) > MAX_DIAGRAM_LINES:
        return "", (
            f"Diagramme trop grand ({len(lines)} lignes, max "
            f"{MAX_DIAGRAM_LINES}). Découpe-le en plusieurs "
            "diagrammes plus simples."
        )
    return "\n".join(text.splitlines()), None


@tool
def create_diagram(
    chart: str,
    caption: str = "",
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Ouvre une activité VISUELLE : un diagramme Mermaid qui sera
    dessiné à l'étudiant dans une carte dédiée du fil de discussion.

    Utilise ce tool quand une structure, un processus ou une relation
    gagne à être montrée plutôt qu'écrite : flux d'un algorithme,
    hiérarchie de classes, machine à états, schéma de base de données,
    chronologie. Pour une simple énumération ou un texte court,
    réponds directement en markdown — n'appelle pas ce tool.

    Règles STRICTES du code Mermaid (un bloc invalide affiche une
    erreur à l'étudiant) :
      - fournis le code BRUT, SANS fence ``` ni bloc markdown ;
      - la PREMIÈRE ligne est le mot-clé du diagramme seul :
        graph TD, flowchart LR, sequenceDiagram, classDiagram,
        stateDiagram-v2, erDiagram, gantt, pie, mindmap, timeline ;
      - ids de nœuds alphanumériques courts (A, B1), libellés entre
        crochets SANS guillemets imbriqués, backticks, points-virgules
        en fin de ligne, HTML brut ni caractères < > dans les libellés ;
      - maximum ~15 nœuds — au-delà, découpe en plusieurs diagrammes.

    Après ce tool : présente brièvement le diagramme à l'étudiant dans
    ta réponse finale (le dessin illustre, il ne remplace pas
    l'explication). Un seul diagramme par appel.

    Args:
        chart: le code Mermaid brut (sans ```). Exemple minimal :
            "graph TD\\n  A[Début] --> B{Condition}\\n  B -- oui --> C[Suite]"
        caption: titre court du diagramme affiché sur la carte
            (ex: "Cycle de vie d'une requête HTTP").
    """
    conf = (config or {}).get("configurable", {}) or {}
    user_id = conf.get("user_id", "") or ""
    thread_id = conf.get("thread_id", "") or ""
    log_event(
        "TOOL_CALL",
        message=(
            f"create_diagram caption={caption!r} "
            f"chart={len(chart or '')} chars"
        ),
        tool_name="create_diagram",
        user_id=user_id,
        thread_id=thread_id,
    )

    cleaned, error = _clean_chart(chart)
    if error is not None:
        log_event(
            "TOOL_ERROR",
            level="WARNING",
            message=f"create_diagram invalid chart: {error}",
            tool_name="create_diagram",
            user_id=user_id,
            thread_id=thread_id,
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"DIAGRAMME REJETÉ — {error}\n\n"
                            "Corrige le code et rappelle "
                            "create_diagram, ou décris la structure "
                            "en texte markdown. Exemple valide :\n"
                            "graph TD\n"
                            "  A[Entree] --> B{Test}\n"
                            "  B -- oui --> C[Action]\n"
                            "  B -- non --> D[Fin]"
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    activity = {
        "activity_id": f"diagram-{int(time.time() * 1000)}",
        "activity_type": "diagram",
        # Activité NON interactive : le normalizer mappe idle →
        # type="diagram"/status="completed" et response_from_text
        # ne met jamais waiting_for_user (cf. awaiting_answer=False).
        "status": "idle",
        "awaiting_answer": False,
        "question": caption or "Diagramme",
        "expected_response_type": "text",
        "source": "agent",
        "hint_level": 0,
        "attempts": 0,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "chart": cleaned,
        "caption": caption or "",
    }

    log_event(
        "ACTIVITY_STARTED",
        message=f"Diagram opened | {caption or 'sans titre'}",
        user_id=user_id,
        thread_id=thread_id,
        tool_name="create_diagram",
        extra={
            "activity_id": activity["activity_id"],
            "subject": "",
            "topic": caption or "",
            "status": "idle",
        },
    )

    return Command(
        update={
            "learning_activity": activity,
            "activity_log": [
                {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "event": "ACTIVITY_STARTED",
                    "status": "idle",
                    "detail": f"diagram {caption or 'sans titre'}"[:300],
                    "hint_level": 0,
                    "activity_type": "diagram",
                }
            ],
            "messages": [
                ToolMessage(
                    content=(
                        "DIAGRAMME PRÊT — la carte est affichée à "
                        "l'étudiant.\n\n"
                        "COMPORTEMENT : accompagne-la dans ta réponse "
                        "finale d'une brève explication (2-4 phrases) "
                        "de ce que le diagramme montre. Ne redonne pas "
                        "le code Mermaid en texte."
                    ),
                    tool_call_id=tool_call_id or "",
                )
            ],
        }
    )
