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
  avgLatency = 0,
  p50Latency = 0,
  p95Latency = 0,
  p99Latency = 0,
}: LatencyCardProps) {
  const getLatencyStatus = (latency: number) => {
    if (latency < 500) return { color: "text-green-600", status: "Excellent" };
    if (latency < 1000) return { color: "text-yellow-600", status: "Good" };
    if (latency < 2000) return { color: "text-orange-600", status: "Fair" };
    return { color: "text-red-600", status: "Poor" };
  };

  const status = getLatencyStatus(avgLatency);

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
              {avgLatency.toFixed(0)}ms
            </span>
            <span className="text-sm text-muted-foreground">
              {status.status}
            </span>
          </div>
          
          <div className="grid grid-cols-3 gap-2 pt-2">
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-xs text-muted-foreground">P50</div>
              <div className="font-semibold">{p50Latency.toFixed(0)}ms</div>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-xs text-muted-foreground">P95</div>
              <div className="font-semibold">{p95Latency.toFixed(0)}ms</div>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-xs text-muted-foreground">P99</div>
              <div className="font-semibold">{p99Latency.toFixed(0)}ms</div>
            </div>
          </div>
        </div>
        
        <div className="text-xs text-muted-foreground space-y-1">
          <div className="flex justify-between">
            <span>P50 (Median):</span>
            <span>{((p50Latency / avgLatency) * 100 || 0).toFixed(0)}% of avg</span>
          </div>
          <div className="flex justify-between">
            <span>P95:</span>
            <span>{((p95Latency / avgLatency) * 100 || 0).toFixed(0)}% of avg</span>
          </div>
          <div className="flex justify-between">
            <span>P99:</span>
            <span>{((p99Latency / avgLatency) * 100 || 0).toFixed(0)}% of avg</span>
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
