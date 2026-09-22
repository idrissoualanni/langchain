// Page /assistant — document interactif (brief §17) — refonte §8
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
import { useToolUIs } from '../assistant-ui/tool-uis';
import { useAssistantStore } from '../assistant-ui/store';
import { useHealth } from '../hooks/useHealth';
import { InlineError } from '../components/ui/error-state';
import { useActivityStore } from '../hooks/use-activity-store';
import { ActivityCard } from '../components/agent/activity-card';
import { ActivityPanel } from '../components/assistant-ui/elements/activity-panel.aui';

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

/** Bandeau d'erreur run — humain + dismiss (§24). */
function RunErrorBanner() {
  const error = useAssistantStore((s) => s.error);
  const setError = useAssistantStore((s) => s.setError);
  if (!error) return null;
  return (
    <div className="mx-auto w-full max-w-[44rem] px-2 pt-2">
      <InlineError message={error} onDismiss={() => setError(null)} />
    </div>
  );
}

/** Header d'activité sticky — ce que fait l'agent maintenant (§6) */
function AgentActivityHeader() {
  const isRunning = useAssistantStore((s) => s.isRunning);
  const activities = useActivityStore((s) => s.activities);
  const running = activities.find((a) => a.status === 'running');
  if (!isRunning && !running) return null;
  return (
    <div className="mx-auto w-full max-w-[44rem] px-2">
      <div className="flex items-center gap-2 rounded-lg border border-live/20 bg-live/5 px-3 py-2 font-mono text-[11px]">
        <span className="size-2 animate-pulse rounded-full bg-live" />
        <span className="text-live">
          {running ? running.title : 'L’agent réfléchit…'}
        </span>
        <span className="ml-auto text-muted-foreground">
          {running ? `${running.type} · en cours` : 'streaming'}
        </span>
      </div>
    </div>
  );
}

/** Ouvreur du panel — compteur d'activités running */
function ActivityOpener() {
  const count = useActivityStore((s) => s.activities.filter((a) => a.status === 'running').length);
  const toggle = useActivityStore((s) => s.togglePanel);
  return (
    <button type="button" onClick={() => toggle(true)} className="text-muted-foreground hover:text-foreground font-mono text-[11px] underline">
      Activité{count ? ` (${count} en cours)` : ''}
    </button>
  );
}

/** Composants montés DANS le runtime (hooks officiels data UI). */
function AssistantRuntimeChildren() {
  useAgentResponseDataUI();
  useToolUIs();
  return (
    <div className="flex h-full min-h-0 flex-row">
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center justify-end px-2 py-1">
          <ActivityOpener />
        </div>
        <RunErrorBanner />
        <AgentActivityHeader />
        <div className="min-h-0 flex-1 overflow-hidden">
          <Thread components={THREAD_COMPONENTS} />
        </div>
      </div>
      <ActivityPanel />
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
