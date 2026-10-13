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

### ADR-004 : Dérogation push unique — nettoyage des branches fusionnées
- **Décision** : Autoriser **un seul** `git push` vers `origin`, avec le bornage mémoire imposé par l'AGENTS.md
  (`git -c pack.threads=1 -c pack.deltaCacheSize=4m -c pack.windowMemory=16m push …`), pour publier `dev` et
  supprimer les branches **distantes déjà fusionnées**. Aucun autre push, aucun déploiement (Render/Vercel)
  depuis ce poste.
- **Justification** : L'AGENTS.md interdit tout `git push` depuis ce poste. L'utilisateur a explicitement étendu
  le périmètre de la consolidation à `origin` (« merger toutes les branches sur dev puis supprimer les autres »).
  La suppression de refs distant​es fusionnées est impossible sans push : la dérogation est donc ponctuelle,
  tracée ici, et validée par l'Architecte (délégué à l'agent principal).
- **Statut** : ✅ Appliqué (ponctuel, à la date du commit de consolidation).

### ADR-005 : Histoires orphelines — attachement d'historique sans reprise d'arborescence
- **Décision** : Fusionner `audit-cleanup`, `mission/v5.2-pedagogical-tools` et
  `origin/knowledge-model-observability-b9643` dans `dev` par `git merge -s ours --allow-unrelated-histories` :
  les 12 commits sont rattachés à l'historique de `dev`, l'arborescence de `dev` reste strictement inchangée.
- **Justification** : Ces branches n'ont **aucun ancêtre commun** avec `dev` et portent l'architecture antérieure
  (361 fichiers propres à l'orpheline, dont `__pycache__` versionnés et `backend/app/agent/*` devenu obsolète).
  Un merge classique réintroduirait ce code mort et 150 conflits ; l'attachement conserve la traçabilité des
  missions V4 → V10 sans régression fonctionnelle.
- **Statut** : ✅ Implémenté.

### ADR-006 : Merge `app-sidebar-file-report-5905f` résolu en faveur de `dev`
- **Décision** : Sur les 45 conflits et 72 fichiers impactés du merge, la version `dev` est retenue, sauf trois
  apports distincts de la branche conservés : le test `EvaluationCard.test.tsx` (4 tests verts), la heuristique de
  streaming de `mermaid-diagram.aui.tsx` (+40 lignes) et la suppression du composant mort `activity-card.tsx`
  (aucune référence). Les artefacts ramenés (`__pycache__`, `frontend/coverage/`, `backend/database/*.db`) sont
  écartés au titre de l'hygiène disque.
- **Justification** : la branche part d'un ancêtre commun lointain et propose l'ancienne architecture (Neon Auth
  → Clerk, graphe 17 → 15 nodes, façade `learning` non refactorisée, `.env.example` Clerk). Sa valeur réelle est
  l'historique qu'elle attache plus ces trois apports, tous vérifiés verts (`pytest`, `tsc`, `vitest`).
- **Statut** : ✅ Implémenté.
