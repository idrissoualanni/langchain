// SubjectValidationPanel — validation admin des matières ( statut + auteur ).
//
// Le statut pilote le GATING : seul `validated` rend la matière visible de
// l'agent. Ce panneau liste TOUTES les matières ( y compris non validées )
// et permet de changer statut/auteur via PATCH /api/admin/subjects/{id}/status.
'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ShieldCheck, RefreshCw } from 'lucide-react';
import { apiRequest } from '@/api/request';

const STATUSES = ['draft', 'review', 'validated', 'archived'] as const;

interface SubjectMeta {
  subject_id: string;
  name: string;
  valid: boolean;
  status: string;
  author: string;
}

export function SubjectValidationPanel() {
  const [subjects, setSubjects] = useState<SubjectMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [edits, setEdits] = useState<Record<string, { status: string; author: string }>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiRequest('/api/admin/subjects');
      const data = await res.json();
      setSubjects(data.subjects || []);
    } catch {
      setSubjects([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const current = (s: SubjectMeta) =>
    edits[s.subject_id] ?? { status: s.status, author: s.author };

  const setField = (id: string, field: 'status' | 'author', value: string) => {
    setEdits((prev) => ({
      ...prev,
      [id]: { ...(prev[id] ?? { status: '', author: '' }), [field]: value },
    }));
  };

  const save = async (s: SubjectMeta) => {
    const c = current(s);
    const res = await apiRequest(`/api/admin/subjects/${s.subject_id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: c.status, author: c.author }),
    });
    if (res.ok) load();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            Validation des matières ({subjects.length})
          </span>
          <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : subjects.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucune matière.</p>
        ) : (
          <div className="space-y-2">
            {subjects.map((s) => {
              const c = current(s);
              return (
                <div
                  key={s.subject_id}
                  className="flex flex-wrap items-center gap-2 rounded border p-2"
                >
                  <span className="min-w-[8rem] font-medium">{s.name}</span>
                  <Badge
                    variant={c.status === 'validated' ? 'default' : 'secondary'}
                  >
                    {c.status}
                  </Badge>
                  <select
                    className="rounded border bg-background px-2 py-1 text-sm"
                    value={c.status}
                    onChange={(e) => setField(s.subject_id, 'status', e.target.value)}
                  >
                    {STATUSES.map((st) => (
                      <option key={st} value={st}>
                        {st}
                      </option>
                    ))}
                  </select>
                  <Input
                    className="max-w-[12rem]"
                    placeholder="auteur"
                    value={c.author}
                    onChange={(e) => setField(s.subject_id, 'author', e.target.value)}
                  />
                  <Button size="sm" onClick={() => save(s)}>
                    Enregistrer
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default SubjectValidationPanel;
