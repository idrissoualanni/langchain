"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2 } from "lucide-react";

interface Session {
  id: string;
  user_id: string;
  created_at: string;
  last_message_at: string;
  message_count: number;
}

export function ActiveSessionsTable() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchSessions() {
      try {
        const res = await fetch("/api/admin/dashboard/active-sessions");
        if (res.ok) {
          const data = await res.json();
          setSessions(data.sessions || []);
        }
      } catch (err) {
        console.error("Erreur chargement sessions:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchSessions();
  }, []);

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle>Sessions Actives (24h)</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : sessions.length === 0 ? (
          <p className="text-center text-muted-foreground py-8">Aucune session active</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID Session</TableHead>
                <TableHead>Utilisateur</TableHead>
                <TableHead>Messages</TableHead>
                <TableHead>Dernière activité</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sessions.slice(0, 10).map((session) => (
                <TableRow key={session.id}>
                  <TableCell className="font-mono text-xs">{session.id.slice(0, 8)}...</TableCell>
                  <TableCell>{session.user_id.slice(0, 12)}...</TableCell>
                  <TableCell>{session.message_count}</TableCell>
                  <TableCell>{new Date(session.last_message_at).toLocaleTimeString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
