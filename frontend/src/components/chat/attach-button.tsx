import { ComposerPrimitive } from "@assistant-ui/react";

export function AttachButton() {
  return (
    <ComposerPrimitive.AddAttachment asChild>
      <button type="button" className="rounded-md bg-muted px-2 py-1 text-sm">
        📎
      </button>
    </ComposerPrimitive.AddAttachment>
  );
}