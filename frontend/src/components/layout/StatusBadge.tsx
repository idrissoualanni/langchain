// StatusBadge — indicateur service ok/ko, étiquette mono
import { cn } from '../../lib/utils';

interface StatusBadgeProps {
  label: string;
  ok: boolean | null; // null = loading
}

export function StatusBadge({ label, ok }: StatusBadgeProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="font-mono text-[11px] text-muted-foreground">{label}</span>
      <span
        className={cn(
          'flex items-center gap-1.5 font-mono text-[11px] font-semibold',
          ok === null && 'text-muted-foreground',
          ok === true && 'text-success',
          ok === false && 'text-destructive'
        )}
      >
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            ok === null && 'bg-muted-foreground',
            ok === true && 'bg-success pulse-dot',
            ok === false && 'bg-destructive'
          )}
        />
        {ok === null ? '…' : ok ? 'ok' : 'ko'}
      </span>
    </div>
  );
}
