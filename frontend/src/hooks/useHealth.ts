// Hook Health — statuts Ollama / LangGraph / SQLite
//
// Render free tier : l'API dort entre les requêtes, un health check la
// réveille ( cold start ~45 s ). Poller à intervalle fixe pendant qu'elle
// dort empile les requêtes, sature le pool de connexions du navigateur
// ( ERR_INSUFFICIENT_RESOURCES ) et empêche tout appel légitif de passer.
// En cas d'échec on ralentit ( backoff exponentiel ) puis on arrête.
//
// Plusieurs composants montent ce hook ( sidebar + ComposerModelPicker ).
// On délègue le poll à un seul intervalle partagé au niveau module pour
// ne jamais ouvrir plusieurs requêtes /api/health en parallèle.
import { useCallback, useEffect, useState } from 'react';
import type { HealthInfo } from '../types/agent';
import { getHealth } from '../api/logs';

const MAX_FAILURES = 5;

type HealthState = { health: HealthInfo | null; error: string | null };

let pollState: HealthState = { health: null, error: null };
let listeners = new Set<(s: HealthState) => void>();
let timer: ReturnType<typeof setTimeout> | null = null;
let failures = 0;
let stopped = false;

function notify() {
  for (const l of listeners) l(pollState);
}

async function tick(intervalMs: number) {
  if (stopped) return;
  try {
    pollState = { health: await getHealth(), error: null };
    failures = 0;
  } catch (e) {
    failures += 1;
    pollState = {
      health: null,
      error: e instanceof Error ? e.message : 'Backend injoignable',
    };
    // Trop d'échecs consécutifs : on arrête de poller pour ne pas
    // saturer le pool de connexions du navigateur contre un backend
    // dormant ou injoignable. refresh() relance le poll.
    if (failures >= MAX_FAILURES) {
      stopped = true;
    }
  }
  notify();

  if (stopped) {
    timer = null;
    return;
  }
  // Délai fixe tant que tout va bien ; il double à chaque échec
  // ( 30s -> 60s -> 120s ... ) jusqu'à l'arrêt complet.
  const delay = failures > 0
    ? Math.min(intervalMs * 2 ** failures, intervalMs * 8)
    : intervalMs;
  timer = setTimeout(() => tick(intervalMs), delay);
}

export function useHealth(intervalMs = 30000) {
  const [state, setState] = useState<HealthState>(pollState);

  const refresh = useCallback(async () => {
    // Repart de zéro : un refresh manuel doit réarmer le poll même après
    // l'arrêt automatique sur échecs répétés.
    failures = 0;
    stopped = false;
    if (timer) clearTimeout(timer);
    await tick(intervalMs);
  }, [intervalMs]);

  useEffect(() => {
    listeners.add(setState);
    setState(pollState);
    if (!timer && !stopped) {
      timer = setTimeout(() => tick(intervalMs), 0);
    }
    return () => {
      listeners.delete(setState);
    };
  }, [intervalMs]);

  return { health: state.health, error: state.error, refresh };
}
