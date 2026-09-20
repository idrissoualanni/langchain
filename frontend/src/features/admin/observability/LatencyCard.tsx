// Latency Card Component
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Clock } from "lucide-react";

interface LatencyCardProps {
  avgLatency?: number;
  p50Latency?: number;
  p95Latency?: number;
  p99Latency?: number;
}

export function LatencyCard({
  avgLatency,
  p50Latency,
  p95Latency,
  p99Latency,
}: LatencyCardProps) {
  const getLatencyStatus = (latency: number) => {
    if (latency < 500) return { color: "text-green-600", status: "Excellent" };
    if (latency < 1000) return { color: "text-yellow-600", status: "Good" };
    if (latency < 2000) return { color: "text-orange-600", status: "Fair" };
    return { color: "text-red-600", status: "Poor" };
  };

  // Sans mesure (avgLatency indéfini) on garde un état neutre : on ne affiche
  // pas "Excellent" pour une latence nulle qui n'existe pas.
  const status =
    avgLatency == null
      ? { color: "text-muted-foreground", status: "N/A" }
      : getLatencyStatus(avgLatency);

  // Les percentiles ne sont pas fournis par le backend : on affiche "N/A"
  // plutôt que des zéros trompeux (0ms de latency P95 n'existe pas).
  const formatMs = (value?: number): string =>
    value != null ? `${value.toFixed(0)}ms` : "N/A";
  const pctOfAvg = (value?: number): string =>
    value != null && (avgLatency ?? 0) > 0
      ? `${((value / avgLatency!) * 100).toFixed(0)}% of avg`
      : "N/A";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Latency</CardTitle>
        <Clock className={`h-4 w-4 ${status.color}`} />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <span className={`text-3xl font-bold ${status.color}`}>
              {formatMs(avgLatency)}
            </span>
            <span className="text-sm text-muted-foreground">
              {status.status}
            </span>
          </div>
          
          <div className="grid grid-cols-3 gap-2 pt-2">
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-xs text-muted-foreground">P50</div>
              <div className="font-semibold">{formatMs(p50Latency)}</div>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-xs text-muted-foreground">P95</div>
              <div className="font-semibold">{formatMs(p95Latency)}</div>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-xs text-muted-foreground">P99</div>
              <div className="font-semibold">{formatMs(p99Latency)}</div>
            </div>
          </div>
        </div>
        
        <div className="text-xs text-muted-foreground space-y-1">
          <div className="flex justify-between">
            <span>P50 (Median):</span>
            <span>{pctOfAvg(p50Latency)}</span>
          </div>
          <div className="flex justify-between">
            <span>P95:</span>
            <span>{pctOfAvg(p95Latency)}</span>
          </div>
          <div className="flex justify-between">
            <span>P99:</span>
            <span>{pctOfAvg(p99Latency)}</span>
          </div>
        </div>
        
        <div className="pt-2 border-t">
          <p className="text-xs text-muted-foreground">
            Target: &lt; 1000ms average latency
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
