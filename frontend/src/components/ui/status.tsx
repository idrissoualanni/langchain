// Status — indicateur accessible (§14/§18) : dot + label, pas couleur seule
import { cn } from '@/lib/utils';

type StatusVariant = 'success' | 'warning' | 'error' | 'live' | 'neutral';

const MAP: Record<StatusVariant, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-destructive',
  live: 'bg-live',
  neutral: 'bg-muted-foreground/40',
};

export function StatusDot({
  variant = 'neutral',
  pulse = false,
  className,
}: {
  variant?: StatusVariant;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-block size-2 shrink-0 rounded-full',
        MAP[variant],
        pulse && variant === 'success' && 'pulse-dot',
        pulse && variant === 'live' && 'tool-pulse',
        className
      )}
    />
  );
}

export function StatusBadgeAccessible({
  label,
  variant = 'neutral',
  pulse = false,
  className,
}: {
  label: string;
  variant?: StatusVariant;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2 py-0.5 font-mono text-[10px] tracking-wide',
        className
      )}
    >
      <StatusDot variant={variant} pulse={pulse} />
      <span className="text-foreground/80">{label}</span>
    </span>
  );
}
