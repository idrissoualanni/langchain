// Couche d'adaptation Assistant UI — provider runtime officiel
//
// Runtime choisi (design validé) : ExternalStoreRuntime OFFICIEL
// (@assistant-ui/react useExternalStoreRuntime) — pattern
// documentation "runtimes/custom/external-store" : nous possédons
// l'état (store.ts), le runtime rend ce qu'on lui fournit.
//
// Multi-thread OFFICIEL : ExternalStoreThreadListAdapter (doc
// "runtimes/concepts/threads" — synchrone, inline) branché sur
// l'API threads existante + renommage persistant.
//
// ModelSelector OFFICIEL : ModelContext via aui.modelContext
// .register() — la sélection arrive à chaque requête chat.
'use client';

import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleImageAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  useExternalStoreRuntime,
  type ExternalStoreThreadListAdapter,
} from '@assistant-ui/react';
import { useAssistantStore, setStoreUser } from './store';
import { convertMessage } from './convert';
import type { BackendModel } from './types';
import { listModels } from './api';

// Pièces jointes — adaptateurs OFFICIELS (images + fichiers texte).
// Le Composer (attachment.aui) gère l'ajout/preview/retrait ; à l'envoi,
// SimpleTextAttachmentAdapter produit un part `text` (contenu du fichier
// encapsulé) que `onNew` transmet au backend.
const attachmentAdapter = new CompositeAttachmentAdapter([
  new SimpleImageAttachmentAdapter(),
  new SimpleTextAttachmentAdapter(),
]);

export function AssistantUIRuntimeProvider({
  userId,
  children,
}: {
  userId: string | null;
  children: ReactNode;
}) {
  // Le store est l'état externe — le runtime lit dessus
  const messages = useAssistantStore((s) => s.messages);
  const isRunning = useAssistantStore((s) => s.isRunning);
  const threads = useAssistantStore((s) => s.threads);
  const threadsLoading = useAssistantStore((s) => s.threadsLoading);
  const currentThreadId = useAssistantStore((s) => s.currentThreadId);
  const historyLoading = useAssistantStore((s) => s.historyLoading);

  const switchThread = useAssistantStore((s) => s.switchThread);
  const switchToNewThread = useAssistantStore((s) => s.switchToNewThread);
  const rename = useAssistantStore((s) => s.rename);
  const removeThread = useAssistantStore((s) => s.removeThread);
  const sendMessage = useAssistantStore((s) => s.sendMessage);
  const cancel = useAssistantStore((s) => s.cancel);
  const loadThreads = useAssistantStore((s) => s.loadThreads);

  // Porte le userId au store (actions threads sans re-passer l'id)
  setStoreUser(userId);

  // Chargement/switch des threads + historique à la sélection
  //
  // F5 (§21) : le thread ACTIF est restauré depuis localStorage
  // ( dsh_current_thread — écrit par store.ts à chaque switch/création ) ;
  // s'il est absent/invalide on retombe sur le plus récent du
  // BACKEND. La source de vérité du CONTENU reste le backend
  // ( /state ) — localStorage ne porte que la sélection.
  useEffect(() => {
    if (userId === null) return;
    loadThreads(userId).then(() => {
      const state = useAssistantStore.getState();
      if (state.currentThreadId !== null) return;
      // 1. Thread actif restauré ( sélection persistée )
      try {
        const saved = JSON.parse(
          localStorage.getItem('dsh_current_thread') ?? 'null',
        ) as { thread_id?: string; user_id?: string } | null;
        const stillOwned =
          saved?.thread_id &&
          saved.user_id === userId &&
          state.threads.some(
            (t) => t.thread_id === saved.thread_id,
          );
        if (stillOwned) {
          void switchThread(userId, saved!.thread_id!);
          return;
        }
      } catch {
        /* localStorage corrompu → fallback */
      }
      // 2. Fallback : thread le plus récent côté backend
      if (state.threads.length > 0) {
        switchThread(userId, state.threads[0].thread_id);
      }
    });
  }, [userId, loadThreads, switchThread]);

  // --- Adaptateur ThreadList OFFICIEL (synchrone, inline) ---
  // Mapping BackendThread (contrat ThreadOut) → ExternalStoreThreadData
  // officiel : id (thread_id), status, title, custom (created_at).
  const threadListAdapter: ExternalStoreThreadListAdapter = useMemo(
    () => ({
      threadId: currentThreadId ?? undefined,
      isLoading: threadsLoading,
      threads: threads.map((t) => ({
        id: t.thread_id,
        remoteId: t.thread_id,
        status: 'regular' as const,
        title: t.name,
        custom: { created_at: t.created_at, user_id: t.user_id },
      })),
      archivedThreads: [], // pas d'archivage côté backend (contrat inchangé)
      onSwitchToNewThread: () => {
        void switchToNewThread(userId);
      },
      onSwitchToThread: (id) => {
        void switchThread(userId, id);
      },
      onRename: (id, title) => {
        void rename(id, title);
      },
      onArchive: () => {
        /* non supporté — pas d'endpoint backend archivage */
      },
      onUnarchive: () => {
        /* non supporté */
      },
      onDelete: (id) => {
        void removeThread(id);
      },
    }),
    [currentThreadId, threads, threadsLoading, userId, switchThread, switchToNewThread, rename, removeThread],
  );

  // --- Runtime OFFICIEL — handlers de la matrice documentation ---
  const runtime = useExternalStoreRuntime({
    // état
    messages,
    isRunning,
    isLoading: historyLoading || threadsLoading,

    // conversion AgentResponse → ThreadMessageLike (data part)
    convertMessage,

    // onNew (requis) : envoi + streaming (store.sendMessage)
    onNew: async (message) => {
      if (userId === null) {
        useAssistantStore
          .getState()
          .setError('Sélectionnez un utilisateur (sidebar gauche).');
        return;
      }
      const text = message.content
        .filter((p) => p.type === 'text')
        .map((p) => p.text)
        .join(String.fromCharCode(10));
      // Envoyer le message au backend chat. C'est le main graph qui
      // décide ensuite, via son propre router de capacités, d'invoquer
      // ou non le sous-graphe coding — on ne double pas l'appel ici.
      await sendMessage(userId, text);
    },

    // onCancel : Stop generation (bouton Cancel officiel du Composer)
    onCancel: async () => {
      cancel();
    },

    // adaptateurs officiels
    adapters: {
      threadList: threadListAdapter,
      attachments: attachmentAdapter,
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}

// ------------------------------------------------------------------
// ModelSelector officiel — modèles depuis GET /api/models
// ------------------------------------------------------------------

export interface ModelCatalog {
  models: BackendModel[];
  activeModel: string;
}

export function useModelCatalog(): ModelCatalog | null {
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  useEffect(() => {
    let alive = true;
    listModels()
      .then((res) => {
        if (alive) {
          setCatalog({
            models: res.models,
            activeModel: res.active_model,
          });
        }
      })
      .catch(() => {
        if (alive) setCatalog(null);
      });
    return () => {
      alive = false;
    };
  }, []);
  return catalog;
}
