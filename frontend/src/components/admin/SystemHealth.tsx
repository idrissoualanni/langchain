"use client";

// Santé du système — statuts RÉELS uniquement.
//
// - Base de données / LangGraph / Model Gateway : GET /api/health
// - LangSmith : GET /api/health/langsmith → {enabled, configured, environment, …}
// - LiveKit : aucun endpoint de santé n'existe → on affiche honnêtement
//   "Non monitoré" au lieu d'un "Dégradé" codé en dur (faux).
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle, AlertTriangle, Loader2, Minus } from "lucide-react";
import { apiRequest } from "@/api/request";

type HealthValue = "healthy" | "degraded" | "down" | "unknown";

interface HealthStatus {
  database: HealthValue;
  langgraph: HealthValue;
  livekit: HealthValue;
  langsmith: HealthValue;
  model_gateway: HealthValue;
}

interface HealthResponse {
  status: string;
  ollama: boolean;
  langgraph: boolean;
  sqlite: boolean;
  model: string;
}

interface LangsmithHealth {
  enabled: boolean;
  configured: boolean;
  environment: string;
  endpoint: string;
  project: string;
}

export function SystemHealth() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchHealth() {
      try {
        // Santé principale (SQLite, Ollama, LangGraph).
        const res = await apiRequest("/api/health");
        const data = (await res.json()) as HealthResponse;

        // Santé LangSmith : statut réel selon la configuration.
        let langsmith: HealthValue = "down";
        try {
          const lsRes = await apiRequest("/api/health/langsmith");
          if (lsRes.ok) {
            const ls = (await lsRes.json()) as LangsmithHealth;
            // Configuré + activé → opérationnel ; configuré mais désactivé → dégradé ;
            // non configuré → indisponible.
            langsmith = ls.configured
              ? ls.enabled
                ? "healthy"
                : "degraded"
              : "down";
          }
        } catch (err) {
          console.error("Erreur chargement santé LangSmith:", err);
        }

        setHealth({
          database: data.sqlite ? "healthy" : "down",
          langgraph: data.langgraph ? "healthy" : "down",
          livekit: "unknown", // Aucun endpoint de santé LiveKit : "non monitoré" (honnête)
          langsmith,
          model_gateway: data.ollama ? "healthy" : "down",
        });
      } catch (err) {
        console.error("Erreur chargement santé système:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchHealth();
  }, []);

  const getStatusBadge = (status: HealthValue) => {
    const statusMap = {
      healthy: { icon: CheckCircle2, color: "bg-green-500", text: "Opérationnel" },
      degraded: { icon: AlertTriangle, color: "bg-yellow-500", text: "Dégradé" },
      down: { icon: XCircle, color: "bg-red-500", text: "Hors ligne" },
      unknown: { icon: Minus, color: "bg-gray-400", text: "Non monitoré" },
    } as const;
    const cfg = statusMap[status];
    const Icon = cfg.icon;
    return (
      <Badge variant="secondary" className={`${cfg.color} text-white`}>
        <Icon className="h-3 w-3 mr-1" />
        {cfg.text}
      </Badge>
    );
  };

  const systems = [
    { name: "Base de données", key: "database" as keyof HealthStatus },
    { name: "LangGraph", key: "langgraph" as keyof HealthStatus },
    { name: "LiveKit (Voix/Vidéo)", key: "livekit" as keyof HealthStatus },
    { name: "LangSmith (Monitoring)", key: "langsmith" as keyof HealthStatus },
    { name: "Model Gateway (LiteLLM)", key: "model_gateway" as keyof HealthStatus },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Santé du Système</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : !health ? (
          <p className="text-center text-muted-foreground">Données indisponibles</p>
        ) : (
          <div className="space-y-4">
            {systems.map((system) => (
              <div key={system.name} className="flex items-center justify-between p-3 border rounded-lg">
                <span className="font-medium">{system.name}</span>
                {getStatusBadge(health[system.key])}
              </div>
            ))}
            <p className="text-xs text-muted-foreground">
              LiveKit n'expose pas d'endpoint de santé : son statut ne peut pas être
              vérifié depuis cette interface.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
