// Stub module for LiveKit components used in the frontend
// Provides minimal implementations to satisfy TypeScript without real LiveKit functionality.

import * as React from 'react';

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
  return <>{children}</>;
};

// Agent and track hooks – return empty placeholders.
export const useAgent = () => ({ state: 'idle' as const });
export const useTracks = () => [] as any[];

export const Track = {
  Source: {
    Camera: 'camera',
    ScreenShare: 'screen',
    Microphone: 'microphone',
  },
} as any;
