// Mission Identité — layout de l'arbre PUBLIC ( /sign-in, /sign-up… ).
//
// Ces routes sont montées AVANT le shell applicatif : sans sidebar (
// donc sans ThreadList qui appelle l'API ), sans header, sans
// CommandPalette ⌘K. Un visiteur sans session ne doit pas voir — ni
// déclencher — l'interface de l'application.
//
// Hauteur : ce wrapper EST le conteneur pleine page. Le parent utilisé
// pour l'instant ( h-svh + overflow-hidden du shell ) était plus bas que
// son enfant → 40 px de contenu tronqués et un scroll imbriqué. Ici le
// parent est un flex ligne : l'enfant ( AuthLayout ) s'étire sur toute
// la hauteur disponible, et la page grandit si le formulaire dépasse
// l'écran. dvh ( pas svh ) : la barre navigateatrice mobile ne fait
// plus rebondir la mise en page.
'use client';

import type { ReactNode } from 'react';

export function PublicLayout({ children }: { children: ReactNode }) {
  return <div className="flex min-h-dvh bg-background">{children}</div>;
}
