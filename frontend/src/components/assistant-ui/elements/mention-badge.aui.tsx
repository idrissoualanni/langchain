"use client";

import { XIcon } from "lucide-react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { COMPOSER_TERMS, hasComposerTerm } from "@/hooks/use-composer-mentions";

/** Badge du terme @ actif dans le composer — retire le terme au clic. */
export function MentionBadge() {
  const text = useAuiState((s) => s.composer.text);
  const aui = useAui();
  const termId = (() => {
    if (!hasComposerTerm(text ?? "")) return null;
    const m = (text ?? "").match(/@([a-z][a-z0-9-]*)/i);
    return m ? m[1].toLowerCase() : null;
  })();
  const term = COMPOSER_TERMS.find((t) => t.id === termId);
  if (!term) return null;

  const remove = () => {
    const next = (text ?? "").replace(new RegExp(`@${term.id}\\b`, "gi"), " ").replace(/[ \t]+/g, " ").trim();
    aui.composer.setText(next);
  };

  return (
    <div className="flex items-center gap-1.5 rounded-full border border-border bg-muted px-2 py-1 text-xs">
      <span aria-hidden>{term.icon}</span>
      <span className="font-medium">{term.label}</span>
      <button type="button" onClick={remove} aria-label={`Retirer ${term.label}`} className="rounded-full p-0.5 hover:bg-foreground/10">
        <XIcon className="size-3" />
      </button>
    </div>
  );
}
