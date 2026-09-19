"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Loader2 } from "lucide-react";

interface ActivityStats {
  total: number;
  completed: number;
  in_progress: number;
  failed: number;
  completion_rate: number;
}

export function ActivityMonitor() {
  const [stats, setStats] = useState<ActivityStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const res = await fetch("/api/admin/dashboard/activity-stats");
        if (res.ok) {
          const data = await res.json();
          setStats({
            total: data.activities?.total || 0,
            completed: data.activities?.completed || 0,
            in_progress: 0,
            failed: 0,
            completion_rate: data.activities?.completion_rate || 0,
          });
        }
      } catch (err) {
        console.error("Erreur chargement activités:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchStats();
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Suivi des Activités</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : !stats ? (
          <p className="text-center text-muted-foreground">Aucune donnée disponible</p>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-sm text-muted-foreground">Total</p>
                <p className="text-2xl font-bold">{stats.total}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Complétées</p>
                <p className="text-2xl font-bold text-green-600">{stats.completed}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Taux</p>
                <p className="text-2xl font-bold text-blue-600">{stats.completion_rate}%</p>
              </div>
            </div>
            
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Progression globale</span>
                <span>{stats.completion_rate}%</span>
              </div>
              <Progress value={stats.completion_rate} className="h-2" />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
