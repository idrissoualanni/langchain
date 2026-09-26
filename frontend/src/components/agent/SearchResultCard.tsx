// SearchResultCard V6.7 — sources d'une réponse search (§24/§31).
// Affiche title/source/url/snippet — JAMAIS source_quality ni
// scores internes (réservés au Context Inspector §32).
// Le texte de la réponse est rendu par le part text officiel ;
// cette carte n'affiche que les sources structurées.
import { motion } from 'framer-motion';
import { BookOpen, ExternalLink } from 'lucide-react';
import type { SearchData } from '../../types/agentResponse';

export function SearchResultCard({ data }: { data: SearchData }) {
  const results = data.results ?? [];
  if (results.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="mb-2 flex items-center gap-2">
        <BookOpen size={13} className="text-muted-foreground" />
        <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
          sources
        </span>
      </div>
      <div className="space-y-1.5">
        {results.map((r, i) => (
          <a
            key={i}
            href={r.url ?? undefined}
            target="_blank"
            rel="noopener noreferrer"
            className={`block rounded-[var(--radius-control)] border border-border bg-card px-3 py-2 transition-colors hover:border-live/40 ${
              r.url ? '' : 'pointer-events-none'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="truncate text-[12px] font-medium text-foreground/90">
                {r.title || r.source}
              </span>
              {r.url && (
                <ExternalLink
                  size={11}
                  className="shrink-0 text-muted-foreground"
                />
              )}
            </div>
            <div className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
              {r.source}
              {r.url ? ` · ${r.url}` : ''}
            </div>
            {r.snippet && (
              <div className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-muted-foreground">
                {r.snippet}
              </div>
            )}
          </a>
        ))}
      </div>
    </motion.div>
  );
}
