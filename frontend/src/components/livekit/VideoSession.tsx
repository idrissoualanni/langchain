"use client";

import { useEffect, useState } from "react";
import { LiveKitRoom, useAgent, useTracks } from "@livekit/components-react";
import { Track } from "livekit-client";
import { useLocalRuntime, WebSpeechDictationAdapter } from "@assistant-ui/react";
import { AgentAudioVisualizerAura } from "@/components/agents-ui/agent-audio-visualizer-aura";
import { AgentControlBar } from "@/components/agents-ui/agent-control-bar";
import { AgentVideoTile } from "@/components/agents-ui/agent-video-tile";
import { useTheme } from "next-themes";
import { Loader2 } from "lucide-react";

/** Mock chat model placeholder – replace with real API later */
const mockChatModel = {
  run: async function* (messages: any[]) {
    const lastMessage = messages[messages.length - 1];
    yield {
      role: "assistant",
      content: `J'ai entendu : "${lastMessage.content}". Je traite ta demande...`,
    };
  },
};

interface VideoSessionProps {
  /** Nom de la salle LiveKit */
  roomName: string;
}

/**
 * VideoSession component
 *
 * - Retrieves a LiveKit token via GET /api/livekit/token?room=<roomName>.
 * - Stores the token and server URL in component state.
 * - Shows a loading fallback UI while fetching and an error UI on failure.
 * - Passes the token to LiveKitRoom and renders the video UI inside it.
 */
export function VideoSession({ roomName }: VideoSessionProps) {
  const { resolvedTheme } = useTheme();

  const [token, setToken] = useState<string>("");
  const [url, setUrl] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch LiveKit token when the component mounts or when the room name changes
  useEffect(() => {
    async function fetchToken() {
      try {
        const response = await fetch(
          `/api/livekit/token?room=${encodeURIComponent(roomName)}`,
          {
            method: "GET",
          }
        );
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        setToken(data.token);
        // Some back‑ends expose the server URL under `url` or `serverUrl`
        setUrl(data.url ?? data.serverUrl ?? "");
      } catch (e: any) {
        console.error("Erreur de récupération du token LiveKit:", e);
        setError(e?.message ?? "Erreur inconnue");
      } finally {
        setLoading(false);
      }
    }

    fetchToken();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomName]);

  // Loading fallback UI
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

  // Connection error UI
  if (error) {
    return (
      <div className="p-4 text-red-500 bg-background">
        Erreur de connexion LiveKit : {error}
      </div>
    );
  }

  // Assistant UI runtime (unchanged from original implementation)
  const runtime = useLocalRuntime(mockChatModel, {
    adapters: {
      dictation: WebSpeechDictationAdapter.isSupported()
        ? new WebSpeechDictationAdapter({
            interimResults: true,
            language: "fr-FR",
          })
        : undefined,
    },
  });

  // LiveKit hooks for agent state and tracks
  const { state: agentState } = useAgent();
  const tracks = useTracks();

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
    <LiveKitRoom
      token={token}
      serverUrl={url}
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
            onToggleMicrophone={(muted) => console.log("Mic:", muted)}
            onToggleCamera={(muted) => console.log("Camera:", muted)}
            onToggleScreenShare={(enabled) => console.log("Screen:", enabled)}
            onDisconnect={() => console.log("Disconnect")}
            className="backdrop-blur-md bg-background/50 rounded-full p-2 flex gap-2"
            showScreenShareButton={true}
          />
        </div>
      </div>
    </LiveKitRoom>
  );
}
