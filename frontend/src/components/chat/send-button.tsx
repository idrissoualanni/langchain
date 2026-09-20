"use client";

import { ComposerPrimitive } from "@assistant-ui/react";

/** Simple Send button used in the Composer.
 * Wraps the ComposerPrimitive.Send primitive to trigger a submission.
 */
export function SendButton() {
  return (
    <ComposerPrimitive.Send asChild>
      <button
        type="button"
        className="rounded-md bg-primary px-4 py-2 text-white hover:bg-primary/90 focus:outline-none"
        aria-label="Envoyer le message"
      >
        Envoyer
      </button>
    </ComposerPrimitive.Send>
  );
}
