// Mission Identité — pont Neon Auth ↔ apiFetch + contexte user réactif.
//
// apiFetch ( api/base.ts ) lit window.__neonGetToken : ce module le
// pose dès qu'une session Neon existe. Un seul endroit injecte le
// token ( §19 ) — aucun autre fichier ne touche au header Authorization.
// Il alimente aussi NeonUserContext ( nom/email pour les pages profil ).
//
// État partagé entre instances ( la page de login déclenche le refresh,
// Protected et la sidebar s'y abonnent ).
'use client';

import { useEffect, useState } from 'react';
import { authClient } from '../lib/neon';
import { NeonUserContext, type NeonUserData } from '../hooks/useCurrentUser';

const EMPTY: NeonUserData = {
  isSignedIn: false,
  userId: null,
  name: null,
  email: null,
  emailVerified: false,
  // pending=false ICI seulement : on AFFIRME « déconnecté » parce
  // qu'on le sait (session résolée, aucun user). L'état initial,
  // plus bas, ne peut pas être celui-ci.
  pending: false,
};

// EF-11 — l'état initial NE PEUT PAS être EMPTY.
//
// Avant, le module démarrait sur `currentUser = EMPTY`, ce qui
// signifie « déconnecté » alors que la session n'était simplement pas
// encore résolée : au cold start, les gardes de routes lisaient
// signedIn=false et redirigeaient vers /sign-in, puis la session
// arrivait et renvoyait vers l'app — l'aller-retour visible à chaque
// rechargement. On distingue donc trois états et non deux : la
// RÉSOLUTION en cours, l'état vide définitif (EMPTY ci-dessus), et
// l'utilisateur connecté.
const PENDING: NeonUserData = { ...EMPTY, pending: true };

let currentUser: NeonUserData = PENDING;
let listeners: Array<(u: NeonUserData) => void> = [];

export function notifyNeonUser(u: NeonUserData) {
  currentUser = u;
  listeners.forEach((fn) => fn(u));
}

export function getNeonUser(): NeonUserData {
  return currentUser;
}

export function subscribeNeonUser(
  fn: (u: NeonUserData) => void
): () => void {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((f) => f !== fn);
  };
}

// JWT signé ( Ed25519 ) mis en cache : la session Better Auth pose un
// token OPAQUE ( session.token, 32 chars, non-JWT ) inutilisable par
// verify_neon_token(). Le vrai JWT n'est servi que par GET /token.
// On le renouvelle avant expiration pour suivre la rotation Neon.
let cachedJWT: string | null = null;
let cachedExp = 0;

