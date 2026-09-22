"use client";

// ActivityPanel V1 — panneau latéral droit (spec FUNCTIONALITIES §38).
//
// Affiche les activités pédagogiques du store zustand (use-activity-store) :
//   - liste des activités (plus récente en premier), cliquables, avec icône
//     par kind, badge de statut et barre de progression ;
//   - section détail de l'activité active, rendue selon son kind
//     (diagram → MermaidDiagram, coding → CodeActivityCard, autres → JSON) ;
//   - état vide si aucune activité.
//
// Le composant ne rend que l'<aside>. C'est la mise en page parente
// (AssistantPage) qui le place en frère droit du thread dans un flex row —
// on ne gère que l'affichage du panneau lui-même ici.
//
// `activity.data` est `unknown` (charge utile brute des événements backend) :
// tout accès est gardé, jamais d'accès direct à une propriété.

import {
  Code2,
  FileText,
  GraduationCap,
  ListChecks,
  Loader2,
  ClipboardCheck,
  Search,
  Sparkles,
  Video,
  Workflow,
  X,
} from "lucide-react";
import type { FC, ReactNode } from "react";

import { CodeActivityCard } from "@/components/agent/CodeActivityCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MermaidDiagram } from "@/components/assistant-ui/elements/mermaid-diagram.aui";
import {
  type Activity,
  type ActivityKind,
  type ActivityStatus,
  useActivityStore,
} from "@/hooks/use-activity-store";
import type { CodeData } from "@/types/agentResponse";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------- helpers

/** Icône associée à chaque kind (spec §38). */
const KIND_ICONS: Record<ActivityKind, typeof Search> = {
  research: Search,
  quiz: ListChecks,
  exercise: GraduationCap,
  evaluation: ClipboardCheck,
  coding: Code2,
  document: FileText,
  diagram: Workflow,
  video: Video,
};

const KIND_LABELS: Record<ActivityKind, string> = {
  research: "Recherche",
  quiz: "Quiz",
  exercise: "Exercice",
  evaluation: "Évaluation",
  coding: "Code",
  document: "Document",
  diagram: "Diagramme",
  video: "Vidéo",
};

const STATUS_META: Record<
  ActivityStatus,
  { label: string; tone: "default" | "accent" | "success" | "error"; icon: ReactNode }
> = {
  pending: { label: "En attente", tone: "default", icon: null },
  running: {
    label: "En cours",
    tone: "accent",
    icon: <Loader2 className="size-3 animate-spin" />,
  },
  completed: { label: "Terminé", tone: "success", icon: null },
  failed: { label: "Échec", tone: "error", icon: null },
};

/** true si la valeur ressemble à un chart Mermaid (première ligne valide). */
function looksLikeMermaid(code: string): boolean {
  const head = code.trim().split(/\s+/)[0]?.toLowerCase() ?? "";
  return [
    "graph",
    "flowchart",
    "sequencediagram",
    "classdiagram",
    "statediagram",
    "erd",
    "gantt",
    "pie",
    "journey",
    "mindmap",
    "timeline",
    "quadrantchart",
    "xychart",
    "blockdiagram",
    "architecture",
    "sankey",
    "packet",
    "kanban",
    "architecture-beta",
  ].includes(head);
}

/**
 * Extrait un chart Mermaid de la charge utile d'une activité `diagram`.
 * Cherche data.chart / data.mermaid / data.diagram (chaînes), puis le cas
 * où data est lui-même le code Mermaid. Retourne null sinon.
 */
function extractMermaidChart(data: unknown): string | null {
  if (typeof data === "string") {
    return looksLikeMermaid(data) ? data : null;
  }
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    for (const key of ["chart", "mermaid", "diagram"]) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) {
        // Le champ existe et est une chaîne : on le considère comme un
        // chart Mermaid (même s'il ne commence pas par un mot-clé connu —
        // Mermaid lèverait une erreur, gérée par MermaidDiagram).
        return candidate;
      }
    }
  }
  return null;
}

