// Sidebar — navigation + sélection user/thread + statuts services
// Les sélecteurs sont directement ici : c'est le centre de contrôle.
import { useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Bot,
  Database,
  MessageSquare,
  ScrollText,
} from 'lucide-react';
import { useHealth } from '../../hooks/useHealth';
import { useSelection } from '../../hooks/useSelection';
import { useUsers } from '../../hooks/useUsers';
import { useThreads } from '../../hooks/useThreads';
import { StatusBadge } from './StatusBadge';
import { UserSelector } from '../users/UserSelector';
import { ThreadSelector } from '../threads/ThreadSelector';

interface SidebarProps {
  onNewUser: () => void;
  onNewThread: () => void;
}

export function Sidebar({ onNewUser, onNewThread }: SidebarProps) {
  const { health } = useHealth();
  const {
    currentUser,
    currentThread,
    threads,
    selectUser,
    selectThread,
    setThreads,
  } = useSelection();
  const { users, loading: usersLoading } = useUsers();
  const {
    threads: userThreads,
    loading: threadsLoading,
  } = useThreads(currentUser?.user_id ?? null);

  // Sync les threads chargés vers le contexte
  // (l'auto-sélection du dernier thread se fait dans useSelection)
  useEffect(() => {
    setThreads(userThreads);
  }, [userThreads, setThreads]);

  const navItems = [
    { to: '/chat', label: 'Chat', icon: MessageSquare },
    { to: '/memory', label: 'Memory', icon: Database },
    { to: '/logs', label: 'Logs', icon: ScrollText },
  ];

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-[#26323d] bg-[#111820]">
      {/* Identité */}
      <div className="flex items-center gap-2.5 border-b border-[#26323d] px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-[#6c63ff] to-[#8b83ff]">
          <Bot size={19} className="text-white" />
        </div>
        <div>
          <div className="text-[15px] font-semibold tracking-tight text-[#f5f7fa]">
            Agent Lab
          </div>
          <div className="font-mono text-[10px] text-[#94a3b8]">
            control center
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-0.5 p-2.5">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[#6c63ff]/10 text-[#6c63ff]'
                  : 'text-[#94a3b8] hover:bg-[#18212b] hover:text-[#f5f7fa]'
              }`
            }
          >
            <Icon size={16} strokeWidth={1.8} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Sélection — user puis thread (directement dans la sidebar) */}
      <div className="space-y-4 border-t border-[#26323d] p-4">
        <div>
          <div className="mb-1.5 font-mono text-[9px] font-semibold uppercase tracking-[0.18em] text-[#94a3b8]/70">
            current user
          </div>
          <UserSelector
            users={users}
            currentUserId={currentUser?.user_id ?? null}
            onChange={selectUser}
            loading={usersLoading}
          />
        </div>

        <div>
          <div className="mb-1.5 font-mono text-[9px] font-semibold uppercase tracking-[0.18em] text-[#94a3b8]/70">
            current thread
          </div>
          <ThreadSelector
            threads={threads}
            currentThreadId={currentThread?.thread_id ?? null}
            onChange={selectThread}
            loading={threadsLoading}
          />
        </div>

        {/* Création */}
        <div className="flex flex-col gap-2">
          <button
            onClick={onNewUser}
            className="flex items-center justify-center gap-2 rounded-lg border border-[#26323d] bg-[#18212b] px-3 py-2 text-sm font-medium text-[#f5f7fa] transition-colors hover:border-[#6c63ff]/50 hover:text-[#6c63ff]"
          >
            + New User
          </button>
          <button
            onClick={onNewThread}
            disabled={!currentUser}
            className="flex items-center justify-center gap-2 rounded-lg border border-[#26323d] bg-[#18212b] px-3 py-2 text-sm font-medium text-[#f5f7fa] transition-colors hover:border-[#6c63ff]/50 hover:text-[#6c63ff] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-[#26323d] disabled:hover:text-[#f5f7fa]"
          >
            + New Thread
          </button>
        </div>
      </div>

      <div className="flex-1" />

      {/* Services */}
      <div className="space-y-2 border-t border-[#26323d] p-4">
        <div className="mb-3 font-mono text-[9px] font-semibold uppercase tracking-[0.18em] text-[#94a3b8]/70">
          services
        </div>
        <StatusBadge label="ollama" ok={health ? health.ollama : null} />
        <StatusBadge label="langgraph" ok={health ? health.langgraph : null} />
        <StatusBadge label="sqlite" ok={health ? health.sqlite : null} />
      </div>

      {/* Pied — agent online */}
      <div className="flex items-center gap-2 border-t border-[#26323d] px-5 py-3.5">
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${
            health?.status === 'ok' || health === null
              ? 'bg-[#22c55e] pulse-dot'
              : 'bg-[#ef4444]'
          }`}
        />
        <span className="text-xs font-medium text-[#94a3b8]">
          {health?.status === 'ok' || health === null
            ? 'Agent online'
            : 'Agent error'}
        </span>
        {health && (
          <span
            className="ml-auto truncate font-mono text-[10px] text-[#94a3b8]/50"
            title={health.model}
          >
            {health.model.split(':')[0]}
          </span>
        )}
      </div>
    </aside>
  );
}
