"use client";

import * as React from "react";
import { Volume2, VolumeX, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface TTSReadAloudProps {
    /** Texte à lire */
    text: string;
    /** Variante du bouton */
    variant?: "ghost" | "outline" | "default";
    /** Taille de l'icône */
    size?: "sm" | "md" | "lg";
    /** Classe CSS additionnelle */
    className?: string;
}

/**
 * Composant TTS Read-Aloud — lit le texte avec l'API Speech du navigateur.
 * 
 * Utilise le SpeechSynthesis du navigateur (Web Speech API).
 * Aucune config backend requise — fonctionne immédiatement.
 * 
 * Pour une qualité supérieure, peut être remplacé par LiveKit TTS ou
 * un service cloud (ElevenLabs) si nécessaire.
 */
export function TTSReadAloud({
    text,
    variant = "ghost",
    size = "sm",
    className = "",
}: TTSReadAloudProps) {
    const [isPlaying, setIsPlaying] = React.useState(false);
    const [isSupported, setIsSupported] = React.useState(true);

    // Vérifier support Web Speech API
    React.useEffect(() => {
        if (typeof window === "undefined" || !window.speechSynthesis) {
            setIsSupported(false);
        }
    }, []);

    const handleSpeak = React.useCallback(() => {
        if (!text || !isSupported) return;

        // Si déjà en train de parler, arrêter
        if (isPlaying) {
            window.speechSynthesis.cancel();
            setIsPlaying(false);
            return;
        }

        // Créer utterance
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "fr-FR";
        utterance.rate = 1.0;
        utterance.pitch = 1.0;

        // Trouver une voix française si disponible
        const voices = window.speechSynthesis.getVoices();
        const frenchVoice = voices.find(
            (v) => v.lang.startsWith("fr") && v.name.includes("Google")
        ) || voices.find((v) => v.lang.startsWith("fr"));
        
        if (frenchVoice) {
            utterance.voice = frenchVoice;
        }

        utterance.onstart = () => {
            setIsPlaying(true);
        };

        utterance.onend = () => {
            setIsPlaying(false);
        };

        utterance.onerror = () => {
            setIsPlaying(false);
        };

        // Démarrer la lecture
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
    }, [text, isPlaying, isSupported]);

    // Arrêter la lecture si le composant est démonté
    React.useEffect(() => {
        return () => {
            if (typeof window !== "undefined") {
                window.speechSynthesis.cancel();
            }
        };
    }, []);

    if (!isSupported) {
        return null;
    }

    const iconSize = size === "sm" ? "h-3 w-3" : size === "lg" ? "h-5 w-5" : "h-4 w-4";
    const buttonSize = size === "sm" ? "h-7" : size === "lg" ? "h-10" : "h-8";

    return (
        <Button
            variant={variant}
            size="sm"
            onClick={handleSpeak}
            disabled={!text}
            className={`gap-1 ${buttonSize} ${className}`}
            title={isPlaying ? "Arrêter la lecture" : "Écouter la réponse"}
            aria-label={isPlaying ? "Arrêter la lecture" : "Écouter la réponse"}
        >
            {isPlaying ? (
                <>
                    <VolumeX className={iconSize} />
                    {size !== "sm" && <span className="text-xs">Arrêter</span>}
                </>
            ) : (
                <>
                    <Volume2 className={iconSize} />
                    {size !== "sm" && <span className="text-xs">Lire</span>}
                </>
            )}
        </Button>
    );
}

/**
 * Hook pour utiliser le TTS dans les composants.
 */
export function useTTS() {
    const [isPlaying, setIsPlaying] = React.useState(false);
    const [isSupported, setIsSupported] = React.useState(false);

    React.useEffect(() => {
        setIsSupported(!!window.speechSynthesis);
    }, []);

    const speak = React.useCallback((text: string) => {
        if (!text || !isSupported) return;

        // Arrêter toute lecture en cours
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "fr-FR";
        utterance.rate = 1.0;

        utterance.onstart = () => setIsPlaying(true);
        utterance.onend = () => setIsPlaying(false);
        utterance.onerror = () => setIsPlaying(false);

        window.speechSynthesis.speak(utterance);
    }, [isSupported]);

    const stop = React.useCallback(() => {
        window.speechSynthesis.cancel();
        setIsPlaying(false);
    }, []);

    return { speak, stop, isPlaying, isSupported };
}

// Types pour Web Speech API
declare global {
    interface Window {
        speechSynthesis: SpeechSynthesis;
    }
}