// Couche d'adaptation Assistant UI — Tool UIs (renderers de tool-call)
//
// Assistant UI rend chaque tool-call via part.toolUI (enregistré par
// useAssistantToolUI) ou le ToolFallback par défaut. Chaque renderer
// produit une carte pliante ToolCall dédiée à un outil backend.
'use client';

import { useState } from 'react';
import {
  useAssistantToolUI,
  type ToolCallMessagePartComponent,
} from '@assistant-ui/react';
import { ToolCall } from '@/components/assistant-ui/elements/tool-call';

type SearchDocsResult = { count: number; bestPath: string };

export const SearchDocsToolUI: ToolCallMessagePartComponent<
  { query: string },
  SearchDocsResult
> = ({ args, argsText, result, status }) => {
  const [open, setOpen] = useState(false);
  return (
    <ToolCall
      label="Searched the docs"
      activeLabel="Searching the docs"
      query={args.query ?? ''}
      request={argsText}
      result={
        result
          ? typeof result === 'string'
            ? result
            : `${result.count} matches, best hit ${result.bestPath}`
          : ''
      }
      running={status.type === 'running'}
      open={open}
      onOpenChange={setOpen}
    />
  );
};

/** Enregistre les Tool UIs tant qu'il est monté.
 *  À appeler DANS l'arbre AssistantRuntimeProvider (cf. AssistantPage). */
export function useToolUIs() {
  useAssistantToolUI({
    toolName: 'search_documents',
    render: SearchDocsToolUI,
  });
}