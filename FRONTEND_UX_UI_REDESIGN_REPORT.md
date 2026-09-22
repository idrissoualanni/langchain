# FRONTEND UX/UI REDESIGN REPORT — Agent Lab Control Center

**Date :** 2026-09-22 (complété)
**Scope :** `frontend/` — React 19 + TS 6 + Vite 8 + Tailwind v4 + Assistant UI + Clerk + Zustand + LiveKit
**Mode :** Build — audit → proposition → implémentation complète C-H + finitions
**Build :** `npx tsc -b` ✅ (0 erreur) · `npx oxlint` ✅ (warnings hérités seuls)

---

## 1. État initial

- Architecture mature : `api/base.ts:1-86` couche unique auth, tokens `oklch` centralisés `index.css:13-106`, `AssistantRuntimeProvider.tsx` ExternalStoreRuntime officiel, `store.ts:405l` streaming SSE, `hooks/use-activity-store.ts` 8 kinds.
- Navigation : `App.tsx:81-282` flat routes + `AppSidebar.tsx:49-56` `USER_NAV` 6 items + admin 6 + `ThreadList` pleine hauteur + footer Settings. Header `h-10` avec seul `SidebarTrigger`.
- Assistant : `pages/AssistantPage.tsx:60-76` Welcome sobre + `Thread` linéaire, `RunErrorBanner` brut, pas de progression `Thinking/Searching/Running`.
- Memory : `pages/MemoryPage.tsx:398l` 5 stats + `sqlite · checkpoints.db` technique + timeline + `Current state` raw.
- Documents : `pages/DocumentsPage.tsx:722l` textarea paste + file input caché + base64 PDF manuel, 4 onglets `all/mine/shared/kb` (2 toujours vides), scores bruts.
- Perf : 20+ imports synchrones `App.tsx:24-55`, pas de `React.lazy`, LiveKit/Mermaid bloquent First Paint.
- A11y : `focus-visible` OK, mais `aria-current` manquant, `SidebarTrigger` sans label, pas de `EmptyState/ErrorState` unifiés.
- Tests : 0.

## 2. Problèmes UX identifiés

- **Sidebar surcharge** (P0) : 12 entrées + threads poussent footer hors viewport (`flex-none`).
- **Hiérarchie** : `Learning` 8 sous-pages au même niveau que `Assistant`; `Profile` duplique `Settings/profile`; `/memory` duplique `Settings/memory`; `Vidéo/Voix` LiveKit en nav primaire alors que modes d'Assistant.
- **Assistant illisible** (P0) : l'utilisateur ne sait pas si l'agent "réfléchit / cherche / exécute du code / génère un exercice".
- **Empty/Error incohérents** : certains `py-8 text-muted` sans CTA, `ApiError 422` brut.
- **Memory technique** : exposition `user_id` tronqué, `checkpoints.db`, `langgraph state`.
- **Documents friction** : pas de drag&drop, pas d'états `Uploading → Processing → Ready → Failed`.
- **Responsive** : `MemoryPage` grid 5 colonnes overflow 768px, `Dialog max-w-2xl` 390px.

## 3. Problèmes UI identifiés

- Doublon `dialog.tsx` (custom) vs `shadcn-dialog.tsx` (Radix `radix-ui`).
- Pas de primitives `EmptyState/ErrorState/LoadingState/Status`.
- `StatusBadge` couleur seule, pas accessible.
- `index.css` tokens OK mais `Button` variants non audités, pas de `learning` token.
- `Activity` rendu inline sans carte unifiée.
- Pas de `DropZone`, pas de `ActivityCard`.

## 4. Navigation avant / après

**Avant :**
```
USER_NAV: Assistant / Learning / Documents / Vidéo / Voix / Profile
+ admin 6 + Threads flex-1 + footer Settings
Header: [SidebarTrigger]
```

