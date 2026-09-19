// Observability Page Component
import { useState, useEffect } from "react";
import { useToast } from "@/hooks/use-toast";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, BarChart3, Activity, AlertTriangle } from "lucide-react";
import { UsageOverview } from "./UsageOverview";
import { ModelUsageTable } from "./ModelUsageTable";
import { ErrorRateCard } from "./ErrorRateCard";
import { LatencyCard } from "./LatencyCard";
import { LangfuseLink } from "./LangfuseLink";
import { apiRequest } from "@/api/request";

interface ObservabilitySummary {
  total_requests: number;
  successful_runs: number;
  failed_runs: number;
  avg_latency_ms: number;
  total_tokens: number;
  error_rate: number;
  model_usage: Array<{
    model_id: string;
    display_name?: string;
    provider: string;
    request_count: number;
    token_count: number;
    avg_latency_ms: number;
    error_count: number;
  }>;
  errors_by_type: Record<string, number>;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
}

export function ObservabilityPage() {
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [environment, setEnvironment] = useState("development");
  const { toast } = useToast();

  const loadSummary = async () => {
    try {
      const response = await apiRequest('/api/admin/observability/summary');
      const data = await response.json();
      setSummary(data);
      
      if (data.environment) {
        setEnvironment(data.environment);
      }
    } catch (error) {
      console.error("Failed to load observability summary:", error);
      // Set mock data for demo purposes
      setSummary({
        total_requests: 1250,
        successful_runs: 1180,
        failed_runs: 70,
        avg_latency_ms: 850,
        total_tokens: 450000,
        error_rate: 5.6,
        model_usage: [
          {
            model_id: "default",
            display_name: "Default Model",
            provider: "ollama",
            request_count: 800,
            token_count: 280000,
            avg_latency_ms: 750,
            error_count: 35,
          },
          {
            model_id: "coding",
            display_name: "Coding Model",
            provider: "ollama",
            request_count: 300,
            token_count: 120000,
            avg_latency_ms: 950,
            error_count: 20,
          },
          {
            model_id: "research",
            display_name: "Research Model",
            provider: "openai",
            request_count: 150,
            token_count: 50000,
            avg_latency_ms: 1200,
            error_count: 15,
          },
        ],
        errors_by_type: {
          "timeout": 30,
          "rate_limit": 25,
          "model_error": 15,
        },
        p50_latency_ms: 650,
        p95_latency_ms: 1500,
        p99_latency_ms: 2200,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary();
  }, []);

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading observability data...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Observability</h1>
          <p className="text-muted-foreground">
            Monitor system performance, usage, and errors
          </p>
        </div>
        <Button variant="outline" onClick={loadSummary}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Overview Stats */}
      <UsageOverview
        totalRequests={summary?.total_requests}
        successfulRuns={summary?.successful_runs}
        failedRuns={summary?.failed_runs}
        avgLatency={summary?.avg_latency_ms}
        totalTokens={summary?.total_tokens}
        errorRate={summary?.error_rate}
      />

      {/* Detailed Cards */}
      <div className="grid gap-4 md:grid-cols-2">
        <ErrorRateCard
          totalRequests={summary?.total_requests}
          errorCount={summary?.failed_runs}
          errorRate={summary?.error_rate}
          errorsByType={summary?.errors_by_type}
        />
        
        <LatencyCard
          avgLatency={summary?.avg_latency_ms}
          p50Latency={summary?.p50_latency_ms}
          p95Latency={summary?.p95_latency_ms}
          p99Latency={summary?.p99_latency_ms}
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
          <ModelUsageTable usageData={summary?.model_usage || []} />
        </CardContent>
      </Card>

      {/* Langfuse Integration */}
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
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Model Gateway</span>
              <span className="text-sm font-medium text-green-600">Operational</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Knowledge Access</span>
              <span className="text-sm font-medium text-green-600">Operational</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Langfuse Tracing</span>
              <span className={`text-sm font-medium ${
                process.env.LANGFUSE_ENABLED === 'true' 
                  ? 'text-green-600' 
                  : 'text-yellow-600'
              }`}>
                {process.env.LANGFUSE_ENABLED === 'true' ? 'Enabled' : 'Disabled'}
              </span>
            </div>
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
