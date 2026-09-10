// Dialog — modal simple (pas de dépendance radix)
import {
  useEffect,
  type ReactNode,
} from 'react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  className?: string;
}

export function Dialog({
  open,
  onClose,
  title,
  children,
  className,
}: DialogProps) {
  // Escape pour fermer
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Panel */}
      <div
        className={cn(
          'relative w-full max-w-md rounded-xl border border-[#26323d] bg-[#111820] shadow-2xl',
          className
        )}
      >
        <div className="flex items-center justify-between border-b border-[#26323d] px-5 py-4">
          <h2 className="text-sm font-semibold text-[#f5f7fa]">{title}</h2>
          <button
            onClick={onClose}
            className="text-[#94a3b8] transition-colors hover:text-[#f5f7fa]"
          >
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
