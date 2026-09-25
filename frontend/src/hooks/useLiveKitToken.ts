// Token LiveKit avec renouvellement automatique avant expiration.
//
// /api/livekit/token émet un JWT d'1 heure. Si la page reste ouverte
// au-delà, le client LiveKit se fait rejeter ( 401 /rtc/v1/validate )
// et boucle en déconnexion/reconnexion sans fin.
// On décode l'expiration ( exp ) côté frontend et on renouvelle 5 min
// avant le terme — l'agent et la room restent joints.
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
 * Seuil de renouvellement au retour au premier plan ( ms ).
 * Un onglet en veille THROTTLE les timers : au retour, s'il reste moins
 * que cette durée avant l'expiration, on renouvelle tout de suite.
 */
const FOREGROUND_REFRESH_WITHIN_MS = 2 * 60_000;

/**
 * Récupère un token LiveKit et le renouvelle avant expiration.
 * Retourne { data, loading, error } — prêt pour LiveKitRoom.
 */
export function useLiveKitToken(purpose: "voice" | "video" = "video") {
  const [data, setData] = useState<TokenState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Référence stable sur le token courant : le listener visibilitychange
  // ne peut pas dépendre de l'état ( sinon re-souscription à chaque
  // renouvellement ) — il lit la valeur via cette ref.
  const dataRef = useRef<TokenState | null>(null);
  dataRef.current = data;

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

    // Onglet en veille : les timers sont throttlés en arrière-plan — le
    // setTimeout de renouvellement peut ne pas se déclencher à temps.
    // Au retour au premier plan, on vérifie l'expiration : < 2 min
    // restantes → renouvellement immédiat ( sinon boucle 401
    // /rtc/v1/validate dès la prochaine action temps réel ).
    function onVisibility() {
      if (!alive) return;
      if (document.visibilityState !== "visible") return;
      const token = dataRef.current?.token;
      if (!token) return;
      const exp = expOf(token);
      if (exp !== null && exp - Date.now() < FOREGROUND_REFRESH_WITHIN_MS) {
        if (timer) clearTimeout(timer);
        refresh();
      }
    }

    refresh();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [purpose]);

  // Identité stable : sans ça chaque re-render ( ex: le chrono de
  // session qui tick toutes les secondes ) passe un nouvel objet `data`
  // au consommateur et fait remonter la room.
  return useMemo(() => ({ data, loading, error }), [data, loading, error]);
}
