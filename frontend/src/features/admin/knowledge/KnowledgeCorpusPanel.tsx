// Panneau « Corpus de cours » — gestion du CONTENU vectorisé dans Neon.
//
// Le corpus de cours vit dans knowledge_sections ( Neon + pgvector ) :
// plus aucun fichier dans le dépôt. Ici l'admin AJOUTE une section
// ( titre + contenu ) qui est VECTORISÉE à l'écriture par le backend
// ( POST /api/admin/knowledge/content ), la liste et la supprime.
// La recherche sémantique voit chaque section immédiatement.
'use client';

import { useCallback, useEffect, useState } from 'react';
import { Database, Loader2, Plus, Trash2 } from 'lucide-react';

import { apiRequest } from '@/api/request';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

interface SectionRow {
  id: number;
  subject_id: string;
  topic_slug: string;
  title: string;
  source_label: string | null;
  created_at: string | null;
  embedded: boolean;
}

export function KnowledgeCorpusPanel() {
  const [sections, setSections] = useState<SectionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    subject_id: '',
    title: '',
    content: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiRequest('/api/admin/knowledge/content');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSections(data.sections || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur de chargement');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleAdd = async () => {
    if (!form.subject_id.trim() || !form.title.trim() || !form.content.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await apiRequest('/api/admin/knowledge/content', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_id: form.subject_id.trim(),
          title: form.title.trim(),
          content: form.content,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || `HTTP ${res.status}`);
      }
      setForm({ subject_id: '', title: '', content: '' });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur d'ajout");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (id: number) => {
    setBusy(true);
    try {
      const res = await apiRequest(`/api/admin/knowledge/content/${id}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur de suppression');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Database className="h-4 w-4" /> Corpus de cours (Neon, vectorisé)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <p className="text-xs leading-relaxed text-destructive">{error}</p>
        )}

        {/* Ajout — vectorisé à l'écriture côté backend */}
        <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
          <div className="space-y-1.5">
            <Label htmlFor="kc-subject">Matière (subject_id)</Label>
            <Input
              id="kc-subject"
              value={form.subject_id}
              onChange={(e) =>
                setForm((p) => ({ ...p, subject_id: e.target.value }))
              }
              placeholder="python"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="kc-title">Titre de section</Label>
            <Input
              id="kc-title"
              value={form.title}
              onChange={(e) =>
                setForm((p) => ({ ...p, title: e.target.value }))
              }
              placeholder="La fonction return"
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="kc-content">Contenu du cours</Label>
            <Textarea
              id="kc-content"
              value={form.content}
              onChange={(e) =>
                setForm((p) => ({ ...p, content: e.target.value }))
              }
              placeholder="Colle ici le contenu de cours de cette section…"
              rows={5}
            />
          </div>
          <div className="sm:col-span-2">
            <Button
              onClick={handleAdd}
              disabled={
                busy ||
                !form.subject_id.trim() ||
                !form.title.trim() ||
                !form.content.trim()
              }
              size="sm"
            >
              {busy ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-2 h-4 w-4" />
              )}
              Ajouter (vectoriser)
            </Button>
          </div>
        </div>

        {/* Inventaire */}
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
          </p>
        ) : sections.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Aucune section pour l'instant.
          </p>
        ) : (
          <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
            {sections.map((s) => (
              <div
                key={s.id}
                className="border-border bg-background hover:bg-muted/40 flex items-center gap-3 rounded-lg border px-3 py-2"
              >
                <Badge variant="outline" className="font-mono text-[10px]">
                  {s.subject_id}
                </Badge>
                <span className="min-w-0 flex-1 truncate text-[13px]">
                  {s.title}
                  <span className="text-muted-foreground ml-2 font-mono text-[10px]">
                    {s.topic_slug}
                  </span>
                </span>
                {s.embedded ? (
                  <Badge
                    variant="outline"
                    className="text-[10px] text-emerald-600"
                  >
                    vectorisé
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px]">
                    sans vecteur
                  </Badge>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  disabled={busy}
                  onClick={() => handleDelete(s.id)}
                  aria-label={`Supprimer ${s.title}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