function decodeExp(jwt: string): number | null {
  try {
    const payload = JSON.parse(
      atob(jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))
    );
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

async function resolveJWT(): Promise<string | null> {
  const now = Date.now();
  if (cachedJWT && cachedExp > now + 60_000) return cachedJWT;
  const token = await authClient.getJWTToken();
  cachedJWT = token;
  cachedExp = token ? decodeExp(token) ?? 0 : 0;
  return token;
}

/** Purge LOCALE et IMMÉDIATE de la session — sans appel réseau.
 *
 *  EF-10 : après un `signOut` RÉUSSI, l'état doit passer à « anonyme »
 *  tout de suite, et non après un aller-retour vers le fournisseur.
 *  `refreshNeonSession()` ne convient pas ici pour deux raisons :
 *
 *  1. Il attend `GET /get-session`. Pendant ce round-trip, l'UI affiche
 *     encore l'utilisateur connecté — c'est précisément le symptôme
 *     que EF-10 décrit (« l'utilisateur reste visuellement connecté »),
 *     simplement plus court. Et si le fournisseur est lent ou
 *     injoignable juste après le sign-out, la déconnexion n'est jamais
 *     reflétée du tout.
 *  2. Sécurité : le cache JWT et `window.__neonGetToken` resteraient
 *     vivants pendant ce même round-trip. Toute requête API partie
 *     entre le sign-out et la réponse de `/get-session` porterait
 *     l'ANCIEN Bearer, que le backend accepte encore jusqu'à son `exp`
 *     — une déconnexion qui n'en est pas une. On retire donc le
 *     jeton AVANT toute attente.
 *
 *  L'ordre n'est pas indifférent : on coupe d'abord la source du jeton
 *  (`__neonGetToken`), puis le cache (défense en profondeur si un
 *  appelant a déjà capturé la référence), et on publie enfin l'état
 *  vide — la notification est ce qui fait basculer les gardes de
 *  routes, elle vient en dernier pour que l'UI bascule une seule fois,
 *  sur un état cohérent. */
export function clearNeonSession(): void {
  (window as any).__neonGetToken = undefined;
  cachedJWT = null;
  cachedExp = 0;
  notifyNeonUser(EMPTY);
}

/** Délai maximal de résolution de session auprès du fournisseur.
 *
 *  EF-19 : `fetch` n'a pas de délai maximal, et l'état `pending`
 *  introduced par EF-11 est un état BLOQUANT ( les gardes de routes
 *  attendent). Sans cette borne, un `GET /get-session` qui ne répond
 *  jamais — réseau noir, fournisseur qui accepte la connexion TCP sans
 *  répondre, DNS lent — laisserait toute l'application figée sur
 *  « Résolution de la session… », sans aucune action possible. On borne
 *  donc, et au-delà on tranche comme une panne réseau. */
const SESSION_TIMEOUT_MS = 15_000;

/** Interroge le fournisseur, mais pas indéfiniment.
 *
 *  On abandonne l'attente sans annuler la requête (`fetch` n'a pas de
 *  timeout natif et Better Auth n'expose pas d'AbortSignal ici) : la
 *  requête en vol se terminera d'elle-même, et comme plus rien n'en
 *  lit le résultat après le `race`, elle ne peut pas écraser un état
 *  publié entre-temps. */
async function getSessionBounded(): Promise<{
  session: Awaited<ReturnType<typeof authClient.getSession>>;
  timedOut: boolean;
}> {
  let timer: number | undefined;
  const deadline = new Promise<{ session: null; timedOut: true }>((resolve) => {
    timer = window.setTimeout(
      () => resolve({ session: null, timedOut: true }),
      SESSION_TIMEOUT_MS
    );
  });
  const answered = authClient
    .getSession()
    .then((session) => ({ session, timedOut: false }));
  try {
    return await Promise.race([answered, deadline]);
  } finally {
    if (timer !== undefined) window.clearTimeout(timer);
  }
}

/** Rafraîchit le token + l'user ( login / focus / retour d'onglet ). */
export async function refreshNeonSession() {
  try {
    const { session, timedOut } = await getSessionBounded();

    if (timedOut) {
      // Deux verdicts DIFFÉRENTS selon ce qu'on sait déjà — confondre
      // les deux est exactement le défaut qu'EF-9 et EF-11 décrivent.
      if (currentUser.isSignedIn) {
        // Session DÉJÀ connue ( retour sur l'onglet, token en cache ) :
        // on ne déconnecte pas sur un silence réseau, on met simplement
        // fin à l'attente. Les gardes se libèrent, le JWT en cache
        // reste valable jusqu'à son `exp`, et le prochain appel API
        // qui reçoit un 401 déclenche le refresh + rejeu ( base.ts ).
        notifyNeonUser({ ...currentUser, pending: false });
        return;
      }
      // Rien de connu ( cold start ) : l'identité est INDÉTERMINÉE.
      // On applique l'invariant I-2 — une défaillance du fournisseur
      // produit un refus, jamais un accès — donc « pas de session »,
      // ce qui mènera l'utilisateur vers /sign-in.
      (window as any).__neonGetToken = undefined;
      notifyNeonUser(EMPTY);
      return;
    }

    (window as any).__neonGetToken = session?.user
      ? () => resolveJWT()
      : undefined;
    // Invalide le cache JWT au changement de session.
    cachedJWT = null;

    notifyNeonUser({
      isSignedIn: !!session?.user,
      userId: session?.user?.id ?? null,
      name: session?.user?.name ?? null,
      email: session?.user?.email ?? null,
      emailVerified: !!session?.user?.emailVerified,
      // La résolution est terminée : plus aucune garde n'a le droit
      // de « patienter », quelle que soit sa réponse.
      pending: false,
    });
  } catch {
    (window as any).__neonGetToken = undefined;
    // Même en cas d'échec on AFFIRME un état (déconnecté) au lieu de
    // rester en attente indéfinie : sans cela, une session invalide
    // laisserait l'app bloquée sur « Résolution de la session… ».
    notifyNeonUser(EMPTY);
  }
}

export function NeonTokenBridge({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<NeonUserData>(currentUser);

  useEffect(() => {
    const unsub = subscribeNeonUser(setUser);
    // Premier chargement : résoudre la session existante.
    refreshNeonSession();
    // Rafraîchir au retour sur l'onglet ( session peut expirer ).
    window.addEventListener('focus', refreshNeonSession);
    return () => {
      unsub();
      window.removeEventListener('focus', refreshNeonSession);
    };
  }, []);

  return (
    <NeonUserContext.Provider value={user}>
      {children}
    </NeonUserContext.Provider>
  );
}
