"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle, AlertTriangle, Loader2 } from "lucide-react";

interface HealthStatus {
  database: "healthy" | "degraded" | "down";
  langgraph: "healthy" | "degraded" | "down";
  livekit: "healthy" | "degraded" | "down";
  langsmith: "healthy" | "degraded" | "down";
  model_gateway: "healthy" | "degraded" | "down";
}

interface HealthResponse {
  status: string;
  ollama: boolean;
  langgraph: boolean;
  sqlite: boolean;
  model: string;
}

export function SystemHealth() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchHealth() {
      try {
        const res = await fetch("/api/health");
        if (res.ok) {
          const data = (await res.json()) as HealthResponse;
          setHealth({
            database: data.sqlite ? "healthy" : "down",
            langgraph: data.langgraph ? "healthy" : "down",
            livekit: "degraded",
            langsmith: "degraded",
            model_gateway: data.ollama ? "healthy" : "down",
          });
        }
      } catch (err) {
        console.error("Erreur chargement santé système:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchHealth();
  }, []);

  const getStatusBadge = (status: string) => {
    const statusMap = {
      healthy: { icon: CheckCircle2, color: "bg-green-500", text: "Opérationnel" },
      degraded: { icon: AlertTriangle, color: "bg-yellow-500", text: "Dégradé" },
      down: { icon: XCircle, color: "bg-red-500", text: "Hors ligne" },
    } as const;
    const cfg = statusMap[status as keyof typeof statusMap];
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
          </div>
        )}
      </CardContent>
    </Card>
  );
}
