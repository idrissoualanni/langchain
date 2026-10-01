// Panneau « Upload & Preview Fichiers » — upload .md/.txt → parsing auto
// en sections vectorisées + liste/preview des fichiers du bucket knowledge_files.
'use client';

import { useCallback, useEffect, useState } from 'react';
import { FileText, Upload, Loader2, Eye, Trash2 } from 'lucide-react';

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
import { toast } from '@/hooks/use-toast';

interface KnowledgeFile {
  path: string;
  subject_id: string;
  sha256: string;
  created_at: string;
  content_preview: string;
  size_bytes: number;
}

interface UploadResult {
  file_path: string;
  subject_id: string;
  sections_created: number;
  sections: Array<{ id: number; topic_slug: string; title: string }>;
}

export function KnowledgeFileUploadPanel() {
  const [files, setFiles] = useState<KnowledgeFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [previewOpen, setPreviewOpen] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);

  // Formulaire upload
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [subjectId, setSubjectId] = useState('');
  const [sourceLabel, setSourceLabel] = useState('');

  const loadFiles = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiRequest('/api/admin/knowledge/files');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setFiles(data || []);
    } catch (e) {
      toast({
        title: "Erreur chargement fichiers",
        description: e instanceof Error ? e.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.endsWith('.md') && !file.name.endsWith('.txt')) {
        toast({
          title: "Type non supporté",
          description: "Seuls les fichiers .md et .txt sont acceptés",
          variant: "destructive",
        });
        return;
      }
      setSelectedFile(file);
      // Auto-remplir subject_id depuis le nom du fichier si vide
      if (!subjectId) {
        const guessed = file.name.replace(/\.(md|txt)$/i, '').split('/')[0];
        setSubjectId(guessed);
      }
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      if (subjectId.trim()) formData.append('subject_id', subjectId.trim());
      if (sourceLabel.trim()) formData.append('source_label', sourceLabel.trim());

      const res = await apiRequest('/api/admin/knowledge/upload', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || `HTTP ${res.status}`);
      }

      const result: UploadResult = await res.json();
      toast({
        title: "Fichier uploadé",
        description: `${result.sections_created} sections créées dans ${result.subject_id}`,
      });
      setSelectedFile(null);
      setSubjectId('');
      setSourceLabel('');
      await loadFiles();
    } catch (e) {
      toast({
        title: "Erreur upload",
        description: e instanceof Error ? e.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setUploading(false);
    }
  };

  const handlePreview = async (path: string) => {
    setPreviewLoading(true);
    setPreviewOpen(path);
    try {
      const res = await apiRequest(`/api/admin/knowledge/files/${encodeURIComponent(path)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setPreviewContent(data.content_preview || data.content || '');
    } catch (e) {
      setPreviewContent('Erreur de lecture');
      toast({
        title: "Erreur preview",
        description: e instanceof Error ? e.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleDelete = async (path: string) => {
    if (!confirm(`Supprimer le fichier ${path} ?`)) return;
    try {
      // Note: pas de route DELETE pour knowledge_files dans le backend actuel
      // On pourrait l'ajouter si besoin
      toast({
        title: "Non implémenté",
        description: "La suppression de fichier source n'est pas encore disponible",
        variant: "destructive",
      });
    } catch (e) {
      toast({
        title: "Erreur",
        description: e instanceof Error ? e.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4" /> Fichiers sources & Upload
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Upload Zone */}
        <div className="border-border border-2 border-dashed rounded-lg p-6">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <input
                type="file"
                id="file-upload"
                accept=".md,.txt"
                onChange={handleFileChange}
                className="sr-only"
                disabled={uploading}
              />
              <label
                htmlFor="file-upload"
                className="flex items-center gap-2 cursor-pointer text-muted-foreground hover:text-foreground"
              >
                <Upload className="h-5 w-5" />
                <span>{selectedFile ? selectedFile.name : 'Choisir un fichier .md ou .txt'}</span>
              </label>
              {selectedFile && (
                <Button variant="ghost" size="sm" onClick={() => setSelectedFile(null)}>
                  ×
                </Button>
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
              <div className="space-y-1.5">
                <Label htmlFor="kf-subject">Matière (subject_id)</Label>
                <Input
                  id="kf-subject"
                  value={subjectId}
                  onChange={(e) => setSubjectId(e.target.value)}
                  placeholder="python"
                  disabled={uploading}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="kf-label">Label source (optionnel)</Label>
                <Input
                  id="kf-label"
                  value={sourceLabel}
                  onChange={(e) => setSourceLabel(e.target.value)}
                  placeholder="upload/mon_cours.md"
                  disabled={uploading}
                />
              </div>
            </div>

            <Button
              onClick={handleUpload}
              disabled={uploading || !selectedFile}
              className="w-full sm:w-auto flex items-center gap-2"
            >
              {uploading && <Loader2 className="h-4 w-4 animate-spin" />}
              {!uploading && <Upload className="h-4 w-4" />}
              <span>{uploading ? 'Upload & vectorisation...' : 'Upload & vectoriser'}</span>
            </Button>
          </div>
        </div>

        {/* Onglets : Liste / Preview — remplacés par état simple */}
        <div className="space-y-3">
          {/* Bouton basculement vue preview */}
          {previewOpen && (
            <Button variant="outline" size="sm" onClick={() => setPreviewOpen(null)} className="w-full sm:w-auto">
              ← Retour à la liste
            </Button>
          )}

          {/* Vue Liste */}
          {!previewOpen && (
            <>
              {loading ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
                </p>
              ) : files.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Aucun fichier source dans le bucket.
                </p>
              ) : (
                <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                  {files.map((f) => (
                    <div
                      key={f.path}
                      className="border-border bg-background hover:bg-muted/40 flex items-center gap-3 rounded-lg border px-3 py-2"
                    >
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {f.subject_id || '—'}
                      </Badge>
                      <span className="min-w-0 flex-1 truncate text-[13px] font-mono">
                        {f.path}
                      </span>
                      <span className="text-muted-foreground text-[11px]">
                        {formatSize(f.size_bytes)}
                      </span>
                      <Badge variant="outline" className="text-[10px]">
                        {f.created_at}
                      </Badge>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => handlePreview(f.path)}
                        disabled={previewLoading}
                      >
                        <Eye className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => handleDelete(f.path)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Vue Preview */}
          {previewOpen && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Badge variant="outline" className="font-mono text-[11px]">
                  {previewOpen}
                </Badge>
                <Button variant="ghost" size="sm" onClick={() => setPreviewOpen(null)}>
                  Fermer
                </Button>
              </div>
              {previewLoading ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
                </p>
              ) : (
                <Textarea
                  value={previewContent}
                  readOnly
                  rows={20}
                  className="font-mono text-[11px] bg-background"
                  spellCheck={false}
                />
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}