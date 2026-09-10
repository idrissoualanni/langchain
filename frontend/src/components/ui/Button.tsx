// Button — style shadcn adapté au dark mode accent
import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost' | 'danger' | 'success';
  size?: 'sm' | 'md' | 'icon';
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6c63ff]/50',
          'disabled:pointer-events-none disabled:opacity-50',
          {
            'bg-[#6c63ff] text-white hover:bg-[#5b52f0] active:scale-[0.98]':
              variant === 'default',
            'border border-[#26323d] bg-[#18212b] text-[#f5f7fa] hover:border-[#364553] hover:bg-[#1d2833]':
              variant === 'outline',
            'text-[#94a3b8] hover:bg-[#18212b] hover:text-[#f5f7fa]':
              variant === 'ghost',
            'bg-[#ef4444]/10 text-[#ef4444] border border-[#ef4444]/30 hover:bg-[#ef4444]/20':
              variant === 'danger',
            'bg-[#22c55e]/10 text-[#22c55e] border border-[#22c55e]/30 hover:bg-[#22c55e]/20':
              variant === 'success',
          },
          {
            'h-8 px-3 text-xs': size === 'sm',
            'h-10 px-4 text-sm': size === 'md',
            'h-9 w-9': size === 'icon',
          },
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = 'Button';
