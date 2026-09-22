// App — layout + router + runtime Assistant UI
//
// Mission Identité : l'identité vient de Clerk ( ou dev ) — PLUS de
// UserSelector ; routes protégées derrière SignedIn / session dev.
// Mission Cleanup : /chat supprimé → redirect vers /assistant.
// Refonte visuelle : le runtime Assistant UI est monté au niveau du
// shell pour que le ThreadList officiel vive dans le rail unique
// (Sidebar) — cf. brief §15/§16.
// Mission Pages Utilisateur : navigation Assistant / Learning /
// Profile / Settings (+ /logs réservé aux admins).
import {
  Navigate,
  Route,
  BrowserRouter as Router,
  Routes,
} from 'react-router-dom';
import { SignedIn, SignedOut, SignIn, SignUp } from '@clerk/clerk-react';
import { AppSidebar } from './components/app-sidebar';
import { lazy, Suspense } from 'react';
import { useLocation } from 'react-router-dom';
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from './components/ui/sidebar';
import { LoadingState } from './components/ui/loading-state';
import { CommandPalette } from './components/layout/command-palette';
import { AssistantPage } from './pages/AssistantPage';
import { DevLoginPage } from './auth/DevLoginPage';
import { AdminGate } from './auth/AdminGate';
import { useCurrentUser } from './hooks/useCurrentUser';
import { SelectionProvider } from './hooks/useSelection';
import { AssistantUIRuntimeProvider } from './assistant-ui/AssistantRuntimeProvider';

// Lazy — code-splitting (§28) : LiveKit/Mermaid/Admin ne bloquent plus le First Paint
const MemoryPage = lazy(() => import('./pages/MemoryPage').then((m) => ({ default: m.MemoryPage })));
const LogsPage = lazy(() => import('./pages/LogsPage').then((m) => ({ default: m.LogsPage })));
const AdminDashboardPage = lazy(() => import('./app/admin/page'));
const TracesPage = lazy(() => import('./features/admin/traces/TracesPage').then((m) => ({ default: m.TracesPage })));
const ModelsPage = lazy(() => import('./features/admin/models/ModelsPage').then((m) => ({ default: m.ModelsPage })));
const KnowledgePage = lazy(() => import('./features/admin/knowledge/KnowledgePage').then((m) => ({ default: m.KnowledgePage })));
const ObservabilityPage = lazy(() => import('./features/admin/observability/ObservabilityPage').then((m) => ({ default: m.ObservabilityPage })));
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })));
const DocumentsPage = lazy(() => import('./pages/DocumentsPage').then((m) => ({ default: m.DocumentsPage })));
const VideoPage = lazy(() => import('./app/video/page'));
const VoicePage = lazy(() => import('./app/voice/page'));
const LearningLayout = lazy(() => import('./pages/learning/LearningLayout').then((m) => ({ default: m.LearningLayout })));
const LearningOverviewPage = lazy(() => import('./pages/learning/LearningOverviewPage').then((m) => ({ default: m.LearningOverviewPage })));
const LearningProgressPage = lazy(() => import('./pages/learning/LearningProgressPage').then((m) => ({ default: m.LearningProgressPage })));
const LearningSubjectsPage = lazy(() => import('./pages/learning/LearningSubjectsPage').then((m) => ({ default: m.LearningSubjectsPage })));
const LearningSubjectDetailPage = lazy(() => import('./pages/learning/LearningSubjectDetailPage').then((m) => ({ default: m.LearningSubjectDetailPage })));
const LearningTopicsPage = lazy(() => import('./pages/learning/LearningTopicsPage').then((m) => ({ default: m.LearningTopicsPage })));
const LearningGoalsPage = lazy(() => import('./pages/learning/LearningGoalsPage').then((m) => ({ default: m.LearningGoalsPage })));
const LearningReviewsPage = lazy(() => import('./pages/learning/LearningReviewsPage').then((m) => ({ default: m.LearningReviewsPage })));
const LearningHistoryPage = lazy(() => import('./pages/learning/LearningHistoryPage').then((m) => ({ default: m.LearningHistoryPage })));
const LearningForYouPage = lazy(() => import('./pages/learning/LearningForYouPage').then((m) => ({ default: m.LearningForYouPage })));
const SettingsLayout = lazy(() => import('./pages/settings/SettingsLayout').then((m) => ({ default: m.SettingsLayout })));
const SettingsProfilePage = lazy(() => import('./pages/settings/SettingsProfilePage').then((m) => ({ default: m.SettingsProfilePage })));
const SettingsAppearancePage = lazy(() => import('./pages/settings/SettingsAppearancePage').then((m) => ({ default: m.SettingsAppearancePage })));
const SettingsLearningPreferencesPage = lazy(() => import('./pages/settings/SettingsLearningPreferencesPage').then((m) => ({ default: m.SettingsLearningPreferencesPage })));
const SettingsMemoryPage = lazy(() => import('./pages/settings/SettingsMemoryPage').then((m) => ({ default: m.SettingsMemoryPage })));
const SettingsModelPage = lazy(() => import('./pages/settings/SettingsModelPage').then((m) => ({ default: m.SettingsModelPage })));
const SettingsNotificationsPage = lazy(() => import('./pages/settings/SettingsNotificationsPage').then((m) => ({ default: m.SettingsNotificationsPage })));
const SettingsSessionsPage = lazy(() => import('./pages/settings/SettingsSessionsPage').then((m) => ({ default: m.SettingsSessionsPage })));
const SettingsDataPage = lazy(() => import('./pages/settings/SettingsDataPage').then((m) => ({ default: m.SettingsDataPage })));

