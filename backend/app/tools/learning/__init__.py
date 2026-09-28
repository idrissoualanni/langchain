# Tools learning — exposition LLM du Learning Profile.
#
# learning.py est la façade qui ré-exporte tous les tools pédagogiques
# définis dans profile.py / goals.py / aggregations.py / session.py.
# On se contente de réexporter ce que cette façade expose ( son __all__ )
# pour garder l'alignement lors des refactors.
from app.tools.learning.learning import (
    complete_learning_goal,
    create_learning_goal,
    forget_memory,
    get_learning_profile,
    get_learning_topic,
    get_past_session_summaries,
    get_strong_concepts,
    get_weak_concepts,
    learning_tools,
    record_learning_observation,
    save_session_summary,
    search_memories,
    update_goal_progress,
)

__all__ = [
    "get_learning_profile",
    "get_learning_topic",
    "record_learning_observation",
    "create_learning_goal",
    "update_goal_progress",
    "complete_learning_goal",
    "get_weak_concepts",
    "get_strong_concepts",
    "get_past_session_summaries",
    "search_memories",
    "forget_memory",
    "save_session_summary",
    "learning_tools",
]
