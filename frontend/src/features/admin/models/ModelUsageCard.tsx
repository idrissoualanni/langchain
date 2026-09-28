// Model Usage Card Component
//
// Affiche l'usage RÉEL d'un modèle depuis
// GET /api/admin/observability/models/usage (réponse : model_name, provider,
// total_calls, total_tokens, avg_latency_ms…). Aucune donnée inventée : tant que
// l'endpoint n'a rien renvoyé pour ce modèle, on affiche "—" / "N/A".
//
// Note : le taux d'erreur par modèle n'est PAS fourni par l'endpoint — la carte
// affiche "N/A" plutôt qu'un "0.0%" trompeur.
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { apiRequest } from "@/api/request";

interface ModelUsageCardProps {
  modelId: string;
  displayName: string;
  provider: string;
}

interface UsageEntry {
  model_name: string;
  provider: string | null;
  total_calls: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number | null;
  avg_latency_ms: number | null;
}

export function ModelUsageCard({
  modelId,
  displayName,
  provider,
}: ModelUsageCardProps) {
  const [usage, setUsage] = useState<UsageEntry | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadUsage() {
      try {
        const res = await apiRequest("/api/admin/observability/models/usage?days=30");
        if (!res.ok) {
          if (!cancelled) setUnavailable(true);
          return;
        }
        const entries: UsageEntry[] = await res.json();
        // L'usage remonte par nom de modèle : égalité stricte uniquement.
        // Pas de .includes() : un id comme 'gpt-4' matcherait abusivement 'gpt-4o'.
        const candidates = [modelId, displayName];
        const match = entries.find((entry) =>
          candidates.includes(entry.model_name),
        );
        if (!cancelled) setUsage(match ?? null);
      } catch {
        if (!cancelled) setUnavailable(true);
      }
    }

    loadUsage();
    return () => {
      cancelled = true;
    };
  }, [modelId, displayName]);

  const requests = usage?.total_calls;
  const tokens = usage?.total_tokens;
  const avgLatency = usage?.avg_latency_ms;

  const renderRequests = requests != null ? requests.toLocaleString() : "—";
  const renderTokens = tokens != null ? `${(tokens / 1000).toFixed(1)}k` : "—";
  const renderLatency = avgLatency != null ? `${avgLatency.toFixed(0)}ms` : "N/A";

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{displayName || modelId}</span>
          <Badge variant="outline">{provider}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {unavailable ? (
          <p className="text-sm text-muted-foreground">
            Données d'usage indisponibles
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Requests</p>
              <p className="text-2xl font-bold">{renderRequests}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Tokens</p>
              <p className="text-2xl font-bold">{renderTokens}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Avg Latency</p>
              <p className="text-2xl font-bold">{renderLatency}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Error Rate</p>
              <p className="text-2xl font-bold text-muted-foreground">N/A</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
