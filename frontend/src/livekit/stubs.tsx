// Stub module for LiveKit components used in the frontend
// Provides minimal implementations to satisfy TypeScript without real LiveKit functionality.

import * as React from 'react';

export interface TrackReference {
  participant: { isLocal?: boolean };
  source?: string;
  publication?: any;
  track?: any;
}

export interface LiveKitRoomProps {
  token: string;
  serverUrl: string;
  connect?: boolean;
  video?: boolean;
  audio?: Record<string, any>;
  "data-lk-theme"?: string;
  className?: string;
  children?: React.ReactNode;
}

export const LiveKitRoom: React.FC<LiveKitRoomProps> = ({ children }) => {
  // Simple placeholder that just renders its children.
  return React.createElement(React.Fragment, null, children);
};

export const VideoTrack: React.FC<{
  trackRef?: TrackReference;
  className?: string;
}> = ({ className }) => {
  return React.createElement('div', { className });
};

// Agent and track hooks – return empty placeholders.
export const useAgent = () => ({ state: 'idle' as 'idle' | 'speaking' | 'listening' });
export const useTracks = () => [] as TrackReference[];

export const Track = {
  Source: {
    Camera: 'camera',
    ScreenShare: 'screen',
    Microphone: 'microphone',
  },
} as any;
