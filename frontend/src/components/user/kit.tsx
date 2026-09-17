// Primitives UI des pages utilisateur (tokens du design system).
//
// Règle : papier / encre / monochrome, accent bleu `--live` uniquement
// pour les états actifs. Aucun hex dispersé, aucun violet/indigo,
// aucun gradient / glassmorphism / glow (brief §17).
import { NavLink } from 'react-router-dom';
import type { HTMLAttributes, ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

// ------------------------------------------------------------------
// En-tête de page
// ------------------------------------------------------------------

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="border-border flex flex-wrap items-start gap-3 border-b px-6 py-5">
      <div className="min-w-0">
        {eyebrow && (
          <span className="text-muted-foreground font-mono text-[11px] tracking-[0.1em] uppercase">
            {eyebrow}
          </span>
        )}
        <h1 className="text-foreground mt-1 text-xl font-medium tracking-tight">
          {title}
        </h1>
        {description && (
          <p className="text-muted-foreground mt-1 max-w-2xl text-sm leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
    </header>
  );
}

// ------------------------------------------------------------------
// Surface (carte) + sous-éléments
// ------------------------------------------------------------------

export function Surface({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'border-border bg-card rounded-[var(--radius-surface)] border',
        className
      )}
      {...props}
    />
  );
}

export function SurfaceHeader({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'border-border flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3',
        className
      )}
      {...props}
    />
  );
}

export function SurfaceTitle({
  className,
  ...props
}: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn(
        'text-foreground text-[13px] font-semibold tracking-tight',
        className
      )}
      {...props}
    />
  );
}

export function SurfaceBody({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('p-4', className)} {...props} />;
}

// ------------------------------------------------------------------
// État vide — message honnête quand aucune donnée backend n'existe
// ------------------------------------------------------------------

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center px-6 py-12 text-center',
        className
      )}
    >
      {Icon && (
        <Icon
          size={28}
          strokeWidth={1.6}
          className="text-muted-foreground/40 mb-3"
          aria-hidden
        />
      )}
      <p className="text-foreground text-sm font-medium">{title}</p>
      {description && (
        <p className="text-muted-foreground mt-1 max-w-md text-sm">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ------------------------------------------------------------------
// Barre de progression (mastery 0..1 · null = jamais évalué)
// ------------------------------------------------------------------

export function ProgressBar({
  value,
  label,
  showValue = true,
}: {
  value: number | null;
  label?: string;
  showValue?: boolean;
}) {
  const pct = value === null ? null : Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div
        className="bg-muted h-1.5 min-w-0 flex-1 overflow-hidden rounded-full"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
        aria-label={label}
      >
        {pct !== null && (
          <div
            className="bg-live h-full rounded-full transition-[width] duration-300"
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
      {showValue && (
        <span className="text-foreground w-10 shrink-0 text-right font-mono text-[11px] tabular-nums">
          {pct === null ? '—' : `${pct}%`}
        </span>
      )}
    </div>
  );
}

// ------------------------------------------------------------------
// Tuile statistique — toujours une valeur réelle + son unité/portée
// ------------------------------------------------------------------

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <Surface className="p-3.5">
      <div className="text-muted-foreground font-mono text-[10px] font-semibold tracking-[0.12em] uppercase">
        {label}
      </div>
      <div className="text-foreground mt-1 text-lg font-semibold tabular-nums">
        {value}
      </div>
      {hint && (
        <div className="text-muted-foreground/70 mt-0.5 font-mono text-[10px]">
          {hint}
        </div>
      )}
    </Surface>
  );
}

// ------------------------------------------------------------------
// Ligne clé/valeur
// ------------------------------------------------------------------

export function KeyValue({
  label,
  value,
  mono,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-muted-foreground text-[12px]">{label}</span>
      <span
        className={cn(
          'text-foreground min-w-0 truncate text-right text-[12px]',
          mono && 'font-mono text-[11px]'
        )}
      >
        {value}
      </span>
    </div>
  );
}

// ------------------------------------------------------------------
// Navigation secondaire (onglets de section)
// ------------------------------------------------------------------

export interface SectionNavItem {
  to: string;
  label: string;
  end?: boolean;
}

export function SectionNav({ items }: { items: SectionNavItem[] }) {
  return (
    <nav
      aria-label="Navigation de section"
      className="border-border flex flex-wrap gap-1 border-b px-4 py-2"
    >
      {items.map(({ to, label, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              'rounded-[var(--radius-control)] px-2.5 py-1 text-[12.5px] font-medium transition-colors',
              isActive
                ? 'bg-muted text-foreground'
                : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
            )
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

// ------------------------------------------------------------------
// Pastille de statut (goal status, activity type…)
// ------------------------------------------------------------------

export type Tone =
  | 'neutral'
  | 'live'
  | 'success'
  | 'warning'
  | 'error';

const TONE_CLASS: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground',
  live: 'bg-live/12 text-live',
  success: 'bg-success/12 text-success',
  warning: 'bg-warning/12 text-warning',
  error: 'bg-destructive/12 text-destructive',
};

export function Pill({
  tone = 'neutral',
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold tracking-wide uppercase',
        TONE_CLASS[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

