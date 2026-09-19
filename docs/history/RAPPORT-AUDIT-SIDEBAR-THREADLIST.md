# RAPPORT D'AUDIT — Sidebar / ThreadList (lecture seule)

> **Périmètre** : audit uniquement, aucune modification de code.
> **Méthode** : lecture statique du code + `grep` ; preuves citées en `fichier:ligne`.
> **Date** : 2026-09-17

---

## A. État actuel

Deux colonnes gauches de **largeur identique (`w-64`)** coexistent sur `/assistant`, sans partage de rôle :

- `Sidebar` = navigation app, **rendue globalement** hors du router (`App.tsx:50`).
- `ThreadList` = conversations, **rendu dans la page** `/assistant` (`AssistantPage.tsx:109-111`).

Le commentaire de `Sidebar.tsx:1` annonce « navigation + thread » mais elle **ne contient plus aucun UI de thread** (`Sidebar.tsx:82-83` = simple `<div className="flex-1" />` vestigial). La création/renommage a été déplacée dans `ThreadList` (`Sidebar.tsx:5-7`).

---

## B. Arbre de rendu réel

```
main.tsx
└─ Root
   └─ ClerkProvider (clerk)                    main.tsx:18
      └─ ClerkTokenBridge                      main.tsx:19
         └─ App                                App.tsx:96
            └─ Router                          App.tsx:97
               └─ SelectionProvider            App.tsx:98
                  └─ AppShell                  App.tsx:45
                     ├─ Sidebar (w-64, global) App.tsx:50 / Sidebar.tsx:27
                     │   ├─ nav Assistant|Memory|Logs(admin)   Sidebar.tsx:35-43
                     │   ├─ <div flex-1/> (slot vide)          Sidebar.tsx:82-83
                     │   ├─ StatusBadge ×3                      Sidebar.tsx:90-92
                     │   └─ UserButton / dev logout             Sidebar.tsx:96-118
                     └─ <main> Routes                          App.tsx:56
                        ├─ /assistant → AssistantPage          App.tsx:62-69
                        │   └─ AssistantUIRuntimeProvider      AssistantPage.tsx:139
                        │      └─ AssistantRuntimeChildren     AssistantPage.tsx:103
                        │         ├─ <aside w-64 hidden md:flex>  AssistantPage.tsx:109
                        │         │   └─ ThreadList            thread-list.aui.tsx:35
                        │         ├─ RunErrorBanner            AssistantPage.tsx:114
                        │         ├─ Thread                    thread.aui.tsx:133
                        │         └─ ComposerModelBar          AssistantPage.tsx:119
                        ├─ /chat → Navigate /assistant         App.tsx:70
                        ├─ /memory → MemoryPage                App.tsx:71-78
                        └─ /logs → AdminGate → LogsPage        App.tsx:80-87
```

**Deux `<aside>`/rails** (Sidebar globale + aside ThreadList), empilés horizontalement sur `/assistant`.

---

## C. Sidebar (navigation app)

`Sidebar.tsx:27` — responsabilité unique réelle : navigation (`:35`), statuts services (`:90`), session (`:106`). Ne rend **jamais** de thread. Nom et commentaire obsolètes (`:1`).

---

## D. ThreadList (conversations)

`thread-list.aui.tsx:35` — rend `New` (`:41`), `Search` (`:43`), items groupés Today/Yesterday/Earlier (`:128-173`), item avec rename inline (`:331`) et menu More (`:395`). Délègue tout au `ExternalStoreThreadListAdapter` (`AssistantRuntimeProvider.tsx:97-129`).

---

## E. Thread actif

Trois représentations concurrentes du **même** fait :

1. **Zustand** `currentThreadId` — autoritatif/vivant (`store.ts:30,120,136`).
2. **localStorage** `dsh_current_thread` — persisté par `store.ts:75-90`.
3. **React context** `SelectionProvider.currentThread` — snapshot au montage (`useSelection.tsx:30`).

---

## F. New conversation

`ThreadListPrimitive.New` (`thread-list.aui.tsx:227`) → adapter `onSwitchToNewThread` (`AssistantRuntimeProvider.tsx:109-111`) → `switchToNewThread` crée un thread backend « New Chat » (`store.ts:128-149`). Aucune réutilisation / déduplication.

---

## G. Assistant UI

Runtime **ExternalStore** officiel (`AssistantRuntimeProvider.tsx:132`), primitives officielles, mais **copies locales** des éléments dans `components/assistant-ui/elements/*` (pas de `@assistant-ui/react-ui`). `Thread` / `ThreadList` / `Composer` custom. `useAgentResponseDataUI` monte la data part (`AgentResponseDataUI.tsx:74`).

---

## H. Zustand

`useAssistantStore` (`store.ts:92`) = source de vérité messages / threads / run / model. `setStoreUser` est appelé **pendant le render** (`AssistantRuntimeProvider.tsx:55`).

---

## I. Duplications

| Concern | Copies | Preuves |
|---|---|---|
| Thread actif | **3** (Zustand / context / localStorage) | `store.ts:30`, `useSelection.tsx:30`, `store.ts:81` |
| Modèle sélectionné | **2** (Zustand `selectedModel` vs `api.modelContext.register`) | `store.ts:300` / `model-selector.aui.tsx:64-75` |
| Rail gauche `w-64` | **2** | `Sidebar.tsx:46` + `AssistantPage.tsx:109` |
| Modèle de données thread | **2** (`Thread` vs `BackendThread`) | `types/agent.ts:12` / `assistant-ui/types.ts` |
| Archive / Delete | UI rendue + adapter no-op | `thread-list.aui.tsx:424-441` / `AssistantRuntimeProvider.tsx:118-126` |

