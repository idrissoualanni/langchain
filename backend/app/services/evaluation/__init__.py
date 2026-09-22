# Evaluation Engine (Phase 2) — §18-§20.
#
# Sépare le SCORING de la MISE À JOUR DU PROFIL :
#
#   Answer → evaluation.engine.evaluate_activity()
#         → evaluation.observations.emit_observation() → profil
#
# Stratégie §19 : deterministic → execution/tests → domain_rules → llm.
#
#   schemas.py       EvaluationResult §20 (contrat stricte, extra=forbid)
#   engine.py        moteur de scoring (déterministe §19)
#   text_scoring.py  helpers de scoring CANONIQUES (partagés tools)
#   observations.py  pont EvaluationResult → LearningObservation