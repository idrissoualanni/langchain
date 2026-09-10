// Contexte de sélection — user/thread courants, persistés
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { Thread, User } from '../types/agent';

interface SelectionContextValue {
  currentUser: User | null;
  currentThread: Thread | null;
  threads: Thread[];
  setUsers: (users: User[]) => void;
  selectUser: (user: User | null) => void;
  selectThread: (thread: Thread | null) => void;
  setThreads: (threads: Thread[]) => void;
}

const SelectionContext = createContext<SelectionContextValue | null>(
  null
);

const LS_USER = 'dsh_current_user';
const LS_THREAD = 'dsh_current_thread';

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<User | null>(() => {
    try {
      return JSON.parse(localStorage.getItem(LS_USER) ?? 'null');
    } catch {
      return null;
    }
  });

  const [currentThread, setCurrentThread] = useState<Thread | null>(
    () => {
      try {
        return JSON.parse(localStorage.getItem(LS_THREAD) ?? 'null');
      } catch {
        return null;
      }
    }
  );

  const [threads, setThreadsState] = useState<Thread[]>([]);

  // Persistance localStorage
  useEffect(() => {
    if (currentUser)
      localStorage.setItem(LS_USER, JSON.stringify(currentUser));
    else localStorage.removeItem(LS_USER);
  }, [currentUser]);

  useEffect(() => {
    if (currentThread)
      localStorage.setItem(LS_THREAD, JSON.stringify(currentThread));
    else localStorage.removeItem(LS_THREAD);
  }, [currentThread]);

  const selectUser = useCallback((user: User | null) => {
    setCurrentUser(user);
    // Changer d'utilisateur invalide toujours le thread courant
    // (jamais conserver le thread d'un autre user)
    setCurrentThread(null);
    setThreadsState([]);
  }, []);

  const selectThread = useCallback((thread: Thread | null) => {
    setCurrentThread(thread);
  }, []);

  const setThreads = useCallback((threads: Thread[]) => {
    setThreadsState(threads);
    // Auto-sélection : si aucun thread actif (ex: user vient de changer)
    // et que le user courant possède des threads, prendre le plus récent.
    setCurrentThread((prevThread) => {
      if (prevThread) {
        // Vérifie que le thread courant appartient toujours au user actif
        const stillValid = threads.some(
          (t) => t.thread_id === prevThread.thread_id
        );
        return stillValid ? prevThread : null;
      }
      if (threads.length > 0 && currentUser) {
        const owned = threads.filter(
          (t) => t.user_id === currentUser.user_id
        );
        return owned[0] ?? null;
      }
      return null;
    });
  }, [currentUser]);

  const setUsers = useCallback((users: User[]) => {
    // Si le user courant a disparu (DB reset), désélectionner
    setCurrentUser((prev) => {
      if (prev && !users.some((u) => u.user_id === prev.user_id)) {
        setCurrentThread(null);
        setThreadsState([]);
        return null;
      }
      return prev;
    });
  }, []);

  const value = useMemo(
    () => ({
      currentUser,
      currentThread,
      threads,
      setUsers,
      selectUser,
      selectThread,
      setThreads,
    }),
    [
      currentUser,
      currentThread,
      threads,
      setUsers,
      selectUser,
      selectThread,
      setThreads,
    ]
  );

  return (
    <SelectionContext.Provider value={value}>
      {children}
    </SelectionContext.Provider>
  );
}

export function useSelection(): SelectionContextValue {
  const ctx = useContext(SelectionContext);
  if (!ctx)
    throw new Error('useSelection must be used within SelectionProvider');
  return ctx;
}
