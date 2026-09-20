// /settings/memory — aperçu de la mémoire longue durée (lecture).
// L'édition complète (faits, profil) reste sur /memory.
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Database, ExternalLink } from 'lucide-react';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { getMemoryOverview } from '../../api/memory';
import type { MemoryOverview } from '../../types/agent';
import { CATEGORY_LABELS, type MemoryCategory } from '../../types/agent';
import {
  EmptyState,
  PageHeader,
  StatTile,
  Surface,
  SurfaceBody,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';

export function SettingsMemoryPage() {
  const { internal } = useCurrentUser();
  const userId = internal?.user_id ?? null;
  const [overview, setOverview] = useState<MemoryOverview | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    setLoading(true);
    getMemoryOverview(userId)
      .then((o) => {
        if (alive) setOverview(o);
      })
      .catch(() => {
        if (alive) setOverview(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [userId]);

  const total = overview?.total_facts ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="settings · memory"
        title="Mémoire"
        description="Ce que l’application retient de vous, par catégorie."
        actions={
          <Link
            to="/memory"
            className="border-border bg-background hover:bg-muted inline-flex items-center gap-2 rounded-[var(--radius-control)] border px-3 py-1.5 text-[12.5px] font-medium"
          >
            <ExternalLink size={13} /> Gérer la mémoire
          </Link>
        }
      />

      <div className="max-w-3xl space-y-5 p-6">
        {loading ? (
          <Surface>
            <EmptyState icon={Database} title="Chargement…" />
          </Surface>
        ) : !overview || total === 0 ? (
          <Surface>
            <EmptyState
              icon={Database}
              title="Aucune donnée disponible pour le moment."
              description="Aucun souvenir n’a encore été enregistré pour votre compte."
            />
          </Surface>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <StatTile label="souvenirs" value={total} />
              <StatTile
                label="catégories"
                value={overview.categories.length}
              />
            </div>

            <Surface>
              <SurfaceHeader>
                <SurfaceTitle>Par catégorie</SurfaceTitle>
              </SurfaceHeader>
              <SurfaceBody className="space-y-4">
                {overview.categories.map((cat) => {
                  const facts = overview.facts_by_category[cat] ?? [];
                  if (facts.length === 0) return null;
                  return (
                    <div key={cat}>
                      <div className="text-muted-foreground font-mono text-[10px] uppercase">
                        {CATEGORY_LABELS[cat as MemoryCategory] ?? cat}
                      </div>
                      <ul className="mt-1 space-y-1">
                        {facts.map((f) => (
                          <li
                            key={f.id}
                            className="text-foreground text-[12.5px]"
                          >
                            {f.content}
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </SurfaceBody>
            </Surface>
          </>
        )}
      </div>
    </>
  );
}
