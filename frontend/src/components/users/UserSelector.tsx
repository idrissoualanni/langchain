// UserSelector — choisir l'utilisateur actif
import { useEffect, useRef, useState } from 'react';
import { ChevronDown, User as UserIcon } from 'lucide-react';
import type { User } from '../../types/agent';

interface UserSelectorProps {
  users: User[];
  currentUserId: string | null;
  onChange: (user: User) => void;
  loading?: boolean;
}

function formatDate(iso: string): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

export function UserSelector({
  users,
  currentUserId,
  onChange,
  loading,
}: UserSelectorProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const current = users.find((u) => u.user_id === currentUserId);
  const disabled = !loading && users.length === 0;

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen(!open)}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={`flex min-w-[180px] items-center gap-2 rounded-lg border border-[#26323d] bg-[#18212b] px-3 py-1.5 text-[13px] text-[#f5f7fa] transition-colors hover:border-[#6c63ff]/50 disabled:cursor-not-allowed ${
          users.length === 0 && !loading ? 'opacity-50' : ''
        }`}
      >
        <UserIcon size={13} className="shrink-0 text-[#6c63ff]" />
        <span className="truncate">
          {current
            ? current.name
            : loading
              ? 'chargement…'
              : users.length === 0
                ? 'aucun utilisateur'
                : 'choisir un utilisateur'}
        </span>
        <ChevronDown size={13} className="ml-auto shrink-0 text-[#94a3b8]" />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute z-30 mt-1.5 max-h-72 w-full min-w-[260px] overflow-y-auto rounded-lg border border-[#26323d] bg-[#111820] py-1 shadow-xl shadow-black/40"
        >
          {users.map((u) => {
            const isCurrent = u.user_id === currentUserId;
            return (
              <button
                key={u.user_id}
                role="option"
                aria-selected={isCurrent}
                onClick={() => {
                  onChange(u);
                  setOpen(false);
                }}
                className={`flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left transition-colors hover:bg-[#18212b] ${
                  isCurrent ? 'bg-[#6c63ff]/10' : ''
                }`}
              >
                <span
                  className={`truncate text-[13px] ${
                    isCurrent ? 'text-[#6c63ff]' : 'text-[#f5f7fa]'
                  }`}
                >
                  {u.name}
                  {isCurrent && (
                    <span className="ml-1.5 font-mono text-[9px] uppercase tracking-wider text-[#6c63ff]">
                      actif
                    </span>
                  )}
                </span>
                <span className="flex w-full items-center gap-2 font-mono text-[10px] text-[#94a3b8]/70">
                  <span>{formatDate(u.created_at)}</span>
                  <span
                    className="truncate text-[#94a3b8]/40"
                    title={u.user_id}
                  >
                    {u.user_id.slice(0, 8)}…
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
