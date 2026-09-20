"use client";

// Rendu des diagrammes Mermaid (spec FUNCTIONALITIES.md §18).
// Le backend produit du code mermaid brut dans ses réponses ; ce composant
// transforme ce code en SVG via l'API mermaid (render est async en v11).
//
// - mermaid.initialize() est appelé une seule fois par thème (le thème est
//   figé à l'initialisation, il faut donc ré-initialiser au switch clair/sombre).
// - useTheme() est le hook projet (@/hooks/useTheme), pas next-themes.
// - En cas d'erreur de parsing, on affiche le code brut + le message d'erreur
//   plutôt que de planter le rendu markdown de tout le message.

import mermaid from "mermaid";
import {
  type FC,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

export type MermaidDiagramProps = {
  /** Code mermaid brut (ex: "graph TB\nA-->B"). */
  chart: string;
  className?: string;
};

// mermaid fige le thème à l'initialisation : on garde une trace module-level
// pour ne ré-initialiser que lorsqu'il change vraiment.
let initializedTheme: "default" | "dark" | null = null;

// Les valeurs de thème mermaid sont 'default' | 'base' | 'dark' | ... ;
// 'light' n'existe pas — 'default' est le thème clair.
const toMermaidTheme = (resolved: string): "default" | "dark" =>
  resolved === "dark" ? "dark" : "default";

const describeError = (e: unknown): string => {
  if (e instanceof Error) return e.message;
  return typeof e === "string" ? e : "Erreur de rendu mermaid inconnue";
};

export const MermaidDiagram: FC<MermaidDiagramProps> = ({ chart, className }) => {
  const { resolvedTheme } = useTheme();
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Id unique par instance : mermaid en a besoin pour l'élément SVG cible.
  const reactId = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const code = chart?.trim();
    if (!code) return;

    // La requête est annulable : si le composant est démonté ou que le
    // code/thème change avant la fin du render async, on ignore le résultat.
    let cancelled = false;

    const mermaidTheme = toMermaidTheme(resolvedTheme);
    if (initializedTheme !== mermaidTheme) {
      mermaid.initialize({ startOnLoad: false, theme: mermaidTheme });
      initializedTheme = mermaidTheme;
    }

    // Les ids mermaid ne supportent pas les ":" issus de useId() (id SVG)
    // ni les caractères interdits dans un sélecteur CSS.
    const diagramId = `mermaid-${reactId.replace(/[^a-zA-Z0-9-]/g, "")}`;

    mermaid
      .render(diagramId, code)
      .then(({ svg, bindFunctions }) => {
        if (cancelled) return;
        setSvg(svg);
        setError(null);
        // Diagrammes interactifs (clics de nœuds, liens) : on branche les
        // écouteurs générés par mermaid sur le conteneur.
        if (bindFunctions && containerRef.current) {
          bindFunctions(containerRef.current);
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setSvg(null);
        setError(describeError(e));
      });

    return () => {
      cancelled = true;
    };
  }, [chart, resolvedTheme, reactId]);

  // Erreur de parsing : on affiche le code brut + le message.
  if (error) {
    return (
      <pre
        className={cn(
          "aui-md-pre border-border/50 bg-muted/30 overflow-x-auto rounded-t-none rounded-b-xl border border-t-0 p-3.5 text-[13px] leading-relaxed",
          className,
        )}
      >
        <code>{chart}</code>
        <span className="text-muted-foreground mt-2 block text-xs">
          Diagramme mermaid invalide : {error}
        </span>
      </pre>
    );
  }

  // Premier rendu (SVG pas encore prêt) : placeholder discret.
  const inner: ReactNode = svg ? (
    <div
      ref={containerRef}
      className="aui-mermaid flex justify-center overflow-x-auto py-4 [&>svg]:max-w-full [&>svg]:h-auto"
      // Le SVG est généré par mermaid (bibliothèque de confiance) : on l'injecte
      // directement. Le code source provient du backend/model, mais mermaid
      // génère du SVG et lève sur les définitions invalides (géré ci-dessus).
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  ) : (
    <div className="text-muted-foreground flex justify-center py-6 text-xs">
      Rendu du diagramme…
    </div>
  );

  return (
    <div
      className={cn(
        "aui-mermaid-root border-border/50 bg-muted/30 rounded-b-xl border border-t-0",
        className,
      )}
    >
      {inner}
    </div>
  );
};

MermaidDiagram.displayName = "MermaidDiagram";
