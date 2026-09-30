# Référentiel d'exigences — Service d'authentification

> Document de référence. Chaque exigence est numérotée, sourcée et **testable**.
> Rédigé le 2026-09-30 après cartographie intégrale du code (backend + frontend).
>
> **Convention de statut** — `CONFORME` : l'exigence est satisfaite par le code
> aujourd'hui, vérifié à la ligne citée. `ÉCART` : le code existe mais ne satisfait
> pas l'exigence. `MANQUANT` : rien ne l'implémente. `BLOQUANT` :atisfied par une
> dépendance externe que nous ne contrôlons pas.
>
> Une exigence sans critère de vérification est un vœu. Chacune ci-dessous en a un.

---

## 1. Périmètre

Ce document couvre **le service d'authentification** : inscription, connexion,
maintien et renouvellement de session, vérification d'adresse, récupération d'accès,
attribution et application du rôle administrateur.

Il ne couvre pas : le stockage des données métier, l'isolation entre utilisateurs
une fois l'identité établie (documentée dans `ARCHITECTURE.md` § isolation), ni le
choix des fournisseurs d'inférence.

### 1.1 Sources de vérité — hiérarchie explicite

En cas de divergence, l'ordre suivant fait foi. Cette hiérarchie n'était nulle part
écrite ; elle est la cause de plusieurs incohérences constatées.

| Rang | Source | Autorité |
|---|---|---|
| 1 | Configuration du fournisseur d'identité (console Neon Auth) | dit si un compte existe, si un email est vérifié, si le mot de passe est valide |
| 2 | `neon_auth.*` (PostgreSQL) | données du fournisseur |
| 3 | `public.users` | données internes : rôle, date de création, rattachement |
| 4 | JWT signé (`sub`, `exp`, `aud`) | identité d'une requête, rien d'autre |
| 5 | Frontend | **aucune** — ne décide jamais, ne stocke aucune autorité |

> **Règle dérivée :** l'UI ne détient aucun secret d'authentification. C'est
> vérifiable : aucun `VITE_*` du dépôt n'est un secret (`frontend/.env.production`
> ne contient que `VITE_AUTH_MODE`, `VITE_NEON_AUTH_URL`, `VITE_API_URL`).
> Critère de test : `grep -ri "secret\|key\|password" frontend/.env*` ne doit
> renvoyer que des lignes commentées ou vides.

### 1.2 Qui décide quoi

| Décision | Autorité | today |
|---|---|---|
| Le compte existe | Neon Auth | `disableSignUp: false` |
| L'email est vérifié | Neon Auth | `requireEmailVerification: false` |
| Le mot de passe est correct | Neon Auth | Better Auth |
| Le `sub` correspond à un compte interne | `public.users` | `resolve_internal_user` |
| Le rôle est `admin` | `ADMIN_EXTERNAL_IDS` **puis** `users.role` | variable d'env prioritaire |
| L'interface peut afficher la section admin | `GET /api/users/me` | relit la ligne en base |

---

## 2. Invariants — non négociables

Un invariant est une propriété qui doit être vraie **toujours**, quel que soit le
contexte d'appel. Toute exception à ces règles est un défaut de sécurité, pas un
cas particulier.

- **I-1** — L'identité d'une requête provient **exclusivement** d'un jeton signé
  vérifié. Aucun `user_id` présent dans un corps de requête, un query string ou un
  en-tête client n'est une source d'identité.
- **I-2** — Toute défaillance du fournisseur d'authentification produit un refus
  (`401`/`503`), jamais un accès. Il n'existe aucun chemin où une erreur de
  vérification aboutit à un usage authentifié.
- **I-3** — Le rôle `admin` est fail-closed : en l'absence de rôle vérifié, le
  comportement est « utilisateur ordinaire ».
- **I-4** — Un client ne peut ni élargir ses droits, ni élargir sa portée, en
  fournissant une valeur dans une requête.

---

## 3. Exigences fonctionnelles

### Inscription

**EF-1 — L'inscription passe exclusivement par le fournisseur d'identité.**
L'application ne crée aucun compte elle-même.
> *Vérifié.* `POST /api/users` n'existe que sous `AUTH_MODE == "dev"`
> (`backend/app/api/users.py:89`).
> **Critère :** en `AUTH_MODE=neon`, un `POST /api/users` renvoie `404`.

**EF-2 — L'inscription ne crée pas de session.**
L'utilisateur doit se connecter explicitement.
> *Vérifié.* `SignUpPage.tsx:82-84` le documente et redirige vers `/verify-email`.
> **Critère :** après inscription réussie, `GET /get-session` renvoie `null`.

### Vérification d'adresse

**EF-3 — L'état de vérification d'un email doit être une décision du fournisseur,
jamais une convention de l'application.**
> *ÉCART.* `requireEmailVerification: false` (console Neon Auth) : un compte non
> vérifié se connecte et accède à l'application entière. La page `/verify-email`,
> son OTP, son renvoi et son cooldown sont donc **inertes** — ils affichent un
> parcours qui ne conditionne rien.
> **Décision en attente** (voir §7, D-1).
> **Critère :** un compte `emailVerified = false` doit soit être rejeté par le
> fournisseur à la connexion, soit pouvoir accéder sans avoir à saisir d'OTP. Les
> deux comportements sont acceptables ; l'état actuel, où le parcours existe sans
> produire d'effet, ne l'est pas.

