"use client";

import * as React from "react";
import { Loader2, Mic, MicOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";

function VoiceButton() {
  const [started, setStarted] = React.useState(false);
  const [connecting, setConnecting] = React.useState(false);
  const { toast } = useToast();

  const handleClick = React.useCallback(async () => {
    try {
      if (!started) {
        setConnecting(true);
        const res = await fetch("/api/livekit/agent/start", { method: "POST" });
        if (res.ok) {
          setStarted(true);
        } else if (res.status === 503) {
          // Le serveur LiveKit n'est pas démarré (ex: local). On l'indique
          // clairement à l'utilisateur plutôt que de rester bloqué en
          // "Connexion".
          const data = await res.json().catch(() => null);
          toast({
            title: "Serveur LiveKit indisponible",
            description:
              data?.detail ??
              "Le serveur LiveKit n'est pas démarré. La voix reste désactivée.",
          });
        } else {
          // Autre erreur serveur (500, 401, …) : ne pas rester silencieux.
          const data = await res.json().catch(() => null);
          toast({
            title: "Démarrage de la voix impossible",
            description:
              data?.detail ?? `Erreur HTTP ${res.status}`,
            variant: "destructive",
          });
        }
        setConnecting(false);
      } else {
        const res = await fetch("/api/livekit/agent/stop", { method: "POST" });
        if (res.status === 503) {
          const data = await res.json().catch(() => null);
          toast({
            title: "Serveur LiveKit indisponible",
            description:
              data?.detail ??
              "Le serveur LiveKit n'est pas démarré. L'agent est déjà arrêté.",
          });
        }
        setStarted(false);
      }
    } catch (error) {
      console.error(error);
      toast({
        title: "Erreur de connexion vocale",
        description: error instanceof Error ? error.message : "Erreur inconnue",
      });
      setConnecting(false);
    }
  }, [started, toast]);

  return (
    <Button
      variant="ghost"
      className="group/voice text-muted-foreground hover:text-foreground h-8 gap-1 rounded-lg"
      onClick={handleClick}
      aria-label={started ? "Arrêter la voix" : "Démarrer la voix"}
    >
      {connecting ? (
        <Loader2 className="size-4 animate-spin" />
      ) : started ? (
        <MicOff className="size-4" />
      ) : (
        <Mic className="size-4" />
      )}
      <span className="text-xs">{connecting ? "Connexion" : "Voix"}</span>
    </Button>
  );
}

VoiceButton.displayName = "VoiceButton";

export { VoiceButton };