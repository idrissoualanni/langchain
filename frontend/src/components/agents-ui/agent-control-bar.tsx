"use client";

import { useState } from "react";
import {
  LogOut,
  Mic,
  MicOff,
  MonitorUp,
  PhoneOff,
  Video,
  VideoOff,
} from "lucide-react";

interface AgentControlBarProps {
  /** Called when the local microphone is toggled; `muted` reflects the new state. */
  onToggleMicrophone?: (muted: boolean) => void;
  /** Called when the local camera is toggled; `muted` reflects the new state. */
  onToggleCamera?: (muted: boolean) => void;
  /** Called when screen sharing is toggled; `enabled` reflects the new state. */
  onToggleScreenShare?: (enabled: boolean) => void;
  /** Called when the user wants to leave/disconnect the session. */
  onDisconnect?: () => void;
  className?: string;
  /** Whether to render the screen-share button. */
  showScreenShareButton?: boolean;
}

/**
 * Control bar with toggle buttons wired to the provided callbacks.
 * Keeps local toggle state purely for icon feedback.
 */
export function AgentControlBar({
  onToggleMicrophone,
  onToggleCamera,
  onToggleScreenShare,
  onDisconnect,
  className,
  showScreenShareButton = true,
}: AgentControlBarProps) {
  const [micMuted, setMicMuted] = useState(false);
  const [cameraMuted, setCameraMuted] = useState(false);
  const [screenSharing, setScreenSharing] = useState(false);

  const toggleMicrophone = () => {
    const muted = !micMuted;
    setMicMuted(muted);
    onToggleMicrophone?.(muted);
  };

  const toggleCamera = () => {
    const muted = !cameraMuted;
    setCameraMuted(muted);
    onToggleCamera?.(muted);
  };

  const toggleScreenShare = () => {
    const enabled = !screenSharing;
    setScreenSharing(enabled);
    onToggleScreenShare?.(enabled);
  };

  const buttonClass =
    "flex h-11 w-11 items-center justify-center rounded-full text-white transition-colors hover:opacity-80";

  return (
    <div className={`flex items-center ${className ?? ""}`}>
      <button
        type="button"
        className={`${buttonClass} ${micMuted ? "bg-red-500" : "bg-primary/80"}`}
        onClick={toggleMicrophone}
        aria-label={micMuted ? "Activer le micro" : "Couper le micro"}
      >
        {micMuted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
      </button>

      <button
        type="button"
        className={`${buttonClass} ${cameraMuted ? "bg-red-500" : "bg-primary/80"}`}
        onClick={toggleCamera}
        aria-label={cameraMuted ? "Activer la caméra" : "Couper la caméra"}
      >
        {cameraMuted ? (
          <VideoOff className="h-5 w-5" />
        ) : (
          <Video className="h-5 w-5" />
        )}
      </button>

      {showScreenShareButton && (
        <button
          type="button"
          className={`${buttonClass} ${
            screenSharing ? "bg-emerald-500" : "bg-primary/80"
          }`}
          onClick={toggleScreenShare}
          aria-label={
            screenSharing ? "Arrêter le partage d'écran" : "Partager l'écran"
          }
        >
          <MonitorUp className="h-5 w-5" />
        </button>
      )}

      <button
        type="button"
        className={`${buttonClass} bg-red-500 hover:bg-red-600`}
        onClick={() => onDisconnect?.()}
        aria-label="Quitter la session"
      >
        <PhoneOff className="h-5 w-5" />
      </button>

      <button
        type="button"
        className={`${buttonClass} bg-muted-foreground/30 hover:bg-muted-foreground/40`}
        onClick={() => onDisconnect?.()}
        aria-label="Déconnexion"
      >
        <LogOut className="h-5 w-5" />
      </button>
    </div>
  );
}