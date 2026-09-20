"use client";

import { useEffect, useState } from "react";
import { LiveKitRoom } from "@livekit/components-react";
import { VideoSession } from "@/components/livekit/VideoSession";
import { apiFetch } from "@/api/base";
import { Loader2 } from "lucide-react";

interface LiveKitTokenResponse {
  token: string;
  url: string;
  room_name: string;
}

export default function VideoPage() {
  const [token, setToken] = useState<string>("");
  const [url, setUrl] = useState<string>("");
  const [roomName, setRoomName] = useState<string>("tutor-video-session");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchToken() {
      try {
        // apiFetch injecte le Bearer token (Clerk ou dev) — §19 : aucune
        // requête ne devrait utiliser fetch() directement.
        const data = await apiFetch<LiveKitTokenResponse>("/api/livekit/token", {
          method: "POST",
          body: JSON.stringify({ room_name: "session-" + Date.now() }),
        });
        setToken(data.token);
        setUrl(data.url);
        setRoomName(data.room_name);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur inconnue");
      } finally {
        setLoading(false);
      }
    }
    fetchToken();
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto" />
          <p className="text-muted-foreground">Initialisation de la session vidéo...</p>
        </div>
      </div>
    );
  }

  if (error || !token || !url) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="text-center space-y-4 max-w-md">
          <p className="text-destructive font-medium">Session vidéo indisponible</p>
          <p className="text-sm text-muted-foreground">
            {error || "Aucun token LiveKit reçu."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <LiveKitRoom
      token={token}
      serverUrl={url}
      connect={true}
      video={true} // Activation vidéo
      audio={{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }}
      data-lk-theme="default"
      className="h-screen w-full bg-background"
    >
      {/*
        Token + URL transmis à VideoSession : la branche `provided` de
        VideoSession se contente alors de rendre son contenu à l'intérieur
        du LiveKitRoom ci-dessus, SANS recréer une seconde salle (ni un
        second fetch /api/livekit/token). Avec la vraie bibliothèque, une
        double <LiveKitRoom> ouvrirait 2 connexions concurrentes vers le
        serveur ; une seule salle suffit.
      */}
      <VideoSession roomName={roomName} token={token} url={url} />
    </LiveKitRoom>
  );
}
