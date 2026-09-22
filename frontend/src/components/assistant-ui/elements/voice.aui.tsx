"use client";

import * as React from "react";
import { Loader2, Mic, MicOff } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { apiFetch, ApiError } from "@/api/base";

function VoiceButton() {
  const [started, setStarted] = React.useState(false);
  const [connecting, setConnecting] = React.useState(false);
  const { toast } = useToast();
  const navigate = useNavigate();

  const handleClick = React.useCallback(async () => {
    // Le bouton voix ouvre une VRAIE session vocale ( page /voice ) :
    // on déclenche le dispatch puis on navigue. La page se connecte à
    // la room et porte l'interface ( visualizer, état agent, mémoire ).
    try {
      if (!started) {
        setConnecting(true);
        // apiFetch retourne le JSON déjà parsé et LÈVE une ApiError
        // ( status + message ) sur toute réponse non-2xx : on ne gère donc
        // plus un objet Response ici.
        await apiFetch("/api/livekit/agent/start", { method: "POST" });
        setStarted(true);
        navigate("/voice");
      } else {
        await apiFetch("/api/livekit/agent/stop", { method: "POST" });
        setStarted(false);
      }
    } catch (error) {
      const apiError = error instanceof ApiError ? error : null;

      if (apiError && apiError.status === 503) {
        // Le serveur LiveKit n'est pas démarré ( ex: local ). On l'indique
        // clairement à l'utilisateur plutôt que de rester bloqué en
        // "Connexion" — pas de variant "destructive", ce n'est pas un bug.
        toast({
          title: "Serveur LiveKit indisponible",
          description:
            apiError.message ??
            (started
              ? "Le serveur LiveKit n'est pas démarré. L'agent est déjà arrêté."
              : "Le serveur LiveKit n'est pas démarré. La voix reste désactivée."),
        });
      } else {
        // Autre erreur serveur ( 500, 401, … ) : ne pas rester silencieux.
        toast({
          title: started
            ? "Arrêt de la voix impossible"
            : "Démarrage de la voix impossible",
          description:
            apiError?.message ??
            (error instanceof Error ? error.message : "Erreur inconnue"),
          variant: "destructive",
        });
      }

      // Échec de l'arrêt → l'agent est de toute façon arrêté côté serveur
      // ( ou jamais démarré ) : on revient à l'état "voix désactivée".
      if (started) {
        setStarted(false);
      }
      console.error(error);
    } finally {
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