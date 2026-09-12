// SearchResultCard V6.7 — sources d'une réponse search (§24/§31).
// Affiche title/source/url/snippet — JAMAIS source_quality ni
// scores internes (réservés au Context Inspector §32).
import { motion } from 'framer-motion';
import { BookOpen, ExternalLink } from 'lucide-react';
import type { SearchData } from '../../types/agentResponse';

export function SearchResultCard({
  message,
  data,
}: {
  message: string;
  data: SearchData;
}) {
  const results = data.results ?? [];
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-3"
    >
      <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[#f5f7fa]/90">
        {message}
      </div>
      {results.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-2">
            <BookOpen size={13} className="text-[#94a3b8]" />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#94a3b8]">
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
                className={`block rounded-lg border border-[#26323d] bg-[#111820] px-3 py-2 transition-colors hover:border-[#6c63ff]/40 ${
                  r.url ? '' : 'pointer-events-none'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="truncate text-[12px] font-medium text-[#f5f7fa]/90">
                    {r.title || r.source}
                  </span>
                  {r.url && (
                    <ExternalLink
                      size={11}
                      className="shrink-0 text-[#94a3b8]"
                    />
                  )}
                </div>
                <div className="mt-0.5 truncate font-mono text-[10px] text-[#6b7a89]">
                  {r.source}
                  {r.url ? ` · ${r.url}` : ''}
                </div>
                {r.snippet && (
                  <div className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-[#94a3b8]">
                    {r.snippet}
                  </div>
                )}
              </a>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}
