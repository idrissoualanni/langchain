// Input — champ texte dark
import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => {
  return (
    <input
      ref={ref}
      className={cn(
        'h-10 w-full rounded-lg border border-[#26323d] bg-[#18212b] px-3 text-sm text-[#f5f7fa]',
        'placeholder:text-[#94a3b8]/60',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6c63ff]/50 focus-visible:border-[#6c63ff]/50',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
    />
  );
});
Input.displayName = 'Input';
