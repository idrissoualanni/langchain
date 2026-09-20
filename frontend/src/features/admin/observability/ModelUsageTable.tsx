// Model Usage Table Component
//
// Affiche la réponse brute de GET /api/admin/observability/models/usage :
// model_name / provider / total_calls / total_tokens / avg_latency_ms…
// (anciennement typée avec des champs inexistants comme model_id ou error_count).
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { ModelUsageEntry } from "./ObservabilityPage";

interface ModelUsageTableProps {
  usageData: ModelUsageEntry[];
}

export function ModelUsageTable({ usageData }: ModelUsageTableProps) {
  const totalRequests = usageData.reduce((sum, m) => sum + m.total_calls, 0);

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Model</TableHead>
            <TableHead>Provider</TableHead>
            <TableHead className="text-right">Requests</TableHead>
            <TableHead className="text-right">Share</TableHead>
            <TableHead className="text-right">Tokens</TableHead>
            <TableHead className="text-right">Avg Latency</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {usageData.map((model) => {
            const share = totalRequests > 0
              ? ((model.total_calls / totalRequests) * 100).toFixed(1)
              : "0.0";

            return (
              <TableRow key={model.model_name}>
                <TableCell>
                  <div>
                    <div className="font-medium">
                      {model.model_name}
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  {model.provider ? (
                    <Badge variant="outline">{model.provider}</Badge>
                  ) : (
                    <span className="text-sm text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  {model.total_calls.toLocaleString()}
                </TableCell>
                <TableCell className="text-right">
                  <span className="text-sm text-muted-foreground">
                    {share}%
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  {(model.total_tokens / 1000).toFixed(1)}k
                </TableCell>
                <TableCell className="text-right">
                  {model.avg_latency_ms != null
                    ? `${model.avg_latency_ms.toFixed(0)}ms`
                    : <span className="text-muted-foreground">N/A</span>}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {usageData.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          No usage data available
        </div>
      )}
    </div>
  );
}
