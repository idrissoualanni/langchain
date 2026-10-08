# DECISIONS.md

## ⚖️ Registre des Décisions Architecturales (ADR)

Ce document trace les choix techniques majeurs et leurs justifications pour éviter la répétition des débats.

### ADR-001 : Choix de Neon Postgres & pgvector
- **Décision** : Utiliser Neon pour la base de données avec l'extension `pgvector`.
- **Justification** : Performance native du HNSW pour la recherche sémantique, scalabilité managée et intégration facile avec FastAPI.
- **Statut** : ✅ Implémenté.

### ADR-002 : Souveraineté de la Mémoire
- **Décision** : Isolation stricte des données de mémoire cognitive. L'administrateur n'a aucun accès aux tables `user_cognitive_memories`.
- **Justification** : Respect de la vie privée et souveraineté totale de l'utilisateur sur son apprentissage.
- **Statut** : ✅ Implémenté.

### ADR-003 : Architecture "Core Persona"
- **Décision** : Injecter un profil synthétisé (Persona) dans le prompt système à chaque tour.
- **Justification** : Évite la perte de contexte sur les préférences utilisateur et les blocages cognitifs.
- **Statut** : ✅ Implémenté.
