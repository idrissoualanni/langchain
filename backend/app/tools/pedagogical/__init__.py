# Tools pédagogiques — exposés au LLM (exercices, quiz, évaluation,
# diagrammes).
from app.tools.pedagogical.diagram import create_diagram
from app.tools.pedagogical.pedagogical import (
    assess_understanding,
    create_exercise,
    create_quiz,
    create_quiz_next,
    evaluate_answer,
    give_hint,
    pedagogical_tools,
    propose_review,
)

pedagogical_tools = [*pedagogical_tools, create_diagram]

__all__ = [
    "assess_understanding",
    "create_diagram",
    "create_exercise",
    "create_quiz",
    "create_quiz_next",
    "evaluate_answer",
    "give_hint",
    "pedagogical_tools",
    "propose_review",
]
