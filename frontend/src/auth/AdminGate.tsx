// Mission Identité — garde ADMIN ( §9/§20 ).
//
// États DISTINCTS, dans cet ordre :
//   1. loading      → résolution de la session en cours ( on attend )
//   2. non-connecté → redirection vers la connexion ( Neon ou dev )
//   3. connecté non-admin → 403 EXPLICITE ( pas de redirection silencieuse :
//      l'utilisateur doit savoir pourquoi il ne peut pas entrer )
//   4. admin        → contenu
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
  const { signedIn, loading, isAdmin, devMode } = useCurrentUser();

  // 1. Résolution de la session : ne rien afficher de stable ( le rôle
  //    n'est pas encore connu — un 403 flasherait pour un admin ).
  if (loading) {
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

  // 3. Connecté mais pas admin : 403 explicite + action possible.
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

  // 4. Admin → contenu.
  return <>{children}</>;
}
