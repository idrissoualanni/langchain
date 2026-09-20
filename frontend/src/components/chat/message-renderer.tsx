"use client";

import { MessagePrimitive } from "@assistant-ui/react";
import { Sources } from "@/components/assistant-ui/elements/sources.aui";
import { TextMessagePart } from "./text-message-part";
import { ResearchCard } from "./cards/research-card";
import { VideoCard } from "./cards/video-card";
import { ProblemArtifact } from "./cards/problem-artifact";

/**
 * Composant principal de rendu des messages.
 * Délègue l'affichage aux composants spécialisés selon le type de contenu.
 */
export function MessageRenderer() {
  return (
    <MessagePrimitive.Root className="flex flex-col gap-4 my-4">
      {/* En-tête du message (Auteur) */}
      <div className="flex items-center gap-2 px-1">
        <MessagePrimitive.If assistant>
          <span className="text-sm font-semibold text-muted-foreground">
            Assistant
          </span>
        </MessagePrimitive.If>
        <MessagePrimitive.If user>
          <span className="text-sm font-semibold">Vous</span>
        </MessagePrimitive.If>
      </div>

      {/* Corps du message avec gestion des parties riches */}
      <div className="pl-10 max-w-[85%]">
        <MessagePrimitive.Parts
          components={{
            // Rendu du texte standard (Markdown supporté)
            Text: TextMessagePart,

            // Rendu des sources (citations, références)
            Source: Sources,

            // Rendu des contenus structurés (Custom Data Parts)
            // Ces parties sont injectées par le backend via les data parts du message
            data: {
              by_name: {
                ResearchResult: (part) => <ResearchCard {...part.data} />,
                VideoContent: (part) => <VideoCard {...part.data} />,
                ProblemSolution: (part) => <ProblemArtifact {...part.data} />,
              },
              // Fallback pour les types inconnus
              Fallback: (part) => (
                <div className="p-3 bg-muted rounded-md text-sm text-muted-foreground">
                  Contenu non supporté : {part.name}
                </div>
              ),
            },
          }}
        />
      </div>
    </MessagePrimitive.Root>
  );
}