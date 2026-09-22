"""Constantes partagées LiveKit ( backend + worker ).

TUTOR_AGENT_NAME est l'unique source de vérité du nom d'agent : il doit
être strictement identique entre l'API ( qui émet le dispatch ) et le
worker ( qui le réclame ). Un mismatch = dispatch jamais réclamé,
silence total dans la room.
"""

TUTOR_AGENT_NAME = "tutor"
