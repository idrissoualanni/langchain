# Tools pédagogiques — exposés au LLM (exercices, quiz, évaluation,
# diagrammes).
from app.tools.pedagogical.illustration import create_illustration as create_diagram
from app.tools.pedagogical.exercise_library import search_exercise_library
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

pedagogical_tools = [*pedagogical_tools, create_diagram, search_exercise_library]

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
    "search_exercise_library",
]