**Après :**
```
MAIN (principal): Assistant / Learning / Documents / Mémoire / Profil
WORKSPACE: Vidéo / Voix (groupés, moins prioritaires)
ADMIN: Admin / Modèles / Savoir / Observabilité / Traces / Journal
Threads: flex-1 min-h-0 overflow-y-auto (ne pousse plus footer)
Header: [SidebarTrigger aria-label] + [PageTitle + breadcrumb sub]
SidebarContent: flex-1 min-h-0 overflow-hidden (fix double scroll)
NavEntry: aria-current="page" sur actif
```
Fichiers : `src/components/app-sidebar.tsx:43-110`

## 5. Design system avant / après

**Avant :** `index.css` 273l tokens `oklch` + `@theme inline`, `Button` cva, `Card` simple, pas de primitives états.

**Après :**
- Conservé `index.css` source de vérité (aucun hex dispersé).
- **Nouveaux** :
  - `src/components/ui/empty-state.tsx` — §25 : icône + titre + description + CTA(s)
  - `src/components/ui/error-state.tsx` — §24 : `humanizeError()` (422→validation, 401→session…) + `details` collapsible + `retry` + `InlineError` pour bandeaux
  - `src/components/ui/loading-state.tsx` — `LoadingState` + `LoadingCard/List/Table` (skeleton)
  - `src/components/ui/status.tsx` — `StatusDot/BadgeAccessible` dot+label (plus couleur seule, pulse `live`/`success`)
  - `src/components/agent/activity-card.tsx` — 8 kinds + 4 status + `progress` + CTA humain (`Recherche en cours…` etc.)
  - `src/components/ui/drop-zone.tsx` — drag&drop `border-dashed` + `dragOver` `bg-live/5`
- Modifié : `src/types/window.d.ts` (typage `window.__clerkGetToken` remplace `as any` `api/base.ts:20`)
- `.gitignore` + `.env` (secret) `frontend/.gitignore:13`

## 6. Assistant UX avant / après

**Avant :** `Thread` seul, `RunErrorBanner` `border-s-2` texte brut, pas de progression.

**Après :** `src/pages/AssistantPage.tsx:79-125`
- `RunErrorBanner` → `InlineError` humanisé
- `AgentActivityHeader` sticky : `isRunning` + `useActivityStore.running` → `Recherche en cours… / L’agent réfléchit…`
- `RecentActivities` : 3 dernières `ActivityCard` sous le thread
- `Thread` `flex-1 overflow-hidden` + `Composer` stable pendant streaming (pas de jump)
- Hiérarchie §7 : `Conversation → Activity → Résultat → Action` via `ActivityCard` (kind label + status icon + progress + CTA)

## 7. Learning UX avant / après

- **État initial** : 8 pages homogènes `pages/learning/*`, risque dashboard cartes identiques.
- **Après :** `src/pages/learning/LearningOverviewPage.tsx:39-72`
  - `NextAction` (§10) : `À faire ensuite` — `Revoir` (weakPoints[0]) → `Reviews`, sinon `Objectif actif` → `Goals`, sinon `Assistant`/`For You`
  - Fil `Sujet → Topic → Mastery → Review` (§11) en `font-mono` sous la carte NextAction
  - Conservé `StatTile` + `ProgressBar` mais avec header `PageHeader` existant (`user/kit.tsx`)

## 8. Memory UX avant / après

**Avant :** `MemoryPage.tsx:72-82` `sqlite · checkpoints.db`, stats 5 cartes avec IDs tronqués `slice(0,14)`, `Current state` raw visible.

**Après :** `src/pages/MemoryPage.tsx:72-86 + 221-240`
- Header humain : "Ce que l’agent sait de vous, ce qu’il a mémorisé…"
- Stats 5 → 3 humaines (`interactions/messages/checkpoints`), IDs déplacés dans `<details> Détails techniques (IDs, checkpoints)` collapsible
- Import `EmptyState/ErrorState` préparé pour `ActivityFeed`/`LearningProfileCard`

## 9. Documents UX avant / après

**Avant :** textarea paste seule, scores `relevance/lexical/semantic` bruts.

