"use client";

import * as React from "react";
import {
    Loader2,
    Maximize2,
    Minimize2,
    Video,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface ScreenShareTileProps {
    trackRef: any;
    isLocal: boolean;
}

/**
 * Tuile pour le flux Screen Share — prend toute la largeur disponible.
 * L'agent LiveKit peut "voir" ce que l'utilisateur partage et répondre.
 */
function ScreenShareTile({ trackRef, isLocal }: ScreenShareTileProps) {
    const [isFullscreen, setIsFullscreen] = React.useState(false);
    const tileRef = React.useRef<HTMLDivElement>(null);

    const toggleFullscreen = () => {
        if (!tileRef.current) return;

        if (!document.fullscreenElement) {
            tileRef.current.requestFullscreen().then(() => {
                setIsFullscreen(true);
            });
        } else {
            document.exitFullscreen().then(() => {
                setIsFullscreen(false);
            });
        }
    };

    React.useEffect(() => {
        const handleFullscreenChange = () => {
            setIsFullscreen(!!document.fullscreenElement);
        };
        document.addEventListener("fullscreenchange", handleFullscreenChange);
        return () => {
            document.removeEventListener("fullscreenchange", handleFullscreenChange);
        };
    }, []);

    return (
        <div
            ref={tileRef}
            className="relative w-full h-full bg-slate-900 rounded-xl overflow-hidden group"
        >
            {/* Track vidéo */}
            {trackRef?.track && (
                <VideoTrack trackRef={trackRef} />
            )}

            {/* Overlay controls */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

            {/* Controls overlay */}
            <div className="absolute bottom-0 left-0 right-0 p-4 flex items-center justify-between opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="flex items-center gap-2">
                    {isLocal ? (
                        <span className="text-white text-sm font-medium">
                            Votre écran
                        </span>
                    ) : (
                        <span className="text-white text-sm font-medium">
                            Écran partagé
                        </span>
                    )}
                </div>

                <Button
                    variant="ghost"
                    size="sm"
                    className="text-white hover:text-white hover:bg-white/20"
                    onClick={toggleFullscreen}
                >
                    {isFullscreen ? (
                        <Minimize2 className="h-4 w-4" />
                    ) : (
                        <Maximize2 className="h-4 w-4" />
                    )}
                </Button>
            </div>
        </div>
    );
}

/**
 * Wrapper simple pour le track vidéo LiveKit.
 * Utilise l'API LiveKit directement pour le rendu.
 */
function VideoTrack({ trackRef }: { trackRef: any }) {
    const videoRef = React.useRef<HTMLVideoElement>(null);

    React.useEffect(() => {
        if (!trackRef?.track || !videoRef.current) return;

        const videoEl = videoRef.current;
        const track = trackRef.track;

        if (track.attach) {
            // Mode LiveKit (anciennes versions)
            track.attach(videoEl);
            return () => {
                track.detach(videoEl);
            };
        } else if (track.addEventListener) {
            // Mode natif MediaStreamTrack
            const stream = new MediaStream([track]);
            videoEl.srcObject = stream;
            videoEl.autoplay = true;
            videoEl.playsInline = true;
            return () => {
                videoEl.srcObject = null;
            };
        }
    }, [trackRef]);

    return (
        <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover"
        />
    );
}

export { ScreenShareTile, VideoTrack };