"use client";

import { XIcon } from "lucide-react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { activeComposerTerm, removeComposerTerm } from "@/hooks/use-composer-mentions";

/** Badge du terme @ actif dans le composer — retire le terme au clic.
 *  Reconnaît le terme tapé (@id) comme celui choisi dans le popover
 *  (directive :mention[…]{name=id}). */
export function MentionBadge() {
  const text = useAuiState((s) => s.composer.text) ?? "";
  const aui = useAui();
  const term = activeComposerTerm(text);
  if (!term) return null;

  const remove = () => aui.composer.setText(removeComposerTerm(text, term.id));

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
