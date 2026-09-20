"use client";

import * as React from "react";
import { Loader2, Mic, MicOff } from "lucide-react";
import { Button } from "@/components/ui/button";

function VoiceButton() {
  const [started, setStarted] = React.useState(false);
  const [connecting, setConnecting] = React.useState(false);

  const handleClick = React.useCallback(async () => {
    try {
      if (!started) {
        setConnecting(true);
        const res = await fetch("/api/livekit/agent/start", { method: "POST" });
        if (res.ok) setStarted(true);
        setConnecting(false);
      } else {
        await fetch("/api/livekit/agent/stop", { method: "POST" });
        setStarted(false);
      }
    } catch (error) {
      console.error(error);
      setConnecting(false);
    }
  }, [started]);

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