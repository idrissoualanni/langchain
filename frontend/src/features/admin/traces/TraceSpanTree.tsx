// TraceSpanTree — arbre de spans d'une trace LangSmith (debugging).
import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import type { TraceSpan } from './tracesApi';

function statusTone(status?: string | null): 'success' | 'error' | 'warning' | 'default' {
  if (status === 'success') return 'success';
  if (status === 'error') return 'error';
  if (status === 'pending' || status === 'in_progress') return 'warning';
  return 'default';
}

function typeTone(runType: string): 'accent' | 'secondary' | 'outline' | 'default' {
  if (runType === 'llm') return 'accent';
  if (runType === 'chain') return 'secondary';
  if (runType === 'tool') return 'outline';
  return 'default';
}

function fmtLatency(ms?: number | null): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1) return `${Math.round(ms * 1000)}µs`;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function fmtTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString('fr-FR', { hour12: false }) + ' ' + d.toLocaleDateString('fr-FR');
}

function JsonBlock({ title, data }: { title: string; data: Record<string, unknown> }) {
  const entries = Object.entries(data ?? {});
  if (entries.length === 0) return null;
  return (
    <div className="space-y-1">
      <div className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
        {title}
      </div>
      <pre className="bg-muted/40 max-h-64 overflow-auto rounded-md p-2 font-mono text-[11px] whitespace-pre-wrap break-words">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

function SpanNode({
  span,
  depth,
  expandedIds,
  toggle,
  defaultExpanded = false,
}: {
  span: TraceSpan;
  depth: number;
  expandedIds: ReadonlySet<string>;
  toggle: (id: string) => void;
  defaultExpanded?: boolean;
}) {
  const hasChildren = span.child_runs.length > 0;
  const isOpen = expandedIds.has(span.run_id);
  const hasError = !!span.error;
  const showDetails = isOpen || (!hasChildren && defaultExpanded);

  return (
    <div>
      <div
        className={cn(
          'group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50',
          depth === 0 && 'bg-muted/30 font-medium'
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => hasChildren && toggle(span.run_id)}
      >
        {hasChildren ? (
          <ChevronRight
            size={14}
            className={cn(
              'text-muted-foreground shrink-0 transition-transform',
              isOpen && 'rotate-90'
            )}
          />
        ) : (
          <span className="w-[14px] shrink-0" />
        )}
        <span className="text-muted-foreground font-mono text-[10px]">
          {span.run_type}
        </span>
        <span className="truncate font-medium">{span.name || span.run_id}</span>
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          <span className="text-muted-foreground font-mono text-[11px]">
            {fmtLatency(span.latency_ms)}
          </span>
          <Badge tone={statusTone(span.status)} className="capitalize">
            {span.status ?? 'unknown'}
          </Badge>
          <Badge variant={typeTone(span.run_type)}>{span.run_type}</Badge>
        </span>
      </div>

      {hasError && (
        <div
          className="border-destructive/30 bg-destructive/5 text-destructive ml-[30px] mt-1 rounded-md border p-2 text-xs break-words"
          style={{ marginLeft: `${depth * 16 + 30}px` }}
        >
          <span className="font-semibold">Erreur :</span> {span.error}
        </div>
      )}

      {showDetails && (
        <div
          className="border-border ml-6 space-y-2 border-l px-3 py-2"
          style={{ marginLeft: `${depth * 16 + 22}px` }}
        >
          <JsonBlock title="inputs" data={span.inputs} />
          <JsonBlock title="outputs" data={span.outputs} />
          <JsonBlock title="metadata" data={span.metadata} />
          {span.feedback && <JsonBlock title="feedback" data={span.feedback} />}
        </div>
      )}

      {isOpen && hasChildren && (
        <div>
          {span.child_runs.map((child) => (
            <SpanNode
              key={child.run_id}
              span={child}
              depth={depth + 1}
              expandedIds={expandedIds}
              toggle={toggle}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function TraceSpanTree({ root }: { root: TraceSpan }) {
  const [expandedIds, setExpandedIds] = useState<ReadonlySet<string>>(() => new Set([root.run_id]));

  const toggle = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => {
    const ids = new Set<string>();
    const walk = (s: TraceSpan) => {
      ids.add(s.run_id);
      s.child_runs.forEach(walk);
    };
    walk(root);
    setExpandedIds(ids);
  };

  const collapseAll = () => setExpandedIds(new Set());

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-muted-foreground font-mono text-[10px] tracking-[0.1em] uppercase">
          trace · {fmtTime(root.start_time)}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={expandAll}
            className="text-muted-foreground hover:text-foreground text-xs"
          >
            Tout déplier
          </button>
          <button
            type="button"
            onClick={collapseAll}
            className="text-muted-foreground hover:text-foreground text-xs"
          >
            Replier
          </button>
        </div>
      </div>
      <div className="border-border overflow-auto rounded-lg border bg-background/40 p-2">
        <SpanNode span={root} depth={0} expandedIds={expandedIds} toggle={toggle} defaultExpanded />
      </div>
    </div>
  );
}