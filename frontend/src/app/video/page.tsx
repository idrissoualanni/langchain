"use client";

import { useEffect, useState } from "react";
import { SessionProvider, useSession } from "@livekit/components-react";
import { Room, TokenSource } from "livekit-client";
import { Loader2 } from "lucide-react";

import { VideoSession } from "@/components/livekit/VideoSession";
import { useLiveKitToken } from "@/hooks/useLiveKitToken";

export default function VideoPage() {
  const { data, loading, error } = useLiveKitToken("video");

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

  if (error || !data?.token || !data?.url) {
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
    <VideoRoomSession
      token={data.token}
      url={data.url}
      roomName={data.roomName}
    />
  );
}

/**
 * Connexion de la salle vidéo via une Session LiveKit.
 *
 * En @livekit/components-react v2, `useAgent()` lit le SessionContext —
 * fourni par <SessionProvider>, PAS par <LiveKitRoom>. C'est la même
 * structure que la page /voice : useSession crée la session, on la démarre
 * manuellement ( start() ne connecte pas tout seul ), puis SessionProvider
 * expose session + room aux enfants ( VideoSession, useAgent, useTracks ).
 *
 * La Room est créée ici ( et pas laissée à useSession ) pour activer
 * dynacast + adaptiveStream : couches vidéo publiées à la demande et
 * qualité adaptée à la taille des tuiles affichées.
 */
function VideoRoomSession({
  token,
  url,
  roomName,
}: {
  token: string;
  url: string;
  roomName: string;
}) {
  // TokenSource.literal attend { serverUrl, participantToken } —
  // les noms du proto LiveKit ( pas token/wsUrl ).
  const tokenSource = useState(
    () => TokenSource.literal({ serverUrl: url, participantToken: token }),
  )[0];

  // Room mémoïsée : dynacast ( pause des couches non consommées ) +
  // adaptiveStream ( qualité selon la tuile affichée ).
  const room = useState(
    () =>
      new Room({
        dynacast: true,
        adaptiveStream: true,
        audioCaptureDefaults: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      }),
  )[0];

  const session = useSession(tokenSource, { room });

  // start() connecte la room et publie caméra + micro. L'écran n'est
  // partagé qu'à la demande ( bouton ) : on ne lance pas de capture au
  // démarrage.
  useEffect(() => {
    void session.start({
      tracks: {
        camera: { enabled: true },
        microphone: {
          enabled: true,
          publishOptions: { preConnectBuffer: true },
        },
      },
    });
    return () => {
      void session.end();
    };
  }, [session]);

  return (
    <SessionProvider session={session} key={roomName}>
      {/*
        Token + URL transmis à VideoSession : sa branche `provided` évite
        un second fetch /api/livekit/token. Surtout, <SessionProvider> a
        déjà fourni le RoomContext ( session.room ) → VideoSession détecte
        la room parente et ne crée PAS de seconde salle.
      */}
      <VideoSession roomName={roomName} token={token} url={url} />
    </SessionProvider>
  );
}
