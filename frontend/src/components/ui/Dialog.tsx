import * as React from 'react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';

export function Dialog({
  open,
  onClose,
  onOpenChange,
  title,
  children,
  className,
}: {
  open: boolean;
  onClose?: () => void;
  onOpenChange?: (open: boolean) => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  // Escape to close
  React.useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (onOpenChange) onOpenChange(false);
        else if (onClose) onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose, onOpenChange]);

  if (!open) return null;

  const handleClose = () => {
    if (onOpenChange) onOpenChange(false);
    else if (onClose) onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={handleClose} />
      {/* Panel */}
      <div className={cn('relative w-full max-w-md rounded-xl border border-border bg-card shadow-2xl', className)}>
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          <button onClick={handleClose} className="text-muted-foreground transition-colors hover:text-foreground">
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function DialogContent({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('p-5', className)}>{children}</div>;
}
export function DialogHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('border-b p-4', className)}>{children}</div>;
}
export function DialogTitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return <h2 className={cn('text-lg font-medium', className)}>{children}</h2>;
}
export function DialogTrigger({ children }: { children: React.ReactNode }) {
  // Simple wrapper – just render children
  return <>{children}</>;
}
