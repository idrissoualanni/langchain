// Observability Page Component
//
// Données 100% réelles : plus aucun fallback de démonstration.
// - /api/admin/observability/summary         → chiffres clés (total_runs, error_rate, latence moyenne…)
// - /api/admin/observability/models/usage    → usage par modèle (réponse ModelUsage[])
// - /api/admin/observability/errors          → journal d'erreurs (réponse ErrorEntry[]), agrégé
//                                              pour alimenter "errors by type"
// - /api/admin/observability/langsmith-link  → environnement courant
//
// Le backend signale une source indisponible soit par `available: false` (summary),
// soit par HTTP 503 + `{"available": false, "error": ...}` (listes). Dans les deux cas
// on affiche un état "Données indisponibles" + bouton Réessayer, jamais de données inventées.
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, BarChart3, Activity, AlertTriangle } from "lucide-react";
import { UsageOverview } from "./UsageOverview";
import { ModelUsageTable } from "./ModelUsageTable";
import { ErrorRateCard } from "./ErrorRateCard";
import { LatencyCard } from "./LatencyCard";
import { LangfuseLink } from "./LangfuseLink";
import { apiRequest } from "@/api/request";

/** Shape réel de GET /api/admin/observability/summary (observability.py:49). */
interface ObservabilitySummary {
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  avg_latency_ms: number;
  total_tokens: number;
  error_rate: number;
  period_hours: number;
  available: boolean;
}

/** Shape réel de GET /api/admin/observability/models/usage (observability.py:105). */
export interface ModelUsageEntry {
  model_name: string;
  provider: string | null;
  total_calls: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number | null;
  avg_latency_ms: number | null;
}

/** Shape réel de GET /api/admin/observability/errors (observability.py:118). */
export interface ErrorEntry {
  run_id: string;
  timestamp: string;
  error_type: string;
  error_message: string;
  workflow: string | null;
  node: string | null;
  stack_trace: string | null;
}

interface LangSmithLinkInfo {
  dashboard_url: string;
  project_name: string;
  environment: string;
}

/** Réponse de GET /api/health (health.py:16). */
interface HealthResponse {
  status: string;
  ollama: boolean;
  langgraph: boolean;
  sqlite: boolean;
  model: string;
}

/** Réponse de GET /api/health/model-gateway (health.py:52). */
interface ModelGatewayHealth {
  enabled: boolean;
  provider: string;
  litellm_url: string | null;
  fallback: string;
  /** Présent uniquement quand LiteLLM est activé. */
  litellm_reachable?: boolean;
}

/** Réponse de GET /api/health/langsmith (health.py:79). */
interface LangsmithHealth {
  enabled: boolean;
  configured: boolean;
  environment: string;
  endpoint: string;
  project: string;
}

/** Réponse d'indisponibilité du backend (HTTP 503). */
interface UnavailableInfo {
  available: false;
  error: string;
}

/**
 * Fetch sécurisé : retourne soit les données, soit un message d'erreur exploitable.
 * Ne lève jamais — l'appelant décide du rendu (état d'erreur vs données).
 */
async function fetchApi<T>(path: string): Promise<{ data: T | null; error: string | null }> {
  try {
    const res = await apiRequest(path);
    if (!res.ok) {
      let detail = `Erreur ${res.status} ${res.statusText}`.trim();
      try {
        const body: Partial<UnavailableInfo> = await res.json();
        if (typeof body.error === "string") detail = body.error;
      } catch {
        /* body non JSON : on garde le status */
      }
      return { data: null, error: detail };
    }
    return { data: (await res.json()) as T, error: null };
  } catch (err) {
    return {
      data: null,
      error: err instanceof Error ? err.message : "Requête échouée",
    };
  }
}

