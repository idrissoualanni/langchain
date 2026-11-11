# Feature flags et inventaire des fonctionnalités

> Audit du 2026-11-11 sur `dev` (`b9eae6e`) + branche `task/feature-flags`.
> Règle : une fonctionnalité dont le backend n'est pas prêt est **désactivée par flag**, pas livrée cassée.

## Mécanisme

- Code : `frontend/src/lib/flags.ts`. Défaut figé dans `FEATURE_FLAGS`.
- Forçage au build (Vercel) : `VITE_FEATURE_<NOM_EN_SNAKE_CASE>=true|false`
  (ex. `VITE_FEATURE_ADMIN_EXERCISES=true`). Valeur illisible → défaut.
- Réactiver un flag = livrer le backend correspondant, puis passer le défaut à `true`.

## Flags actifs

| Flag | Défaut | Effet quand éteint | Raison | Pour réactiver |
|---|---|---|---|---|
| `adminExercises` | `false` | Route `/admin/exercises` et entrée « Exercices » du menu admin masquées | `GET/PUT /api/admin/exercises`, `POST /api/admin/exercises/{id}/validate` n'existent pas (seul `repositories/exercises.py` existe) | Exposer les routes admin (api → services → repositories) + `API.md` |
| `adminGroups` | `false` | `GroupSelector` n'appelle plus `/api/admin/groups` (404) et passe directement en saisie manuelle | Route `/api/admin/groups` absente | Implémenter la route + `API.md` |

## Inventaire

### ✅ Fonctionne (vérifié)

| Domaine | Preuve |
|---|---|
| Graphe LangGraph | `compile_main_graph` compile (MemorySaver + InMemoryStore) : 17 nœuds, 25 arêtes ; les 7 workflows (`main`, `activity`, `problem`, `research`, `coding`, `video`, `document`) ont une branche réelle (`WIRED_WORKFLOWS`) |
| Outils | 38 outils enregistrés (`app.tools.all_tools`) |
| Imports API | `app.main`, `app.infrastructure.livekit`, `app.tools`, `app.graph.main` importent sans erreur |
| Contrat frontend ↔ backend | 73 chemins `/api/...` du frontend croisés avec les 99 chemins OpenAPI : tous présents sauf les 2 flaggés ci-dessus |
| LiveKit (code) | Routes `token`, `agent/start|status|stop`, `screen-share/*` : frontend et backend alignés ; nom d'agent `tutor` identique dans `constants.py`, `agent/config.py`, `agent/livekit.toml` ; `agent/` compile |
| Mentions `@` (routage) | Backend : `workflow` validé contre `KNOWN_WORKFLOWS`, inconnu ignoré + tracé |
| Mentions `@` (popover) | **Corrigé** dans cette branche : un terme choisi dans le popover est maintenant reconnu (voir ci-dessous) |
| UI | Lint OK (warnings seulement), build Vite OK, tests Vitest verts |

### 🐞 Corrigé dans `task/feature-flags`

- **Mentions `@` choisies dans le popover ignorées.** Le popover assistant-ui insère
  `:mention[Deep Research]{name=deep-research}`, alors que `parseComposerTerms` ne
  reconnaissait que `@deep-research`. Effet : pas de routage vers le workflow, directive
  brute envoyée au modèle, badge absent. Seul le terme tapé à la main fonctionnait.
  Correctif : `normalizeComposerText` ramène les directives connues à `@id` ; le badge
  utilise les mêmes fonctions. Test de reproduction : `use-composer-mentions.test.ts`.

### ❌ Absent / non vérifiable

| Sujet | État |
|---|---|
| Commandes `/` | **Non implémentées** (aucun code frontend ni backend). assistant-ui 0.15 fournit `unstable_useSlashCommandAdapter` : à concevoir avant d'implémenter (quelles commandes ?) |
| LiveKit en conditions réelles | Non vérifiable depuis ce poste (secrets et LiveKit Cloud). À contrôler après déploiement : `GET /api/livekit/agent/status` |
| Tests `integration` (Neon) | Sautés hors base |

### 🚫 Écarté (connu, non bloquant)

| Sujet | État |
|---|---|
| Conversion DOCX → Markdown | `mammoth` 1.13 échappe la ponctuation (`lecon\.`). Affichage correct, texte indexé bruité. Test `test_docx_to_markdown` en `xfail`. Correctif : désescaper la sortie avant découpage |
| Bibliothèque d'exercices admin | Flag `adminExercises=false` (routes backend absentes) |
| Groupes admin | Flag `adminGroups=false` (route backend absente) |
| Commandes `/` | Non implémentées |
| Service Render staging | Inexistant (404) : `deploy.yml` (staging puis prod) ne peut pas aboutir ; déploiement prod fait directement via l'API Render |

### ⚠️ Risques de déploiement

1. **LiveKit — secrets par défaut** : `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET` retombent sur
   `devkey`/`devsecret` si absents. En prod, les jetons émis seraient invalides sans erreur
   claire. Vérifier que les 3 variables `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
   sont posées sur Render.
2. **LiveKit — nom d'agent** : l'agent Cloud lit son nom dans `LIVEKIT_AGENT_NAME` (secret
   LiveKit Cloud). Absent → l'agent s'enregistre sans nom et le dispatch `tutor` n'est jamais
   réclamé (silence dans la room).
3. **`AGENT_SERVICE_SECRET`** : doit être identique côté Render et côté agent LiveKit Cloud,
   sinon `/api/agent-memory/*` répond 401/503 et l'agent vocal perd la mémoire.
4. **Tests Vitest sous Windows** : lancés depuis un chemin `c:\…` (minuscule), 4 tests
   échouent à tort (modules chargés en double). Lancer depuis `C:\…`. La CI Linux n'est pas
   concernée.
5. **`ruff`** non installé sur ce poste : l'étape « Ruff » de la CI n'a pas été rejouée localement.