/** Route protégée : session requise ( mode dev → page dev login ). */
function Protected({ children }: { children: React.ReactNode }) {
  const { signedIn, devMode } = useCurrentUser();
  if (devMode && !signedIn) return <Navigate to="/dev-login" replace />;
  return (
    <>
      {/* mode clerk : garde officielle Clerk */}
      {!devMode && (
        <>
          <SignedOut>
            <Navigate to="/sign-in" replace />
          </SignedOut>
          <SignedIn>{children}</SignedIn>
        </>
      )}
      {devMode && signedIn && <>{children}</>}
    </>
  );
}

function PageTitle() {
  const { pathname } = useLocation();
  const map: Record<string, string> = {
    '/assistant': 'Assistant',
    '/learning': 'Learning',
    '/documents': 'Documents',
    '/memory': 'Mémoire',
    '/profile': 'Profil',
    '/settings': 'Paramètres',
    '/video': 'Vidéo',
    '/voice': 'Voix',
    '/admin': 'Admin',
    '/logs': 'Journal',
  };
  const seg = `/${pathname.split('/')[1] ?? ''}`;
  const label = map[seg] ?? '';
  const sub = pathname.split('/').slice(2).join(' / ');
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="truncate text-[13px] font-medium tracking-tight text-foreground">{label}</span>
      {sub && <span className="hidden truncate font-mono text-[11px] text-muted-foreground sm:inline">/ {sub}</span>}
    </div>
  );
}

