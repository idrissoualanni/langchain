"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CheckCircle2, CircleDashed, AlertTriangle, FileCheck, Lightbulb } from "lucide-react";

interface ProblemStep {
  step_number: number;
  description: string;
  user_answer?: string;
  is_correct?: boolean;
  feedback?: string;
}

interface ProblemArtifactProps {
  problem_statement: string;
  subject: string;
  steps: ProblemStep[];
  final_solution?: string;
  rigor_score?: number; // 0-100
  status: "in_progress" | "completed" | "needs_help";
}

/**
 * Artefact de résolution de problème mathématique/scientifique.
 * Affiche l'énoncé, les étapes de résolution, la validation et le score de rigueur.
 */
export function ProblemArtifact({ 
  problem_statement, 
  subject, 
  steps, 
  final_solution, 
  rigor_score, 
  status 
}: ProblemArtifactProps) {
  return (
    <Card className="w-full max-w-3xl border-l-4 border-l-indigo-500 shadow-md">
      <CardHeader className="pb-2 bg-indigo-50/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileCheck className="h-5 w-5 text-indigo-600" />
            <div>
              <CardTitle className="text-lg text-indigo-900">Résolution de Problème</CardTitle>
              <p className="text-xs text-indigo-700 font-medium uppercase tracking-wide">{subject}</p>
            </div>
          </div>
          {rigor_score !== undefined && status === "completed" && (
            <div className="text-right">
              <div className="text-2xl font-bold text-indigo-600">{rigor_score}%</div>
              <div className="text-[10px] uppercase tracking-wider text-indigo-500">Score de Rigueur</div>
            </div>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-6 p-6">
        {/* Énoncé du problème */}
        <div className="p-4 bg-white rounded-md border shadow-sm">
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Énoncé :</h4>
          <p className="text-gray-900 leading-relaxed">{problem_statement}</p>
        </div>

        {/* Étapes de résolution */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <CircleDashed className="h-4 w-4" />
            Étapes de Résolution
          </h4>
          
          <ScrollArea className="h-64 w-full rounded-md border p-3 bg-muted/20">
            <div className="space-y-4">
              {steps.map((step, idx) => (
                <div key={idx} className="relative pl-8 pb-4 border-l-2 border-gray-200 last:border-0">
                  {/* Indicateur de statut */}
                  <div className={`absolute -left-[9px] top-0 h-4 w-4 rounded-full border-2 ${
                    step.is_correct === true ? "bg-green-500 border-green-500" :
                    step.is_correct === false ? "bg-red-500 border-red-500" :
                    "bg-white border-gray-400"
                  }`}>
                    {step.is_correct === true && <CheckCircle2 className="h-3 w-3 text-white absolute -top-0.5 -left-0.5" />}
                    {step.is_correct === false && <AlertTriangle className="h-3 w-3 text-white absolute -top-0.5 -left-0.5" />}
                  </div>

                  <div className="space-y-1">
                    <div className="text-sm font-medium text-gray-800">
                      Étape {step.step_number}: {step.description}
                    </div>
                    
                    {step.user_answer && (
                      <div className="mt-2 p-2 bg-white rounded text-sm border">
                        <span className="text-xs text-muted-foreground block mb-1">Votre réponse :</span>
                        <code className="font-mono text-xs bg-muted px-1 py-0.5 rounded">
                          {step.user_answer}
                        </code>
                      </div>
                    )}

                    {step.feedback && (
                      <div className={`mt-2 p-2 rounded text-xs flex gap-2 ${
                        step.is_correct === true ? "bg-green-50 text-green-800" :
                        step.is_correct === false ? "bg-red-50 text-red-800" :
                        "bg-blue-50 text-blue-800"
                      }`}>
                        <Lightbulb className="h-3 w-3 flex-shrink-0 mt-0.5" />
                        <span>{step.feedback}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* Solution Finale (si terminée) */}
        {final_solution && status === "completed" && (
          <div className="mt-4 p-4 bg-indigo-50 rounded-md border border-indigo-100">
            <h4 className="text-sm font-semibold text-indigo-900 mb-2">Solution Finale :</h4>
            <div className="p-3 bg-white rounded font-mono text-sm text-gray-800 overflow-x-auto">
              {final_solution}
            </div>
          </div>
        )}

        {/* Statut global */}
        {status === "needs_help" && (
          <div className="p-3 bg-amber-50 border border-amber-200 rounded-md text-amber-800 text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            <span>Certaines étapes nécessitent une révision. Continuez à essayer ou demandez un indice.</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
