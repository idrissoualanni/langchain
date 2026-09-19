"use client";

import { useEffect, useState } from "react";
import { LiveKitRoom, useAgent, useTracks } from "@livekit/components-react";
import { Track } from "livekit-client";
import { useLocalRuntime, WebSpeechDictationAdapter } from "@assistant-ui/react";
import { AgentAudioVisualizerAura } from "@/components/agents-ui/agent-audio-visualizer-aura";
import { AgentControlBar } from "@/components/agents-ui/agent-control-bar";
import { AgentVideoTile } from "@/components/agents-ui/agent-video-tile";
import { useTheme } from "next-themes";

// Modèle factice pour l'exemple (à remplacer par votre hook d'appel API réel)
const mockChatModel = {
  run: async function* (messages: any[]) {
    const lastMessage = messages[messages.length - 1];
    yield { role: "assistant", content: `J'ai entendu : "${lastMessage.content}". Je traite ta demande...` };
  },
};

interface VideoSessionProps {
  token: string;
  url: string;
  roomName: string;
}

export function VideoSession({ token, url, roomName }: VideoSessionProps) {
  const { resolvedTheme } = useTheme();
  const [isConnected, setIsConnected] = useState(false);
  
  // 1. Configuration du Runtime Assistant UI avec Dictée Web Speech
  const runtime = useLocalRuntime(mockChatModel, {
    adapters: {
      dictation: WebSpeechDictationAdapter.isSupported()
        ? new WebSpeechDictationAdapter({ 
            interimResults: true, 
            language: "fr-FR" 
          })
        : undefined,
    },
  });

  // 2. Hooks LiveKit pour l'état de l'agent et les pistes audio/vidéo
  const { state: agentState } = useAgent();
  const tracks = useTracks();

  // Filtrer les pistes vidéo et audio
  const videoTracks = tracks.filter((trackRef) => trackRef.source === Track.Source.Camera);
  const screenShareTracks = tracks.filter((trackRef) => trackRef.source === Track.Source.ScreenShare);
  const audioTracks = tracks.filter((trackRef) => trackRef.source === Track.Source.Microphone);

  // Détection automatique de l'état (speaking/listening/idle)
  const isSpeaking = agentState === "speaking";
  const isListening = !isSpeaking && audioTracks.some(t => t.participant.isLocal);

  let visualState: "speaking" | "listening" | "idle" = "idle";
  if (isSpeaking) visualState = "speaking";
  else if (isListening) visualState = "listening";

  return (
    <div className="flex flex-col h-full w-full space-y-4 p-4">
      
      {/* Zone principale : Vidéo ou Visualiseur */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4 min-h-[400px]">
        
        {/* Tile Vidéo Locale */}
        <div className="relative bg-muted rounded-lg overflow-hidden flex items-center justify-center">
          {videoTracks.length > 0 ? (
            <AgentVideoTile
              trackRef={videoTracks[0]}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="text-muted-foreground text-sm">Caméra désactivée</div>
          )}
          <div className="absolute bottom-2 left-2 bg-black/50 text-white text-xs px-2 py-1 rounded">
            Moi
          </div>
        </div>

        {/* Tile Vidéo Distante ou Partage d'écran */}
        <div className="relative bg-muted rounded-lg overflow-hidden flex items-center justify-center">
          {screenShareTracks.length > 0 ? (
            <AgentVideoTile
              trackRef={screenShareTracks[0]}
              className="w-full h-full object-contain"
            />
          ) : videoTracks.filter(t => !t.participant.isLocal).length > 0 ? (
            <AgentVideoTile
              trackRef={videoTracks.find(t => !t.participant.isLocal)!}
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

      {/* Zone inférieure : Visualiseur Audio + Contrôles */}
      <div className="flex flex-col items-center justify-center space-y-4 py-4">
        
        {/* Visualiseur Audio Style "Aura" */}
        <div className="relative w-32 h-32">
          <AgentAudioVisualizerAura
            size="lg"
            color="#1FD5F9"
            colorShift={0.3}
            state={visualState}
            themeMode={resolvedTheme}
            className="aspect-square w-full"
          />
          
          {/* Indicateur de statut textuel */}
          <div className="absolute bottom-0 left-0 right-0 text-center text-xs font-medium text-muted-foreground">
            {visualState === "speaking" ? "Je parle..." : 
             visualState === "listening" ? "Je t'écoute..." : "En attente"}
          </div>
        </div>

        {/* Contrôles (Mute, Caméra, Screen Share, Disconnect) */}
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
  );
}