function AppShell() {
  return (
    <SidebarProvider className="bg-background text-foreground h-svh overflow-hidden">
      <a
        href="#main-content"
        className="sr-only z-[100] rounded bg-primary px-3 py-1 text-sm text-primary-foreground focus:not-sr-only focus:absolute focus:left-3 focus:top-3"
      >
        Aller au contenu
      </a>
      <AppSidebar />

      <SidebarInset className="min-w-0 overflow-hidden">
        <header className="border-border flex h-10 shrink-0 items-center gap-2 border-b px-3">
          <SidebarTrigger aria-label="Basculer la navigation" aria-expanded={undefined} />
          <PageTitle />
          <span className="ml-auto hidden font-mono text-[10px] text-muted-foreground sm:inline">⌘K</span>
        </header>
        <CommandPalette />
        <div id="main-content" className="min-h-0 flex-1 overflow-hidden">
          <Suspense fallback={<div className="p-6"><LoadingState label="Chargement de la page…" /></div>}>
            <Routes>
          <Route index element={<Navigate to="/assistant" replace />} />
          <Route path="/dev-login" element={<DevLoginPage />} />
          <Route path="/sign-in" element={<SignIn routing="hash" />} />
          <Route path="/sign-up" element={<SignUp routing="hash" />} />

          <Route
            path="/assistant"
            element={
              <Protected>
                <AssistantPage />
              </Protected>
            }
          />
          <Route path="/chat" element={<Navigate to="/assistant" replace />} />

          {/* Vidéo — session LiveKit */}
          <Route
            path="/video"
            element={
              <Protected>
                <VideoPage />
              </Protected>
            }
          />

          {/* Voix — session vocale LiveKit ( agent tuteur temps réel ) */}
          <Route
            path="/voice"
            element={
              <Protected>
                <VoicePage />
              </Protected>
            }
          />

          {/* Learning — section à navigation secondaire */}
          <Route
            path="/learning"
            element={
              <Protected>
                <LearningLayout />
              </Protected>
            }
          >
            <Route index element={<LearningOverviewPage />} />
            <Route path="progress" element={<LearningProgressPage />} />
            <Route path="subjects" element={<LearningSubjectsPage />} />
            <Route
              path="subjects/:subjectId"
              element={<LearningSubjectDetailPage />}
            />
            <Route path="topics" element={<LearningTopicsPage />} />
            <Route path="goals" element={<LearningGoalsPage />} />
            <Route path="reviews" element={<LearningReviewsPage />} />
            <Route path="history" element={<LearningHistoryPage />} />
            <Route path="for-you" element={<LearningForYouPage />} />
          </Route>

          {/* Profile */}
          <Route
            path="/profile"
            element={
              <Protected>
                <ProfilePage />
              </Protected>
            }
          />

          {/* Documents (RAG V10) — documents personnels de l'utilisateur */}
          <Route
            path="/documents"
            element={
              <Protected>
                <DocumentsPage />
              </Protected>
            }
          />

          {/* Settings — section à navigation secondaire */}
          <Route
            path="/settings"
            element={
              <Protected>
                <SettingsLayout />
              </Protected>
            }
          >
            <Route index element={<Navigate to="/settings/profile" replace />} />
            <Route path="profile" element={<SettingsProfilePage />} />
            <Route path="appearance" element={<SettingsAppearancePage />} />
            <Route
              path="learning"
              element={<SettingsLearningPreferencesPage />}
            />
            <Route path="memory" element={<SettingsMemoryPage />} />
            <Route path="model" element={<SettingsModelPage />} />
            <Route
              path="notifications"
              element={<SettingsNotificationsPage />}
            />
            <Route path="sessions" element={<SettingsSessionsPage />} />
            <Route path="data" element={<SettingsDataPage />} />
          </Route>

          {/* Mémoire — accès direct conservé (aussi via Settings → Memory) */}
          <Route
            path="/memory"
            element={
              <Protected>
                <MemoryPage />
              </Protected>
            }
          />
          {/* Logs : ADMIN uniquement (§22) */}
          <Route
            path="/logs"
            element={
              <AdminGate>
                <LogsPage />
              </AdminGate>
            }
          />
          <Route
            path="/admin"
            element={
              <AdminGate>
                <AdminDashboardPage />
              </AdminGate>
            }
          />
          <Route
            path="/admin/traces"
            element={
              <AdminGate>
                <TracesPage />
              </AdminGate>
            }
          />
          <Route
            path="/admin/models"
            element={
              <AdminGate>
                <ModelsPage />
              </AdminGate>
            }
          />
          <Route
            path="/admin/knowledge"
            element={
              <AdminGate>
                <KnowledgePage />
              </AdminGate>
            }
          />
          <Route
            path="/admin/observability"
            element={
              <AdminGate>
                <ObservabilityPage />
              </AdminGate>
            }
          />

        </Routes>
          </Suspense>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

/** Runtime Assistant UI monté au-dessus du shell (ThreadList dans la Sidebar). */
function AppRuntime() {
  const { internal, signedIn } = useCurrentUser();
  return (
    <AssistantUIRuntimeProvider
      userId={signedIn ? internal?.user_id ?? null : null}
    >
      <AppShell />
    </AssistantUIRuntimeProvider>
  );
}

export default function App() {
  return (
    <Router>
      <SelectionProvider>
        <AppRuntime />
      </SelectionProvider>
    </Router>
  );
}