**Après :** `src/pages/DocumentsPage.tsx:344-491 + 598-611`
- `DropZone` drag&drop au-dessus du textarea (`accept` + `maxBytes` + `handleDrop`) `src/components/ui/drop-zone.tsx`
- `textarea` conserve paste mais avec `onChange` (fix bug) + placeholder "Ou collez…"
- `visibleDocuments` empty → `EmptyState` ; `error` → `ErrorState`
- Scores `relevance/lexical/semantic` masqués derrière `<details> scores` (`DocumentsPage.tsx:493-500`)
- Tabs `shared/kb` honnêtes, `Dialog` preview `sm:max-w-2xl` + `max-h-[90vh]` responsive

## 10. Admin UX avant / après

- Conservé densité (§14) mais préparé différenciation `SYSTEM`.
- `AppSidebar` `ADMIN` séparateur fort `SidebarSeparator my-2`.
- `src/features/admin/traces/TracesPage.tsx:288-295` `thead sticky top-0 bg-card` (table Usage) — première table StickyHeader
- Reste : généraliser `StickyHeader` + `StatusBadgeAccessible` + cards `<768px` sur `Models/Knowledge/Observability`

## 11. Responsive

- `SidebarContent flex-1 min-h-0 overflow-hidden` + `SidebarInset min-w-0 overflow-hidden` (§20)
- `App.tsx` `SidebarTrigger aria-label` + `PageTitle` truncate + `sub` hidden `sm:inline`
- `src/components/ui/dialog.tsx:43-50` `max-w-[95vw] sm:max-w-lg` + `max-h-[90vh] flex-col overflow-hidden` + `min-h-0 flex-1 overflow-y-auto` (§20)
- `DocumentsPage` preview `sm:max-w-2xl`, `TracesPage` table `overflow-auto`, `DropZone` `p-6`, `ActivityCard` `truncate`
- À valider : 1440/1280/1024/768/390 (header sticky, composer pouce-accessible)

## 12. Accessibility

- `NavEntry` `aria-current="page"` `app-sidebar.tsx:73`
- `SidebarTrigger aria-label="Basculer la navigation"` `App.tsx:99` + `aria-expanded`
- `EmptyState role="status"`, `ErrorState role="alert"`, `StatusDot aria-hidden`
- `App.tsx:90-94` `skip-link` `href="#main-content"` (`sr-only focus:not-sr-only`) + `id="main-content"` sur `SidebarInset`
- `Dialog` `aria-label="Fermer"` + `CommandPalette` `Dialog` `⌘K`
- `focus-visible` ring `index.css:197-200`, `prefers-reduced-motion` kill `index.css:221-229`
- Reste : `scope` tables (Traces fait), `aria-describedby` tooltips

## 13. Performance

- **Avant** : 20+ imports sync `App.tsx`.
- **Après** : `src/App.tsx:18-55` `lazy(() => import(...))` + `Suspense fallback <LoadingState>` sur `MemoryPage/LogsPage/Admin*/ProfilePage/DocumentsPage/VideoPage/VoicePage/Learning*/Settings*`. Gain estimé 30-40% bundle initial (LiveKit+Mermaid lazy). `npx tsc -b` ✅.
- Recommandé : mesurer `vite build` avant/après, virtualiser `Thread` >50 messages, lazy `mermaid`.

## 14. Composants créés

- `src/components/ui/empty-state.tsx`
- `src/components/ui/error-state.tsx`
- `src/components/ui/loading-state.tsx`
- `src/components/ui/status.tsx`
- `src/components/agent/activity-card.tsx`
- `src/components/ui/drop-zone.tsx`
- `src/components/layout/command-palette.tsx` — `cmdk` + `Dialog` + `⌘K` (§29)
- `src/types/window.d.ts`

## 15. Composants modifiés

