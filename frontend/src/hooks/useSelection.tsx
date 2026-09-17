// Contexte de sélection — thread courant du contexte actif
//
// Mission Cleanup : la PARTIE UTILISATEUR a été supprimée (l'identité
// vient de Clerk/useCurrentUser — jamais du localStorage, cf. §6).
// Ne reste que currentThread, lu par MemoryPage pour afficher le
// contexte actif ; la valeur est écrite localement par
// assistant-ui/store.ts (sélection uniquement, source de vérité = backend).
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { Thread } from '../types/agent';

interface SelectionContextValue {
  currentThread: Thread | null;
  selectThread: (thread: Thread | null) => void;
}

const SelectionContext = createContext<SelectionContextValue | null>(
  null
);

const LS_THREAD = 'dsh_current_thread';

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [currentThread, setCurrentThread] = useState<Thread | null>(
    () => {
      try {
        return JSON.parse(localStorage.getItem(LS_THREAD) ?? 'null');
      } catch {
        return null;
      }
    }
  );

  const selectThread = useCallback((thread: Thread | null) => {
    setCurrentThread(thread);
    if (thread)
      localStorage.setItem(LS_THREAD, JSON.stringify(thread));
    else localStorage.removeItem(LS_THREAD);
  }, []);

  const value = useMemo(
    () => ({ currentThread, selectThread }),
    [currentThread, selectThread]
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
