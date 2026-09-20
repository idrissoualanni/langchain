// DocumentsPage V10 — documents personnels de l'utilisateur (RAG).
//
// Deux zones :
//   - Upload : fichier texte/MD/paste → indexation SQLite (+embeddings).
//   - Liste + recherche : CRUD documents, recherche hybride avec
//     statut contrôlé (found/insufficient/unavailable/error).
import { useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  FileUp,
  Loader2,
  Search,
  Trash2,
  Upload as UploadIcon,
  X,
} from 'lucide-react';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { useDocuments } from '../hooks/useDocuments';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';

const MAX_BYTES = 2_000_000;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} Ko`;
  return `${(n / (1024 * 1024)).toFixed(1)} Mo`;
}

const STATUS_LABEL: Record<string, string> = {
  found: 'Pertinents trouvés',
  insufficient: 'Aucun résultat pertinent',
  unavailable: 'Aucun document indexé',
  error: 'Recherche indisponible',
};

export function DocumentsPage() {
  const { internal: currentUser, signedIn } = useCurrentUser();
  const userId = signedIn ? currentUser?.user_id ?? null : null;
  const {
    documents,
    loading,
    error,
    upload,
    uploadDocument,
    deleteDocument,
    query,
    setQuery,
    searching,
    hits,
    searchStatus,
    searchError,
    searchDocuments,
  } = useDocuments(userId);

  const [pasted, setPasted] = useState<string>('');
  const [fileName, setFileName] = useState<string>('');
  const [isPdfPick, setIsPdfPick] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const doUpload = async () => {
    const content = pasted.trim();
    if (!fileName.trim() || !content) return;
    await uploadDocument(
      fileName.trim(),
      content,
      isPdfPick ? 'application/pdf' : 'text/plain'
    );
    if (upload.state !== 'error') {
      setPasted('');
      setFileName('');
      setIsPdfPick(false);
    }
  };

  const fileToBase64 = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('Lecture du fichier impossible'));
      reader.onload = () => {
        const result = String(reader.result ?? '');
        const comma = result.indexOf(',');
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.readAsDataURL(file);
    });

  const onFilePick = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setFileName('');
      setPasted('');
      setIsPdfPick(false);
      return;
    }
    setIsPdfPick(file.name.toLowerCase().endsWith('.pdf'));
    if (file.name.toLowerCase().endsWith('.pdf')) {
      try {
        const b64 = await fileToBase64(file);
        setPasted(b64);
        setFileName(file.name);
      } catch {
        setFileName('');
        setPasted('');
        setIsPdfPick(false);
      }
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? '').slice(0, MAX_BYTES);
      setPasted(text);
      setFileName(file.name);
    };
    reader.readAsText(file);
  };

  const onClearPdf = () => {
    setFileName('');
    setPasted('');
    setIsPdfPick(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* En-tête */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-foreground">
            <FileText size={16} className="text-live" strokeWidth={1.8} />
            Mes documents
          </h1>
          <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
            rag · sqlite · embeddings · {documents.length} document(s)
          </p>
        </div>
      </div>

      {!signedIn || !userId ? (
        <Card className="p-10 text-center">
          <FileText size={32} className="mx-auto mb-3 text-muted-foreground/30" />
          <div className="text-sm text-muted-foreground">
            Connectez-vous pour gérer vos documents personnels.
          </div>
        </Card>
      ) : (
        <div className="space-y-5">
          {/* Upload */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-[13px]">
                <FileUp size={13} className="text-live" strokeWidth={1.8} />
                Ajouter un document
              </CardTitle>
              <span className="font-mono text-[10px] text-muted-foreground/60">
                md · txt · rst · pdf (max 2 Mo)
              </span>
            </CardHeader>
            <CardContent className="space-y-3">
              <textarea
                className="w-full resize-y rounded-lg border border-border bg-background p-3 font-mono text-xs leading-relaxed text-foreground focus:outline-none focus:ring-1 focus:ring-live/40"
                rows={5}
                placeholder={
                  isPdfPick
                    ? '(contenu PDF encodé en base64 — prêt pour indexation)'
                    : 'Collez le contenu texte de votre document ici (cours, notes, code, syntheses)...'
                }
                value={isPdfPick ? (fileName ? '(fichier sélectionné)' : '') : pasted}
                disabled={isPdfPick}
              />
              {isPdfPick && fileName && (
                <div className="flex items-center gap-2 rounded-md border border-live/30 bg-live/5 px-3 py-2 font-mono text-[11px] text-live">
                  <FileText size={13} className="shrink-0" strokeWidth={1.8} />
                  <span className="truncate">{fileName}</span>
                  <span className="text-muted-foreground/70">
                    · PDF encodé · {pasted.length} caractères base64 · contenu
                    indexé côté serveur
                  </span>
                  <button
                    type="button"
                    onClick={onClearPdf}
                    className="ml-auto rounded p-1 text-muted-foreground/70 transition-colors hover:text-error"
                    title="Retirer le fichier PDF"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <input
                  ref={fileRef}
                  type="file"
                  accept=".md,.txt,.rst,.markdown,.pdf,text/plain,application/pdf"
                  className="hidden"
                  onChange={(e) => onFilePick(e.target.files?.[0])}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileRef.current?.click()}
                >
                  <UploadIcon className="h-3.5 w-3.5" />
                  Choisir un fichier
                </Button>
                <Input
                  className="h-9 w-56 font-mono text-xs"
                  placeholder="nom-du-fichier.md"
                  value={fileName}
                  onChange={(e) => setFileName(e.target.value)}
                />
                <Button
                  type="button"
                  size="sm"
                  className="h-9"
                  onClick={doUpload}
                  disabled={upload.state === 'uploading' || !fileName.trim() || !pasted.trim()}
                >
                  {upload.state === 'uploading' ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <FileUp className="h-3.5 w-3.5" />
                  )}
                  Indexer
                </Button>
              </div>
              {upload.state === 'error' && (
                <div className="rounded-md bg-error/10 px-3 py-2 font-mono text-[11px] text-error">
                  {upload.message}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Recherche */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-[13px]">
                <Search size={13} className="text-live" strokeWidth={1.8} />
                Recherche dans mes documents
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <Input
                  className="h-9 font-mono text-xs"
                  placeholder="Que voulez-vous retrouver ? (recherche hybride : sémantique + lexical)"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void searchDocuments(query);
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  className="h-9"
                  onClick={() => void searchDocuments(query)}
                  disabled={searching || !query.trim()}
                >
                  {searching ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Search className="h-3.5 w-3.5" />
                  )}
                  Chercher
                </Button>
              </div>

              {searchStatus && (
                <div className="font-mono text-[10px] text-muted-foreground">
                  {STATUS_LABEL[searchStatus] ?? searchStatus} · {hits.length}{' '}
                  extrait(s)
                </div>
              )}
              {searchError && (
                <div className="rounded-md bg-error/10 px-3 py-2 font-mono text-[11px] text-error">
                  {searchError}
                </div>
              )}

              <AnimatePresence initial={false}>
                {hits.length > 0 && (
                  <motion.ul
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="space-y-2"
                  >
                    {hits.map((h) => (
                      <motion.li
                        key={h.chunk_id}
                        initial={{ opacity: 0, y: -6 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="rounded-lg border border-border bg-muted/50 p-3"
                      >
                        <div className="mb-1 flex items-baseline gap-2">
                          <span className="font-mono text-[11px] font-semibold text-live">
                            {h.filename || h.doc_id}
                          </span>
                          <span className="font-mono text-[9px] text-muted-foreground/60">
                            score {h.relevance.toFixed(3)} · lex{' '}
                            {h.lexical_score.toFixed(2)} · sem{' '}
                            {h.semantic_score.toFixed(2)}
                          </span>
                        </div>
                        <p className="line-clamp-3 text-xs leading-relaxed text-foreground/85">
                          {h.content}
                        </p>
                      </motion.li>
                    ))}
                  </motion.ul>
                )}
              </AnimatePresence>
            </CardContent>
          </Card>

          {/* Mes documents */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-[13px]">
                <FileText size={13} className="text-live" strokeWidth={1.8} />
                Mes documents
              </CardTitle>
              <span className="font-mono text-[10px] text-muted-foreground/60">
                {documents.length} indexé(s)
              </span>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="py-8 text-center font-mono text-[11px] text-muted-foreground">
                  chargement…
                </div>
              ) : error ? (
                <div className="rounded-md bg-error/10 px-3 py-2 font-mono text-[11px] text-error">
                  {error}
                </div>
              ) : documents.length === 0 ? (
                <div className="py-8 text-center font-mono text-[11px] text-muted-foreground">
                  Aucun document indexé pour le moment.
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {documents.map((d) => (
                    <li
                      key={d.doc_id}
                      className="group flex items-center gap-3 py-2.5"
                    >
                      <FileText
                        size={15}
                        className="shrink-0 text-muted-foreground/50"
                        strokeWidth={1.6}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-mono text-xs font-medium text-foreground/90">
                          {d.filename}
                        </div>
                        <div className="font-mono text-[10px] text-muted-foreground/60">
                          {d.chunk_count} extrait(s) · {formatBytes(d.size_bytes)}{' '}
                          · {d.created_at?.replace('T', ' ').slice(0, 16)}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => void deleteDocument(d.doc_id)}
                        className="rounded p-1 text-muted-foreground/50 opacity-0 transition-opacity hover:text-error group-hover:opacity-100"
                        title="Supprimer ce document"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}