// App — layout + router + modals globaux
import { useState } from 'react';
import { Navigate, Route, BrowserRouter as Router, Routes } from 'react-router-dom';
import { Sidebar } from './components/layout/Sidebar';
import { ChatPage } from './pages/ChatPage';
import { MemoryPage } from './pages/MemoryPage';
import { LogsPage } from './pages/LogsPage';
import { CreateUserModal } from './components/users/CreateUserModal';
import { CreateThreadModal } from './components/chat/CreateThreadModal';
import { SelectionProvider, useSelection } from './hooks/useSelection';
import { useUsers } from './hooks/useUsers';
import { useThreads } from './hooks/useThreads';
import type { Thread, User } from './types/agent';

function AppShell() {
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [threadModalOpen, setThreadModalOpen] = useState(false);

  const { create: createUserFn } = useUsers();
  const { currentUser, selectUser, selectThread } = useSelection();
  const { create: createThreadFn } = useThreads(
    currentUser?.user_id ?? null
  );

  const handleUserCreated = (user: User) => {
    selectUser(user);
  };

  const handleThreadCreated = (thread: Thread) => {
    selectThread(thread);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-[#0b0f14]">
      <Sidebar
        onNewUser={() => setUserModalOpen(true)}
        onNewThread={() => setThreadModalOpen(true)}
      />

      <main className="min-w-0 flex-1">
        <Routes>
          <Route
            path="/chat"
            element={
              <ChatPage
                onOpenNewUserModal={() => setUserModalOpen(true)}
                onOpenNewThreadModal={() => setThreadModalOpen(true)}
              />
            }
          />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </main>

      {/* Modals globaux (sidebar + pages) */}
      <CreateUserModal
        open={userModalOpen}
        onClose={() => setUserModalOpen(false)}
        onCreate={createUserFn}
        onCreated={handleUserCreated}
      />
      <CreateThreadModal
        open={threadModalOpen}
        onClose={() => setThreadModalOpen(false)}
        onCreate={async (name) => {
          if (!currentUser) throw new Error('Aucun utilisateur sélectionné');
          return createThreadFn(name);
        }}
        onCreated={handleThreadCreated}
      />
    </div>
  );
}

export default function App() {
  return (
    <Router>
      <SelectionProvider>
        <AppShell />
      </SelectionProvider>
    </Router>
  );
}
