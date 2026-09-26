// DocumentsPage V11 — documents personnels de l'utilisateur (RAG).
//
// Trois zones :
//   - Upload : fichier texte/MD/paste → indexation SQLite (+embeddings).
//   - Recherche : CRUD documents, recherche hybride avec statut
//     contrôlé (found/insufficient/unavailable/error).
//   - Bibliothèque : onglets de filtrage (§11) + menu d'actions par
//     document (Ouvrir / Résumer / Poser une question / Générer un
//     QCM / Supprimer).
//
// Règle d'honnêteté : un onglet sans donnée backend réelle affiche un
// état vide explicite — JAMAIS de donnée fabriquée.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Eye,
  FileText,
  FileUp,
  HelpCircle,
  ListChecks,
  Loader2,
  MoreVertical,
  Search,
  ScrollText,
  Trash2,
  Upload as UploadIcon,
  X,
} from 'lucide-react';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { useDocuments } from '../hooks/useDocuments';
import { searchDocuments as searchDocumentsApi } from '../api/documents';
import { apiFetch } from '../api/base';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { Dialog } from '../components/ui/Dialog';
import { DropZone } from '../components/ui/drop-zone';
import { EmptyState } from '../components/ui/empty-state';
import { ErrorState } from '../components/ui/error-state';

const MAX_BYTES = 2_000_000;

/** Document potentiellement enrichi de métadonnées de partage/ownership.
 * Le backend actuel ne peuple pas ces champs (DocumentOut est user-scoped)
 * → les filtres restent défensifs et s'adaptent si l'API les ajoute. */
type DocWithMeta = {
  doc_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  chunk_count: number;
  created_at: string;
  owner_id?: string;
  shared?: boolean;
  metadata?: Record<string, unknown>;
};

type DocTab = 'all' | 'mine' | 'shared' | 'kb';

const TABS: { id: DocTab; label: string }[] = [
  { id: 'all', label: 'Tous' },
  { id: 'mine', label: 'Mes documents' },
  { id: 'shared', label: 'Partagés avec moi' },
  { id: 'kb', label: 'Base de connaissances' },
];

interface KnowledgeBaseItem {
  id: string;
  name: string;
  description: string;
  subject_id: string;
  scope: string;
  enabled: boolean;
}

