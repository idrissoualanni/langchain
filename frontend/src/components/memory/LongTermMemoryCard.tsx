// LongTermMemoryCard v3 — MemoryFacts structurés par catégorie
// Source de vérité : SqliteStore (user_id-keyed), indépendant du thread.
// Deux modes : structuré (catégories + bullets) et Raw Memory
// (inspecteur dev : objets exacts avec id/source/confidence).
import { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  BrainCircuit,
  Check,
  Code2,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react';
import type {
  MemoryCategory,
  MemoryFact,
  MemoryOverview,
} from '../../types/agent';
import {
  CATEGORY_LABELS,
  MEMORY_CATEGORIES,
} from '../../types/agent';

type FilterCategory = 'all' | MemoryCategory;

interface LongTermMemoryCardProps {
  overview: MemoryOverview | null;
  loading: boolean;
  onRefresh: () => void;
  onSaveProfile: (
    fields: { name?: string; description?: string }
  ) => Promise<unknown>;
  onAddFact: (fact: {
    category: string;
    content: string;
    confidence?: number;
  }) => Promise<unknown>;
  onEditFact: (
    factId: string,
    fields: { content?: string; category?: string }
  ) => Promise<unknown>;
  onRemoveFact: (factId: string) => Promise<unknown>;
  hasUser: boolean;
}

const CATEGORY_ORDER: MemoryCategory[] = [
  'identity',
  'background',
  'personality',
  'preference',
  'interest',
];

export function LongTermMemoryCard({
  overview,
  loading,
  onRefresh,
  onSaveProfile,
  onAddFact,
  onEditFact,
  onRemoveFact,
  hasUser,
}: LongTermMemoryCardProps) {
  const [rawMode, setRawMode] = useState(false);
  const [filter, setFilter] = useState<FilterCategory>('all');

  // --- Édition profil (name/description v2) ---
  const [editingProfile, setEditingProfile] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);

  // --- Ajout d'un fait ---
  const [adding, setAdding] = useState(false);
  const [newCategory, setNewCategory] =
    useState<MemoryCategory>('interest');
  const [newContent, setNewContent] = useState('');
  const [savingFact, setSavingFact] = useState(false);

  // --- Édition d'un fait ---
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);

  const [savedFlash, setSavedFlash] = useState(false);

  const factsByCat = overview?.facts_by_category ?? {};

  // Catégories affichées : la catégorie filtrée, ou toutes les non-vides
  const cats = useMemo(() => {
    if (filter !== 'all') {
      return [filter as MemoryCategory];
    }
    return CATEGORY_ORDER.filter(
      (c) => (factsByCat[c]?.length ?? 0) > 0
    );
  }, [filter, factsByCat]);

  const flash = () => {
    setSavedFlash(true);
    setTimeout(() => setSavedFlash(false), 1500);
  };

  const startEditProfile = () => {
    setName(overview?.identity.name ?? '');
    setDescription(overview?.identity.description ?? '');
    setEditingProfile(true);
  };

  const saveProfile = async () => {
    const fields: { name?: string; description?: string } = {};
    if (name.trim()) fields.name = name.trim();
    if (description.trim()) fields.description = description.trim();
    if (!fields.name && !fields.description) {
      setEditingProfile(false);
      return;
    }
    setSavingProfile(true);
    try {
      await onSaveProfile(fields);
      setEditingProfile(false);
      flash();
    } catch {
      // L'erreur remonte via le hook — on reste en mode édition
    } finally {
      setSavingProfile(false);
    }
  };

  const addFact = async () => {
    if (!newContent.trim()) return;
    setSavingFact(true);
    try {
      await onAddFact({
        category: newCategory,
        content: newContent.trim(),
      });
      setNewContent('');
      setAdding(false);
      flash();
    } catch {
      // reste en mode ajout
    } finally {
      setSavingFact(false);
    }
  };

  const startEditFact = (fact: MemoryFact) => {
    setEditingId(fact.id);
    setEditContent(fact.content);
  };

  const saveEditFact = async () => {
    if (!editingId || !editContent.trim()) return;
    setSavingEdit(true);
    try {
      await onEditFact(editingId, { content: editContent.trim() });
      setEditingId(null);
      flash();
    } catch {
      // reste en édition
    } finally {
      setSavingEdit(false);
    }
  };

  const removeFact = async (factId: string) => {
    try {
      await onRemoveFact(factId);
      flash();
    } catch {
      // ignore
    }
  };

  const totalFacts = overview?.total_facts ?? 0;

  return (
    <section className="rounded-xl border border-border bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2.5">
          <BrainCircuit className="h-4.5 w-4.5 text-accent" />
          <div>
            <h2 className="font-mono text-sm font-semibold tracking-tight text-text">
              Long-Term Memory
            </h2>
            <p className="font-mono text-xs text-muted">
              cross-thread · user_id-keyed · {totalFacts}{' '}
              {totalFacts === 1 ? 'fact' : 'facts'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {savedFlash && (
            <span className="flex items-center gap-1 font-mono text-xs text-success">
              <Check className="h-3.5 w-3.5" /> saved
            </span>
          )}
          <button
            type="button"
            onClick={() => setRawMode((v) => !v)}
            className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 font-mono text-xs transition-colors ${
              rawMode
                ? 'border-accent bg-accent/15 text-accent'
                : 'border-border bg-surface2 text-muted hover:text-text'
            }`}
            title="Inspecteur dev : objets bruts du store"
          >
            <Code2 className="h-3.5 w-3.5" />
            Raw
          </button>
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading || !hasUser}
            className="flex items-center gap-1.5 rounded-md border border-border bg-surface2 px-2.5 py-1.5 font-mono text-xs text-muted transition-colors hover:text-text disabled:opacity-40"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`}
            />
            Refresh
          </button>
        </div>
      </header>

      {!hasUser ? (
        <div className="px-4 py-8 text-center">
          <p className="font-mono text-sm text-muted">
            Sélectionne un utilisateur pour voir sa mémoire longue durée.
          </p>
        </div>
      ) : rawMode ? (
        <div className="px-4 py-3">
          <p className="mb-3 font-mono text-xs text-muted">
            Inspecteur dev — objets exacts stockés dans le SqliteStore
            (namespace <code className="text-accent">users/profile/&#123;user_id&#125;</code>,
            clé <code className="text-accent">facts</code>).
          </p>
          <pre className="max-h-96 overflow-auto rounded-lg border border-border bg-surface2 p-3 font-mono text-xs leading-relaxed text-text/90">
{JSON.stringify(overview, null, 2)}
          </pre>
        </div>
      ) : (
        <div className="px-4 py-4">
          {/* --- Identity (profil v2) --- */}
          <div className="mb-4 rounded-lg border border-border bg-surface2 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-xs font-semibold uppercase tracking-wider text-muted">
                Identity · Name
              </span>
              <button
                type="button"
                onClick={startEditProfile}
                className="flex items-center gap-1 rounded p-1 text-muted transition-colors hover:text-accent"
                title="Modifier le profil"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </div>
            {editingProfile ? (
              <div className="space-y-2">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Nom"
                  className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-sm text-text placeholder:text-muted/50 focus:border-accent focus:outline-none"
                />
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Description"
                  rows={2}
                  className="w-full resize-none rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-sm text-text placeholder:text-muted/50 focus:border-accent focus:outline-none"
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setEditingProfile(false)}
                    className="rounded-md border border-border px-2.5 py-1 font-mono text-xs text-muted hover:text-text"
                  >
                    Annuler
                  </button>
                  <button
                    type="button"
                    onClick={saveProfile}
                    disabled={savingProfile}
                    className="flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 font-mono text-xs text-white disabled:opacity-50"
                  >
                    {savingProfile ? '…' : <Check className="h-3.5 w-3.5" />}
                    Save
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-1.5">
                <p className="font-mono text-sm text-text">
                  {overview?.identity.name ?? (
                    <span className="text-muted/60">
                      (aucun nom enregistré)
                    </span>
                  )}
                </p>
                {overview?.identity.description && (
                  <p className="font-mono text-xs leading-relaxed text-muted">
                    {overview.identity.description}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* --- Filtres par catégorie --- */}
          <div className="mb-3 flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => setFilter('all')}
              className={`rounded-full px-2.5 py-1 font-mono text-xs transition-colors ${
                filter === 'all'
                  ? 'bg-accent text-white'
                  : 'bg-surface2 text-muted hover:text-text'
              }`}
            >
              all · {totalFacts}
            </button>
            {MEMORY_CATEGORIES.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setFilter(c)}
                className={`rounded-full px-2.5 py-1 font-mono text-xs transition-colors ${
                  filter === c
                    ? 'bg-accent text-white'
                    : 'bg-surface2 text-muted hover:text-text'
                }`}
              >
                {CATEGORY_LABELS[c].toLowerCase()} ·{' '}
                {factsByCat[c]?.length ?? 0}
              </button>
            ))}
          </div>

          {/* --- Faits par catégorie --- */}
          <div className="space-y-4">
            {cats.length === 0 && (
              <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center font-mono text-sm text-muted">
                Aucun fait enregistré. L'agent enregistre uniquement les
                informations que tu déclares explicitement sur toi
                (nom, formation, préférences, centres d'intérêt…) — ou
                ajoute-en un ci-dessous.
              </p>
            )}
            {cats.map((cat) => {
              const facts = factsByCat[cat] ?? [];
              return (
                <div key={cat}>
                  <div className="mb-1.5 flex items-center justify-between">
                    <h3 className="font-mono text-xs font-semibold uppercase tracking-wider text-muted">
                      {CATEGORY_LABELS[cat]}
                    </h3>
                    <span className="font-mono text-xs text-muted/70">
                      {facts.length}
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    <AnimatePresence initial={false}>
                      {facts.map((fact) => (
                        <motion.li
                          key={fact.id}
                          layout
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, x: -8 }}
                          className="group flex items-start justify-between gap-2 rounded-lg border border-border bg-surface2 px-3 py-2"
                        >
                          {editingId === fact.id ? (
                            <div className="flex w-full items-center gap-2">
                              <input
                                value={editContent}
                                onChange={(e) =>
                                  setEditContent(e.target.value)
                                }
                                className="flex-1 rounded-md border border-border bg-surface px-2 py-1 font-mono text-sm text-text focus:border-accent focus:outline-none"
                                autoFocus
                              />
                              <button
                                type="button"
                                onClick={saveEditFact}
                                disabled={savingEdit}
                                className="rounded p-1 text-success hover:bg-surface"
                              >
                                <Check className="h-4 w-4" />
                              </button>
                              <button
                                type="button"
                                onClick={() => setEditingId(null)}
                                className="rounded p-1 text-muted hover:bg-surface"
                              >
                                <X className="h-4 w-4" />
                              </button>
                            </div>
                          ) : (
                            <>
                              <span className="font-mono text-sm leading-relaxed text-text">
                                {fact.content}
                              </span>
                              <span className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                                <button
                                  type="button"
                                  onClick={() => startEditFact(fact)}
                                  className="rounded p-1 text-muted hover:text-accent"
                                  title="Modifier ce fait"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => removeFact(fact.id)}
                                  className="rounded p-1 text-muted hover:text-error"
                                  title="Supprimer ce fait"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </span>
                            </>
                          )}
                        </motion.li>
                      ))}
                    </AnimatePresence>
                  </ul>
                </div>
              );
            })}
          </div>

          {/* --- Ajout manuel --- */}
          {adding ? (
            <div className="mt-4 space-y-2 rounded-lg border border-border bg-surface2 p-3">
              <div className="flex gap-2">
                <select
                  value={newCategory}
                  onChange={(e) =>
                    setNewCategory(e.target.value as MemoryCategory)
                  }
                  className="rounded-md border border-border bg-surface px-2 py-1.5 font-mono text-xs text-text focus:border-accent focus:outline-none"
                >
                  {MEMORY_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {CATEGORY_LABELS[c]}
                    </option>
                  ))}
                </select>
                <input
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addFact()}
                  placeholder="Nouveau fait (ex: Aime la robotique)"
                  className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-sm text-text placeholder:text-muted/50 focus:border-accent focus:outline-none"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setAdding(false);
                    setNewContent('');
                  }}
                  className="rounded-md border border-border px-2.5 py-1 font-mono text-xs text-muted hover:text-text"
                >
                  Annuler
                </button>
                <button
                  type="button"
                  onClick={addFact}
                  disabled={savingFact || !newContent.trim()}
                  className="flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 font-mono text-xs text-white disabled:opacity-50"
                >
                  {savingFact ? '…' : <Check className="h-3.5 w-3.5" />}
                  Ajouter
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border px-3 py-2.5 font-mono text-xs text-muted transition-colors hover:border-accent hover:text-accent"
            >
              <Plus className="h-3.5 w-3.5" />
              Ajouter un fait
            </button>
          )}
        </div>
      )}
    </section>
  );
}
