// TracesPage — debugging & suivi des traces via le SDK LangSmith.
import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, BarChart3, ExternalLink, Loader2, RefreshCw, Search } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import {
  fetchErrors,
  fetchModelUsage,
  fetchRunDetail,
  fetchRuns,
  type ModelUsage,
  type TraceError,
  type TraceRun,
  type TraceSpan,
} from './tracesApi';
import { TraceSpanTree } from './TraceSpanTree';

function fmtTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString('fr-FR', { hour12: false }) + ' ' + d.toLocaleDateString('fr-FR');
}

function fmtLatency(ms?: number | null): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function statusTone(status: string): 'success' | 'error' | 'warning' | 'default' {
  if (status === 'success') return 'success';
  if (status === 'error') return 'error';
  if (status === 'pending') return 'warning';
  return 'default';
}

export function TracesPage() {
  const [runs, setRuns] = useState<TraceRun[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [status, setStatus] = useState<'all' | 'success' | 'error'>('all');
  const [limit, setLimit] = useState(50);
  const [selected, setSelected] = useState<TraceRun | null>(null);
  const [detail, setDetail] = useState<TraceSpan | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [errors, setErrors] = useState<TraceError[]>([]);
  const [usage, setUsage] = useState<ModelUsage[]>([]);
  const [pageError, setPageError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoadingList(true);
    setPageError(null);
    try {
      setRuns(await fetchRuns({ limit, status }));
    } catch (e) {
      setPageError(e instanceof Error ? e.message : 'Erreur en chargeant les runs');
    } finally {
      setLoadingList(false);
    }
  }, [limit, status]);

  const loadDetail = useCallback(async (run: TraceRun) => {
    setSelected(run);
    setDetail(null);
    setDetailError(null);
    setLoadingDetail(true);
    try {
      setDetail(await fetchRunDetail(run.run_id));
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "Erreur en chargeant la trace");
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const loadSide = useCallback(async () => {
    try {
      const [errs, usg] = await Promise.all([fetchErrors(25), fetchModelUsage(7)]);
      setErrors(errs);
      setUsage(usg);
    } catch {
      /* sections non bloquantes */
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    loadSide();
  }, [loadSide]);

  return (
    <div className="space-y-6 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold">Traces LangSmith</h1>
          <p className="text-muted-foreground text-sm">
            Debugging et suivi des exécutions de l'agent (SDK LangSmith)
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as 'all' | 'success' | 'error')}
            className="border-input bg-background h-9 rounded-md border px-3 text-sm"
            title="Filtrer par statut"
          >
            <option value="all">Tous les statuts</option>
            <option value="success">Succès</option>
            <option value="error">Erreurs</option>
          </select>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="border-input bg-background h-9 rounded-md border px-3 text-sm"
            title="Nombre d'exécutions"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
          <Button variant="outline" onClick={loadList} disabled={loadingList}>
            <RefreshCw className={cn('mr-2 h-4 w-4', loadingList && 'animate-spin')} />
            Rafraîchir
          </Button>
          <Button variant="outline" asChild>
            <a href="https://smith.langchain.com" target="_blank" rel="noreferrer">
              <ExternalLink className="mr-2 h-4 w-4" />
              LangSmith
            </a>
          </Button>
        </div>
      </div>

      {pageError && (
        <div className="border-destructive/30 bg-destructive/10 text-destructive rounded-lg border p-3 text-sm">
          {pageError}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {/* Liste des runs */}
        <Card className="min-h-[300px]">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Search className="h-4 w-4" />
              Exécutions ({runs.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-[620px] overflow-auto">
            {loadingList ? (
              <div className="flex h-40 items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : runs.length === 0 ? (
              <div className="text-muted-foreground py-10 text-center text-sm">
                Aucune exécution trouvée.
              </div>
            ) : (
              <ul className="space-y-1">
                {runs.map((run) => (
                  <li key={run.run_id}>
                    <button
                      type="button"
                      onClick={() => loadDetail(run)}
                      className={cn(
                        'hover:bg-muted/50 w-full rounded-md px-3 py-2 text-left transition-colors',
                        selected?.run_id === run.run_id && 'bg-muted/60 ring-1 ring-border'
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <Badge tone={statusTone(run.status)} className="capitalize">
                          {run.status}
                        </Badge>
                        <span className="truncate font-medium">
                          {run.name || run.run_id.slice(0, 12)}
                        </span>
                        <span className="text-muted-foreground ml-auto shrink-0 font-mono text-[11px]">
                          {fmtLatency(run.latency_ms)}
                        </span>
                      </div>
                      <div className="text-muted-foreground mt-1 flex items-center gap-2 text-[11px]">
                        <span className="font-mono">{run.run_id.slice(0, 13)}…</span>
                        <span>{fmtTime(run.start_time)}</span>
                        {run.workflow && <span>· {run.workflow}</span>}
                        {run.error_message && (
                          <span className="text-destructive truncate italic">
                            · {run.error_message.slice(0, 80)}
                          </span>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Détail d'une trace */}
        <Card className="min-h-[300px]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              {selected ? (
                <span className="flex items-center gap-2">
                  Détail de la trace
                  <span className="text-muted-foreground truncate font-mono text-xs">
                    {selected.run_id}
                  </span>
                </span>
              ) : (
                'Détail de la trace'
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!selected ? (
              <div className="text-muted-foreground py-16 text-center text-sm">
                Sélectionnez une exécution pour inspecter sa trace (spans, inputs, outputs, erreurs).
              </div>
            ) : loadingDetail ? (
              <div className="flex h-40 items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : detailError ? (
              <div className="border-destructive/30 bg-destructive/10 text-destructive rounded-lg border p-3 text-sm">
                {detailError}
              </div>
            ) : detail ? (
              <TraceSpanTree root={detail} />
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Erreurs */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <AlertTriangle className="h-4 w-4" />
              Erreurs récentes ({errors.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-[320px] overflow-auto">
            {errors.length === 0 ? (
              <div className="text-muted-foreground py-8 text-center text-sm">
                Aucune erreur enregistrée.
              </div>
            ) : (
              <ul className="space-y-2">
                {errors.map((err) => (
                  <li key={err.run_id} className="border-border rounded-md border p-2 text-xs">
                    <div className="flex items-center gap-2">
                      <Badge tone="error">{err.error_type || 'error'}</Badge>
                      <span className="text-muted-foreground">{fmtTime(err.timestamp)}</span>
                      {err.node && <span className="font-mono">{err.node}</span>}
                    </div>
                    <div className="text-destructive mt-1 break-words">{err.error_message}</div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Usage par modèle */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <BarChart3 className="h-4 w-4" />
              Usage par modèle (7 jours)
            </CardTitle>
          </CardHeader>
          <CardContent className="max-h-[320px] overflow-auto">
            {usage.length === 0 ? (
              <div className="text-muted-foreground py-8 text-center text-sm">
                Aucune donnée d'usage.
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground border-b text-left text-xs">
                    <th className="pb-2 font-medium">Modèle</th>
                    <th className="pb-2 font-medium">Provider</th>
                    <th className="pb-2 text-right font-medium">Appels</th>
                    <th className="pb-2 text-right font-medium">Tokens</th>
                    <th className="pb-2 text-right font-medium">Latence moy.</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.map((m) => (
                    <tr key={m.model_name} className="border-b last:border-0">
                      <td className="py-1.5 font-medium">{m.model_name}</td>
                      <td className="text-muted-foreground py-1.5">
                        {m.provider ?? '—'}
                      </td>
                      <td className="py-1.5 text-right font-mono">{m.total_calls}</td>
                      <td className="py-1.5 text-right font-mono">
                        {m.total_tokens.toLocaleString('fr-FR')}
                      </td>
                      <td className="py-1.5 text-right font-mono">
                        {fmtLatency(m.avg_latency_ms)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}