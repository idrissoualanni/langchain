// Badge — status pills
import type { HTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

type Tone = 'default' | 'success' | 'warning' | 'error' | 'accent';

const toneClasses: Record<Tone, string> = {
  default: 'bg-[#18212b] text-[#94a3b8] border-[#26323d]',
  success: 'bg-[#22c55e]/10 text-[#22c55e] border-[#22c55e]/30',
  warning: 'bg-[#f59e0b]/10 text-[#f59e0b] border-[#f59e0b]/30',
  error: 'bg-[#ef4444]/10 text-[#ef4444] border-[#ef4444]/30',
  accent: 'bg-[#6c63ff]/10 text-[#6c63ff] border-[#6c63ff]/30',
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ className, tone = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium',
        toneClasses[tone],
        className
      )}
      {...props}
    />
  );
}
