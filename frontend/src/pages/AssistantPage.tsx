// Page /assistant — document interactif (brief §17)
//
// Le runtime Assistant UI et le ThreadList officiel sont montés au
// niveau du shell (App.tsx) : la Sidebar porte les conversations, la
// page porte le Thread. Toutes les primitives restent officielles.
import { useEffect } from 'react';
import { useAuiState } from '@assistant-ui/react';
import {
  Thread,
  type ThreadComponents,
} from '../components/assistant-ui/elements/thread.aui';
import { ModelSelector } from '../components/assistant-ui/elements/model-selector.aui';
import { useModelCatalog } from '../assistant-ui/AssistantRuntimeProvider';
import { useAgentResponseDataUI } from '../assistant-ui/AgentResponseDataUI';
import { useAssistantStore } from '../assistant-ui/store';
import { useHealth } from '../hooks/useHealth';

/**
 * Sélecteur de modèle intégré au Composer (brief §19).
 * La valeur affichée provient du ModelContext officiel Assistant UI via
 * `useAuiState` — le ModelSelector enregistre ce contexte.
 */
function ComposerModelPicker() {
  const catalog = useModelCatalog();
  const setModel = useAssistantStore((s) => s.setModel);
  const modelName = useAuiState((s) => s.modelContext.modelName);
  const { health } = useHealth();

  const models = (catalog?.models ?? []).map((m) => ({
    id: m.id,
    name: m.name,
    description: m.description || undefined,
  }));

  if (models.length === 0) {
    const label = modelName ?? health?.model;
    if (!label) return null;
    return (
      <div className="text-muted-foreground flex min-w-0 items-center gap-1.5 font-mono text-[11px]">
        <span className="bg-live size-1.5 shrink-0 rounded-full" />
        <span className="truncate">{label}</span>
      </div>
    );
  }

  return (
    <ModelSelector
      models={models}
      defaultValue={modelName ?? catalog?.activeModel}
      onValueChange={(id) => setModel(id)}
      size="sm"
      variant="ghost"
      align="start"
    />
  );
}

/** Welcome sobre : eyebrow mono, titre clair, description courte (brief §18). */
const THREAD_COMPONENTS: ThreadComponents = {
  ComposerToolbar: ComposerModelPicker,
  Welcome: () => (
    <div className="mb-8 flex flex-col items-start px-2">
      <span className="text-muted-foreground font-mono text-[11px] tracking-[0.1em] uppercase">
        assistant
      </span>
      <h1 className="text-foreground mt-2 text-2xl font-medium tracking-tight">
        Prêt à réviser ?
      </h1>
      <p className="text-muted-foreground mt-2 max-w-md text-sm leading-relaxed">
        Posez une question, demandez un exercice, un quiz ou un indice.
        Vos conversations sont persistées côté backend.
      </p>
    </div>
  ),
};

/** Bandeau d'erreur run (états error UX) — règle rouge discrète (brief §30). */
function RunErrorBanner() {
  const error = useAssistantStore((s) => s.error);
  const setError = useAssistantStore((s) => s.setError);
  if (!error) return null;
  return (
    <div
      role="alert"
      className="border-destructive/40 bg-destructive/5 text-destructive mx-auto mb-2 flex w-full max-w-[44rem] items-start gap-2 rounded-[var(--radius-document)] border-s-2 px-3 py-2 text-sm"
    >
      <span className="min-w-0 flex-1 break-words">{error}</span>
      <button
        type="button"
        onClick={() => setError(null)}
        className="text-destructive/70 hover:text-destructive shrink-0 text-xs underline"
      >
        masquer
      </button>
    </div>
  );
}

/** Composants montés DANS le runtime (hooks officiels data UI). */
function AssistantRuntimeChildren() {
  // Data part "agent-response" → cartes pédagogiques (mécanisme officiel)
  useAgentResponseDataUI();
  return (
    <div className="flex h-full min-h-0 flex-col">
      <RunErrorBanner />
      <div className="min-h-0 flex-1">
        <Thread components={THREAD_COMPONENTS} />
      </div>
    </div>
  );
}

export function AssistantPage() {
  useEffect(() => {
    document.title = 'Agent Lab — Assistant';
    return () => {
      document.title = 'Agent Lab — Control Center';
    };
  }, []);

  return <AssistantRuntimeChildren />;
}
