// Mission Identité — pont Neon Auth ↔ contexte user réactif.
//
// Ce module est désormais le SEUL détenteur du JWT Neon côté front, et
// il ne le rend à personne : il l'échange une fois contre un cookie
// HttpOnly (`POST /api/auth/session`) puis n'en garde que l'échéance.
// Le JWT a maintenant une durée de vie de QUINZE MINUTES côté cookie,
// pas trente jours.
//
// Pourquoi ce changement : le header `Authorization: Bearer` était
// injecté dans TOUTE requête via `window.__neonGetToken`, une fonction
// globale. Or une fonction globale est, par définition, lisible par
// n'importe quel script de la page. Un XSS n'avait qu'à l'appeler pour
// s'approprier la session ; il suffisait aussi d'ouvrir les DevTools.
//
// Un cookie `HttpOnly` n'est atteignable ni par le JS de la page, ni par
// une console, ni par l'onglet Network. Le seul effet qui reste à un
// script injecté est d'ÉMETTRE des requêtes au nom de la victime —
// c'est une usurpation de réponse, pas un vol de session, et la
// révocation de session coupe court.
//
// La session longue durée (30–90 j) reste celle de Better Auth, côté
// Neon. Notre cookie ne fait que REFLETER le JWT, renouvelé en silence
// trois minutes avant son expiration.
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

// ----------------------------------------------------------------------
// Mission Sécurité — bascule du JWT vers le cookie HttpOnly
// ----------------------------------------------------------------------

const API_URL = import.meta.env.VITE_API_URL || '';
const SESSION_PATH = '/api/auth/session';

/** Fenêtre de renouvellement : 3 min AVANT l'expiration du JWT.
 *
 *  Trente secondes suffiraient pour un appel isolé. Trois minutes
 *  couvrent le pire cas réel : l'onglet mis en arrière-plan, où les
 *  timers sont throttlés puis figés par le navigateur — on ne peut pas
 *  compter sur un `setTimeout` qui sonne à la seconde. Renewer en
 *  avance absorbe ce retard sans que l'utilisateur le voie. */
const RENEWAL_WINDOW_MS = 3 * 60_000;

let renewalTimer: number | null = null;

function cancelRenewal(): void {
  if (renewalTimer !== null) {
    window.clearTimeout(renewalTimer);
    renewalTimer = null;
  }
}

/** Échange le JWT contre le cookie HttpOnly. `true` si posé.
 *
 *  Le JWT entre dans le corps de la requête et ne ressort JAMAIS dans
 *  la réponse : le backend le vérifie puis le dépose en `Set-Cookie`.
 *  Il n'y a donc aucun point où le token redevient lisible par la page.
 *  On garde `credentials: 'include'` et non `omit` : au premier
 *  renouvellement, un vieux cookie périmé ferait échouer la
 *  vérification server. */
async function pushSessionCookie(jwt: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}${SESSION_PATH}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: jwt }),
    });
    return res.ok;
  } catch {
    // Réseau indisponible : l'UI reste utilisable, le prochain refresh
    // ( focus d'onglet, 401 ) retentera la pose du cookie.
    return false;
  }
}

/** Supprime le cookie côté API au sign-out.
 *
 *  SANS cet appel, le cookie survivrait au signOut côté Neon et le
 *  backend continuerait d'accepter les requêtes pendant les ~15
 *  minutes restantes : une déconnexion qui n'en serait pas une. Le
 *  cookie est borné dans le temps par construction, mais « au plus
 *  quinze minutes » n'est pas « déconnecté ». */
async function dropSessionCookie(): Promise<void> {
  try {
    await fetch(`${API_URL}${SESSION_PATH}`, {
      method: 'DELETE',
      credentials: 'include',
    });
  } catch {
    /* le cookie expirera de lui-même */
  }
}

