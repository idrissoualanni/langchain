// Page 404 — route inconnue.
//
// Catch-all : avant cette page, une URL inconnue tombait dans le vide
// ( Routes sans correspondance → écran blanc ). On explique et on
// propose deux sorties au lieu de planter l'utilisateur.
'use client';

import { Link } from 'react-router-dom';
import { Home, Search } from 'lucide-react';

import { Button } from '@/components/ui/button';

export function NotFoundPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
        Erreur 404
      </p>
      <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
        Cette page n'existe pas
      </h1>
      <p className="max-w-sm text-[13px] text-muted-foreground">
        L'URL est peut-être fausse, ou la page a été déplacée. Le reste de
        l'application reste accessible.
      </p>
      <div className="mt-2 flex flex-wrap items-center justify-center gap-2.5">
        <Link to="/assistant">
          <Button type="button" size="sm">
            <Home />
            Retour à l'assistant
          </Button>
        </Link>
        <Link to="/assistant">
          <Button type="button" variant="outline" size="sm">
            <Search />
            Rechercher une page (⌘K)
          </Button>
        </Link>
      </div>
    </div>
  );
}
