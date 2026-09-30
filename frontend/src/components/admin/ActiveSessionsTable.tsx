"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2 } from "lucide-react";
// Même endpoint protégé que ActivityMonitor, même raison : un `fetch`
// nu ne pose pas d'Authorization → 401 → le tableau se vidait
// (« Aucune donnée »), indistinguishable d'une journée réellement
// vide. apiFetchRaw passe par la couche auth centrale.
import { apiFetchRaw } from "@/api/base";

interface DailyStat {
  date: string;
  thread_count: number;
  user_count: number;
}

export function ActiveSessionsTable() {
  const [stats, setStats] = useState<DailyStat[]>([]);
  const [loading, setLoading] = useState(true);
  // EF-18 : même raison que dans ActivityMonitor — un échec ( dont un
  // 401 faute d'en-tête d'authentification ) ne doit PAS se lire comme
  // « aucune session active aujourd'hui », qui est une affirmation
  // métier. On remonte l'erreur et on laisse `stats` vide.
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // `alive` : même garde-fou que dans ActivityMonitor — la réponse
    // ne doit pas écrire dans l'état d'un composant démonté.
    let alive = true;
    async function fetchStats() {
      try {
        const res = await apiFetchRaw("/api/admin/dashboard/activity-stats");
        if (!res.ok) {
          // 401/403 = session ou droits ; autre chose = panne serveur.
          throw new Error(
            res.status === 401 || res.status === 403
              ? "Session non autorisée pour cette donnée (erreur " + res.status + ")."
              : "Le serveur n'a pas pu renvoyer l'activité (erreur " + res.status + ")."
          );
        }
        const data = await res.json();
        if (!alive) return;
        setStats(data.daily_stats || []);
      } catch (err) {
        console.error("Erreur chargement stats activités:", err);
        if (alive) {
          setStats([]);
          setError(
            err instanceof Error
              ? err.message
              : "Impossible de charger l'activité."
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
        <CardTitle>Activité par jour (14 jours)</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <p className="text-center text-destructive py-8 text-sm">{error}</p>
        ) : stats.length === 0 ? (
          <p className="text-center text-muted-foreground py-8">Aucune donnée</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Threads</TableHead>
                <TableHead>Utilisateurs</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stats.slice(0, 14).map((stat) => (
                <TableRow key={stat.date}>
                  <TableCell className="font-mono text-xs">{stat.date}</TableCell>
                  <TableCell>{stat.thread_count}</TableCell>
                  <TableCell>{stat.user_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
