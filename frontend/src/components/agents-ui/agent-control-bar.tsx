"use client";

import { useState } from "react";
import {
  Loader2,
  Mic,
  MicOff,
  MonitorOff,
  MonitorUp,
  PhoneOff,
  Video,
  VideoOff,
} from "lucide-react";

interface AgentControlBarProps {
  /** Called when the local microphone is toggled; `muted` reflects the new state. */
  onToggleMicrophone?: (muted: boolean) => void | Promise<void>;
  /** Called when the local camera is toggled; `muted` reflects the new state. */
  onToggleCamera?: (muted: boolean) => void | Promise<void>;
  /** Called when screen sharing is toggled; `enabled` reflects the new state. */
  onToggleScreenShare?: (enabled: boolean) => void | Promise<void>;
  /** Called when the user wants to leave/disconnect the session. */
  onDisconnect?: () => void;
  className?: string;
  /** Whether to render the screen-share button. */
  showScreenShareButton?: boolean;
  /**
   * États réels du participant LiveKit. Quand ils sont fournis, ils priment
   * sur l'état local : l'UI reflete toujours la room, même si le partage est
   * arrêté côté système ( barre Chrome, raccourci, onglet fermé ).
   */
  microphoneEnabled?: boolean;
  cameraEnabled?: boolean;
  screenShareEnabled?: boolean;
  /** Bloque les boutons le temps qu'un toggle asynchrone se résolve. */
  busy?: boolean;
}

/**
 * Control bar with toggle buttons wired to the provided callbacks.
 *
 * État contrôlé : si le parent passe les drapeaux `*Enabled`, ils sont la
 * seule source de vérité ( l'état local n'est plus utilisé, on ne risque
 * plus le désynchronisme bouton-vs-room ). Sinon, on retombe sur l'état
 * local interne pour les usages autonomes.
 */
export function AgentControlBar({
  onToggleMicrophone,
  onToggleCamera,
  onToggleScreenShare,
  onDisconnect,
  className,
  showScreenShareButton = true,
  microphoneEnabled,
  cameraEnabled,
  screenShareEnabled,
  busy = false,
}: AgentControlBarProps) {
  // États de repli ( uniquement utilisés sans contrôle externe ).
  const [micMuted, setMicMuted] = useState(false);
  const [cameraMuted, setCameraMuted] = useState(false);
  const [screenSharing, setScreenSharing] = useState(false);

  const micOn = microphoneEnabled ?? !micMuted;
  const cameraOn = cameraEnabled ?? !cameraMuted;
  const sharing = screenShareEnabled ?? screenSharing;

  const toggleMicrophone = () => {
    if (microphoneEnabled === undefined) setMicMuted(micOn);
    void onToggleMicrophone?.(!micOn);
  };

  const toggleCamera = () => {
    if (cameraEnabled === undefined) setCameraMuted(cameraOn);
    void onToggleCamera?.(!cameraOn);
  };

  const toggleScreenShare = () => {
    if (screenShareEnabled === undefined) setScreenSharing(!sharing);
    void onToggleScreenShare?.(!sharing);
  };

  const buttonClass =
    "flex h-11 w-11 items-center justify-center rounded-full text-white transition-colors hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <div className={`flex items-center gap-2 ${className ?? ""}`}>
      <button
        type="button"
        className={`${buttonClass} ${micOn ? "bg-primary/80" : "bg-red-500"}`}
        onClick={toggleMicrophone}
        disabled={busy}
        aria-label={micOn ? "Couper le micro" : "Activer le micro"}
        aria-pressed={!micOn}
      >
        {micOn ? <Mic className="h-5 w-5" /> : <MicOff className="h-5 w-5" />}
      </button>

      <button
        type="button"
        className={`${buttonClass} ${cameraOn ? "bg-primary/80" : "bg-red-500"}`}
        onClick={toggleCamera}
        disabled={busy}
        aria-label={cameraOn ? "Couper la caméra" : "Activer la caméra"}
        aria-pressed={!cameraOn}
      >
        {cameraOn ? (
          <Video className="h-5 w-5" />
        ) : (
          <VideoOff className="h-5 w-5" />
        )}
      </button>

      {showScreenShareButton && (
        <button
          type="button"
          className={`${buttonClass} ${
            sharing ? "bg-emerald-500" : "bg-primary/80"
          }`}
          onClick={toggleScreenShare}
          disabled={busy}
          aria-label={
            sharing ? "Arrêter le partage d'écran" : "Partager l'écran"
          }
          aria-pressed={sharing}
        >
          {busy ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : sharing ? (
            <MonitorOff className="h-5 w-5" />
          ) : (
            <MonitorUp className="h-5 w-5" />
          )}
        </button>
      )}

      {/* Une seule déconnexion — le bouton LogOut était un doublon de
          PhoneOff ( même handler, même action ). */}
      <button
        type="button"
        className={`${buttonClass} bg-red-500 hover:bg-red-600`}
        onClick={() => onDisconnect?.()}
        aria-label="Quitter la session"
      >
        <PhoneOff className="h-5 w-5" />
      </button>
    </div>
  );
}
