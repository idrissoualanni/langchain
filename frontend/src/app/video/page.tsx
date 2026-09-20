"use client";

import { useEffect, useState } from "react";
import { LiveKitRoom } from "@livekit/components-react";
import { VideoSession } from "@/components/livekit/VideoSession";
import { Loader2 } from "lucide-react";

export default function VideoPage() {
  const [token, setToken] = useState<string>("");
  const [url, setUrl] = useState<string>("");
  const [roomName, setRoomName] = useState<string>("tutor-video-session");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchToken() {
      try {
        const res = await fetch("/api/livekit/token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            room_name: "session-" + Date.now(),
            enable_video: true 
          }),
        });
        if (!res.ok) throw new Error("Failed to fetch token");
        const data = await res.json();
        setToken(data.token);
        setUrl(data.url);
        setRoomName(data.room_name);
      } catch (error) {
        console.error("Erreur fetching token LiveKit:", error);
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
