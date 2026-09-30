// Mission Identité — garde ADMIN ( §9/§20 ).
//
// États DISTINCTS, dans cet ordre :
//   0. session en cours  → la session Neon n'est pas résolue ( EF-11 )
//   1. loading           → rôle en cours de résolution ( on attend )
//   2. non-connecté      → redirection vers la connexion ( Neon ou dev )
//   3. erreur de vérif.  → échec explicite + réessai ( EF-15 )
//   4. connecté non-admin→ 403 EXPLICITE ( pas de redirection silencieuse :
//      l'utilisateur doit savoir pourquoi il ne peut pas entrer )
//   5. admin             → contenu
//
// Le rôle vient de la SESSION résolue backend ( /api/users/me ) — jamais
// déclaré par le frontend.
'use client';

import type { ReactNode } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { Lock } from 'lucide-react';

import { useCurrentUser } from '../hooks/useCurrentUser';
import { Button } from '../components/ui/button';

export function AdminGate({ children }: { children: ReactNode }) {
  const { signedIn, loading, isAdmin, devMode, sessionPending, error, reload } =
    useCurrentUser();

  // 0a. EF-11 : la session Neon n'est pas encore résolue. `signedIn`
  //     vaut false « provisoirement » — traiter ça comme une
  //     déconnexion produisait l'aller-retour /admin → /sign-in →
  //     /admin à chaque cold start. On attend.
  // 1. Résolution de la session / du rôle : ne rien afficher de
  //    stable ( un 403 flasherait pour un admin ).
  if (sessionPending || loading) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2">
        <span className="text-sm text-muted-foreground">
          Vérification des droits…
        </span>
      </div>
    );
  }

  // 2. Pas de session → connexion ( Neon en prod, dev-login en dev ).
  if (!signedIn) {
    return <Navigate to={devMode ? '/dev-login' : '/sign-in'} replace />;
  }

  // 3. EF-15 : le rôle est INCONNU, pas « non-admin ». Afficher le
  //    403 ci-dessous sur une panne réseau reviendrait à deny
  //    l'accès à un administrateur dont la session n'a simplement
  //    pas pu être vérifiée — exactement le downgrade silencieux
  //    qu'on combat. On nomme l'échec et on propose de réessayer.
  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <Lock className="size-8 text-muted-foreground" strokeWidth={1.5} />
        <h1 className="font-serif text-lg font-medium tracking-tight text-foreground">
          Vérification impossible
        </h1>
        <p className="max-w-sm text-[13px] text-muted-foreground">
          {error}
        </p>
        <Button type="button" variant="outline" size="sm" onClick={reload}>
          Réessayer
        </Button>
      </div>
    );
  }

  // 4. Connecté mais pas admin : 403 explicite + action possible.
  //    On ne redirige PAS : l'utilisateur saurait juste qu'il est
  //    arrivé quelque part sans droit, sans en comprendre la cause.
  if (!isAdmin) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <Lock className="size-8 text-muted-foreground" strokeWidth={1.5} />
        <h1 className="font-serif text-lg font-medium tracking-tight text-foreground">
          Accès réservé aux administrateurs
        </h1>
        <p className="max-w-sm text-[13px] text-muted-foreground">
          Ton compte n'a pas les droits administrateur pour cette
          section. Si c'est une erreur, contacte l'équipe responsable
          de l'instance.
        </p>
        <Link to="/assistant" className="mt-1">
          <Button type="button" variant="outline" size="sm">
            Retour à l'assistant
          </Button>
        </Link>
      </div>
    );
  }

  // 5. Admin → contenu.
  return <>{children}</>;
}