type KbState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; items: KnowledgeBaseItem[] }
  | { status: 'unavailable'; reason: string };

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
  const { internal: currentUser, signedIn, isAdmin } = useCurrentUser();
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

  const navigate = useNavigate();

  const [pasted, setPasted] = useState<string>('');
  const [fileName, setFileName] = useState<string>('');
  const [isPdfPick, setIsPdfPick] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Onglet de la bibliothèque (§11)
  const [tab, setTab] = useState<DocTab>('all');

  // Aperçu "Ouvrir" — extraits réels du document (recherche hybride)
  const [previewDoc, setPreviewDoc] = useState<DocWithMeta | null>(null);
  const [previewChunks, setPreviewChunks] = useState<string[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Onglet "Base de connaissances" — retrieval backend si un endpoint
  // accessible existe, sinon état vide honnête.
  const [kb, setKb] = useState<KbState>({ status: 'idle' });

  const docs = documents as DocWithMeta[];

  const isMine = (d: DocWithMeta) =>
    !d.owner_id || (userId !== null && d.owner_id === userId);

  const isShared = (d: DocWithMeta) =>
    d.shared === true || d.metadata?.shared === true;

  const visibleDocuments = useMemo<DocWithMeta[]>(() => {
    switch (tab) {
      case 'all':
        return docs;
      case 'mine':
        // L'API documents est user-scoped : tout document listé est
        // nécessairement le sien (ownership validé côté backend).
        return docs.filter(isMine);
      case 'shared':
        return docs.filter(isShared);
      case 'kb':
        return [];
    }
  }, [docs, tab, userId]);

  // ---- Base de connaissances : retrieval réel si l'endpoint existe ----
  useEffect(() => {
    if (tab !== 'kb' || kb.status !== 'idle') return;
    // Aucun endpoint de retrieval knowledge n'est exposé aux utilisateurs
    // standards : seul /api/admin/knowledge (CRUD admin, sans retrieval)
    // existe. Un admin voit la liste réelle des bases ; les autres
    // obtiennent un état vide explicite — pas de donnée fabriquée.
    if (!isAdmin) {
      setKb({
        status: 'unavailable',
        reason:
          'Aucune base de connaissances accessible. Le retrieval de connaissances partagées n’est pas disponible pour votre compte.',
      });
      return;
    }
    setKb({ status: 'loading' });
    apiFetch<{ knowledge_bases: KnowledgeBaseItem[] }>('/api/admin/knowledge')
      .then((res) =>
        setKb({ status: 'ready', items: res.knowledge_bases ?? [] })
      )
      .catch((e) =>
        setKb({
          status: 'unavailable',
          reason:
            e instanceof Error
              ? `Base de connaissances indisponible — ${e.message}`
              : 'Base de connaissances indisponible.',
        })
      );
  }, [tab, isAdmin, kb.status]);

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

  // ---- Actions par document (§11) ----
  const goToAssistant = (prompt: string) => {
    navigate(`/assistant?q=${encodeURIComponent(prompt)}`);
  };

  const summarizeDoc = (d: DocWithMeta) =>
    goToAssistant(
      `Résume le document « ${d.filename} » : extraits les points clés et les notions essentielles.`
    );

  const askAboutDoc = (d: DocWithMeta) =>
    goToAssistant(
      `À propos du document « ${d.filename} » : aide-moi à le comprendre en répondant à mes questions sur son contenu.`
    );

  const quizFromDoc = (d: DocWithMeta) =>
    goToAssistant(
      `Génère un QCM sur le contenu du document « ${d.filename} ».`
    );

  // "Ouvrir" : récupère les extraits réels du document via la recherche
  // hybride (filtrée sur ce doc_id) — aucun contenu n'est inventé.
  const openDoc = async (d: DocWithMeta) => {
    setPreviewDoc(d);
    setPreviewError(null);
    if (!userId) {
      setPreviewChunks([]);
      setPreviewError('Session requise pour lire le contenu.');
      return;
    }
    setPreviewLoading(true);
    try {
      const resp = await searchDocumentsApi(userId, d.filename, 20);
      const mine = resp.results
        .filter((r) => r.doc_id === d.doc_id)
        .map((r) => r.content);
      setPreviewChunks(mine);
      if (resp.status === 'error') setPreviewError(resp.error || null);
    } catch (e) {
      setPreviewChunks([]);
      setPreviewError(
        e instanceof Error ? e.message : 'Lecture du document impossible'
      );
    } finally {
      setPreviewLoading(false);
    }
  };

  const TAB_LABEL: Record<DocTab, string> = {
    all: 'Tous les documents',
    mine: 'Mes documents',
    shared: 'Partagés avec moi',
    kb: 'Base de connaissances',
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* En-tête */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-foreground">
            <FileText size={16} className="text-live" strokeWidth={1.8} />
            Documents
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
          {/* Upload — drag & drop (§13) */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-[13px]">
                <FileUp size={13} className="text-live" strokeWidth={1.8} />
                Ajouter un document
              </CardTitle>
              <span className="font-mono text-[10px] text-muted-foreground">
                md · txt · rst · pdf (max 2 Mo) · glisser-déposer
              </span>
            </CardHeader>
            <CardContent className="space-y-3">
              <DropZone
                accept=".md,.txt,.rst,.pdf"
                maxBytes={MAX_BYTES}
                onFiles={(files) => onFilePick(files[0])}
              />
              <textarea
                className="w-full resize-y rounded-lg border border-border bg-background p-3 font-mono text-xs leading-relaxed text-foreground focus:outline-none focus:ring-1 focus:ring-live/40"
                rows={4}
                placeholder={
                  isPdfPick
                    ? '(contenu PDF encodé en base64 — prêt pour indexation)'
                    : 'Ou collez le contenu texte ici (cours, notes, code, synthèses)...'
                }
                value={isPdfPick ? (fileName ? '(fichier sélectionné)' : '') : pasted}
                onChange={(e) => setPasted(e.target.value)}
                disabled={isPdfPick}
              />
              {isPdfPick && fileName && (
                <div className="flex items-center gap-2 rounded-md border border-live/30 bg-live/5 px-3 py-2 font-mono text-[11px] text-live">
                  <FileText size={13} className="shrink-0" strokeWidth={1.8} />
                  <span className="truncate">{fileName}</span>
                  <span className="text-muted-foreground">
                    · PDF encodé · {pasted.length} caractères base64 · contenu
                    indexé côté serveur
                  </span>
                  <button
                    type="button"
                    onClick={onClearPdf}
                    className="ml-auto rounded p-1 text-muted-foreground transition-colors hover:text-error"
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
                          <details className="ml-auto">
                            <summary className="cursor-pointer list-none font-mono text-[9px] text-muted-foreground hover:text-foreground">
                              scores
                            </summary>
                            <span className="font-mono text-[9px] text-muted-foreground">
                              {h.relevance.toFixed(3)} · lex {h.lexical_score.toFixed(2)} · sem{' '}
                              {h.semantic_score.toFixed(2)}
                            </span>
                          </details>
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

          {/* Bibliothèque — onglets §11 + actions par document */}
          <Card>
            <CardHeader className="flex-row items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2 text-[13px]">
                <FileText size={13} className="text-live" strokeWidth={1.8} />
                {TAB_LABEL[tab]}
              </CardTitle>
              {/* Onglets */}
              <div className="flex flex-wrap gap-1">
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTab(t.id)}
                    className={`rounded-[var(--radius-control)] px-2.5 py-1 text-[12.5px] font-medium transition-colors ${
                      tab === t.id
                        ? 'bg-muted text-foreground'
                        : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </CardHeader>
            <CardContent>
              {tab === 'kb' ? (
                kb.status === 'loading' ? (
                  <div className="py-8 text-center font-mono text-[11px] text-muted-foreground">
                    chargement de la base de connaissances…
                  </div>
                ) : kb.status === 'ready' ? (
                  kb.items.length === 0 ? (
                    <div className="py-8 text-center font-mono text-[11px] text-muted-foreground">
                      Aucune base de connaissances configurée.
                    </div>
                  ) : (
                    <ul className="divide-y divide-border">
                      {kb.items.map((k) => (
                        <li
                          key={k.id}
                          className="group flex items-center gap-3 py-2.5"
                        >
                          <FileText
                            size={15}
                            className="shrink-0 text-muted-foreground"
                            strokeWidth={1.6}
                          />
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-mono text-xs font-medium text-foreground/90">
                              {k.name}
                            </div>
                            <div className="font-mono text-[10px] text-muted-foreground">
                              {k.subject_id} · {k.scope} ·{' '}
                              {k.enabled ? 'activée' : 'désactivée'}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )
                ) : kb.status === 'unavailable' ? (
                  <div className="py-8 text-center">
                    <FileText
                      size={28}
                      className="mx-auto mb-3 text-muted-foreground/30"
                      strokeWidth={1.6}
                    />
                    <p className="text-sm font-medium text-foreground">
                      Base de connaissances
                    </p>
                    <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                      {kb.reason}
                    </p>
                  </div>
                ) : (
                  <div className="py-8 text-center font-mono text-[11px] text-muted-foreground">
                    Base de connaissances — en attente.
                  </div>
                )
              ) : loading ? (
                <div className="py-8 text-center font-mono text-[11px] text-muted-foreground">
                  chargement…
                </div>
              ) : error ? (
                <ErrorState message={error} details={error} />
              ) : visibleDocuments.length === 0 ? (
                <EmptyState
                  icon={<FileText />}
                  title={tab === 'shared' ? 'Aucun document partagé' : 'Aucun document'}
                  description={
                    tab === 'shared'
                      ? 'Le partage n’est pas encore disponible.'
                      : 'Ajoutez votre premier document ci-dessus pour commencer.'
                  }
                />
              ) : (
                <ul className="divide-y divide-border">
                  {visibleDocuments.map((d) => (
                    <li
                      key={d.doc_id}
                      className="group flex items-center gap-3 py-2.5"
                    >
                      <FileText
                        size={15}
                        className="shrink-0 text-muted-foreground"
                        strokeWidth={1.6}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-mono text-xs font-medium text-foreground/90">
                          {d.filename}
                        </div>
                        <div className="font-mono text-[10px] text-muted-foreground">
                          {d.chunk_count} extrait(s) · {formatBytes(d.size_bytes)}{' '}
                          · {d.created_at?.replace('T', ' ').slice(0, 16)}
                        </div>
                      </div>

                      {/* Menu d'actions (§11) */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 data-[state=open]:opacity-100"
                            title="Actions sur ce document"
                            aria-label={`Actions sur ${d.filename}`}
                          >
                            <MoreVertical className="h-4 w-4" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-48">
                          <DropdownMenuItem onClick={() => void openDoc(d)}>
                            <Eye className="h-3.5 w-3.5" />
                            Ouvrir
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => summarizeDoc(d)}>
                            <ScrollText className="h-3.5 w-3.5" />
                            Résumer
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => askAboutDoc(d)}>
                            <HelpCircle className="h-3.5 w-3.5" />
                            Poser une question
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => quizFromDoc(d)}>
                            <ListChecks className="h-3.5 w-3.5" />
                            Générer un QCM
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => void deleteDocument(d.doc_id)}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Supprimer
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Aperçu "Ouvrir" — extraits réels du document */}
      <Dialog
        open={previewDoc !== null}
        onOpenChange={(open: boolean) => {
          if (!open) {
            setPreviewDoc(null);
            setPreviewChunks([]);
            setPreviewError(null);
          }
        }}
        title={previewDoc?.filename ?? 'Document'}
        className="sm:max-w-2xl"
      >
        {previewLoading ? (
          <div className="flex items-center gap-2 py-6 font-mono text-[11px] text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            lecture des extraits…
          </div>
        ) : previewError ? (
          <div className="rounded-md bg-error/10 px-3 py-2 font-mono text-[11px] text-error">
            {previewError}
          </div>
        ) : previewChunks.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">
            Aucun extrait exploitable pour ce document.
          </p>
        ) : (
          <div className="max-h-[60vh] space-y-2 overflow-y-auto">
            {previewChunks.map((c, i) => (
              <p
                key={i}
                className="rounded-lg border border-border bg-muted/50 p-3 text-xs leading-relaxed text-foreground/85"
              >
                {c}
              </p>
            ))}
          </div>
        )}
      </Dialog>
    </div>
  );
}
