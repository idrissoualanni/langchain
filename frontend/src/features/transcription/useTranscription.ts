"use client";

import * as React from "react";
import type {
  TranscriptionSpeechRecognition,
  TranscriptionSpeechRecognitionConstructor,
} from "@/types/speech-recognition";

// Alias local : window.SpeechRecognition est déjà déclaré globalement par
// @assistant-ui/core, on récupère le constructeur via une affectation typée.


interface UseTranscriptionOptions {
  language?: string;
  onTranscript?: (text: string, isFinal: boolean) => void;
}

interface UseTranscriptionReturn {
  isListening: boolean;
  transcript: string;
  startListening: () => void;
  stopListening: () => void;
  error: string | null;
}

export function useTranscription(
  options: UseTranscriptionOptions = {}
): UseTranscriptionReturn {
  const { language = "fr-FR", onTranscript } = options;
  const [isListening, setIsListening] = React.useState(false);
  const [transcript, setTranscript] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const recognitionRef = React.useRef<TranscriptionSpeechRecognition | null>(null);

  React.useEffect(() => {
    // Vérifier support Web Speech API
    // window.SpeechRecognition est déclaré par @assistant-ui/core ( sans
    // maxAlternatives/callbacks ) ; on force le type complet défini dans
    // src/types/speech-recognition.d.ts.
    const SpeechRecognition = (window.SpeechRecognition ||
      window.webkitSpeechRecognition) as
      | TranscriptionSpeechRecognitionConstructor
      | undefined;

    if (!SpeechRecognition) {
      setError("Ton navigateur ne supporte pas la reconnaissance vocale");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = language;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = "";
      let interimTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript;
        } else {
          interimTranscript += result[0].transcript;
        }
      }

      const currentTranscript = finalTranscript || interimTranscript;
      setTranscript(currentTranscript);

      if (finalTranscript && onTranscript) {
        onTranscript(finalTranscript, true);
      } else if (interimTranscript && onTranscript) {
        onTranscript(interimTranscript, false);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.error("Speech recognition error:", event.error);
      if (event.error !== "no-speech") {
        setError(`Erreur: ${event.error}`);
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      // Auto-restart si toujours en mode listening
      if (isListening) {
        try {
          recognition.start();
        } catch {
          // Ignore si déjà démarré
        }
      }
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.stop();
    };
  }, [language, onTranscript, isListening]);

  const startListening = React.useCallback(() => {
    if (!recognitionRef.current) return;
    setError(null);
    try {
      recognitionRef.current.start();
      setIsListening(true);
    } catch (e) {
      console.error("Failed to start recognition:", e);
      setError("Impossible de démarrer la dictée. Réessaie.");
    }
  }, []);

  const stopListening = React.useCallback(() => {
    if (!recognitionRef.current) return;
    try {
      recognitionRef.current.stop();
    } catch {
      // Ignore si déjà arrêté
    }
    setIsListening(false);
  }, []);

  return {
    isListening,
    transcript,
    startListening,
    stopListening,
    error,
  };
}

// Types Web Speech API : voir src/types/speech-recognition.d.ts
// ( déclaré globalement une seule fois, avec une instance typée ).