/** Guard : la charge utile ressemble-t-elle à un CodeData de l'agent ? */
function isCodeData(data: unknown): data is CodeData {
  if (!data || typeof data !== "object") return false;
  const record = data as Record<string, unknown>;
  return (
    typeof record.language === "string" &&
    typeof record.starter_code === "string"
  );
}

/** JSON défensif et indenté pour le fallback <pre>. */
function safeStringify(data: unknown): string {
  try {
    return JSON.stringify(data, null, 2) ?? String(data);
  } catch {
    return String(data);
  }
}

// ---------------------------------------------------------- rendu détail

const JsonBlock: FC<{ data: unknown; maxHeight?: string }> = ({
  data,
  maxHeight = "max-h-64",
}) => (
  <pre
    className={cn(
      "aui-activity-json overflow-auto whitespace-pre-wrap rounded-lg border border-border/50 bg-muted/30 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground",
      maxHeight,
    )}
  >
    {safeStringify(data)}
  </pre>
);

const SectionLabel: FC<{ children: ReactNode }> = ({ children }) => (
  <div className="mb-1.5 font-mono text-[9px] font-semibold tracking-[0.15em] text-muted-foreground/70 uppercase">
    {children}
  </div>
);

/**
 * Rendu détaillé d'une activité selon son kind. Composant interne —
 * n'est pas exporté (ActivityPanel est le seul point d'entrée public).
 */
const ActivityDetail: FC<{ activity: Activity }> = ({ activity }) => {
  const { data } = activity;

  switch (activity.type) {
    case "diagram": {
      const chart = extractMermaidChart(data);
      if (chart) {
        return (
          <div className="space-y-1.5">
            <SectionLabel>Diagramme</SectionLabel>
            <MermaidDiagram chart={chart} />
          </div>
        );
      }
      return (
        <div className="space-y-1.5">
          <SectionLabel>Données du diagramme</SectionLabel>
          <JsonBlock data={data} />
        </div>
      );
    }

    case "document": {
      // TODO: brancher useGeneratedFiles() quand l'API MCP existe.
      // Pour l'instant on affiche ce que le backend a déposé dans data.
      return (
        <div className="space-y-1.5">
          <SectionLabel>Fichiers générés</SectionLabel>
          <JsonBlock data={data} />
        </div>
      );
    }

    case "coding": {
      if (isCodeData(data)) {
        // threadId/userId viendront du contexte de thread quand le panneau
        // sera monté dans AssistantPage ; CodeEditor accepte null.
        return (
          <div className="space-y-1.5">
            <SectionLabel>Éditeur de code</SectionLabel>
            <CodeActivityCard data={data} threadId={null} userId={null} />
          </div>
        );
      }
      return (
        <div className="space-y-1.5">
          <SectionLabel>Résultat d'exécution</SectionLabel>
          <JsonBlock data={data} />
        </div>
      );
    }

    case "research":
    case "quiz":
    case "exercise":
    case "evaluation":
    case "video":
      return <JsonBlock data={data} maxHeight="max-h-80" />;

    default: {
      // Exhaustivité : kinds futurs inconnus → JSON lisible.
      const _exhaustive: never = activity.type;
      void _exhaustive;
      return <JsonBlock data={data} />;
    }
  }
};

// ------------------------------------------------------------- panneau

const EmptyState: FC = () => (
  <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
    <div className="bg-muted/40 flex size-12 items-center justify-center rounded-full">
      <Sparkles className="text-muted-foreground size-5" />
    </div>
    <div className="space-y-1">
      <p className="text-sm font-medium">Aucune activité pour l'instant</p>
      <p className="text-muted-foreground text-xs leading-relaxed">
        Lancez un quiz, un exercice ou une correction de code depuis le bouton
        « Activité » de la barre de saisie pour les suivre ici.
      </p>
    </div>
  </div>
);

