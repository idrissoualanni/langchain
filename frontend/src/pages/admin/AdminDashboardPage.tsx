import { useEffect, useState } from "react";
import { MetricCard } from "@/components/admin/MetricCard";
import { ActiveSessionsTable } from "@/components/admin/ActiveSessionsTable";
import { ActivityMonitor } from "@/components/admin/ActivityMonitor";
import { SystemHealth } from "@/components/admin/SystemHealth";
import { Loader2, AlertCircle } from "lucide-react";
import { apiRequest } from "@/api/request";

interface DashboardMetrics {
  users: { total: number; active_24h: number };
  threads: { total: number; active_24h: number };
  activities: { total: number; completed: number; completion_rate: number };
  learning: { profiles: number };
}

export default function AdminDashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchMetrics() {
      try {
        const res = await apiRequest("/api/admin/dashboard/metrics");
        if (!res.ok) throw new Error("Accès refusé ou erreur serveur");
        const data = await res.json();
        setMetrics(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erreur inconnue");
      } finally {
        setLoading(false);
      }
    }
    fetchMetrics();
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-lg font-medium text-destructive">{error}</p>
        <p className="text-sm text-muted-foreground">
          Vérifiez que vous êtes connecté avec un compte administrateur.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[72rem] space-y-8 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-3xl font-bold tracking-tight">Dashboard Admin</h1>
        <p className="text-sm text-muted-foreground">
          Dernière mise à jour: {new Date().toLocaleTimeString()}
        </p>
      </div>

      {/* Cartes Métriques */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Utilisateurs Totaux"
          value={metrics?.users.total ?? 0}
          subtitle={`${metrics?.users.active_24h ?? 0} actifs (24h)`}
          trend="neutral"
        />
        <MetricCard
          title="Threads Actifs"
          value={metrics?.threads.active_24h ?? 0}
          subtitle={`Total: ${metrics?.threads.total ?? 0}`}
          trend="up"
        />
        <MetricCard
          title="Taux de Complétion"
          value={`${metrics?.activities.completion_rate ?? 0}%`}
          subtitle={`${metrics?.activities.completed ?? 0}/${metrics?.activities.total ?? 0} activités`}
          trend="up"
        />
        <MetricCard
          title="Profils Apprentissage"
          value={metrics?.learning.profiles ?? 0}
          subtitle="Profils actifs"
          trend="neutral"
        />
      </div>

      {/* Sections Principales */}
      <div className="grid gap-6 lg:grid-cols-2">
        <ActiveSessionsTable />
        <ActivityMonitor />
      </div>

      <SystemHealth />
    </div>
  );
}
