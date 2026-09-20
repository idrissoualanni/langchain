import { ComposerPrimitive } from "@assistant-ui/react";
import { cn } from '@/lib/utils';

export function AttachButton() {
  return (
    <ComposerPrimitive.Attach asChild>
      <button type="button" className="rounded-md bg-muted px-2 py-1 text-sm">
        📎
      </button>
    </ComposerPrimitive.Attach>
  );
}
