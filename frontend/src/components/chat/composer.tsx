"use client";

import { ComposerPrimitive } from "@assistant-ui/react";
import { SendButton } from "./send-button";
import { AttachButton } from "./attach-button";
import { useComposerMentions } from "@/hooks/use-composer-mentions";

export function Composer() {
  const { adapter, directive } = useComposerMentions();

  return (
    <ComposerPrimitive.Unstable_TriggerPopoverRoot>
      <ComposerPrimitive.Unstable_TriggerPopover char="@" adapter={adapter}>
        <ComposerPrimitive.Unstable_TriggerPopover.Directive
          formatter={directive.formatter}
          onInserted={directive.onInserted}
        />
      </ComposerPrimitive.Unstable_TriggerPopover>

      <ComposerPrimitive.Root className="flex items-end gap-2 p-2 rounded-xl border bg-background shadow-sm focus-within:ring-2 focus-within:ring-primary/50 transition-all">
        <ComposerPrimitive.Input
          className="flex-1 max-h-32 min-h-[44px] resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground"
          placeholder="Posez une question ou tapez @ pour un mode spécial..."
        />

        <AttachButton />
        <SendButton />
      </ComposerPrimitive.Root>
    </ComposerPrimitive.Unstable_TriggerPopoverRoot>
  );
}