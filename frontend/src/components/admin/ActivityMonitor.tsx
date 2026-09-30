"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Loader2 } from "lucide-react";
// Auth : cet écran est sous AdminGate mais interroge un endpoint
// protégé → un `fetch` nu partait sans Authorization et revenait 401,
// l'UI tombait dans « Aucune donnée disponible » sans jamais dire
// pourquoi. apiFetchRaw injecte le jeton et rejoue après un refresh
// si le 401 venait d'un JWT expiré.
import { apiFetchRaw } from "@/api/base";

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
  // EF-18 : distinguer « aucune activité » de « je n'ai pas pu
  // l'obtenir ». Avant, un simple `if (res.ok)` sans branche `else`
  // faisait atterrir l'écran silencieusement dans « Aucune donnée
  // disponible » dès que la requête échouait : un problème
  // d'authentification se lisait comme une journée vide, sans le
  // moindre indice sur sa cause.
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // `alive` : le composant peut être démonté pendant la requête
    // ( navigation admin → autre page ). Sans ce garde-fou, la réponse
    // tardive tenterait d'écrire dans l'état d'un composant mort.
    let alive = true;
    async function fetchStats() {
      try {
        const res = await apiFetchRaw("/api/admin/dashboard/activity-stats");
        if (!res.ok) {
          // 401/403 = session ou droits : message explicite, sinon
          // l'admin cherche une panne de données qui n'existe pas.
          throw new Error(
            res.status === 401 || res.status === 403
              ? "Session non autorisée pour cette donnée (erreur " + res.status + ")."
              : "Le serveur n'a pas pu renvoyer les statistiques (erreur " + res.status + ")."
          );
        }
        const data = await res.json();
        if (!alive) return;
        setStats({
          total: data.activities?.total || 0,
          completed: data.activities?.completed || 0,
          in_progress: 0,
          failed: 0,
          completion_rate: data.activities?.completion_rate || 0,
        });
      } catch (err) {
        console.error("Erreur chargement activités:", err);
        if (alive) {
          setStats(null);
          setError(
            err instanceof Error
              ? err.message
              : "Impossible de charger les activités."
          );
        }
      } finally {
        if (alive) setLoading(false);
      }
    }
    fetchStats();
    return () => {
      alive = false;
    };
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
        ) : error ? (
          <p className="text-center text-destructive py-6 text-sm">{error}</p>
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
