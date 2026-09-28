// Complément de typage Web Speech API pour useTranscription.ts.
//
// @assistant-ui/core déclare déjà SpeechRecognitionInstance ( start/stop/
// abort, lang/continuous/interimResults ) en global. On ne peut pas
// fusionner une interface exportée depuis un module : on déclare donc un
// type d'instance local au module, avec les propriétés standards que la
// lib d'assistant-ui n'inclut pas ( maxAlternatives + callbacks ).
export interface TranscriptionSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

export interface TranscriptionSpeechRecognitionConstructor {
  new (): TranscriptionSpeechRecognition;
}

declare global {
  interface Window {
    SpeechRecognition?: TranscriptionSpeechRecognitionConstructor;
    webkitSpeechRecognition?: TranscriptionSpeechRecognitionConstructor;
  }
}
