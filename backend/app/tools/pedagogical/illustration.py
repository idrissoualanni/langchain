# Tool illustrations V7.0 — création d'activités visuelles (Mermaid & Tableaux).
#
# Même mécanique que create_exercise/create_quiz : Command(update={...})
# natif LangGraph, l'activité vit dans CustomAgentState.learning_activity
# (persistée par le checkpointer). Le frontend rend l'activité via le
# contrat AgentResponse type="illustration", et la carte IllustrationCard
# applique le style du projet.
#
# GARDE-FOUS DE VALIDITÉ :
#   - Pour 'diagram' : validation Mermaid stricte (§27-§30) ;
#   - Pour 'table' : validation du format des données structurées ;
#   - blocs ```mermaid ... ``` retirés automatiquement ;
#   - nombre de lignes/cellules borné (règle pédagogique) ;
#   - repli contrôlé : illustration invalide → message d'erreur.
from __future__ import annotations

import re
import time
from enum import Enum
from typing import Annotated

from langchain.tools import InjectedToolCallId
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.config import RunnableConfig
from langgraph.types import Command

from app.logging.events import log_event

class IllustrationType(str, Enum):
    DIAGRAM = "diagram"
    TABLE = "table"

# Types acceptés par le renderer frontend (mermaid-diagram.aui.tsx)
DIAGRAM_KEYWORDS = {
    "graph", "flowchart", "sequenceDiagram", "classDiagram",
    "stateDiagram", "stateDiagram-v2", "erDiagram", "gantt",
    "pie", "mindmap", "timeline", "journey", "gitGraph",
}

MAX_DIAGRAM_LINES = 30

def _clean_diagram(chart: str) -> tuple[str, str | None]:
    """Normalise le code mermaid fourni. Retour (chart, erreur)."""
    text = (chart or "").strip()
    if not text:
        return "", "Le contenu du diagramme est vide."

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
def create_illustration(
    illustration_type: IllustrationType,
    content: str,
    caption: str = "",
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Ouvre une activité VISUELLE : un diagramme ou un tableau synthétique
    qui sera dessiné à l'étudiant dans une carte dédiée du fil de discussion.

    Utilise ce tool quand une structure, un processus ou une comparaison
    gagne à être montrée plutôt qu'écrite :
      - type='diagram' : flux d'un algorithme, hiérarchie de classes,
        machine à états, schéma de BDD, chronologie (utilise Mermaid).
      - type='table' : comparaisons de concepts, synthèses de caractéristiques,
        tableaux de vérité (fournis les données structurées en format clair).

    Règles STRICTES pour le type 'diagram' :
      - fournis le code BRUT, SANS fence ``` ni bloc markdown ;
      - la PREMIÈRE ligne est le mot-clé du diagramme seul ;
      - maximum ~15 nœuds.

    Après ce tool : présente brièvement l'illustration à l'étudiant dans
    ta réponse finale. Un seul élément par appel.

    Args:
        illustration_type: 'diagram' pour un schéma Mermaid, 'table' pour un tableau.
        content: code Mermaid brut pour 'diagram', ou données structurées pour 'table'.
        caption: titre court de l'illustration affiché sur la carte.
    """
    conf = (config or {}).get("configurable", {}) or {}
    user_id = conf.get("user_id", "") or ""
    thread_id = conf.get("thread_id", "") or ""
    log_event(
        "TOOL_CALL",
        message=(
            f"create_illustration type={illustration_type} "
            f"caption={caption!r} content={len(content or '')} chars"
        ),
        tool_name="create_illustration",
        user_id=user_id,
        thread_id=thread_id,
    )

    final_content = content
    if illustration_type == IllustrationType.DIAGRAM:
        cleaned, error = _clean_diagram(content)
        if error is not None:
            log_event(
                "TOOL_ERROR",
                level="WARNING",
                message=f"create_illustration invalid diagram: {error}",
                tool_name="create_illustration",
                user_id=user_id,
                thread_id=thread_id,
            )
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=(
                                f"ILLUSTRATION REJETÉE — {error}\n\n"
                                "Corrige le code et rappelle "
                                "create_illustration. Exemple valide :\n"
                                "graph TD\n"
                                "  A[Entree] --> B{Test}\n"
                                "  B -- oui --> C[Action]"
                            ),
                            tool_call_id=tool_call_id or "",
                        )
                    ]
                }
            )
            final_content = cleaned

    activity = {
        "activity_id": f"illustration-{int(time.time() * 1000)}",
        "activity_type": "illustration",
        "sub_type": illustration_type,
        "status": "idle",
        "awaiting_answer": False,
        "question": caption or "Illustration",
        "expected_response_type": "text",
        "source": "agent",
        "hint_level": 0,
        "attempts": 0,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "content": final_content,
        "caption": caption or "",
    }

    log_event(
        "ACTIVITY_STARTED",
        message=f"Illustration opened | {caption or 'sans titre'}",
        user_id=user_id,
        thread_id=thread_id,
        tool_name="create_illustration",
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
                    "detail": f"illustration ({illustration_type}) {caption or 'sans titre'}"[:300],
                    "hint_level": 0,
                    "activity_type": "illustration",
                }
            ],
            "messages": [
                ToolMessage(
                    content=(
                        "ILLUSTRATION PRÊTE — la carte est affichée à "
                        "l'étudiant.\n\n"
                        "COMPORTEMENT : accompagne-la dans ta réponse "
                        "finale d'une brève explication. Ne redonne pas "
                        "le contenu brut dans le texte."
                    ),
                    tool_call_id=tool_call_id or "",
                )
            ],
        }
    )
