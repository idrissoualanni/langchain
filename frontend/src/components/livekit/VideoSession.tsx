"use client";

import { useEffect, useState } from "react";
import {
  LiveKitRoom,
  useAgent,
  useLocalParticipant,
  useRoomContext,
  useTracks,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import { useTheme } from "@/hooks/useTheme";
import { AgentAudioVisualizerAura } from "@/components/agents-ui/agent-audio-visualizer-aura";
import { AgentControlBar } from "@/components/agents-ui/agent-control-bar";
import { AgentVideoTile } from "@/components/agents-ui/agent-video-tile";
import { Loader2 } from "lucide-react";
import { apiFetch } from "@/api/base";

interface LiveKitTokenResponse {
  token: string;
  url: string;
  room_name: string;
}

interface VideoSessionProps {
  /** Nom de la salle LiveKit (utilisé pour la récupération autonome du token). */
  roomName: string;
  /** Token LiveKit pré-fourni (par ex. par la page parente). */
  token?: string;
  /** URL du serveur LiveKit pré-fournie. */
  url?: string;
}

/**
 * VideoSession component
 *
 * - When `token` and `url` are provided (e.g. by a parent page that already
 *   renders a `<LiveKitRoom>`), they are used as-is and no nested room is
 *   created.
 * - Otherwise the component fetches its own token via un POST authentifié
 *   sur `/api/livekit/token` et enveloppe son UI dans un
 *   `<LiveKitRoom>` autonome.
 */
export function VideoSession({ roomName, token: tokenProp, url: urlProp }: VideoSessionProps) {
  const provided = Boolean(tokenProp && urlProp);

  const [fetchedToken, setFetchedToken] = useState<string>("");
  const [fetchedUrl, setFetchedUrl] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(!provided);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (provided) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function fetchToken() {
      try {
        // POST authentifié via apiFetch (§19) — la route est POST-only,
        // un GET avec query string renvoie 405.
        const data = await apiFetch<LiveKitTokenResponse>(
          "/api/livekit/token",
          {
            method: "POST",
            body: JSON.stringify({ room_name: roomName }),
          }
        );
        if (cancelled) return;
        setFetchedToken(data.token);
        setFetchedUrl(data.url);
      } catch (e) {
        if (cancelled) return;
        console.error("Erreur de récupération du token LiveKit:", e);
        setError(e instanceof Error ? e.message : "Erreur inconnue");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchToken();
    return () => {
      cancelled = true;
    };
  }, [provided, roomName]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto" />
          <p className="text-muted-foreground">Initialisation de la session vidéo…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-red-500 bg-background">
        Erreur de connexion LiveKit : {error}
      </div>
    );
  }

  const content = <VideoSessionContent />;

  if (provided) {
    return content;
  }

  return (
    <LiveKitRoom
      token={fetchedToken}
      serverUrl={fetchedUrl}
      connect={true}
      video={true}
      audio={{
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      }}
      data-lk-theme="default"
      className="h-screen w-full bg-background"
    >
      {content}
    </LiveKitRoom>
  );
}

function VideoSessionContent() {
  // Thème résolu (clair/sombre) fourni par le hook projet — plus de valeur
  // codée en dur.
  const { resolvedTheme } = useTheme();

  // LiveKit hooks for agent state and tracks
  const { state: agentState } = useAgent();
  const tracks = useTracks();
  // Participant local (pour activer/désactiver micro, caméra, partage d'écran)
  const { localParticipant } = useLocalParticipant();
  // Room courante (pour la déconnexion) — les hooks doivent être appelés
  // à l'intérieur d'un <LiveKitRoom>, ce qui est le cas ici.
  const room = useRoomContext();

  // Filter video, screen‑share and audio tracks
  const videoTracks = tracks.filter(
    (trackRef) => trackRef.source === Track.Source.Camera
  );
  const screenShareTracks = tracks.filter(
    (trackRef) => trackRef.source === Track.Source.ScreenShare
  );
  const audioTracks = tracks.filter(
    (trackRef) => trackRef.source === Track.Source.Microphone
  );

  const isSpeaking = agentState === "speaking";
  const isListening =
    !isSpeaking && audioTracks.some((t) => t.participant.isLocal);
  let visualState: "speaking" | "listening" | "idle" = "idle";
  if (isSpeaking) visualState = "speaking";
  else if (isListening) visualState = "listening";

  return (
    <div className="flex flex-col h-full w-full space-y-4 p-4">
      {/* Main video area */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4 min-h-[400px]">
        {/* Local video tile */}
        <div className="relative bg-muted rounded-lg overflow-hidden flex items-center justify-center">
          {videoTracks.length > 0 ? (
            <AgentVideoTile
              trackRef={videoTracks[0]}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="text-muted-foreground text-sm">Caméra désactivée</div>
          )}
          <div className="absolute bottom-2 left-2 bg-black/50 text-white text-xs px-2 py-1 rounded">Moi</div>
        </div>

        {/* Remote or screen‑share tile */}
        <div className="relative bg-muted rounded-lg overflow-hidden flex items-center justify-center">
          {screenShareTracks.length > 0 ? (
            <AgentVideoTile
              trackRef={screenShareTracks[0]}
              className="w-full h-full object-contain"
            />
          ) : videoTracks.filter((t) => !t.participant.isLocal).length > 0 ? (
            <AgentVideoTile
              trackRef={videoTracks.find((t) => !t.participant.isLocal)!}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="text-muted-foreground text-sm">En attente d'un participant</div>
          )}
          {screenShareTracks.length > 0 && (
            <div className="absolute top-2 right-2 bg-red-500 text-white text-xs px-2 py-1 rounded animate-pulse">
              Partage d'écran
            </div>
          )}
        </div>
      </div>

      {/* Bottom audio visualizer and controls */}
      <div className="flex flex-col items-center justify-center space-y-4 py-4">
        <div className="relative w-32 h-32">
          <AgentAudioVisualizerAura
            size="lg"
            color="#1FD5F9"
            colorShift={0.3}
            state={visualState}
            themeMode={resolvedTheme}
            className="aspect-square w-full"
          />
          <div className="absolute bottom-0 left-0 right-0 text-center text-xs font-medium text-muted-foreground">
            {visualState === "speaking"
              ? "Je parle..."
              : visualState === "listening"
              ? "Je t'écoute..."
              : "En attente"}
          </div>
        </div>

        <AgentControlBar
          onToggleMicrophone={async (muted) => {
            // `muted` = nouvel état coupé → on active le micro si non coupé
            await localParticipant.setMicrophoneEnabled(!muted);
          }}
          onToggleCamera={async (muted) => {
            await localParticipant.setCameraEnabled(!muted);
          }}
          onToggleScreenShare={async (enabled) => {
            await localParticipant.setScreenShareEnabled(enabled);
          }}
          onDisconnect={() => {
            room.disconnect();
          }}
          className="backdrop-blur-md bg-background/50 rounded-full p-2 flex gap-2"
          showScreenShareButton={true}
        />
      </div>
    </div>
  );
}