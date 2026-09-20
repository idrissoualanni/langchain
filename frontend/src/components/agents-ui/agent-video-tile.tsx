"use client";

import { VideoTrack } from "@/livekit/stubs";
import type { TrackReference } from "@/livekit/stubs";

interface AgentVideoTileProps {
  /** The LiveKit track reference to render, or `undefined` for a placeholder. */
  trackRef?: TrackReference;
  className?: string;
}

/**
 * Renders a single LiveKit video track (camera or screen-share) inside a tile,
 * or a simple placeholder when no track is available yet.
 */
export function AgentVideoTile({ trackRef, className }: AgentVideoTileProps) {
  if (!trackRef) {
    return (
      <div className={`flex items-center justify-center bg-muted text-sm text-muted-foreground ${className ?? ""}`}>
        Aucune vidéo disponible
      </div>
    );
  }

  return <VideoTrack trackRef={trackRef} className={className} />;
}
