"use client";

import * as React from "react";
import { Mic, MicOff, Copy, Send, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTranscription } from "./useTranscription";
import { apiFetchRaw } from "@/api/base";

import { useAui } from "@assistant-ui/react";
import { useNavigate } from "react-router-dom";

interface TranscriptionPanelProps {
  /** Mode: standalone ou dictée (envoie vers le chat) */
  mode?: "standalone" | "dictate";
  /** Retourne à cette URL après dictée */
  returnTo?: string;
  /** Callback appelé quand l'utilisateur valide le texte */
  onTextConfirmed?: (text: string) => void;
}

export function TranscriptionPanel({
  mode = "standalone",
  returnTo = "/assistant",
  onTextConfirmed,
}: TranscriptionPanelProps) {
  const navigate = useNavigate();
  const aui = useAui();
  const [isUploading, setIsUploading] = React.useState(false);
  const [uploadError, setUploadError] = React.useState<string | null>(null);

  const handleTranscript = React.useCallback((_text: string, _isFinal: boolean) => {
    // Ne rien faire en temps réel, attendre validation
  }, []);

  const {
    isListening,
    transcript,
    startListening,
    stopListening,
    error: recognitionError,
  } = useTranscription({
    language: "fr-FR",
    onTranscript: handleTranscript,
  });

  const handleCopy = React.useCallback(() => {
    if (transcript) {
      navigator.clipboard.writeText(transcript);
    }
  }, [transcript]);

  const handleInsert = React.useCallback(() => {
    if (!transcript.trim()) return;

    if (mode === "dictate") {
      // Envoie vers le composer et retourne
      aui.composer.setText(transcript.trim());
      aui.composer.send();
      navigate(returnTo);
    } else if (onTextConfirmed) {
      onTextConfirmed(transcript.trim());
    }
  }, [transcript, mode, aui, navigate, returnTo, onTextConfirmed]);

  const handleClear = React.useCallback(() => {
    // Le transcript se vide automatiquement via le hook
  }, []);

  const handleFileUpload = React.useCallback(
    async (file: File) => {
      if (!file.type.startsWith("audio/")) {
        setUploadError("Veuillez sélectionner un fichier audio");
        return;
      }

      setIsUploading(true);
      setUploadError(null);

      try {
        const formData = new FormData();
        formData.append("file", file);

        // Appel à l'API backend pour transcription Deepgram.
        //
        // Auth : on passe par la couche centrale ( apiFetchRaw ). Avant,
        // l'en-tête était construit à la main avec
        // `Bearer ${window.__neonGetToken?.() || ""}` — or
        // __neonGetToken est une PROMISE : l'interpolation produisait
        // littéralement "Bearer [object Promise]", un header que le
        // backend rejette → 401 sur chaque upload. apiFetchRaw attend
        // le vrai jeton, et rejoue l'appel après un refresh si le 401
        // venait d'un JWT simplement expiré.
        const response = await apiFetchRaw("/api/transcription/transcribe", {
          method: "POST",
          body: formData,
        });

        // apiFetchRaw renvoie une Response et ne lève PAS ( contrairement
        // à apiFetch ) : c'est à l'appelant de tester `ok`. On ne se
        // contente donc pas d'un « Erreur HTTP: 401 » — un refus de
        // session affiché comme une panne de transcription envoie
        // l'utilisateur jouer avec son micro alors que le problème est
        // son authentification.
        if (!response.ok) {
          if (response.status === 401 || response.status === 403) {
            throw new Error(
              "Session refusée par le serveur (erreur " + response.status + "). Reconnecte-toi puis réessaie."
            );
          }
          throw new Error(
            "Transcription refusée par le serveur (erreur " + response.status + ")."
          );
        }

        // Le résultat sera affiché dans le transcript via le hook
        await response.json();
      } catch (e) {
        setUploadError(
          e instanceof Error ? e.message : "Erreur inconnue"
        );
      } finally {
        setIsUploading(false);
      }
    },
    []
  );

  return (
    <Card className="w-full max-w-md">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Mic className="h-5 w-5 text-primary" />
            Transcription vocale
          </CardTitle>
          <span
            className={`text-xs px-2 py-1 rounded-full ${
              isListening
                ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                : "bg-muted text-muted-foreground"
            }`}
          >
            {isListening ? "En écoute" : "Inactif"}
          </span>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Status et contrôles */}
        <div className="flex items-center justify-center gap-4">
          <Button
            variant={isListening ? "destructive" : "default"}
            size="lg"
            onClick={isListening ? stopListening : startListening}
            className="rounded-full h-14 w-14"
          >
            {isListening ? (
              <MicOff className="h-6 w-6" />
            ) : (
              <Mic className="h-6 w-6" />
            )}
          </Button>
        </div>

        {/* État de reconnaissance */}
        {recognitionError && (
          <p className="text-sm text-destructive text-center">{recognitionError}</p>
        )}

        {/* Zone de transcription */}
        <div className="bg-muted/30 rounded-lg p-4 min-h-[120px]">
          {isListening && !transcript && (
            <div className="flex items-center justify-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Parlez maintenant...</span>
            </div>
          )}
          <p className={`text-sm leading-relaxed ${!transcript ? "italic text-muted-foreground" : ""}`}>
            {transcript || "Votre texte apparaîtra ici..."}
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopy}
            disabled={!transcript}
          >
            <Copy className="h-4 w-4 mr-1" />
            Copier
          </Button>

          <Button
            variant="default"
            size="sm"
            onClick={handleInsert}
            disabled={!transcript.trim() || isListening}
          >
            {mode === "dictate" ? (
              <>
                <Send className="h-4 w-4 mr-1" />
                Envoyer
              </>
            ) : (
              <>
                <Send className="h-4 w-4 mr-1" />
                Insérer
              </>
            )}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleClear}
            disabled={!transcript || isListening}
          >
            <Trash2 className="h-4 w-4 mr-1" />
            Effacer
          </Button>
        </div>

        {/* Upload fichier (fallback) */}
        <div className="border-t pt-4">
          <p className="text-xs text-muted-foreground mb-2">
            Ou transcribez un fichier audio :
          </p>
          <label className="flex items-center gap-2 cursor-pointer">
            <Button variant="outline" size="sm" asChild>
              <span>
                {isUploading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                    Transcribing...
                  </>
                ) : (
                  "Choisir un fichier"
                )}
              </span>
            </Button>
            <input
              type="file"
              accept="audio/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
              }}
              disabled={isUploading}
            />
          </label>
          {uploadError && (
            <p className="text-xs text-destructive mt-1">{uploadError}</p>
          )}
        </div>

        {/* Info provider */}
        <p className="text-xs text-muted-foreground text-center border-t pt-2">
          Powered by Deepgram Nova-3 • Web Speech API (fallback)
        </p>
      </CardContent>
    </Card>
  );
}