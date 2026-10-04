# Plan de déploiement — Agent vocal LiveKit (LiveKit Cloud)

> Document d'exécution. Chaque étape porte sa **preuve de vérification** :
> un déploiement n'est « réussi » que si une sonde l'a constaté (cf. AGENTS.md §2).
> Aucun secret n'apparaît ici : uniquement des instructions de pose.

---

## 0. Ce que l'agent est

| Élément | Valeur | Source de vérité |
|---|---|---|
| Nom d'agent | `tutor` | `backend/app/infrastructure/livekit/constants.py` (`TUTOR_AGENT_NAME`) |
| ID LiveKit | `CA_39eRjheyTL2P` | `agent/livekit.toml` (`[agent] id`) |
| Projet | `agent-cnavrwad` | `agent/livekit.toml` (`[project] subdomain`) |
| Région | `eu-central` | Commande de déploiement |
| Contexte de build | `agent/` (**jamais** la racine) | `agent/Dockerfile` |

### ⚠️ La règle qui casse tout : le nom

`tutor` doit être **rigoureusement identique** à trois endroits. Un seul écart
= le dispatch lancé par l'API ne trouve jamais sa cible = l'agent reste muet
sans erreur visible.

```
1. backend/app/infrastructure/livekit/constants.py  → TUTOR_AGENT_NAME = "tutor"
2. agent/livekit.toml                              → [agent] name = "tutor"
3. agent/.env.local                                → LIVEKIT_AGENT_NAME = tutor   (injecté)
```

**Piège documenté** : `lk agent create` **supprime** la clé `name` de
`livekit.toml`. Il faut la **restaurer à la main après chaque `create`**,
avant `deploy`. C'est la cause historique du silence de l'agent.

---

## 1. Pré-requis et contrôles préalables

Le disque local n'a plus de marge : **C: 236 Go utilisés, ~0,5 Go libres**.
C'est la cause racine des échecs `ENOSPC` déjà rencontrés. Le déploiement
LiveKit étant **distant**, il ne consomme pas le disque local — mais toute
préparation locale (build, install) échouera.

```powershell
# 1. Mesurer AVANT de conclure (AGENTS.md §3)
Get-PSDrive C | Select-Object @{n='Free_GB';e={[math]::Round($_.Free/1GB,2)}}

# 2. Libérer si < 5 Go
npm cache clean --force
pnpm store prune
```

| Contrôle | Attendu | Comment |
|---|---|---|
| Disque libre | > 5 Go | `Get-PSDrive C` |
| CLI LiveKit | installé | `lk --version` |
| Credentials | 4 variables dans `.env.local` | inventaire **des noms** uniquement |

---

## 2. Choisir la commande : `create` ou `deploy` ?

| Cas | Commande | Effet |
|---|---|---|
| **Mise à jour du code** (cas courant) | `lk agent deploy` | Reconstruit et redéploie. **`id` et `name` conservés.** |
| Premier déploiement / agent supprimé | `lk agent create` | ⚠️ **Efface `name`** → le restaurer juste après |

```bash
cd C:\Users\hp\Desktop\langchain\agent
```

---

## 3. Déploiement

### 3.1 Séquence standard (changement de code)

```bash
cd agent

lk agent deploy --project live --region eu-central --secrets-file .env.local --yes
```

### 3.2 Si `create` a été utilisé — RESTAURER le nom

```bash
# Vérifier immédiatement — name doit être présent et valoir "tutor"
cat livekit.toml
```

Si `name` a disparu, le remettre **avant tout déploiement** :

```toml
[project]
  subdomain = "agent-cnavrwad"

[agent]
  id = "CA_39eRjheyTL2P"
  # ⚠️ Restauré après `lk agent create` — cf. section 0
  name = "tutor"
```

Puis re-déployer.

---

## 4. Vérification — le cœur du déploiement

### 4.1 Le déploiement lui-même

```bash
lk agent status
```

| Champ | Attendu |
|---|---|
| ID | `CA_39eRjheyTL2P` |
| Name | `tutor` |
| Deployment | `production` |
| Region | `eu-central` |
| **Deployed At** | **date du jour** — c'est la preuve clé |
| Status | `Sleeping` normal (démarre à la première session) |

⚠️ `Sleeping` n'est **pas** un échec : `AgentServer(num_idle_processes=0)`
garantit qu'aucun processus ne tourne sans session. `Sleeping` avec une date
de déploiement du jour est l'état normal et attendu.

⚠️ Un statut « live » ne prouve rien : lire les logs.

### 4.2 Le pipeline vocal — LA sonde décisive

Un déploiement « réussi » peut avoir un agent **muet**. La seule preuve est la
ligne de log émise par `agent/agent.py` :

```python
logger.info("Pipeline : %s", config.to_dict())
```

Elle porte `stt_model`, `llm_model`, `tts_model`, `tts_voice`.

