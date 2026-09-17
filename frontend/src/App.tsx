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
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from './components/ui/sidebar';
import { MemoryPage } from './pages/MemoryPage';
import { LogsPage } from './pages/LogsPage';
import { AssistantPage } from './pages/AssistantPage';
import { ProfilePage } from './pages/ProfilePage';
import { LearningLayout } from './pages/learning/LearningLayout';
import { LearningOverviewPage } from './pages/learning/LearningOverviewPage';
import { LearningProgressPage } from './pages/learning/LearningProgressPage';
import { LearningSubjectsPage } from './pages/learning/LearningSubjectsPage';
import { LearningSubjectDetailPage } from './pages/learning/LearningSubjectDetailPage';
import { LearningTopicsPage } from './pages/learning/LearningTopicsPage';
import { LearningGoalsPage } from './pages/learning/LearningGoalsPage';
import { LearningReviewsPage } from './pages/learning/LearningReviewsPage';
import { LearningHistoryPage } from './pages/learning/LearningHistoryPage';
import { LearningForYouPage } from './pages/learning/LearningForYouPage';
import { SettingsLayout } from './pages/settings/SettingsLayout';
import { SettingsProfilePage } from './pages/settings/SettingsProfilePage';
import { SettingsAppearancePage } from './pages/settings/SettingsAppearancePage';
import { SettingsLearningPreferencesPage } from './pages/settings/SettingsLearningPreferencesPage';
import { SettingsMemoryPage } from './pages/settings/SettingsMemoryPage';
import { SettingsNotificationsPage } from './pages/settings/SettingsNotificationsPage';
import { SettingsDataPage } from './pages/settings/SettingsDataPage';
import { DevLoginPage } from './auth/DevLoginPage';
import { AdminGate } from './auth/AdminGate';
import { useCurrentUser } from './hooks/useCurrentUser';
import { SelectionProvider } from './hooks/useSelection';
import { AssistantUIRuntimeProvider } from './assistant-ui/AssistantRuntimeProvider';

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

function AppShell() {
  return (
    <SidebarProvider className="bg-background text-foreground h-svh overflow-hidden">
      <AppSidebar />

      <SidebarInset className="min-w-0 overflow-hidden">
        <header className="border-border flex h-10 shrink-0 items-center gap-1 border-b px-2">
          <SidebarTrigger />
        </header>
        <div className="min-h-0 flex-1 overflow-hidden">
          <Routes>
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
            <Route
              path="notifications"
              element={<SettingsNotificationsPage />}
            />
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
          <Route path="*" element={<Navigate to="/assistant" replace />} />
        </Routes>
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
