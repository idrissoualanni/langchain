# Couche infrastructure — frontières techniques du backend.
#
# Regroupe les adaptateurs vers l'extérieur : persistance SQLite
# (database), exécution de code isolée (sandbox), intégration MCP
# (mcp), sessions voix/vidéo temps réel (livekit) et traçabilité
# LangSmith (observability). Aucune logique métier ici : les services
# et le graphe consomment ces briques, jamais l'inverse.
