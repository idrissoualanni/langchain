// Token LiveKit avec renouvellement automatique avant expiration.
//
// /api/livekit/token émet un JWT d'1 heure. Si la page reste ouverte
// au-delà, le client LiveKit se fait rejeter ( 401 /rtc/v1/validate )
// et boucle en déconnexion/reconnexion sans fin.
// On décode l'expiration ( exp ) côté frontend et on renouvelle 5 min
// avant le terme — l'agent et la room restent joints.
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/api/base";

/** Nombre de reprises après un échec TRANSITOIRE ( réseau / 5xx ).
 *
 *  Borné à 3 : au-delà, la panne n'est plus transitoire et le hook arrête
 *  de temporiser — l'UI affiche l'erreur, ce qui vaut mieux qu'une
 *  boucle de requêtes invisible pendant des heures. */
const MAX_TRANSIENT_RETRIES = 3;

/** Délai avant reprise après un échec transitoire ( ms ). */
const TRANSIENT_RETRY_MS = 15_000;

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
 *
 * Le corps de la requête est vide : le backend ( `TokenRequest` ) ne
 * connaît que `room_name` / `user_id` et déduit la room de la session
 * — un `purpose` envoyé ici était silencieusement ignoré.
 */
export function useLiveKitToken() {
  const [data, setData] = useState<TokenState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Compteur de reprises transitoires — une REF, pas un état : il est lu
  // et écrit DANS la fonction async refresh(), et un useState y créerait
  // une closure périmée (chaque rendu repartirait de la valeur capturée).
  const retryRef = useRef(0);

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
          body: JSON.stringify({}),
        });
        if (!alive) return;
        setData({
          token: res.token,
          url: res.url,
          roomName: res.room_name,
        });
        setError(null);
        // Succès → le compteur de reprises repart de zéro : les 3
        // tentatives tolérées valent pour 3 échecs CONSÉCUTIFS.
        retryRef.current = 0;

        // Renouveler 5 min avant l'expiration ( défaut 50 min si exp illisible ).
        const exp = expOf(res.token);
        const delay = exp ? Math.max(exp - Date.now() - 5 * 60_000, 30_000) : 50 * 60_000;
        timer = setTimeout(refresh, delay);
      } catch (e) {
        if (!alive) return;
        const msg = e instanceof Error ? e.message : "Erreur inconnue";
        setError(msg);

        // ⚠️ Une session perdue ne se répare PAS en temporisant.
        //
        // Le cookie de session suit le JWT ( 15 min ) et se renouvelle en
        // silence. Si cette requête échoue, ce n'est PAS l'expiration du
        // token LiveKit : le renouvellement n'a lieu qu'après un SUCCÈS,
        // donc aucun timer n'est armé à ce moment. Retenter dans 50 min
        // produirait un échec MUET — l'écran « Session vocale indisponible »
        // reste affiché sans rien signaler pendant tout ce temps.
        //
        // On distingue les deux causes :
        //   ApiError 401/403 → session perdue → on SURVIT, pas de retry
        //                     ( le remède est la reconnexion, pas temporiser )
        //   réseau / 5xx    → transitoire           → on retente, borné
        const permanent =
          e instanceof ApiError && (e.status === 401 || e.status === 403);
        if (!permanent) {
          // Reprise bornée : le compteur est remis à zéro au succès, donc
          // 3 échecs CONSÉCUTIFS déclenchent l'arrêt, pas 3 échecs par jour.
          const next = retryRef.current + 1;
          retryRef.current = next;
          if (next <= MAX_TRANSIENT_RETRIES) {
            // L'erreur est visible tout de suite, MAIS la session repart
            // seule : le hook n'abandonne pas au premier incident réseau.
            setError(msg);
            timer = setTimeout(refresh, TRANSIENT_RETRY_MS);
          } else {
            setError(
              `${msg} — échec réseau, abandon après ${MAX_TRANSIENT_RETRIES} tentatives. Recharge la page.`,
            );
          }
        }
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
  }, []);

  // Identité stable : sans ça chaque re-render ( ex: le chrono de
  // session qui tick toutes les secondes ) passe un nouvel objet `data`
  // au consommateur et fait remonter la room.
  return useMemo(() => ({ data, loading, error }), [data, loading, error]);
}
