// Token LiveKit avec renouvellement automatique avant expiration.
//
// /api/livekit/token émet un JWT d'1 heure. Si la page reste ouverte
// au-delà, le client LiveKit se fait rejeter ( 401 /rtc/v1/validate )
// et boucle en déconnexion/reconnexion sans fin.
// On décode l'expiration ( exp ) côté frontend et on renouvelle 5 min
// avant le terme — l'agent et la room restent joints.
"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/api/base";

export interface LiveKitTokenResponse {
  token: string;
  url: string;
  room_name: string;
}

interface TokenState {
  token: string;
  url: string;
  roomName: string;
}

function expOf(jwt: string): number | null {
  try {
    const part = jwt.split(".")[1];
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = JSON.parse(json).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

/**
 * Récupère un token LiveKit et le renouvelle avant expiration.
 * Retourne { data, loading, error } — prêt pour LiveKitRoom.
 */
export function useLiveKitToken(purpose: "voice" | "video" = "video") {
  const [data, setData] = useState<TokenState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function refresh() {
      try {
        const res = await apiFetch<LiveKitTokenResponse>("/api/livekit/token", {
          method: "POST",
          body: JSON.stringify(purpose === "voice" ? { purpose: "voice" } : {}),
        });
        if (!alive) return;
        setData({
          token: res.token,
          url: res.url,
          roomName: res.room_name,
        });
        setError(null);

        // Renouveler 5 min avant l'expiration ( défaut 50 min si exp illisible ).
        const exp = expOf(res.token);
        const delay = exp ? Math.max(exp - Date.now() - 5 * 60_000, 30_000) : 50 * 60_000;
        timer = setTimeout(refresh, delay);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : "Erreur inconnue");
      } finally {
        if (alive) setLoading(false);
      }
    }

    refresh();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [purpose]);

  return { data, loading, error };
}
