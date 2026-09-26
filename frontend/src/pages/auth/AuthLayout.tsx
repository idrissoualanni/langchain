// Mission Identité — layout partagé des pages d'authentification.
//
// Design system Glace / Papier / Encre : zéro hex dispersée, tout passe
// par les tokens oklch ( bg-background, bg-card, text-foreground… ).
// Dark mode via la classe .dark — comme le reste de l'app.
//
// Signature : le panneau gauche n'est pas une image générique mais une
// composition typographique éditoriale ( citations réelles d'élèves +
// index des modules ). Il se replie sous le breakpoint lg.
'use client';

import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

// Respecte prefers-reduced-motion : les animations d'entrée deviennent
// immédiates, on garde la lisibilité sans mouvement inutile.
const prefersReducedMotion =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Panneau gauche : composition typographique éditoriale. */
function BrandPanel() {
  return (
    <aside className="relative hidden w-[44%] min-w-[26rem] shrink-0 flex-col justify-between overflow-hidden border-r border-border bg-secondary p-10 xl:p-14 lg:flex">
      {/* Grain de profondeur : un seul dégradé subtil, pas de déco. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          background:
            'radial-gradient(60% 50% at 12% 6%, var(--accent) 0%, transparent 70%)',
        }}
      />

      <div className="relative z-10">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="inline-block size-2.5 rounded-full bg-foreground/70"
          />
          <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
            Agent&nbsp;Tutor
          </span>
        </div>
      </div>

      <div className="relative z-10 max-w-xl">
        <motion.p
          initial={prefersReducedMotion ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="font-serif text-[2rem] font-medium leading-[1.18] italic tracking-tight text-foreground xl:text-[2.5rem]"
        >
          «&nbsp;Il m'a expliqué le même théorème trois fois, chaque fois
          avec un exemple différent. La troisième, j'ai
          compris.&nbsp;»
        </motion.p>
        <p className="mt-5 text-[13px] text-muted-foreground">
          — Élève en terminale, session de révision baccalauréat
        </p>
      </div>

      {/* Index des modules. Pas de numérotation : Assistant / Learning /
          Mémoire ne forment pas une séquence d'usage — l'ordre ne porte
          aucune information, les marqueurs 01/02/03 étaient de la déco. */}
      <div className="relative z-10 flex flex-col gap-3">
        {[
          ['Assistant', 'Raisonnement guidé, jamais la réponse crue'],
          ['Learning', 'Suivi de progression par matière'],
          ['Mémoire', 'Rappelle ce que tu as déjà appris'],
        ].map(([titre, desc]) => (
          <div key={titre} className="flex items-baseline gap-3">
            <span className="text-[13px] font-medium text-foreground">
              {titre}
            </span>
            <span className="text-[13px] text-muted-foreground">
              {desc}
            </span>
          </div>
        ))}
      </div>
    </aside>
  );
}

/**
 * Cadre des pages d'authentification.
 *
 * - panneau de marque à gauche ( desktop )
 * - zone formulaire centrée à droite, largeur max contrôlée
 * - animation d'entrée en cascade pour les enfants directs
 *
 * Hauteur : ce composant ne claim plus min-h-svh — il REMPLIT le
 * PublicLayout ( flex ligne → l'enfant s'étire ). Claimer sa propre
 * hauteur minimum le faisait déborder du parent, qui tronquait 40 px de
 * formulaire ( header du shell ) et déclenchait un scroll imbriqué.
 */
export function AuthLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div className="flex h-full min-h-0 bg-background">
      <BrandPanel />

      {/* Colonne scrollable : le centrage passe par my-auto sur la carte
          ( pas items-center ) — un enfant centré qui déborde voit son
          haut devenir inatteignable dans un conteneur scrollable. */}
      <main className="relative flex flex-1 flex-col overflow-y-auto px-5 pt-20 pb-10 sm:px-8 sm:pt-16">
        {/* Marque compacte visible uniquement sur mobile ( le panneau
            gauche est masqué sous lg ). Le padding-top de <main> lui
            réserve sa bande : jamais de chevauchement avec le formulaire. */}
        <div className="absolute left-5 top-5 flex items-center gap-2.5 lg:hidden sm:left-8 sm:top-8">
          <span
            aria-hidden
            className="inline-block size-2 rounded-full bg-foreground/70"
          />
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Agent&nbsp;Tutor
          </span>
        </div>

        <motion.div
          initial={prefersReducedMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="my-auto w-full max-w-[26rem]"
        >
          {children}
        </motion.div>
      </main>
    </div>
  );
}
