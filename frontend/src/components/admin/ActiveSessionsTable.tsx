"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2 } from "lucide-react";

interface DailyStat {
  date: string;
  thread_count: number;
  user_count: number;
}

export function ActiveSessionsTable() {
  const [stats, setStats] = useState<DailyStat[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const res = await fetch("/api/admin/dashboard/activity-stats");
        if (res.ok) {
          const data = await res.json();
          setStats(data.daily_stats || []);
        }
      } catch (err) {
        console.error("Erreur chargement stats activités:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchStats();
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
