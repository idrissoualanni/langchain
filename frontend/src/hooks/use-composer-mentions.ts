"use client";

import { unstable_useMentionAdapter } from "@assistant-ui/react";

/**
 * Hook pour gérer les mentions intelligentes dans le Composer.
 * Permet de déclencher des workflows spécifiques via @mention.
 */
export function useComposerMentions() {
  return unstable_useMentionAdapter({
    items: [
      {
        id: "deep-research",
        type: "research-mode",
        label: "Deep Research",
        description: "Recherche approfondie multi-sources avec analyse critique",
        icon: "🔬",
      },
      {
        id: "academic-search",
        type: "research-mode",
        label: "Recherche Académique",
        description: "Priorité aux articles scientifiques et publications",
        icon: "🎓",
      },
      {
        id: "news-search",
        type: "research-mode",
        label: "Actualités Récentes",
        description: "Sources d'actualité des dernières 48h",
        icon: "📰",
      },
      {
        id: "video",
        type: "workflow-trigger",
        label: "Vidéo",
        description: "Interagir avec une vidéo (transcription, segments)",
        icon: "🎥",
      },
      {
        id: "agenda",
        type: "mcp-tool",
        label: "Agenda",
        description: "Vérifier disponibilités ou créer un événement (Google Calendar)",
        icon: "📅",
      },
      {
        id: "code",
        type: "workflow-trigger",
        label: "Coding Session",
        description: "Démarrer une session de codage assisté avec sandbox",
        icon: "💻",
      },
      {
        id: "exercise",
        type: "activity",
        label: "Exercice",
        description: "Suggestion d'activité d'exercice (ACTIVITY_TYPE_EXERCISE)",
        icon: "🧩",
      },
    ],
  });
}