function scheduleRenewal(expMs: number): void {
  cancelRenewal();
  // Pas d'expiration connue ( claim absent ou illisible ) : on ne
  // programme rien plutôt que de boucler sur un délai arbitraire. Le
  // retry 401 de base.ts prend alors le relais.
  if (!expMs) return;
  // Plancher à 30 s : évite une rafale d'appels si le JWT arrive
  // presque expiré ( horloge du fournisseur en avance ).
  const delay = Math.max(30_000, expMs - Date.now() - RENEWAL_WINDOW_MS);
  renewalTimer = window.setTimeout(() => {
    renewalTimer = null;
    void syncSessionCookie();
  }, delay);
}

/** JWT neuf → cookie posé → prochain renouvellement programmé. */
async function syncSessionCookie(): Promise<boolean> {
  const token = await resolveJWT();
  if (!token) {
    cancelRenewal();
    return false;
  }
  const ok = await pushSessionCookie(token);
  scheduleRenewal(cachedExp);
  return ok;
}

/** Purge LOCALE et IMMÉDIATE de la session — sans appel réseau bloquant.
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
 *  2. Sécurité : le COOKIE de session resterait vivant pendant ce même
 *     round-trip. Toute requête API partie entre le sign-out et la
 *     réponse de `/get-session` porterait l'ANCIEN cookie, que le
 *     backend accepte encore jusqu'à son `exp` — une déconnexion qui
 *     n'en est pas une. On coupe donc la source AVANT toute attente :
 *     le timer de renouvellement est annulé, ce qui empêche le pire
 *     scénario (un renouvellement programmé qui ressuscite la session
 *     quelques secondes après la déconnexion), et le cookie est
 *     révoqué côté API en tâche de fond.
 *
 *  L'ordre n'est pas indifférent : on coupe d'abord ce qui pourrait
 *  regenerer le secret (timer + cache), on révoque le cookie, et on
 *  publie enfin l'état vide — la notification est ce qui fait basculer
 *  les gardes de routes, elle vient en dernier pour que l'UI bascule
 *  une seule fois, sur un état cohérent. */
export function clearNeonSession(): void {
  cancelRenewal();
  cachedJWT = null;
  cachedExp = 0;
  void dropSessionCookie();
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

/** Rafraîchit la session : état utilisateur + cookie de session.
 *
 *  Appelé au login, au cold start, et à chaque retour sur l'onglet. */
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
      cancelRenewal();
      cachedJWT = null;
      cachedExp = 0;
      notifyNeonUser(EMPTY);
      return;
    }

    // Invalide le cache JWT au changement de session AVANT tout
    // ré-échange : sinon `syncSessionCookie()` rendrait le jeton
    // précédent, que le sign-out vient d'invalider chez le fournisseur.
    cachedJWT = null;
    cachedExp = 0;

    const signedIn = !!session?.user;
    // Notification AVANT la synchronisation du cookie : les gardes de
    // routes se libèrent sans attendre un aller-retour réseau ( EF-11 ).
    notifyNeonUser({
      isSignedIn: signedIn,
      userId: session?.user?.id ?? null,
      name: session?.user?.name ?? null,
      email: session?.user?.email ?? null,
      emailVerified: !!session?.user?.emailVerified,
      // La résolution est terminée : plus aucune garde n'a le droit
      // de « patienter », quelle que soit sa réponse.
      pending: false,
    });

    // ICI on attend, et c'est délibéré : `retryAfter401` ( base.ts )
    // consomme le retour de cette fonction puis rejoue la requête. Sans
    // cet `await`, le rejeu partirait avec le cookie expiré — donc un
    // second 401, et le retry ne servirait à rien.
    if (signedIn) {
      await syncSessionCookie();
    } else {
      cancelRenewal();
      void dropSessionCookie();
    }
  } catch {
    cancelRenewal();
    cachedJWT = null;
    cachedExp = 0;
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
      // Un timer de renouvellement survivrait au démontage et
      // continuerait de poser des cookies sur une page morte.
      cancelRenewal();
    };
  }, []);

  return (
    <NeonUserContext.Provider value={user}>
      {children}
    </NeonUserContext.Provider>
  );
}
