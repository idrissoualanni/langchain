"use client";

import { MessagePrimitive } from "@assistant-ui/react";
import { Sources } from "@/components/assistant-ui/elements/sources.aui";
import { TextMessagePart } from "./text-message-part";
import { ResearchCard } from "./cards/research-card";
import { VideoCard } from "./cards/video-card";
import { ProblemArtifact } from "./cards/problem-artifact";
import { TTSReadAloud } from "./TTSReadAloud";

/**
 * Extracteur de texte pour le TTS.
 * Récupère le texte des parties de message.
 */
function getMessageText(content: any): string {
    if (typeof content === "string") return content;
    if (Array.isArray(content)) {
        return content.map(getMessageText).filter(Boolean).join(" ");
    }
    if (content && typeof content === "object") {
        if (content.text) return content.text;
        if (content.content) return getMessageText(content.content);
    }
    return "";
}

/**
 * Composant principal de rendu des messages.
 * Délègue l'affichage aux composants spécialisés selon le type de contenu.
 */
export function MessageRenderer() {
    // État pour le texte du dernier message assistant (pour TTS)
    const [lastAssistantText, setLastAssistantText] = React.useState("");

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
                        Text: (props) => {
                            // Dans cette version d'assistant-ui, le
                            // composant Text reçoit directement la
                            // TextMessagePart ( props.text / props.status ).
                            const text = getMessageText(props.text);
                            // Stocker le texte pour le TTS quand c'est un message assistant
                            React.useEffect(() => {
                                if (text) {
                                    setLastAssistantText(text);
                                }
                            }, [text]);
                            return <TextMessagePart text={props.text} status={props.status} type="text" />;
                        },

                        // Rendu des sources (citations, références)
                        Source: Sources,

                        // Rendu des contenus structurés (Custom Data Parts)
                        data: {
                            by_name: {
                                ResearchResult: (part) => <ResearchCard {...part.data} />,
                                VideoContent: (part) => <VideoCard {...part.data} />,
                                ProblemSolution: (part) => <ProblemArtifact {...part.data} />,
                            },
                            Fallback: (part) => (
                                <div className="p-3 bg-muted rounded-md text-sm text-muted-foreground">
                                    Contenu non supporté : {part.name}
                                </div>
                            ),
                        },
                    }}
                />
            </div>

            {/* Actions du message — TTS pour les messages assistant */}
            <MessagePrimitive.If assistant>
                <div className="flex items-center justify-end gap-2 pr-4">
                    <TTSReadAloud text={lastAssistantText} size="sm" variant="ghost" />
                </div>
            </MessagePrimitive.If>
        </MessagePrimitive.Root>
    );
}

// Add React import for useEffect
import * as React from "react";