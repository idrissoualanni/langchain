# SHIM de compatibilité (refactor — phase migration).
#
# Le worker vocal se lance désormais via :
#   python -m app.infrastructure.livekit.agent
# (ancien : python -m app.livekit.agent)
from app.infrastructure.livekit.agent import TutorAgent

__all__ = ["TutorAgent"]