const ActivityRow: FC<{
  activity: Activity;
  active: boolean;
  onSelect: (id: string) => void;
}> = ({ activity, active, onSelect }) => {
  const Icon = KIND_ICONS[activity.type] ?? Sparkles;
  const status = STATUS_META[activity.status] ?? STATUS_META.pending;
  const progress =
    typeof activity.progress === "number" && !Number.isNaN(activity.progress)
      ? Math.min(Math.max(activity.progress, 0), 100)
      : null;

  return (
    <button
      type="button"
      onClick={() => onSelect(activity.id)}
      aria-current={active ? "true" : undefined}
      className={cn(
        "group/row w-full border-b border-border/40 px-3 py-2.5 text-left transition-colors",
        "hover:bg-accent/40 focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-2",
        active && "bg-accent",
      )}
    >
      <div className="flex items-center gap-2.5">
        <Icon
          className={cn(
            "size-4 shrink-0",
            active ? "text-foreground" : "text-muted-foreground",
          )}
        />
        <span className="flex-1 truncate text-sm font-medium">
          {activity.title}
        </span>
        <Badge tone={status.tone} variant={status.tone} className="shrink-0">
          {status.icon}
          {status.label}
        </Badge>
      </div>
      <div className="text-muted-foreground/80 mt-1 flex items-center gap-2 pl-6.5 text-[10px] font-medium tracking-wide">
        {KIND_LABELS[activity.type]}
      </div>
      {progress !== null && (
        <div className="mt-2 pl-6.5">
          <Progress value={progress} className="h-1" />
        </div>
      )}
    </button>
  );
};

/**
 * Panneau latéral droit des activités (spec §38).
 *
 * Ne rend rien quand le panneau est fermé (panelOpen === false) — c'est
 * l'unique consommateur de l'état `panelOpen` du store.
 */
export function ActivityPanel() {
  const panelOpen = useActivityStore((s) => s.panelOpen);
  const activities = useActivityStore((s) => s.activities);
  const activeActivityId = useActivityStore((s) => s.activeActivityId);
  const setActive = useActivityStore((s) => s.setActive);
  const togglePanel = useActivityStore((s) => s.togglePanel);

  if (!panelOpen) return null;

  const activeActivity =
    activities.find((a) => a.id === activeActivityId) ?? null;

  return (
    <aside
      aria-label="Activité"
      className="bg-background border-border flex w-96 shrink-0 flex-col overflow-hidden border-l"
    >
      {/* Header */}
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-3">
        <h2 className="text-sm font-semibold">Activité</h2>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => togglePanel(false)}
          aria-label="Fermer le panneau d'activité"
        >
          <X className="size-4" />
        </Button>
      </header>

      {/* Corps : liste + détail de l'activité active */}
      <ScrollArea className="flex min-h-0 flex-1 flex-col">
        {activities.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            <nav aria-label="Liste des activités" role="list">
              {activities.map((activity) => (
                <div role="listitem" key={activity.id}>
                  <ActivityRow
                    activity={activity}
                    active={activity.id === activeActivityId}
                    onSelect={setActive}
                  />
                </div>
              ))}
            </nav>

            {activeActivity ? (
              <section
                aria-label="Détail de l'activité"
                className="border-t border-border p-3"
              >
                <div className="mb-2 flex items-baseline justify-between gap-2">
                  <h3 className="line-clamp-2 text-xs font-semibold">
                    {activeActivity.title}
                  </h3>
                  <span className="text-muted-foreground shrink-0 text-[10px] font-medium">
                    {KIND_LABELS[activeActivity.type]}
                  </span>
                </div>
                <ActivityDetail activity={activeActivity} />
              </section>
            ) : (
              <div className="text-muted-foreground border-t border-border p-4 text-center text-xs">
                Sélectionnez une activité pour en voir le détail.
              </div>
            )}
          </>
        )}
      </ScrollArea>
    </aside>
  );
}

ActivityPanel.displayName = "ActivityPanel";