```bash
lk agent logs   # nécessite une session récente
```

> **Limite honnête** : l'agent endormi refuse de rendre ses logs
> (« The agent has shut down due to inactivity »). Il faut donc **une session
> réelle** pour lire cette ligne. C'est une contrainte de l'outillage, pas un

### 4.3 Test de bout en bout

1. Ouvrir l'application avec un compte vérifié
2. Cliquer le bouton **Voix** → dispatch + navigation vers `/voice`
3. **Vérifier que l'agent PARLE** (l'accueil `GREETING` doit être audible)
   - agent muet ⟹ vérifier `tts_model` au log (§4.2) — voir §5.1
4. Poser une question → réponse vocale
5. Couper/rétablir le micro → l'agent réagit
6. Cliquer **Terminer** → retour à `/assistant`, agent arrêté

### 4.4 Vérifier l'absence d'agent orphelin

```powershell
curl.exe -s -H "Origin: https://frontend-sigma-lilac-62.vercel.app" `
  https://agent-tutor-api.onrender.com/api/livekit/agent/status
```

`status: "stopped"` après le départ = bon. Un `started` résiduel = agent
orphelin qui consomme de l'inference (voir §6).

---

## 5. Les pièges — et pourquoi ils cassent silencieusement

### 5.1 TTS sans endpoint dans la région → agent muet 🔴

`agent/` est déployé en **eu-central**, donc les requêtes partent vers la
région data **eu**. Les modèles `rime/*` n'ont **aucun endpoint** en `eu` :
LiveKit répond `REGION_RESTRICTED` et **l'agent reste muet — sans erreur
visible côté application**.

C'est exactement ce qu'a corrigé le commit `9b46fcf`
(« TTS Deepgram Aura-2 — Rime n'existe pas en eu-central »).

**Règles** :
- Le TTS doit avoir un endpoint **EU**
- Les replis sont limités à `deepgram/aura-2` et `cartesia/sonic-3`
  (`_TTS_FALLBACKS`, `session_factory.py`)
- **Ne pas nommer une voix d'un autre fournisseur** avec un modèle Deepgram
  (ex. voix `rime` + `deepgram/aura-2`) : la synthèse échoue
- `tts_voice` vide = voix par défaut du fournisseur (recommandé)

### 5.2 L'ordre des imports dans `agent.py` → CrashLoop 🔴

```python
server = AgentServer(...)           # ligne 62
async def entrypoint(ctx): ...      # ligne 73
server.rtc_session()(entrypoint)     # ligne 139  ← DOIT être après
```

`rtc_session()(entrypoint)` s'exécute **à l'import du module**. Placé avant la
définition de `entrypoint` → `NameError` → le conteneur part en **CrashLoop**.

### 5.3 Utilisateur non root 🔴

Le conteneur doit tourner en `USER app`, pas en `uid 0` (commit `55adf35`).

Piège associé : les dépendances allaient dans `/root/.local` via `pip --user`,

---

## 6. Agent orphelin — le seul défaut que le client ne peut pas toujours réparer

Quand l'utilisateur ferme l'onglet, le `fetch` de suppression est annulé et le
dispatch **survit** côté LiveKit Cloud. L'agent reste connecté à une room vide,
consommant STT + LLM + TTS **facturés**.

Le frontend envoie désormais `POST /agent/stop` avec `keepalive: true` au
démontage (`app/voice/page.tsx`) — c'est le seul mécanisme qui survit à la
fermeture d'un onglet.

**Ce que `keepalive` ne couvre pas** (limite assumée) :
- `kill -9` du navigateur ou de l'OS
- coupure réseau brutale
- le mobile qui tue le processus en arrière-plan

**Filet de sécurité côté backend** — recommandé :

Une politique de réconciliation (« tout dispatch dont la room est vide depuis
plus de N minutes est supprimé ») est le seul remède durable.
**Non implémentée à ce jour** — c'est le principal reliquat de ce plan.

---

## 7. Retour arrière

Un rollback sur LiveKit Cloud = redéployer un commit connu bon.

```bash
cd agent
git log --oneline -- agent/          # identifier le commit sain
git checkout <commit_sain> -- .      # ⚠️ ne PAS commiter ici
lk agent deploy --project live --region eu-central --secrets-file .env.local --yes
```

| Symptôme | Cause probable | Remède |
|---|---|---|
| Agent muet | TTS `REGION_RESTRICTED` (§5.1) | `.env.local` : `LIVEKIT_TTS_MODEL=deepgram/aura-2` |
| Agent muet | dispatch non trouvé | `name = "tutor"` restauré (§5.1) |
| CrashLoop | ordre des imports (§5.2) | `rtc_session()(entrypoint)` après `entrypoint` |
| `ModuleNotFoundError` | liste de fichiers figée | glob `*.py` restauré (§5.4) |
| Conteneur root | `USER app` retiré | venv `/opt/venv` + `COPY --chown` (§5.3) |

**Avant tout rollback** : lire l'état réel. Un rollback exécuté sur un système
sain supprime des correctifs et crée un second incident (AGENTS.md §6).

---

## 8. Checklist de déploiement

- [ ] Disque libre > 5 Go
- [ ] `lk --version` fonctionne
- [ ] Noms des secrets inventoriés (valeurs **jamais** affichées)
- [ ] `livekit.toml` : `id` **et** `name = "tutor"` présents
- [ ] `TUTOR_AGENT_NAME` aligné côté API
- [ ] `.env.local` : `LIVEKIT_TTS_MODEL` a un endpoint **EU**
- [ ] `lk agent deploy` lancé depuis `agent/` (jamais la racine)
- [ ] `lk agent status` : `Deployed At` = aujourd'hui, `Name` = `tutor`
- [ ] Session réelle : **l'agent parle** (log `Pipeline :`)
- [ ] Départ de session : `agent/status` → `stopped` (pas d'orphelin)
- [ ] Journal de déploiement à jour (date, version, ce qui a changé)

---

## 9. Diagnostic rapide

| Symptôme | Vérifier | Section |
|---|---|---|
| « Serveur LiveKit indisponible » (503) | `/api/health`, `LIVEKIT_HOST` côté API | §4.3 |
| Écran « Session vocale indisponible » | cookie de session valide, `/api/livekit/token` | §4.3 |
| Agent connecté mais **muet** | `tts_model` au log `Pipeline :` | §5.1 |
| Agent **absent** de la room | `name = "tutor"` | §5.1 |
| Déconnexions en boucle | renouvellement du token (50 min) | §4.3 |

---

## 10. État vérifié au 2026-10-04

Relevé réel, avant toute action :

```
Agent  : tutor (CA_39eRjheyTL2P) · eu-central · production
Version: uQX6qocroLza
Déployé: 2026-10-01T21:18:35Z   ← PÉRIMÉ
Status : Sleeping (normal)
```

**Écart avec le dépôt** — deux correctifs du 03/10 ne sont pas déployés :

| Commit | Date | Contenu | Déployé |
|---|---|---|---|
| `baf5ff6` | 01/10 | voix TTS, glob Dockerfile | ✅ |
| `9b46fcf` | 03/10 | fix TTS Deepgram Aura-2 (Rime absent en eu-central) | ❌ |
| `55adf35` | 03/10 | fix : conteneur non-root (`USER app`) | ❌ |

→ **Action requise** : `lk agent deploy` pour intégrer les deux correctifs.
Le point non-root est certain (il dépend du Dockerfile lui-même). Le point
TTS est atténué par `.env.local` (`LIVEKIT_TTS_MODEL=deepgram/aura-2`) mais
**non prouvé** : les logs sont inaccessibles sur un agent endormi (§4.2).

et `/root` étant en mode `700`, **ajouter `USER app` seul aurait cassé le
démarrage**. Le Dockerfile résout cela avec un venv à `/opt/venv` (lisible
par tous) + `COPY --chown=app:app`.

**Conséquence de l'oubli** : le conteneur tourne en root — un contournement
de toutes les protections du runtime.

### 5.4 Module Python oublié dans l'image

Le Dockerfile utilise volontairement un **glob** `COPY *.py ./` : une liste
explicite avait oublié `memory_tools.py` lors de son ajout, ce qui cassait le
job en production (`ModuleNotFoundError`).

→ **Ne jamais remplacer le glob par une liste de fichiers.**

### 5.5 Import circulaire — la seconde source de vérité

`server.rtc_session()(entrypoint)` **sans** `agent_name=` : l'identité vient de
`LIVEKIT_AGENT_NAME`. Passer le nom ici créerait une **seconde source de
vérité** divergente du dispatch API.

> bug — et c'est pourquoi le déploiement ne peut pas être validé seul.

| `livekit.toml` complet | `id` + `name` présents | lecture du fichier |
| Nom aligné | `tutor` aux 3 endroits | `Select-String TUTOR_AGENT_NAME` |

**Inventaire des secrets sans les afficher** (§4 — seul le nom est autorisé) :

```powershell
# NOMS uniquement — ne jamais afficher les valeurs
Select-String -Path agent\.env.local -Pattern '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=' |
  ForEach-Object { $_.Matches[0].Groups[1].Value }
```

Attendu : `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
`LIVEKIT_AGENT_NAME`, `LIVEKIT_STT_MODEL`, `LIVEKIT_STT_LANGUAGE`,
`LIVEKIT_LLM_MODEL`, `LIVEKIT_TTS_MODEL`, `LIVEKIT_MAX_TURNS`,
`LIVEKIT_LOG_LEVEL`, `LIVEKIT_TELEMETRY_ALLOW_PII`, `AGENT_API_URL`,
`AGENT_SERVICE_SECRET`.
