// Model Usage Table Component
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

interface ModelUsage {
  model_id: string;
  display_name?: string;
  provider: string;
  request_count: number;
  token_count: number;
  avg_latency_ms: number;
  error_count: number;
}

interface ModelUsageTableProps {
  usageData: ModelUsage[];
}

export function ModelUsageTable({ usageData }: ModelUsageTableProps) {
  const totalRequests = usageData.reduce((sum, m) => sum + m.request_count, 0);
  
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
            <TableHead className="text-right">Errors</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {usageData.map((model) => {
            const share = totalRequests > 0 
              ? ((model.request_count / totalRequests) * 100).toFixed(1) 
              : "0.0";
            
            return (
              <TableRow key={model.model_id}>
                <TableCell>
                  <div>
                    <div className="font-medium">
                      {model.display_name || model.model_id}
                    </div>
                    <div className="text-xs text-muted-foreground font-mono">
                      {model.model_id}
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{model.provider}</Badge>
                </TableCell>
                <TableCell className="text-right">
                  {model.request_count.toLocaleString()}
                </TableCell>
                <TableCell className="text-right">
                  <span className="text-sm text-muted-foreground">
                    {share}%
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  {(model.token_count / 1000).toFixed(1)}k
                </TableCell>
                <TableCell className="text-right">
                  {model.avg_latency_ms.toFixed(0)}ms
                </TableCell>
                <TableCell className="text-right">
                  <span className={model.error_count > 0 ? "text-red-600" : "text-green-600"}>
                    {model.error_count}
                  </span>
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
