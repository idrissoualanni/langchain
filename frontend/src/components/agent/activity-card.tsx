// ActivityCard — couche UX unifiée des activités agentiques (§7)
// Remplace les ToolStatus dispersés par une carte lisible : kind → label humain, status → visuel

import {
  Beaker,
  BookOpen,
  Code2,
  FileSearch,
  GraduationCap,
  HelpCircle,
  Lightbulb,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock3,
  Film,
  Network,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActivityKind, ActivityStatus } from '@/hooks/use-activity-store';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const KIND_META: Record<ActivityKind, { label: string; icon: typeof Beaker; color: string }> = {
  research: { label: 'Recherche', icon: FileSearch, color: 'text-live' },
  quiz: { label: 'Quiz', icon: HelpCircle, color: 'text-live' },
  exercise: { label: 'Exercice', icon: Beaker, color: 'text-live' },
  evaluation: { label: 'Évaluation', icon: GraduationCap, color: 'text-success' },
  coding: { label: 'Code', icon: Code2, color: 'text-warning' },
  document: { label: 'Document', icon: BookOpen, color: 'text-live' },
  diagram: { label: 'Diagramme', icon: Network, color: 'text-live' },
  video: { label: 'Vidéo', icon: Film, color: 'text-live' },
};

const STATUS_META: Record<ActivityStatus, { label: string; icon: typeof Clock3; cls: string }> = {
  pending: { label: 'En attente', icon: Clock3, cls: 'text-muted-foreground' },
  running: { label: 'En cours', icon: Loader2, cls: 'text-live tool-pulse' },
  completed: { label: 'Terminé', icon: CheckCircle2, cls: 'text-success' },
  failed: { label: 'Échec', icon: XCircle, cls: 'text-destructive' },
};

export interface ActivityCardProps {
  kind: ActivityKind;
  title: string;
  status: ActivityStatus;
  progress?: number; // 0..100
  data?: unknown;
  onAction?: () => void;
  actionLabel?: string;
  className?: string;
}

function humanStatus(kind: ActivityKind, status: ActivityStatus): string {
  // §6 : "Thinking / Searching / Reading / Using tool / Running code / Generating exercise..."
  if (status === 'running') {
    switch (kind) {
      case 'research': return 'Recherche en cours…';
      case 'quiz': return 'Génération du quiz…';
      case 'exercise': return 'Préparation de l’exercice…';
      case 'evaluation': return 'Évaluation en cours…';
      case 'coding': return 'Exécution du code…';
      case 'document': return 'Lecture du document…';
      case 'diagram': return 'Génération du diagramme…';
      case 'video': return 'Préparation de la vidéo…';
      default: return 'Traitement en cours…';
    }
  }
  if (status === 'completed') return 'Terminé';
  if (status === 'failed') return 'Une erreur est survenue';
  return STATUS_META[status].label;
}

export function ActivityCard({
  kind,
  title,
  status,
  progress,
  onAction,
  actionLabel,
  className,
}: ActivityCardProps) {
  const km = KIND_META[kind] ?? KIND_META.exercise;
  const sm = STATUS_META[status];
  const KindIcon = km.icon;
  const StatusIcon = sm.icon;

  return (
    <Card className={cn('overflow-hidden', status === 'running' && 'border-live/30', className)}>
      <CardHeader className="flex-row items-center justify-between gap-2 py-3">
        <CardTitle className="flex items-center gap-2 text-[13px]">
          <KindIcon size={13} className={km.color} strokeWidth={1.8} />
          <span className="truncate">{title}</span>
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-muted-foreground">
            {km.label}
          </span>
        </CardTitle>
        <span className={cn('flex items-center gap-1 font-mono text-[11px]', sm.cls)}>
          <StatusIcon size={12} className={cn(status === 'running' && 'animate-spin')} />
          {humanStatus(kind, status)}
        </span>
      </CardHeader>
      {(progress !== undefined || onAction) && (
        <CardContent className="space-y-3 pt-0">
          {progress !== undefined && (
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-live transition-all duration-500"
                style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
              />
            </div>
          )}
          {onAction && status === 'completed' && (
            <button
              type="button"
              onClick={onAction}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-control)] bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Lightbulb size={12} />
              {actionLabel ?? 'Voir le résultat'}
            </button>
          )}
          {status === 'failed' && onAction && (
            <button
              type="button"
              onClick={onAction}
              className="text-xs text-destructive underline underline-offset-2 hover:text-destructive/80"
            >
              {actionLabel ?? 'Réessayer'}
            </button>
          )}
        </CardContent>
      )}
    </Card>
  );
}

// Version compacte pour le Thread (inline sous le message)
export function ActivityInline({
  kind,
  status,
  title,
}: Pick<ActivityCardProps, 'kind' | 'status' | 'title'>) {
  const km = KIND_META[kind] ?? KIND_META.exercise;
  const Icon = km.icon;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/60 px-2 py-0.5 font-mono text-[10px]">
      <Icon size={11} className={km.color} />
      <span className="text-foreground/80">{title}</span>
      <span className={cn('ml-1', STATUS_META[status].cls)}>{STATUS_META[status].label}</span>
    </span>
  );
}