---

## J. Problèmes classés

- **CRITICAL — `useSelection` figé.** `selectThread` n'a **aucun appelant** (0 occurrence hors définition `useSelection.tsx:20,40`). `SelectionProvider.currentThread` n'est lu qu'au montage (`:30-38`), jamais resynchronisé : `MemoryPage` (`MemoryPage.tsx:25,39`) affiche un thread **périmé/absent** après tout switch, jusqu'à rechargement complet. Divergence avec `store.currentThreadId`.
- **HIGH — ThreadList inaccessible sur mobile.** `hidden … md:flex` (`AssistantPage.tsx:109`) : sous `md`, aucune gestion de conversations, aucun drawer alternatif.
- **HIGH — Contrôles morts.** Archive / Delete rendus (`thread-list.aui.tsx:424-441`) mais `onArchive` / `onDelete` vides (`AssistantRuntimeProvider.tsx:118-126`) → échec silencieux.
- **MEDIUM — Triple source de vérité** du thread actif (cf. I).
- **MEDIUM — `setStoreUser` en render** (`AssistantRuntimeProvider.tsx:55`) : effet de bord hors `useEffect`.
- **MEDIUM — Modèle à double chemin** : `modelContext.register` n'est pas utilisé par le transport (le run lit `selectedModel`, `store.ts:196`).
- **MEDIUM — « New Chat » illimité** : clics répétés créent N threads backend (`store.ts:133`).
- **LOW — Doc/nom obsolètes** : « navigation + thread » (`Sidebar.tsx:1`) + slot vide (`:82-83`).
- **LOW — i18n incohérent** : « New Thread / Search threads / Today / Delete » dans une UI FR.
- **LOW — Message trompeur** `"Sélectionnez un utilisateur (sidebar gauche)"` (`AssistantRuntimeProvider.tsx:146`) référence un UserSelector supprimé (identité = Clerk).
- **INFO — Nettoyage OK** : `ChatPage.tsx` absent, `/chat` → `/assistant` (`App.tsx:70`).

---

## K. Architecture recommandée

1. **Une seule source de vérité** : Zustand pour le thread actif ; `MemoryPage` lit un sélecteur `useActiveThread()` — plus de `SelectionProvider` à état propre (le supprimer ou le dériver strictement du store).
2. **Un seul rail gauche** : soit `Sidebar` absorbe `ThreadList` (contexte `/assistant`), soit `ThreadList` devient un panneau contextuel — pas deux `w-64` adjacents. Sur mobile : drawer.
3. **Contrôles = capacités** : masquer Archive / Delete tant que l'adapter ne les supporte pas.
4. **Modèle** : un seul chemin (Zustand **ou** `modelContext`), pas les deux.
5. **Effets** : `setStoreUser` dans `useEffect`.

---

## L. Plan de correction (non appliqué)

- **P0** : `useSelection` ← dériver de `store.currentThreadId` (ou supprimer le contexte). Fichiers : `useSelection.tsx`, `MemoryPage.tsx`.
- **P1** : accès mobile `ThreadList` (drawer / bouton). Fichier : `AssistantPage.tsx`.
- **P2** : masquer Archive / Delete non supportés. Fichiers : `thread-list.aui.tsx` + `AssistantRuntimeProvider.tsx`.
- **P3** : unifier le modèle (retirer `modelContext` ou brancher le transport dessus).
- **P4** : dédup « New Chat », `setStoreUser` → `useEffect`, i18n FR, commentaires obsolètes.

---

## Matrice des responsabilités

| Concern | Propriétaire | Preuve |
|---|---|---|
| Navigation app | `Sidebar` | `Sidebar.tsx:35` |
| Statuts services | `Sidebar` | `Sidebar.tsx:90` |
| Affichage identité | `Sidebar` (UserButton) | `Sidebar.tsx:106` |
| Liste des conversations | `ThreadList` | `thread-list.aui.tsx:35` |
| Nouvelle conversation | `ThreadListPrimitive.New` → `adapter.onSwitchToNewThread` | `thread-list.aui.tsx:227` / `AssistantRuntimeProvider.tsx:109` |
| Sélection de thread | `ThreadListItemPrimitive.Trigger` → `adapter.onSwitchToThread` | `AssistantRuntimeProvider.tsx:112` |
| Renommage | `onRename` → `store.rename` | `thread-list.aui.tsx:356` / `AssistantRuntimeProvider.tsx:115` |
| Archive / Delete (UI) | `ThreadList` | `thread-list.aui.tsx:424-441` |
| Archive / Delete (comportement) | adapter no-op | `AssistantRuntimeProvider.tsx:118-126` |
| Thread actif (vivant) | Zustand `currentThreadId` | `store.ts:30,120` |
| Thread actif (persisté) | localStorage `dsh_current_thread` | `store.ts:75-90` |
| Thread actif (contexte) | `SelectionProvider.currentThread` (**stale**) | `useSelection.tsx:30` |
| Messages / run | Zustand | `store.ts:33,37` |
| Modèle (sélection UI) | Zustand `selectedModel` | `store.ts:41,300` |
| Modèle (contexte officiel) | `api.modelContext.register` | `model-selector.aui.tsx:64-75` |