export function ObservabilityPage() {
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null);
  const [modelUsage, setModelUsage] = useState<ModelUsageEntry[]>([]);
  const [errors, setErrors] = useState<ErrorEntry[]>([]);
  const [environment, setEnvironment] = useState("development");

  // Santé système réelle (carte System Health ci-dessous).
  const [systemHealth, setSystemHealth] = useState<HealthResponse | null>(null);
  const [gatewayHealth, setGatewayHealth] = useState<ModelGatewayHealth | null>(null);
  const [langsmithHealth, setLangsmithHealth] = useState<LangsmithHealth | null>(null);

  const [loading, setLoading] = useState(true);
  // Erreur fatale : la donnée principale (summary) est indisponible.
  const [error, setError] = useState<string | null>(null);
  // Sections secondaires (usage/errors) : indisponibles mais non bloquantes.
  const [usageError, setUsageError] = useState<string | null>(null);
  const [errorsError, setErrorsError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    setUsageError(null);
    setErrorsError(null);

    const [
      summaryRes,
      usageRes,
      errorsRes,
      linkRes,
      healthRes,
      gatewayRes,
      langsmithRes,
    ] = await Promise.all([
      fetchApi<ObservabilitySummary>("/api/admin/observability/summary"),
      fetchApi<ModelUsageEntry[]>("/api/admin/observability/models/usage"),
      fetchApi<ErrorEntry[]>("/api/admin/observability/errors"),
      fetchApi<LangSmithLinkInfo>("/api/admin/observability/langsmith-link"),
      fetchApi<HealthResponse>("/api/health"),
      fetchApi<ModelGatewayHealth>("/api/health/model-gateway"),
      fetchApi<LangsmithHealth>("/api/health/langsmith"),
    ]);

    // Section principale : indisponible → état d'erreur explicite.
    if (summaryRes.error || !summaryRes.data) {
      setError(summaryRes.error ?? "Résumé indisponible");
    } else if (!summaryRes.data.available) {
      setError(
        "Les données d'observabilité sont indisponibles (LangSmith n'est pas configuré).",
      );
      setSummary(summaryRes.data);
    } else {
      setSummary(summaryRes.data);
    }

    if (usageRes.data) {
      setModelUsage(usageRes.data);
    } else {
      setModelUsage([]);
      setUsageError(usageRes.error);
    }

    if (errorsRes.data) {
      setErrors(errorsRes.data);
    } else {
      setErrors([]);
      setErrorsError(errorsRes.error);
    }

    if (linkRes.data) {
      setEnvironment(linkRes.data.environment);
    }

    // Santé système : échec d'un check = "Indisponible", jamais Operational.
    setSystemHealth(healthRes.data);
    setGatewayHealth(gatewayRes.data);
    setLangsmithHealth(langsmithRes.data);

    setLoading(false);
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading observability data...</div>;
  }

  // État d'erreur clair : aucune donnée inventée.
  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Observability</h1>
            <p className="text-muted-foreground">
              Monitor system performance, usage, and errors
            </p>
          </div>
        </div>
        <Card className="border-red-200">
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <AlertTriangle className="h-10 w-10 text-red-600" />
            <div className="space-y-1">
              <h2 className="text-xl font-semibold">Données indisponibles</h2>
              <p className="max-w-md text-sm text-muted-foreground">
                {error}
              </p>
            </div>
            <Button variant="outline" onClick={loadAll}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Réessayer
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Erreurs agrégées par type depuis le journal réel (le summary ne fournit pas errors_by_type).
  const errorsByType = errors.reduce<Record<string, number>>((acc, entry) => {
    acc[entry.error_type] = (acc[entry.error_type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Observability</h1>
          <p className="text-muted-foreground">
            Monitor system performance, usage, and errors
          </p>
        </div>
        <Button variant="outline" onClick={loadAll}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Overview Stats */}
      <UsageOverview
        totalRequests={summary?.total_runs}
        successfulRuns={summary?.successful_runs}
        failedRuns={summary?.failed_runs}
        avgLatency={summary?.avg_latency_ms}
        totalTokens={summary?.total_tokens}
        errorRate={summary?.error_rate}
      />

      {/* Detailed Cards */}
      <div className="grid gap-4 md:grid-cols-2">
        <ErrorRateCard
          totalRequests={summary?.total_runs}
          errorCount={summary?.failed_runs}
          errorRate={summary?.error_rate}
          errorsByType={errorsByType}
        />

        {/* p50/p95/p99 ne sont pas fournis par le backend : on laisse les cartes
            afficher "N/A" plutôt que des chiffres inventés. */}
        <LatencyCard
          avgLatency={summary?.avg_latency_ms}
          p50Latency={undefined}
          p95Latency={undefined}
          p99Latency={undefined}
        />
      </div>

      {/* Model Usage Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Model Usage
          </CardTitle>
        </CardHeader>
        <CardContent>
          {usageError ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <AlertTriangle className="h-6 w-6 text-yellow-600" />
              <p className="text-sm text-muted-foreground">
                Données d'utilisation indisponibles : {usageError}
              </p>
            </div>
          ) : (
            <ModelUsageTable usageData={modelUsage} />
          )}
        </CardContent>
      </Card>

      {/* Error log (source des errors_by_type ci-dessus) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Recent Errors ({errors.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {errorsError ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Journal d'erreurs indisponible : {errorsError}
            </p>
          ) : errors.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Aucune erreur récente
            </p>
          ) : (
            <div className="space-y-3">
              {errors.slice(0, 10).map((entry) => (
                <div
                  key={entry.run_id}
                  className="rounded-lg border p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-sm text-red-600">
                      {entry.error_type}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(entry.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {entry.error_message}
                  </p>
                  {(entry.workflow || entry.node) && (
                    <p className="mt-1 text-xs text-muted-foreground font-mono">
                      {[entry.workflow, entry.node].filter(Boolean).join(" / ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Intégration dashboard de tracing + santé système réelle */}
      <div className="grid gap-4 md:grid-cols-2">
        <LangfuseLink environment={environment} />

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              System Health
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {(() => {
              // Aucun statut n'est codé en dur : chaque ligne vient d'un
              // endpoint réel, et un check injoignable s'affiche "Indisponible".
              const boolRow = (label: string, ok: boolean | undefined) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <span
                    className={`text-sm font-medium ${
                      ok === undefined
                        ? "text-muted-foreground"
                        : ok
                          ? "text-green-600"
                          : "text-red-600"
                    }`}
                  >
                    {ok === undefined
                      ? "Indisponible"
                      : ok
                        ? "Operational"
                        : "Down"}
                  </span>
                </div>
              );

              // Model Gateway : LiteLLM si activé (reachable?), sinon fallback direct.
              const gatewayRow = (() => {
                let text: string;
                let className: string;
                if (!gatewayHealth) {
                  text = "Indisponible";
                  className = "text-muted-foreground";
                } else if (gatewayHealth.enabled) {
                  if (gatewayHealth.litellm_reachable === false) {
                    text = "Degraded";
                    className = "text-yellow-600";
                  } else {
                    text = "Operational (LiteLLM)";
                    className = "text-green-600";
                  }
                } else {
                  text = systemHealth?.ollama ? "Direct (Ollama)" : "Down";
                  className = systemHealth?.ollama
                    ? "text-green-600"
                    : "text-red-600";
                }
                return (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">
                      Model Gateway (LiteLLM)
                    </span>
                    <span className={`text-sm font-medium ${className}`}>
                      {text}
                    </span>
                  </div>
                );
              })();

              // LangSmith Tracing : la page consomme LangSmith, pas Langfuse.
              const langsmithRow = (() => {
                let text: string;
                let className: string;
                if (!langsmithHealth) {
                  text = "Indisponible";
                  className = "text-muted-foreground";
                } else if (!langsmithHealth.configured) {
                  text = "Not configured";
                  className = "text-red-600";
                } else if (!langsmithHealth.enabled) {
                  text = "Configured (disabled)";
                  className = "text-yellow-600";
                } else {
                  text = "Enabled";
                  className = "text-green-600";
                }
                return (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">
                      LangSmith Tracing
                    </span>
                    <span className={`text-sm font-medium ${className}`}>
                      {text}
                    </span>
                  </div>
                );
              })();

              return (
                <>
                  {gatewayRow}
                  {boolRow("Base de données", systemHealth?.sqlite)}
                  {boolRow("LangGraph", systemHealth?.langgraph)}
                  {langsmithRow}
                </>
              );
            })()}
            <div className="pt-2 border-t">
              <p className="text-xs text-muted-foreground">
                Environment: <span className="font-medium capitalize">{environment}</span>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
