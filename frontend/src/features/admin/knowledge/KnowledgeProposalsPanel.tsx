// KnowledgeProposalsPanel — propositions de connaissance ( décision admin ).
//
// Liste les propositions soumises par l'agent ( status=pending par
// défaut ) et permet de les APPROUVER ( → vectorisées, entrent au corpus )
// ou de les REJETER. Rien n'entre au corpus sans décision admin.
'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Check, Inbox, RefreshCw, X } from 'lucide-react';
import { apiRequest } from '@/api/request';

interface Proposal {
  id: number;
  subject_id: string;
  title: string;
  content: string;
  author: string;
  proposed_by: string;
  reason: string;
  status: string;
  created_at: string;
}

const FILTERS = ['pending', 'approved', 'rejected', ''] as const;

export function KnowledgeProposalsPanel() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [filter, setFilter] = useState<string>('pending');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = filter ? `?status=${filter}` : '';
      const res = await apiRequest(`/api/admin/knowledge/proposals${qs}`);
      const data = await res.json();
      setProposals(data.proposals || []);
    } catch {
      setProposals([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const decide = async (id: number, approve: boolean) => {
    const res = await apiRequest(
      `/api/admin/knowledge/proposals/${id}/decide`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approve }),
      }
    );
    if (res.ok) load();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Inbox className="h-5 w-5" />
            Propositions de connaissance ({proposals.length})
          </span>
          <div className="flex items-center gap-1">
            {FILTERS.map((f) => (
              <Button
                key={f || 'all'}
                size="sm"
                variant={filter === f ? 'default' : 'ghost'}
                onClick={() => setFilter(f)}
              >
                {f || 'tout'}
              </Button>
            ))}
            <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading && <p className="text-sm text-muted-foreground">Chargement…</p>}
        {!loading && proposals.length === 0 && (
          <p className="text-sm text-muted-foreground">Aucune proposition.</p>
        )}
        {proposals.map((p) => (
          <div key={p.id} className="rounded border p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{p.title}</span>
              <Badge variant={p.status === 'approved' ? 'default' : 'secondary'}>
                {p.status}
              </Badge>
              <span className="text-muted-foreground">
                {p.subject_id}
                {p.author ? ` · ${p.author}` : ''}
              </span>
              {p.proposed_by ? (
                <span className="text-muted-foreground">
                  proposé par {p.proposed_by}
                </span>
              ) : null}
            </div>
            {p.reason && (
              <div className="mt-1 text-muted-foreground">Motif : {p.reason}</div>
            )}
            <div className="mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap text-muted-foreground">
              {p.content.slice(0, 600)}
              {p.content.length > 600 ? '…' : ''}
            </div>
            {p.status === 'pending' && (
              <div className="mt-2 flex gap-2">
                <Button size="sm" onClick={() => decide(p.id, true)}>
                  <Check className="h-4 w-4" /> Approuver
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => decide(p.id, false)}
                >
                  <X className="h-4 w-4" /> Rejeter
                </Button>
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default KnowledgeProposalsPanel;
