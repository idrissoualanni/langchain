"use client";

import { ComposerPrimitive, useLocalRuntime } from "@assistant-ui/react";
import { SendButton } from "./send-button";
import { AttachButton } from "./attach-button";
import { useComposerMentions } from "@/hooks/use-composer-mentions";
import { useState } from "react";

// Modèle factice pour l'exemple (à connecter à votre API réelle)
const mockChatModel = {
  run: async function* (messages: any[]) {
    yield { role: "assistant", content: "Réponse simulée..." };
  },
};

export function Composer() {
  const { mentionInputProps, suggestionsProps } = useComposerMentions();
  const [isSuggestionsOpen, setIsSuggestionsOpen] = useState(false);

  // Note: Dans une vraie implémentation, remplacez mockChatModel par votre hook d'appel API
  // const runtime = useLocalRuntime(realChatModel, { adapters: { ... } });

  return (
    <div className="relative w-full">
      <ComposerPrimitive.Root
        className="flex items-end gap-2 p-2 rounded-xl border bg-background shadow-sm focus-within:ring-2 focus-within:ring-primary/50 transition-all"
        {...mentionInputProps}
      >
        <ComposerPrimitive.Input
          className="flex-1 max-h-32 min-h-[44px] resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground"
          placeholder="Posez une question ou tapez @ pour un mode spécial..."
          onFocus={() => setIsSuggestionsOpen(true)}
          onBlur={() => setTimeout(() => setIsSuggestionsOpen(false), 200)}
          {...suggestionsProps.inputProps}
        />

        {/* Dropdown des suggestions de mentions */}
        {suggestionsProps.isOpen && isSuggestionsOpen && (
          <div className="absolute bottom-full left-0 mb-2 w-72 max-h-80 overflow-auto rounded-md border bg-popover text-popover-foreground shadow-lg z-50 animate-in fade-in slide-in-from-bottom-2">
            <div className="p-2 text-xs font-semibold text-muted-foreground border-b">
              Modes & Workflows
            </div>
            {suggestionsProps.items.map((item) => (
              <button
                key={item.key}
                className="w-full px-3 py-2.5 text-left hover:bg-accent flex items-start gap-3 rounded-sm transition-colors"
                onClick={() => suggestionsProps.onSelect(item)}
              >
                <span className="text-lg">{item.icon}</span>
                <div className="flex-1">
                  <div className="font-medium text-sm">{item.label}</div>
                  <div className="text-xs text-muted-foreground line-clamp-1">
                    {item.description}
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}

        <AttachButton />
        <SendButton />
      </ComposerPrimitive.Root>
    </div>
  );
}
