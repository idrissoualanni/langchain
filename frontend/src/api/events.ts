// SSE — bus d'événements agent temps réel
//
// Mission Identité (§17/§18) : ce bus diffuse TOUTE l'activité
// ( messages utilisateurs inclus ) → le backend le réserve aux ADMIN
// et exige une PREUVE de session par le header Authorization (
// backend/app/logging/sse.py ).
//
// Pourquoi plus d'EventSource NATIF : le 2e argument du constructeur
// n'accepte que { withCredentials } — les navigateurs ont refusé
// d'ajouter des headers à EventSource ( whatwg/html#2177 ). L'ancien
// code ouvrait donc un flux SANS token → 401 → et comme `onerror`
// était vide, EventSource rejouait la connexion à l'INFINI sur un
// 401 définitif : boucle réseau silencieuse, jamais d'information.
//
// Correction : on lit le flux avec fetch — seule voie compatible
// headers, déjà utilisée pour /api/chat/stream ( assistant-ui/api.ts ).
// apiFetchRaw injecte le Bearer ET joue un refresh + rejeu unique sur
// 401, donc un JWT simplement expiré ne casse plus le flux. La
// reconnexion devient NOTRE responsabilité : elle est BORNÉE ( nombre
// max de tentatives + backoff progressif) au lieu d'être infinie.
import { apiFetchRaw } from './base';
import type { AgentEvent } from '../types/agent';

/** Nombre maximal de reconnexions avant abandon : au-delà, on ne
 *  martèle plus un endpoint qui refuse la connexion (c'était
 *  exactement le comportement infini d'EventSource). */
const MAX_RECONNECTS = 5;

/** Backoff progressif 1s → 2s → 4s → 8s → 16s, plafonné : un réseau
 *  qui revient ne doit pas attendre 30 s, un réseau mort ne doit pas
 *  être sondé en boucle serrée. */
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

/** Séparateurs SSE — construits via fromCharCode : un \n littéral
 *  ferait passer le lint no-control-regex / no-useless-escape et
 *  alourdit la comparaison à chaque frame. */
const FRAME_SEP = String.fromCharCode(10, 10);
const LINE_SEP = String.fromCharCode(10);

/** Nom d'événement émis par le backend pour les données métier
 *  ( les `ping` de keepalive sont ignorés : le payload "{}" n'a
 *  aucun sens applicatif ). */
const BUS_EVENT = 'agent-event';

/** Extrait l'agent-event d'un frame `event: agent-event\ndata: {...}`.
 *  Renvoie null pour un ping, un frame vide ou du JSON invalide : on
 *  veut qu'un keepalive ou une trame corrompue n'interrompe jamais la
 *  lecture du flux. */
function parseFrame(frame: string): AgentEvent | null {
  const lines = frame.split(LINE_SEP);
  const name = lines.find((l) => l.startsWith('event:'))?.slice(6).trim();
  if (name && name !== BUS_EVENT) return null;

  const dataLine = lines.find((l) => l.startsWith('data:'));
  if (!dataLine) return null;
  try {
    return JSON.parse(dataLine.slice(5).trim()) as AgentEvent;
  } catch {
    return null;
  }
}

/** Connexion au flux SSE /api/events ( authentifié ).
 *  Retourne une fonction de déconnexion — qui ferme le socket ET
 *  annule toute reconnexion programmée. */
export function connectAgentEvents(
  onEvent: (event: AgentEvent) => void
): () => void {
  // Un seul AbortController pour toute la vie du flux : il coupe le
  // fetch en cours ET rend le prochain inutile après déconnexion.
  const controller = new AbortController();
  let stopped = false;
  let timer: number | null = null;
  let attempt = 0;

  /** Lit le corps du flux jusqu'à la fermeture du serveur. Renvoie
   *  true si au moins un événement est passé : c'est le signal
   *  « connexion saine » qui remet le compteur de tentatives à zéro
   *  (sinon une reconnexion réussie mais muette serait comptée
   *  comme un échec). */
  const pump = async (body: ReadableStream<Uint8Array>): Promise<boolean> => {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let received = false;

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      // { stream: true } : un chunk peut couper un caractère UTF-8
      // en deux — sans ça, un événement en français peut casser le
      // JSON du frame suivant.
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split(FRAME_SEP);
      // Le dernier fragment est incomplet par construction : on le
      // garde pour le prochain chunk.
      buffer = frames.pop() ?? '';

      for (const frame of frames) {
        const event = parseFrame(frame);
        if (!event) continue;
        received = true;
        onEvent(event);
      }
    }
    return received;
  };

  const scheduleReconnect = (): void => {
    if (stopped) return;
    if (attempt >= MAX_RECONNECTS) {
      console.warn(
        `[events] flux /api/events abandonné après ${MAX_RECONNECTS} tentatives de reconnexion`,
      );
      return;
    }
    attempt += 1;
    const delay = Math.min(
      BACKOFF_BASE_MS * 2 ** (attempt - 1),
      BACKOFF_MAX_MS
    );
    timer = window.setTimeout(() => {
      timer = null;
      void run();
    }, delay);
  };

  async function run(): Promise<void> {
    if (stopped) return;

    let healthy = false;
    let fatal = false;

    try {
      const res = await apiFetchRaw('/api/events', {
        headers: { Accept: 'text/event-stream' },
        signal: controller.signal,
      });

      if (res.status === 401 || res.status === 403) {
        // La session est refusée. apiFetchRaw a DÉJÀ tenté un refresh
        // + rejeu unique : recommencer ne peut pas aboutir, et
        // martèler l'endpoint ne ferait que le garder en 401. On
        // abandonne — l'UI de logs reste simplement « déconnectée ».
        console.warn(
          `[events] /api/events → HTTP ${res.status} : flux non autorisé, abandon`,
        );
        fatal = true;
      } else if (!res.ok || !res.body) {
        console.warn(`[events] /api/events → HTTP ${res.status}`);
      } else {
        healthy = await pump(res.body);
      }
    } catch (err) {
      // Une fermeture volontaire ( démontage du composant ) n'est pas
      // une panne : on ne la remonte pas.
      if (!stopped) console.warn('[events] flux /api/events interrompu', err);
    }

    if (stopped) return;
    if (fatal) {
      stopped = true;
      return;
    }
    // Flux ayant réellement été productif → on repart de zéro.
    if (healthy) attempt = 0;
    scheduleReconnect();
  }

  void run();

  return () => {
    stopped = true;
    if (timer !== null) {
      window.clearTimeout(timer);
      timer = null;
    }
    controller.abort();
  };
}
