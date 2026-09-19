"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ExternalLink, FileText, CheckCircle2, AlertCircle } from "lucide-react";

interface Source {
  url: string;
  title: string;
  snippet?: string;
  relevance?: number;
}

interface ResearchCardProps {
  query: string;
  summary: string;
  sources: Source[];
  status: "completed" | "in_progress" | "failed";
  confidence?: number;
}

/**
 * Carte affichant les résultats d'une recherche approfondie (Deep Research).
 * Inclut le résumé, les sources citées et le niveau de confiance.
 */
export function ResearchCard({ query, summary, sources, status, confidence }: ResearchCardProps) {
  return (
    <Card className="w-full max-w-2xl border-l-4 border-l-blue-500 shadow-md">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-blue-500" />
            <CardTitle className="text-lg">Rapport de Recherche</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {status === "completed" && (
              <Badge variant="default" className="bg-green-100 text-green-800">
                <CheckCircle2 className="h-3 w-3 mr-1" />
                Terminé
              </Badge>
            )}
            {status === "in_progress" && (
              <Badge variant="secondary" className="animate-pulse">
                En cours...
              </Badge>
            )}
            {status === "failed" && (
              <Badge variant="destructive">
                <AlertCircle className="h-3 w-3 mr-1" />
                Échec
              </Badge>
            )}
            {confidence !== undefined && (
              <Badge variant="outline" className="text-xs">
                Confiance: {(confidence * 100).toFixed(0)}%
              </Badge>
            )}
          </div>
        </div>
        <p className="text-sm text-muted-foreground mt-1">Requête: "{query}"</p>
      </CardHeader>
      
      <CardContent className="space-y-4">
        {/* Résumé exécutif */}
        <div className="p-3 bg-muted/50 rounded-md text-sm leading-relaxed">
          {summary}
        </div>

        {/* Liste des sources */}
        {sources.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Sources ({sources.length})
            </h4>
            <ScrollArea className="h-32 w-full rounded-md border p-2">
              <ul className="space-y-2">
                {sources.map((source, idx) => (
                  <li key={idx} className="text-sm group">
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-start gap-2 hover:text-primary transition-colors"
                    >
                      <ExternalLink className="h-3 w-3 mt-1 flex-shrink-0 text-muted-foreground group-hover:text-primary" />
                      <div>
                        <div className="font-medium line-clamp-1">{source.title}</div>
                        {source.snippet && (
                          <div className="text-xs text-muted-foreground line-clamp-2">
                            {source.snippet}
                          </div>
                        )}
                      </div>
                    </a>
                  </li>
                ))}
              </ul>
            </ScrollArea>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
