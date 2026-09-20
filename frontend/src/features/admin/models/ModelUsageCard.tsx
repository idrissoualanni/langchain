// Model Usage Card Component
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ModelUsageCardProps {
  modelId: string;
  displayName: string;
  provider: string;
  requestCount?: number;
  tokenCount?: number;
  avgLatency?: number;
  errorRate?: number;
}

export function ModelUsageCard({ 
  modelId, 
  displayName, 
  provider,
  requestCount = 0,
  tokenCount = 0,
  avgLatency = 0,
  errorRate = 0
}: ModelUsageCardProps) {
  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{displayName || modelId}</span>
          <Badge variant="outline">{provider}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">Requests</p>
            <p className="text-2xl font-bold">{requestCount.toLocaleString()}</p>
          </div>
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">Tokens</p>
            <p className="text-2xl font-bold">{(tokenCount / 1000).toFixed(1)}k</p>
          </div>
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">Avg Latency</p>
            <p className="text-2xl font-bold">{avgLatency.toFixed(0)}ms</p>
          </div>
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">Error Rate</p>
            <p className={`text-2xl font-bold ${errorRate > 5 ? 'text-red-600' : 'text-green-600'}`}>
              {errorRate.toFixed(1)}%
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