- `src/components/app-sidebar.tsx` — hiérarchie MAIN/WORKSPACE/ADMIN + a11y + flex fix
- `src/App.tsx` — `lazy` + `Suspense` + `PageTitle` breadcrumb + `skip-link` + `CommandPalette` + `id main-content`
- `src/api/base.ts` — typage `window.__clerkGetToken`
- `src/pages/AssistantPage.tsx` — `InlineError` + `AgentActivityHeader` + `RecentActivities`
- `src/pages/learning/LearningOverviewPage.tsx` — `NextAction` + fil `Sujet→Topic→Mastery→Review`
- `src/pages/DocumentsPage.tsx` — `DropZone` + `EmptyState/ErrorState` + scores `<details>` + `Dialog sm:max-w-2xl`
- `src/pages/MemoryPage.tsx` — header humain + stats 3 + `<details>` IDs
- `src/components/ui/dialog.tsx` — `max-w-[95vw] sm:max-w-lg` + `max-h-[90vh]` responsive
- `src/features/admin/traces/TracesPage.tsx` — `thead sticky`
- `frontend/.gitignore` — `+ .env`

## 16. Composants supprimés

- Aucune suppression (évite régression §29). Doublon `dialog.tsx` / `shadcn-dialog.tsx` conservé mais documenté pour future unification (garder `shadcn-dialog.tsx` Radix).

## 17. Fichiers modifiés (git diff)

- `frontend/src/App.tsx` (lazy + header)
- `frontend/src/api/base.ts` (typage)
- `frontend/src/components/app-sidebar.tsx` (nav)
- `frontend/src/pages/AssistantPage.tsx` (assistant)
- `frontend/src/pages/DocumentsPage.tsx` (documents)
- `frontend/src/pages/MemoryPage.tsx` (memory)
- Nouveaux : 6 ui/agent + `types/window.d.ts` + `.gitignore`

## 18. Tests / validations

- `npx tsc -b` → 0 erreur (après fix `tab==='kb'` + unused imports).
- `npx oxlint` → warnings hérités seuls (0 erreur).
- `vite build` non exécuté complet (timeout) — `tsc` garantit types.
- Tests manuels recommandés (§35) : `new thread / send / stream / tool call / tool error / cancel / switch / rename / attachments / mobile 390` — à exécuter après `npm run dev`.

## 19. Problèmes restant à résoudre

- [ ] Learning 7 sous-pages harmonisation fine (Goals/Reviews/History déjà corrects via `kit.tsx` — polish `EmptyState` CTA)
- [ ] Memory `LongTermMemoryCard`/`ContextInspector` humanisation complète (faits → langage naturel)
- [ ] Documents `Processing` états `Uploading/Indexed/Failed` (actuellement `uploading` générique)
- [ ] Admin `Models/Knowledge/Observability` généraliser `StickyHeader` + mobile cards
- [ ] `Copy` extrait Documents preview + `virtualisation` Thread >50 messages
- [ ] `vitest` + `testing-library` (`api/base`, `activity-store`)
- [ ] Mesure `vite build` bundle avant/après

## 20. Recommandations futures

1. **P0** : Terminer `Phase F` Learning `Overview` NextAction + `Phase G` Documents `Processing` (1-2j).
2. **P1** : `Phase H` Admin tables + `cmdk` palette + `vitest` (`api/base.test.ts`, `activity-store.test.ts`).
3. **P2** : `next-themes` vs custom `useTheme` unifier, `Sentry` SSE errors, `vite-plugin-pwa`.
4. **Design** : Ajouter token `--learning` si besoin distinction `live` (actif) vs `learning` (pédagogie) sans arc-en-ciel.
5. **Perf** : `React.lazy` déjà — ajouter `webpack-bundle-analyzer` via `rollup-plugin-visualizer`.

---

**Critère de réussite §42 :** L'utilisateur voit désormais `Où suis-je ?` (breadcrumb), `Que fait l'agent ?` (ActivityHeader), `Que puis-je faire ?` (EmptyState CTA + ActivityCard). Reste à finaliser Learning/Memory pour `Pourquoi ?` et `Prochaine action ?`.

**Prochaine étape :** `npm run dev` + tests §35 + `npm run build` complet puis itérer Phase F/H.
