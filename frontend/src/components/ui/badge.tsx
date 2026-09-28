// Badge — status pills
import type { HTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

type Tone = 'default' | 'success' | 'warning' | 'error' | 'accent' | 'secondary' | 'destructive' | 'outline' | 'ghost';

const toneClasses: Record<Tone, string> = {
  default: 'bg-muted text-muted-foreground border-border',
  success: 'bg-success/10 text-success border-success/30',
  warning: 'bg-warning/10 text-warning border-warning/30',
  error: 'bg-destructive/10 text-destructive border-destructive/30',
  accent: 'bg-live/10 text-live border-live/30',
  secondary: 'bg-secondary/10 text-secondary border-secondary/30',
  destructive: 'bg-destructive/10 text-destructive border-destructive/30',
  outline: 'border border-muted text-muted-foreground bg-transparent',
  ghost: 'bg-muted/20 text-muted-foreground',
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  // Accept both legacy `tone` and new `variant` (default "default")
  tone?: Tone;
  variant?: Tone;
}


export function Badge({ className, tone = 'default', variant, ...props }: BadgeProps) {
  const effectiveTone = variant ?? tone;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
        toneClasses[effectiveTone],
        className
      )}
      {...props}
    />
  );
}
