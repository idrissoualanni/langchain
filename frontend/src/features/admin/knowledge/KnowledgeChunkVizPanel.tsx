// KnowledgeChunkVizPanel — onglet admin « Visualisation 3D des chunks ».
//
// Enveloppe useChunkViz + ChunkEmbeddingViz3D : filtre matière optionnel,
// chargement, et panneau de détail du chunk sélectionné ( titre, matière,
// auteur, source ).
'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Boxes, RefreshCw } from 'lucide-react';
import { ChunkEmbeddingViz3D } from './ChunkEmbeddingViz3D';
import { useChunkViz, type ChunkPoint } from './useChunkViz';

export function KnowledgeChunkVizPanel() {
  const [subject, setSubject] = useState('');
  const [selected, setSelected] = useState<ChunkPoint | null>(null);
  const { data, loading, error, reload } = useChunkViz(subject || undefined);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Boxes className="h-5 w-5" />
            Visualisation 3D des chunks vectorisés
          </span>
          <div className="flex items-center gap-2">
            <Input
              className="max-w-[12rem]"
              placeholder="matière (optionnel)"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
            <Button variant="ghost" size="sm" onClick={reload} disabled={loading}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading && <p className="text-sm text-muted-foreground">Chargement…</p>}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {data && data.count === 0 && !loading && (
          <p className="text-sm text-muted-foreground">
            Aucun chunk vectorisé à afficher.
          </p>
        )}
        {data && data.count > 0 && (
          <ChunkEmbeddingViz3D
            points={data.points}
            edges={data.edges}
            dim={data.dim}
            explainedVariance={data.explained_variance}
            onSelect={setSelected}
          />
        )}
        {selected && (
          <div className="rounded border p-3 text-sm">
            <div className="font-medium">{selected.title}</div>
            <div className="text-muted-foreground">
              {selected.subject_id} · {selected.topic_slug}
              {selected.author ? ` · ${selected.author}` : ''}
            </div>
            <div className="text-muted-foreground">{selected.source_label}</div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default KnowledgeChunkVizPanel;