**EF-4 — L'application doit pouvoir déclencher l'envoi d'un code de vérification.**
> *CONFORME.* `SignUpPage.tsx:87` et `VerifyEmailPage.tsx:102` appellent
> `POST /send-verification-email`. Testé : cet endpoint répond `200` **sans session**
> (mon hypothèse initiale d'une session requise était fausse).
> **Critère :** `POST /send-verification-email` renvoie un `2xx` et une ligne est
> créée dans `neon_auth.verification`.

**EF-5 — Le renvoi d'un code doit être limité en fréquence côté client.**
> *CONFORME.* `RESEND_COOLDOWN = 60` (`SignUpPage.tsx:24`), compte à rebours et
> bouton désactivé. `VerifyEmailPage` a reçu le même mécanisme.
> **Critère :** deux clics en moins de 60 s ne produisent qu'un appel.

### Connexion

**EF-6 — L'erreur de connexion ne doit jamais divulguer si un compte existe.**
> *CONFORME.* `SignInPage.tsx:63-69` renvoie « Email ou mot de passe incorrect. »
> pour `INVALID_EMAIL_OR_PASSWORD` comme pour `INVALID_EMAIL`. Le fournisseur
> lui-même est indistinct (`401 INVALID_EMAIL_OR_PASSWORD` sur mauvais mot de passe,
> testé).
> **Critère :** le corps de la réponse est identique pour « compte inexistant » et
> « mot de passe faux ».

**EF-7 — L'interface doit distinguer les causes d'échec par le champ `code` du
fournisseur, jamais par le texte du message.**
> *CONFORME.* `lib/neon.ts` expose `NeonAuthError` (champs `code`, `status`) et
> `hasAuthCode()` ; les pages `SignIn`, `SignUp` et `VerifyEmail` discriminent par
> `code`, avec le texte en simple repli.
> **Pourquoi c'était cassé :** Better Auth place `EMAIL_NOT_VERIFIED` **uniquement**
> dans `code`, jamais dans `message`. Le code testait `/EMAIL_NOT_VERIFIED/i` sur le
> message : la branche était structurellement inatteignable et tout tombait dans
> « mot de passe incorrect », faisant retaper indéfiniment un mot de passe valide.
> **Critère :** un `code` inconnu doit produire le message brut du fournisseur, pas
> un message inventé.

### Session — maintien et expiration

**EF-8 — L'expiration du jeton est invisible pour l'utilisateur.**
Un `401` déclenche **une seule** tentative de renouvellement puis un rejeu de la
requête originale.
> *PARTIEL.* Le mécanisme existe : `base.ts:94-103` (`retryAfter401`) →
> `tryRefreshSession` (l.47-53) → re-tentative unique si un `Authorization` est
> disponible après refresh. Le cache de jeton anticipate l'expiration à 60 s
> (`NeonTokenBridge.tsx:65`). Trois manques :
> 1. **Aucune déduplication.** Deux appels concurrents en cache-miss déclenchent deux
>    `GET /token` ; `refreshNeonSession` n'est pas dédupliqué non plus. Le `focus`
>    (l.104) et chaque `401`_simultané lancent des rafales de `GET /get-session`.
> 2. **Aucune protection contre la boucle.** Un `401` après refresh déclenche un
>    second cycle ; le garde de l.101 (`if (!('Authorization' in after)) return null`)
>    ne couvre que le cas « pas de jeton du tout ».
> 3. **Pas de distinction d'erreur** : `getJson` fait `if (!res.ok) return null`
>    (`lib/neon.ts:108`), donc un `500` du fournisseur devient « pas de session ».
> **Critère :** N appels API simultanés sur session froide produisent **une seule**
> requête `/token`. Une panne du fournisseur ne provoque pas de boucle de retry.

**EF-9 — Une erreur réseau sur la résolution de session ne doit pas déconnecter
l'utilisateur.**
> *ÉCART.* `NeonTokenBridge.tsx:90-93` : le `catch` réseau aboutit à
> `notifyNeonUser(EMPTY)`, identique à une expiration réelle. Un fournisseur
> momentanément injoignable au retour sur onglet déconnecte l'utilisateur de l'UI.
> **Critère :** un `get-session` en erreur réseau conserve la session connue et
> signale une indeterminate distincte de « déconnecté ».

**EF-10 — La déconnexion doit mettre à jour l'état de session de façon immédiate.**
> *ÉCART.* `auth/NeonUserMenu.tsx:26-33` appelle `signOut()` puis
> `navigate('/sign-in')`, mais **n'appelle jamais `notifyNeonUser(EMPTY)`** :
> `RequireAnonymous` (`App.tsx:102-104`) relit `signedIn === true` et renvoie
> vers `/assistant`. L'état se répare seul au premier `401` API ; si aucun appel
> n'est déclenché, l'utilisateur reste visuellement connecté.
> Aggravant : `signOut` avale ses erreurs (`lib/neon.ts:130-132`) — une panne réseau
> laisse la session réellement active.
> **Critère :** après `signOut`, `getNeonUser().isSignedIn` vaut `false` sans qu'aucun
> appel réseau ne soit nécessaire.

**EF-11 — Une route protégée ne doit pas rediriger avant que la session soit
résolue.**
> *ÉCART.* L'état initial du pont est `EMPTY` (`NeonTokenBridge.tsx:16-22`) et
> `refreshNeonSession` ne tourne qu'en `useEffect` (l.102). Tout chargement à froid
> d'une route protégée passe par `/sign-in` avant résolution, puis `RequireAnonymous`
> renvoie vers `/assistant` : double redirection visible pour **tout** utilisateur
> connecté à chaque rechargement.
> **Critère :** un état `loading` initial (« session en cours de résolution ») doit
> exister et être distinct de « pas de session ».

### Récupération d'accès

**EF-12 — L'application ne doit pas annoncer une fonctionnalité qu'elle n'assure
pas.**
> *CONFORME.* `forgetPassword` et `resetPassword` lèvent `RESET_UNAVAILABLE`
> (`lib/neon.ts:184-188` et `191-198`). `ForgotPasswordPage.tsx:40-43,79-87` affiche
> un bandeau expliquant honnêtement que la réinitialisation n'est pas activée, avec
> une issue de repli vers la vérification d'email. Le lien « mot de passe oublié »
> est conservé, conformément à la décision produit.
> **Critère :** aucune interface ne suggère l'arrivée d'un email de réinitialisation
> que le système n'envoie pas.

**EF-13 — Un lien de réinitialisation inerte doit produire un écran explicite, pas
une erreur opaque.**
> *CONFORME.* `ResetPasswordPage.tsx:101-122` affiche « Lien invalide » avec la
> raison et une issue de repli.
> **Réserve :** ce code est **mort** — `resetPassword` lève systématiquement avant
> tout appel réseau. À supprimer ou à brancher, mais pas à laisser en l'état.

### Rôle administrateur

**EF-14 — Le rôle ne doit être应用于 qu'à partir d'une source unique et
auditable.**
> *ÉCART.* Deux mécanismes se superposent : `ADMIN_EXTERNAL_IDS` (variable
> d'environnement) **prime** sur `users.role`, et l'écart est ensuite persisté en
> base (`resolver.py:149-156`). La variable est donc autoritaire et la base est un
> miroir. Un retrait de la variable d'env ne rétrograde personne.
> **Critère :** le rôle effectif doit être dérivable d'une seule lecture ; l'écart
> entre variable et base ne doit pas exister à l'état quiescent.

**EF-15 — L'interface ne doit jamais afficher un droit que le backend n'accorde pas,
ni l'inverse.**
> *ÉCART.* `GET /api/users/me` (`api/users.py:66-75`) **relit la ligne en base** pour
> le rôle, alors que l'autorisation backend utilise le rôle calculé à la volée. Une
> panne de cet appel (`useCurrentUser.ts:102-104` → `internal = null`, puis l.117
> `role ?? 'user'`) dégrade silencieusement l'utilisateur au rang ordinaire **sans
> message**. Symptôme observé : `AdminGate` affiche 403 et le groupe admin de la
> barre latérale disparaît, sans indication de cause.
> **Critère :** un échec de résolution d'identité doit produire un état d'erreur
> explicite, jamais un « pas admin » silencieux.

**EF-16 — Le backend doit exposer le rôle qu'il applique, pas un rôle relu ailleurs.**
> *ÉCART structurel.* Le rôle appliqué par le resolver et le rôle renvoyé par
> `/api/users/me` proviennent de deux lectures. Ils convergent aujourd'hui grâce à la
> persistance d'écart, mais rien ne garantit la convergence.
> **Critère :** `GET /api/users/me` doit renvoyer le rôle que la requête courante
> applique effectivement.

**EF-17 — Les lignes sans `external_user_id` ne doivent jamais être rattachées
arbitrairement.**
> *CONFORME.* `resolver.py:138-139` le documente et ne le fait pas.
> **Conséquence à traiter :** 3 lignes de `public.users` sont orphelines (leur `sub`
> est absent de `neon_auth."user"`) et 1 porte `external_user_id IS NULL` (créée par
> `POST /api/users` en mode dev, exécuté contre la base de production). Ces lignes
> sont inatteignables par construction.
> **Critère :** un inventaire des lignes non rattachables est produit et une décision
> de purge est prise.

### Surface réseau

**EF-18 — Toute requête à l'API doit porter un jeton, et par un chemin unique.**
> *ÉCART MAJEUR.* Le wrapper `api/base.ts` le fait (`authHeader`, l.25-40). **Quatre
> appels le contournent**, tous en chemin **relatif** :
> | Fichier | Problème |
> |---|---|
> | `src/api/events.ts:12` | `EventSource` ne peut pas porter d'en-tête ; `onerror` vide → reconnexion infinie silencieuse |
> | `src/features/transcription/TranscriptionPanel.tsx:88` | `Bearer ${window.__neonGetToken?.() || ""}` — **Promise non attendue**, le littéral de gabarit la stringifie → en-tête invalide |
> | `src/components/admin/ActivityMonitor.tsx:23` | `fetch("/api/admin/dashboard/activity-stats")` **sans en-tête** → `401` permanent → « Aucune donnée disponible » |
> | `src/components/admin/ActiveSessionsTable.tsx:21` | idem → « Aucune donnée » |
>
> Ces quatre pannes sont **affichées comme des données absentes** : une
> authentification cassée se lit comme un tableau vide.
> **Critère :** aucun `fetch(` en dehors de `api/base.ts` n'atteint l'API sans passer
> par `authHeader`. Le test est un `grep` de `/api/` dans le frontend, chaque
> occurrence devant être justifiée.

**EF-19 — Un appel réseau bloqué ne doit pas produire de chargement éternel.**
> *ÉCART.* `useCurrentUser.ts:90-111` appelle `/api/users/me` sans `AbortController`
> ni délai maximal. Le démarrage à froid de Render (~45 s, documenté dans
> `useHealth.ts:3-6`) laisse `Protected` et `AdminGate` sur un spinner qui ne se
> résout pas.
> **Critère :** toute résolution d'identité est bornée en temps et bascule en état
> d'erreur explicite au-delà.

**EF-20 — Une route inconnue ne doit pas exposer l'application à un visiteur
anonyme.**
> *ÉCART.* `App.tsx:408` place `/*` hors de toute garde : `/inconnu` monte
> `AppRuntime` → `AppShell` → `NotFoundPage` (`l.322`, non protégée). Un visiteur
> anonyme voit barre latérale, en-tête et `ThreadList` (qui appelle l'API) sur une
> page 404.
> **Critère :** une route inconnue sous session absente mène à `/sign-in` ou à une
> 404 nue, jamais au shell applicatif.

---

## 4. Exigences de sécurité

**ES-1 — Un JWT n'est accepté que si sa signature est vérifiée via le JWKS
officiel du fournisseur.**
> *CONFORME.* `PyJWKClient(NEON_AUTH_JWKS_URL, cache_keys=True)`
> (`resolver.py:68-84`), algorithme forcé `["EdDSA"]` (l.108, Neon signe en
> Ed25519/OKP). Aucune clé en dur, aucun `verify_signature=False`.
> **Critère :** un jeton signé avec une clé étrangère est rejeté.

**ES-2 — Les claims obligatoires doivent être exigés, pas seulement vérifiés quand
elles sont présentes.**
> *CONFORME.* `options={"require": ["exp", "iat", "sub"]}` (`resolver.py:103`).
> **Critère :** un jeton sans `sub` est rejeté, pas traité comme anonyme.

**ES-3 — L'audience doit être validée dès que l'URL de base est connue.**
> *CONFORME.* `resolver.py:117-120` : `audience = NEON_AUTH_BASE_URL`, sinon
> `verify_aud = False`.
> **Critère :** un jeton émis pour une autre audience est rejeté.

**ES-4 — L'émetteur (`iss`) doit être vérifié, ou son absence justifiée.**
> *ÉCART ASSUMÉ.* `resolver.py:89-93` argue que la signature JWKS épingle déjà le
> fournisseur. L'argument est recevable mais la décision doit être **enregistrée**,
> pas seulement commentée dans le code.
> **Critère :** une entrée de `DECISIONS.md` couvre ce choix.

**ES-5 — Un jeton transporté en query string est un jeton exposé.**
> *✅ CORRIGÉ (2026-09-30).* Le jeton ne transite plus jamais en query string.
> - **SSE** (`logging/sse.py`) : header `Authorization: Bearer` **uniquement**,
>   le fallback `?auth=` a été supprimé — le frontend réel passait déjà par
>   `apiFetchRaw` avec le header (lot 1, `events.ts`), le fallback était un
>   vestige pour un client natif `EventSource` qui n'existe plus.
> - **WebSocket `/ws/logs`** (`ws/logs.py`) : endpoint **mort** — aucun client
>   frontend ne l'appelle (0 `new WebSocket` actif), aucun test backend ne le
>   couvre. Supprimé avec son dossier `app/ws/`, l'import et le montage dans
>   `main.py`.
> - **`wsUrl`** (`frontend/src/api/base.ts`) : helper mort retiré.
> **Critère :** le jeton de transport doit avoir une durée de vie courte et être
> renouvelé plutôt que réutilisé ; son exposition par les journaux doit être
> assumée par écrit ou supprimée. → L'exposition est supprimée (plus aucun
> transport par query string).

**ES-6 — Une demande d'accès doit pouvoir être distinguée d'une absence de
demande.**
> *ÉCART.* `optional_current_user` (`resolver.py:320-337`) avale toute
> `HTTPException` et renvoie `None`. Volontaire pour les routes publiques qui
> s'enrichissent si authentifiées — mais **aucun journal ne distingue** « pas de
> jeton » de « jeton falsifié ». Une attaque par jeton falsifié est indétectable.
> **Critère :** un jeton rejeté doit être journalisé avec sa raison, tout en
> renvoyant une réponse indiscernable pour le client.

**ES-7 — Le provisionnement au premier login doit être atomique.**
> *ÉCART.* `resolve_internal_user` (`resolver.py:128-188`) fait un `SELECT` puis un
> `INSERT` sans transaction ni verrou. Deux premières connexions simultanées du même
> compte font échouer le second `INSERT` sur l'index unique
> `idx_users_external_id` → **`500` sur une connexion légitime**, au pire moment.
> **Critère :** deux requêtes concurrentes sur un compte inconnu produisent un seul
> compte, et les deux réponses sont en `2xx`.

**ES-8 — Aucun endpoint d'authentification ne doit être accessible sans limitation
de débit.**
> *MANQUANT.* Ni le sign-in, ni le renvoi de code, ni l'inscription n'ont de
> limitation. Le cooldown de 60 s est purement côté client (`SignUpPage.tsx:24`) et
> donc contournable.
> **Critère :** au-delà d'un seuil, l'API refuse avec un `429` et journalise.

**ES-9 — Le mode développement ne doit jamais opérer sur une base de production.**
> *CONFORME.* `config.py` refuse de démarrer si `AUTH_MODE == "dev"` et si
> `DATABASE_URL` pointe une base distante (détection : hôte absent, `localhost`,
> `127.0.0.1`, `::1`, `0.0.0.0`, ou nom d'hôte sans point ni `:`).
> **Pourquoi :** `POST /api/users` en mode dev écrit **sans**
> `external_user_id` (`api/users.py:99`). Une exécution accidentelle contre la base
> de production a créé une ligne `sub = NULL` et un compte de test persistant.
> **Critère :** ce refus est testé (5 cas : dev+Neon refuse ; dev+postgres local
> passe ; dev+pas de `DATABASE_URL` passe ; neon+Neon passe ; dev+socket Unix passe).

**ES-10 — Les tables applicatives doivent être protégées contre une lecture directe
de la base.**
> *ÉCART.* RLS désactivée partout, **0 policy**, 37 tables. Le rôle applicatif
> `current_user` est `neondb_owner` avec **`rolbypassrls = True`** : activer RLS
> sur `public` ne le protégerait pas. En revanche `neon_auth.*` est possédé par un
> rôle à `bypassrls = False`.
> **Décision :** ne pas activer RLS sur `neon_auth.*` (stockage géré par Neon).
> RLS sur `public` reste un durcissement possible, à condition de changer d'abord
> le rôle applicatif.
> **Critère :** après durcissement, une connexion SQL directe avec le rôle
> applicatif ne doit pas pouvoir lire `public.users`.

---

## 5. Exigences d'observabilité

**EO-1 — L'état du service d'authentification doit être interrogeable sans
exposer de donnée sensible.**
> *CONFORME.* `GET /api/health/auth` (`api/health.py:103-114`) renvoie
> `{"mode", "jwks_reachable"}`. Aucune clé, aucun secret.
> **Critère :** la réponse ne contient aucune valeur d'environnement autre que
> `AUTH_MODE`.

**EO-2 — Un refus d'authentification doit être journalisé.**
> *PARTIEL.* `AUTH_REJECT` est émis (résolveur l.258-263, l.290-293), mais le motif
> réel n'est pas structuré et aucun identifiant de requête ne relie l'événement à la
> requête HTTP.
> **Critère :** un journal de refus contient la raison, l'horodatage et un
> identifiant corrélable.

**EO-3 — Un contrôle de santé ne doit pas générer de requête inutile.**
> *ÉCART MINEUR.* `jwks_reachable()` (`resolver.py:351-373`) crée un
> `PyJWKClient` **neuf** à chaque contrôle au lieu de réutiliser le singleton
> paresseux : une requête réseau vers le well-known au moins toutes les 30 s, par
> instance.

---

## 6. Exigences d'exploitation

**EX-1 — La chaîne de bout en bout doit être testée.**
> *MANQUANT.* Aucune preuve n'existe que `session → /token → vérification JWKS →
> résolution → /api/users/me` fonctionne ensemble. Les tentatives manuelles ont
> échoué : le nom du cookie de session de Better Auth est inconnu dans ce
> déploiement, donc aucun jeton réel n'a pu être obtenu de façon automatisée.
> **Critère :** un test d'intégration obtient une session réelle, extrait un JWT et
> appelle `/api/users/me` avec un `200`.

**EX-2 — Il doit exister une seule manière de configurer les administrateurs.**
> *ÉCART.* Le repli `os.getenv("ADMIN_EXTERNAL_IDS") or os.getenv("ADMIN_CLERK_IDS", "")`
> (`config.py:179-186`) est un filet de sécurité assumé, mais
> `ADMIN_CLERK_IDS=user_3JPtI5ct41bR1cr6fsBtZCWmFC5` est toujours présent dans
> `backend/.env` avec un identifiant Clerk périmé. Une variable vide et un identifiant
> faux ont le même effet : personne administrateur, sans avertissement.
> **Critère :** `ADMIN_CLERK_IDS` est retirée une fois `ADMIN_EXTERNAL_IDS` renseignée
> sur **tous** les environnements, Render compris.

**EX-3 — Les variables d'environnement effectives doivent être vérifiables.**
> *MANQUANT.* `.env.production` déclare être surchargeable par le tableau de bord
> Vercel, mais les valeurs réellement appliquées au build sont hors du dépôt. Une
> dérive entre le dépôt et la production est indétectable.
> **Critère :** un journal de démarrage trace les variables d'auth **présentes ou
> absentes**, jamais leurs valeurs.

**EX-4 — La topologie réseau vers le backend doit être unique.** — ✅ CORRIGÉ (2026-09-30)
> *ÉCART ARCHITECTURAL.* `frontend/vercel.json:27-31` déclare un *rewrite*
> `/api/:path*` → `https://agent-tutor-api.onrender.com/api/:path*`. Il existe donc
> **deux chemins vers le même backend** :
> - **absolu** — `apiFetch` via `VITE_API_URL` : cross-origin direct vers Render,
>   soumis au CORS de Render (`ALLOWED_ORIGINS`);
> - **relatif** — les quatre appels bruts : same-origin, passe par le proxy Vercel,
>   **contourne le CORS du navigateur**.
>
> C'est l'explication structurelle de leur comportement divergent, et cela invalide
> l'affirmation inscrite dans ADR-015 selon laquelle tout le trafic irait directement
> à Render. `vercel.json:9-17` pose par ailleurs `Access-Control-Allow-Origin: *`
> sur `/api/(.*)`, inutile en same-origin et trompeur.
> **Critère :** soit tous les appels passent par une seule forme d'URL, soit le
> rewrite est supprimé et tout passe en absolu. Les deux ne peuvent pas coexister
> sans être documentées.
>
> **Résolution (2026-09-30)** : les 4 appels relatifs passent désormais par
> `apiFetch`/`apiFetchRaw` (lot 1, EF-18) et le rewrite `/api/:path*` a été
> **supprimé** de `vercel.json` (il ne reste que le fallback SPA). Un seul chemin
> réseau : l'absolue `VITE_API_URL`.
> **Prérequis opérationnel** : la variable `VITE_API_URL=https://agent-tutor-api.onrender.com`
> doit être posée dans le dashboard Vercel (Settings → Environment Variables),
> sinon le front en prod échoue — échec **visible**, voulu (cf. ADR-023/EF-15).

---

## 7. Décisions en attente

| Réf | Question | Statut |
|---|---|---|
| **D-1** | Faut-il exiger la vérification d'email ? | **À décider.** `requireEmailVerification: false` rend le parcours `/verify-email` décoratif (EF-3). Trois options :delegate au fournisseur (`true`), vérifier côté backend (coûteux, deux sources de règle), ou retirer le parcours. |
| **D-2** | Le transport email est-il activé côté Neon ? | **Bloquant, à vérifier en console.** Aucune écriture SMTP n'est configurée. Les OTP sont bien générés en base (`neon_auth.verification`) mais rien n'arrive, et l'API répond `200 {"status":true}` **même quand l'envoi échoue** — le succès HTTP ne prouve rien. Tant que ce point n'est pas résolu, ni la vérification d'email ni la récupération d'accès ne peuvent fonctionner. |
| **D-3** | Quelle autorité pour le rôle : variable d'environnement ou base ? | Non tranchée. Aujourd'hui la variable prime et la base est un miroir (EF-14). |
| **D-4** | Le rôle doit-il figurer dans le JWT ? | Non évaluée. Lève la dépendance à `/api/users/me` pour l'affichage du rôle (EF-15), au prix d'une révocation retardée. |
| **D-5** | Suppression ou branchement de `ResetPasswordPage` ? | Code mort aujourd'hui (EF-13). |

---

## 8. Écarts — ordre de traitement proposé

Aucun correctif n'a été appliqué : ce document precede la correction, conformément à
la demande.

| Rang | Écart | Exigences | Pourquoi d'abord |
|---|---|---|---|
| 1 | Transport email non configuré | D-2 | Bloque toute la vérification d'email et la récupération. Aucun code ne le résoudra. |
| 2 | Quatre appels API sans authentification | EF-18 | Panne en cours, **invisible** (affichée comme des données absentes). |
| 3 | Déconnexion ne rafraîchit pas l'état | EF-10 | L'utilisateur reste connecté alors qu'il ne l'est plus. |
| 4 | Double redirection à froid | EF-11 | Visible par chaque utilisateur à chaque rechargement. |
| 5 | Échec de `/api/users/me` = downgrade silencieux | EF-15 | Panne d'authentification présentée comme une absence de droit. |
| 6 | Course au premier login | ES-7 | `500` sur une connexion légitime, au pire moment. |
| 7 | Chargement éternel sans délai maximal | EF-19 | Dégâts sur démarrage à froid de Render. |
| 8 | Topologie réseau double | EX-4 | Cause structurelle du rang 2 ; à traiter avec lui. |
| 9 | Jeton de transport en query string | ES-5 | Exposition par les journaux. — ✅ TRAITÉ (2026-09-30) |
| 10 | Non-2xx traité comme absence de session | EF-8, EF-9 | Boucle retry et déconnexions intempestives. |
| 11 | Pas de limitation de débit | ES-8 | Attaque par force brute sur le sign-in. |
| 12 | Jetons de transport refusés non journalisés | ES-6 | Attaque indétectable. |
| 13 | Topologie réseau double, headers CORS trompeurs | EX-4 | Confond la maintenance. |
| 14 | Lignes orphelines en base | EF-17 | Données mortes, aucune décision de purge. |
| 15 | Repli `ADMIN_CLERK_IDS` encore présent | EX-2 | Configuration ambiguë. |

---

## 9. Ce qui est déjà correct et ne doit pas être cassé

Ces propriétés sont vérifiées et bonnes. Les corriger serait une régression.

- **I-1 à I-4** tiennent : identité uniquement par jeton signé, défaillance du
  fournisseur = refus, rôle fail-closed, aucun élargissement par requête.
- `require: ["exp","iat","sub"]`, EdDSA forcé, audience validée.
- `AUTH_MODE` inconnu → `503`, jamais un accès (`resolver.py:283-297`).
- Le rôle transite par le **Runtime Context** `AgentContext`, pas par l'état LangGraph
  persisté : un rôle n'est donc pas figé pour la durée d'un fil de discussion.
- Provisionnement non arbitraire des utilisateurs sans `external_user_id`.
- Ownership systématique sur les données (`_require_owner_or_admin`,
  `api/users.py:43-63`), avec convention anti-énumération `404`/`403`.
- Le jeton n'est stocké qu'**en mémoire** — jamais en `localStorage`.
- Aucun secret d'authentification dans le frontend.
- `AdminGate` refuse explicitement (403 avec issue), jamais par redirection silencieuse.
- Discrimination des erreurs par `code` et non par le texte du message.
- Garde-fou `AUTH_MODE=dev` + base distante.

---

## 10. Preuves vérifiées en base — 2026-09-30

Vérification directe sur la base Neon (schema `neon_auth`, rôle `neondb_owner`,
lecture seule, via `backend/scripts/check_auth_security.py`) :

### 10.1 Mots de passe hashés — ✅ CONFORME

- Le hash vit dans **`neon_auth.account.password`** (pas dans `user`) :
  Better Auth range le mot de passe dans la table `account`, ligne
  `providerId = 'credential'`, `userId` → `user.id`.
- **7 comptes sur 7** ont un hash (aucun mot de passe en clair) :
  `abmcompanysn@gmail.com`, `idrissoualanni0@gmail.com`,
  `kenagboton7@gmail.com`, `prod-run-check@example.invalid`,
  `prod-run-check2@example.invalid`, `rockssmbaba@gmail.com`,
  `sefouabdoulaziz@gmail.com`.
- **Format : `scrypt` Better Auth** — 161 caractères, `sel:hash` encodés en
  hexadécimal (sel 16 octets = 32 hex, hash 64 octets = 128 hex).
  Jamais de sha1, jamais de base64 trivial.
- Le hashage est fait par le fournisseur (Better Auth managé par Neon),
  **pas par notre code** : notre rôle est de vérifier, pas de hasher.

### 10.2 Vérification d'email par OTP — ⚠️ MÉCANISME EN PLACE, ENVOI BLOQUÉ

- **`neon_auth.project_config.email_and_password`** :
  `enabled: True`, `emailVerificationMethod: 'otp'` → le mécanisme choisi
  par le produit est bien l'OTP.
- Les OTP sont stockés dans **`neon_auth.verification`** :
  `identifier = 'email-verification-otp-<email>'`, `value` = hash
  sha256 (base64url 32 octets) + suffixe `:0` → **jamais le code en clair**.
- Endpoint de vérification consommé par le frontend :
  `POST /email-otp/verify-email {email, otp}`.
- **BLOQUANT (D-2, hors code)** : `sendVerificationEmailOnSignUp: False`,
  `sendVerificationEmailOnSignIn: False`, `email_provider: {'type': 'shared'}`
  → les OTP sont créés en base mais **aucun email n'est envoyé**.
  La livraison ne peut être activée que dans la **console Neon**
  (config SMTP / activation de l'envoi du fournisseur partagé).

## 11. Correctifs implémentés — lot 1 (2026-09-30)

Écarts du §8 corrigés. Vérifications : `tsc --noEmit` EXIT 0 (frontend/),
`python -m compileall -q app` EXIT 0 (backend/). Aucun des 3 fichiers
WIP frontend n'a été touché.

### 11.1 EF-18 — ✅ 4 appels sans en-tête d'authentification

- `src/api/events.ts` : flux SSE réécrit sur `apiFetchRaw` (au lieu
  d'`EventSource` natif), en-tête `Authorization` systématique,
  reconnexion bornée (MAX_RECONNECTS=5, backoff 1 s → 30 s), arrêt
  propre, 401/403 = abandon fatal (pas de boucle infinie).
- `src/features/transcription/TranscriptionPanel.tsx` : fini le
  `` `Bearer ${window.__neonGetToken?.() || ""}` `` (Promise
  stringifiée → en-tête invalide) → `apiFetchRaw`.
- `src/components/admin/ActivityMonitor.tsx` + `ActiveSessionsTable.tsx` :
  fetch brut sans en-tête (→ 401 permanent affiché « Aucune donnée »)
  → `apiFetchRaw`, état d'erreur explicite, garde anti-écriture après
  démontage du composant.

### 11.2 EF-10 — ✅ Déconnexion

- `src/auth/NeonUserMenu.tsx` : `signOut()` avec propagation d'erreur
  (message visible en cas d'échec), à la réussite → `clearNeonSession()`
  (purge jeton, cache JWT, `notifyNeonUser(EMPTY)`) puis navigation.
- `src/lib/neon.ts` : `signOut` ne mange plus ses erreurs
  (le `catch` silencieux supprimé, l'erreur remonte à l'appelant).

### 11.3 EF-11 — ✅ Double redirection à froid

- `src/auth/NeonTokenBridge.tsx` : état initial **`PENDING`** (session en
  cours de résolution) distinct de `EMPTY` (déconnecté) ; résolution
  bornée `SESSION_TIMEOUT_MS = 15 s` (cold start Render ~45 s).
- `src/App.tsx` : gardes `Protected` / `RequireAnonymous` / `PublicRoute`
  attendent l'état `PENDING` au lieu de rediriger vers l'écran d'entrée.

### 11.4 EF-15 — ✅ Plus de downgrade silencieux

- `src/hooks/useCurrentUser.ts` : 3 états explicites (chargement /
  succès / erreur), `describeMeError()` distingue
  AbortError / ApiError-401 / ApiError-autre / TypeError ;
  `role` = rôle réel ou `null`, **plus jamais `?? 'user'`**.
- `src/auth/AdminGate.tsx` : erreur visible avec bouton recharger,
  refus 403 explicite pour non-admin.

### 11.5 EF-19 — ✅ Timeout de chargement

- `src/hooks/useCurrentUser.ts` : AbortController + `ME_TIMEOUT_MS = 30 s`
  sur `/api/users/me` (cold start Render) ; `NeonTokenBridge` : résolution
  de session bornée 15 s.

### 11.6 ES-7 — ✅ Course au premier login atomique

- `backend/app/auth/resolver.py` : `_PROVISION_SQL` =
  `INSERT ... ON CONFLICT (external_user_id) WHERE external_user_id IS NOT NULL
  DO NOTHING` (index partiel), boucle de 2 tentatives avec re-SELECT —
  jamais deux INSERT concurrents ne lèvent de violation de contrainte.

### 11.7 ADR-023 — ✅ Appliqué au résolveur

- `_current_user_from_row` : le rôle lu en base (`stored_role`) est
  l'**autorité unique** au runtime ; `ADMIN_EXTERNAL_IDS` ne sert qu'au
  bootstrap initial (provision). L'auto-persistance `set_user_role` est
  supprimée du chemin de lecture : un écart env/base est **journalisé**
  (`AUTH_ROLE_DIFF`, niveau WARN) et visible, jamais auto-réparé.
- `backend/_t_guard.py` (script jetable) supprimé.

### 11.8 EX-4 — ✅ Topologie réseau unique

- Les 4 appels qui utilisaient un `fetch` relatif (`events.ts`, `TranscriptionPanel.tsx`,
  `ActivityMonitor.tsx`, `ActiveSessionsTable.tsx`) passent désormais tous par
  `apiFetch`/`apiFetchRaw` — corrigés dans le lot 1 (EF-18).
- Le rewrite `/api/:path*` de `vercel.json` a été **supprimé** : il ne reste que le
  fallback SPA. Un seul chemin réseau : l'URL absolue `VITE_API_URL` (cross-origin,
  soumis au CORS de Render).
- Documentation alignée : `ARCHITECTURE.md` §2 (Mermaid), §7.2 (surface d'attaque),
  §8 (pavé [F] réécrit), §9 (tableau déploiement).
- **Prérequis de déploiement** : poser `VITE_API_URL=https://agent-tutor-api.onrender.com`
  dans le dashboard Vercel — sans quoi le front en prod échoue (échec visible voulu).

### 11.9 ES-5 — ✅ Plus aucun jeton en query string

- **SSE** (`logging/sse.py`) : header `Authorization: Bearer` **uniquement**. Le
  fallback `?auth=` a été supprimé — le frontend réel passait déjà par
  `apiFetchRaw` avec le header (lot 1, `events.ts`) ; le fallback ne servait
  qu'à un client natif `EventSource` qui n'existe plus.
- **WebSocket `/ws/logs`** (`ws/logs.py`) : endpoint **mort** (aucun client
  frontend actif, aucun test) → supprimé avec `app/ws/`, l'import et le montage
  dans `app/main.py`.
- **`wsUrl`** (`frontend/src/api/base.ts`) : helper mort retiré.
- Vérifié : `compileall -q app` EXIT 0 (backend) et `tsc --noEmit` EXIT 0 (frontend).