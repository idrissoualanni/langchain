"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Play, Pause, Video, Clock } from "lucide-react";
import { useState } from "react";

interface VideoSegment {
  start_time: number;
  end_time: number;
  text: string;
  topic?: string;
}

interface VideoCardProps {
  // video_id removed (unused)
  title: string;
  duration: number;
  thumbnail_url?: string;
  segments: VideoSegment[];
  status: "processing" | "ready" | "error";
}

/**
 * Carte vidéo intégrant le lecteur, la transcription segmentée et la navigation.
 */
export function VideoCard({ video_id, title, duration, thumbnail_url, segments, status }: VideoCardProps) {
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  // Formattage du temps (secondes -> MM:SS)
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Navigation vers un segment
  const jumpToTime = (time: number) => {
    setCurrentTime(time);
    // Ici, appeler l'API du lecteur vidéo réel
    console.log(`Jump to ${time}s`);
  };

  if (status === "processing") {
    return (
      <Card className="w-full max-w-2xl border-l-4 border-l-yellow-500">
        <CardContent className="p-6 flex items-center gap-4">
          <Video className="h-10 w-10 text-yellow-500 animate-pulse" />
          <div>
            <h3 className="font-semibold">Traitement de la vidéo en cours...</h3>
            <p className="text-sm text-muted-foreground">Transcription et segmentation en cours.</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (status === "error") {
    return (
      <Card className="w-full max-w-2xl border-l-4 border-l-red-500 bg-red-50">
        <CardContent className="p-6">
          <h3 className="font-semibold text-red-800">Erreur lors du traitement de la vidéo</h3>
          <p className="text-sm text-red-600">Veuillez réessayer plus tard.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-2xl border-l-4 border-l-purple-500 shadow-md overflow-hidden">
      <CardHeader className="pb-2 bg-muted/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Video className="h-5 w-5 text-purple-500" />
            <CardTitle className="text-lg">{title}</CardTitle>
          </div>
          <Badge variant="outline">{formatTime(duration)}</Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-4">
        {/* Zone Vidéo (Placeholder pour lecteur réel) */}
        <div className="aspect-video bg-black rounded-md relative group cursor-pointer flex items-center justify-center">
          {thumbnail_url ? (
            <img src={thumbnail_url} alt={title} className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" />
          ) : (
            <div className="text-muted-foreground flex flex-col items-center">
              <Video className="h-12 w-12 mb-2" />
              <span>Lecteur Vidéo</span>
            </div>
          )}
          
          {/* Overlay Contrôles */}
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 group-hover:bg-black/20 transition-colors">
            <Button
              size="icon"
              variant="secondary"
              className="h-16 w-16 rounded-full hover:scale-110 transition-transform"
              onClick={() => setIsPlaying(!isPlaying)}
            >
              {isPlaying ? <Pause className="h-8 w-8" /> : <Play className="h-8 w-8 ml-1" />}
            </Button>
          </div>

          {/* Barre de progression (Bas) */}
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-700/50">
            <div 
              className="h-full bg-purple-500 transition-all duration-100" 
              style={{ width: `${(currentTime / duration) * 100}%` }}
            />
          </div>
        </div>

        {/* Timeline des Segments */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <span>Segments & Transcription</span>
            <Clock className="h-3 w-3" />
          </div>
          
          <ScrollArea className="h-40 w-full rounded-md border p-2 bg-muted/20">
            <div className="space-y-1">
              {segments.map((seg, idx) => (
                <button
                  key={idx}
                  onClick={() => jumpToTime(seg.start_time)}
                  className={`w-full text-left p-2 rounded text-xs transition-colors flex gap-3 ${
                    currentTime >= seg.start_time && currentTime < seg.end_time
                      ? "bg-purple-100 text-purple-900 font-medium"
                      : "hover:bg-muted"
                  }`}
                >
                  <span className="font-mono text-[10px] text-muted-foreground flex-shrink-0">
                    {formatTime(seg.start_time)}
                  </span>
                  <span className="line-clamp-2 flex-1">{seg.text}</span>
                  {seg.topic && (
                    <Badge variant="secondary" className="text-[9px] h-5 px-1 flex-shrink-0">
                      {seg.topic}
                    </Badge>
                  )}
                </button>
              ))}
            </div>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
}
