// Panneau « Matières » — configuration des définitions YAML dans Neon.
//
// Les définitions de matières vivent dans subject_definitions ( Neon ) :
// plus aucun YAML dans le dépôt. L'admin les liste, voit/édite le YAML
// ( validé par le backend contre SubjectConfig ) et peut en créer —
// le registry se recharge immédiatement, sans redémarrage.
'use client';

import { useCallback, useEffect, useState } from 'react';
import { FileCode2, Loader2, Plus, Trash2 } from 'lucide-react';

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

interface SubjectRow {
  subject_id: string;
  name: string;
  valid: boolean;
}

export function SubjectDefinitionsPanel() {
  const [subjects, setSubjects] = useState<SubjectRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [yamlText, setYamlText] = useState('');
  const [newId, setNewId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiRequest('/api/admin/subjects');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSubjects(data.subjects || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur de chargement');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openDefinition = async (subjectId: string) => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiRequest(
        `/api/admin/subjects/${subjectId}/definition`,
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSelected(subjectId);
      setYamlText(data.yaml);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur de lecture');
    } finally {
      setBusy(false);
    }
  };

  const saveDefinition = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiRequest(
        `/api/admin/subjects/${selected}/definition`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ yaml: yamlText }),
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || `HTTP ${res.status}`);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur de sauvegarde');
    } finally {
      setBusy(false);
    }
  };

  const createSubject = async () => {
    const id = newId.trim();
    if (!id) return;
    setBusy(true);
    setError(null);
    // Squelette minimal valide — l'admin complète les champs ensuite.
    const skeleton = `id: ${id}\nname: ${id}\ndomain: general\ndescription: >\n  Matière ${id}.\nteaching_style: []\npedagogical_guidelines: []\ncapabilities:\n  - explain\ntools:\n  common:\n    - create_exercise\n    - evaluate_answer\n    - give_hint\n  specialized: []\nknowledge:\n  sources: []\ntopics: []\naliases: []\nmodel:\n  provider: ollama\n  name: qwen2.5\n`;
    try {
      const res = await apiRequest(
        `/api/admin/subjects/${id}/definition`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ yaml: skeleton }),
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || `HTTP ${res.status}`);
      }
      setNewId('');
      setSelected(id);
      setYamlText(skeleton);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur de création');
    } finally {
      setBusy(false);
    }
  };

  const deleteSubject = async (subjectId: string) => {
    setBusy(true);
    try {
      const res = await apiRequest(
        `/api/admin/subjects/${subjectId}/definition`,
        { method: 'DELETE' },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (selected === subjectId) {
        setSelected(null);
        setYamlText('');
      }
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
          <FileCode2 className="h-4 w-4" /> Matières — définitions (Neon)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <p className="text-xs leading-relaxed text-destructive">{error}</p>
        )}

        {/* Création */}
        <div className="flex items-end gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="sd-new">Nouvelle matière (id)</Label>
            <Input
              id="sd-new"
              value={newId}
              onChange={(e) => setNewId(e.target.value)}
              placeholder="philosophie"
              className="w-56"
            />
          </div>
          <Button
            size="sm"
            disabled={busy || !newId.trim()}
            onClick={createSubject}
          >
            {busy ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Plus className="mr-2 h-4 w-4" />
            )}
            Créer
          </Button>
        </div>

        {/* Liste */}
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
          </p>
        ) : (
          <div className="flex max-h-44 flex-wrap gap-1.5 overflow-y-auto">
            {subjects.map((s) => (
              <span key={s.subject_id} className="inline-flex items-center">
                <Button
                  variant={selected === s.subject_id ? 'default' : 'outline'}
                  size="sm"
                  className="h-7 font-mono text-[11px]"
                  disabled={busy}
                  onClick={() => openDefinition(s.subject_id)}
                >
                  {s.subject_id}
                  {!s.valid && <span className="ml-1 text-destructive">⚠</span>}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-6"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(`Supprimer la définition « ${s.subject_id} » ? Cette action est définitive.`)) {
                      void deleteSubject(s.subject_id);
                    }
                  }}
                  aria-label={`Supprimer ${s.subject_id}`}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </span>
            ))}
          </div>
        )}

        {/* Éditeur YAML */}
        {selected && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="font-mono text-[10px]">
                {selected}
              </Badge>
              <span className="text-muted-foreground text-[11px]">
                YAML validé par le backend — registry rechargé à la
                sauvegarde
              </span>
            </div>
            <Textarea
              value={yamlText}
              onChange={(e) => setYamlText(e.target.value)}
              rows={14}
              className="font-mono text-[12px]"
              spellCheck={false}
            />
            <Button
              size="sm"
              disabled={busy || !yamlText.trim()}
              onClick={saveDefinition}
            >
              {busy ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Enregistrer (valider + recharger)
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
