// StatusBadge — indicateur service ok/ko, étiquette mono
import { cn } from '../../lib/utils';

interface StatusBadgeProps {
  label: string;
  ok: boolean | null; // null = loading
}

export function StatusBadge({ label, ok }: StatusBadgeProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="font-mono text-[11px] text-[#94a3b8]">{label}</span>
      <span
        className={cn(
          'flex items-center gap-1.5 font-mono text-[11px] font-semibold',
          ok === null && 'text-[#94a3b8]',
          ok === true && 'text-[#22c55e]',
          ok === false && 'text-[#ef4444]'
        )}
      >
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            ok === null && 'bg-[#94a3b8]',
            ok === true && 'bg-[#22c55e] pulse-dot',
            ok === false && 'bg-[#ef4444]'
          )}
        />
        {ok === null ? '…' : ok ? 'ok' : 'ko'}
      </span>
    </div>
  );
}
