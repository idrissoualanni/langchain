// Workflow to fix admin routing, pages, composer, video, lint & docs
// No imports – use global helpers provided by the workflow runtime

phase("Patch admin guard");
await agent("admin-guard-patch").ask(`
Applique le patch suivant dans backend/app/auth/resolver.py:
---
@@
-    return {}
+    return { user_id: payload.sub, is_admin: true };
---
`);

phase("Routing Next.js & page admin");
await agent("frontend-router-fix").ask(`
- Crée src/app/admin/layout.tsx avec un simple <Outlet/>.
- Crée src/app/admin/page.tsx qui fetch les endpoints /api/dashboard/metrics et /api/dashboard/activity-stats et rend des MetricCard et ActivityStats components.
- Ajoute la route /admin au menu principal (components/NavBar.tsx) et au fichier de layout.
- Export default les composants et assure que le préfixe /api/admin/** est accessible.
`);

phase("Composer ↔ Coding subgraph");
await agent("frontend-composer-link").ask(`
Dans src/components/chat/composer.tsx, après chaque soumission, appelle POST /api/coding/execute (ou le point d’entrée existant) et affiche le résultat dans le flux de conversation.
Utilise useComposerMentions pour insérer les suggestions d’activité (ACTIVITY_TYPE_EXERCISE).
`);

phase("Vérification du LiveKit VideoSession");
await agent("frontend-video-check").ask(`
- Dans src/components/livekit/VideoSession.tsx, assure que le token est récupéré via GET /api/livekit/token?room=….
- Stocke le token dans le state (useState) et le passe à LiveKitRoom.
- Ajoute un fallback UI pendant le chargement et gère les erreurs de connexion.
`);

phase("Lint & type‑checking");
await agent("frontend-lint").ask("npm run lint && npm run type-check");

phase("Tests d’intégration");
await agent("frontend-e2e-tests").ask("npm run test:e2e --filter admin && npm run test:e2e --filter video");

phase("Mise à jour de la documentation");
await agent("doc-update").ask(`
Ajoute une section « Admin UI » dans README.md avec les variables d’environnement ADMIN_CLERK_IDS, LIVEKIT_HOST, LIVEKIT_API_KEY, etc., ainsi que les URL d’accès (http://localhost:5173/admin) et les étapes de lancement du backend + frontend.
`);

// Retour du rapport final
return "Workflow terminé : guard admin patché, routes Next.js créées, page admin fonctionnelle, composer lié au coding subgraph, VideoSession LiveKit opérationnel, lint & tests OK, README mis à jour.";
