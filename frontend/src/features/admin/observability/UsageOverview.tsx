// Usage Overview Component
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface UsageOverviewProps {
  totalRequests?: number;
  successfulRuns?: number;
  failedRuns?: number;
  avgLatency?: number;
  totalTokens?: number;
  errorRate?: number;
}

export function UsageOverview({
  totalRequests = 0,
  successfulRuns = 0,
  failedRuns = 0,
  avgLatency = 0,
  totalTokens = 0,
  errorRate = 0,
}: UsageOverviewProps) {
  const stats = [
    {
      label: "Total Requests",
      value: totalRequests.toLocaleString(),
      trend: undefined,
    },
    {
      label: "Successful Runs",
      value: successfulRuns.toLocaleString(),
      trend: "positive",
    },
    {
      label: "Failed Runs",
      value: failedRuns.toLocaleString(),
      trend: failedRuns > 0 ? "negative" : undefined,
    },
    {
      label: "Avg Latency",
      value: `${avgLatency.toFixed(0)}ms`,
      trend: undefined,
    },
    {
      label: "Total Tokens",
      value: `${(totalTokens / 1000).toFixed(1)}k`,
      trend: undefined,
    },
    {
      label: "Error Rate",
      value: `${errorRate.toFixed(2)}%`,
      trend: errorRate > 5 ? "negative" : "positive",
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {stat.label}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stat.value}</div>
            {stat.trend && (
              <p className={`text-xs ${
                stat.trend === "positive" 
                  ? "text-green-600" 
                  : stat.trend === "negative"
                  ? "text-red-600"
                  : "text-muted-foreground"
              }`}>
                {stat.trend === "positive" ? "↑" : "↓"} Good
              </p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
