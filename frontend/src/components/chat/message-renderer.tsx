"use client";

import { MessagePrimitive, useMessage } from "@assistant-ui/react";
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
  const { message } = useMessage();

  return (
    <MessagePrimitive.Root className="flex flex-col gap-4 my-4">
      {/* En-tête du message (Avatar, Nom, Timestamp) */}
      <div className="flex items-center gap-2 px-1">
        <MessagePrimitive.Avatar className="h-8 w-8 rounded-full" />
        <MessagePrimitive.AuthorName className="text-sm font-semibold" />
        <MessagePrimitive.CreatedAt className="text-xs text-muted-foreground" />
      </div>

      {/* Corps du message avec gestion des parties riches */}
      <div className="pl-10 max-w-[85%]">
        <MessagePrimitive.Parts
          components={{
            // Rendu du texte standard (Markdown supporté)
            Text: TextMessagePart,
            
            // Rendu des sources (citations, références)
            Source: Sources,
            
            // Rendu des contenus structurés (Custom Parts)
            // Ces parties sont injectées par le backend via le metadata du message
            ResearchResult: ({ data }: any) => <ResearchCard {...data} />,
            VideoContent: ({ data }: any) => <VideoCard {...data} />,
            ProblemSolution: ({ data }: any) => <ProblemArtifact {...data} />,
            
            // Fallback pour les types inconnus
            Unknown: ({ type, content }: any) => (
              <div className="p-3 bg-muted rounded-md text-sm text-muted-foreground">
                Contenu non supporté : {type}
              </div>
            ),
          }}
        />
      </div>
    </MessagePrimitive.Root>
  );
}
