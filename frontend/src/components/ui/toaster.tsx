// Toaster — rendu réel des notifications issues du store useToastStore.
//
// Affiché via un portail React sur document.body et animé avec framer-motion.
// Monté impérativement par mountToaster() (appelé depuis @/hooks/use-toast) afin
// de ne nécessiter aucune modification des composants racine existants.
import { createPortal } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

import { useToastStore, type Toast, type ToastVariant } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

const VARIANT_STYLES: Record<
  ToastVariant,
  { container: string; icon: typeof Info; iconClass: string }
> = {
  default: {
    container: 'border bg-background text-foreground',
    icon: Info,
    iconClass: 'text-blue-500',
  },
  success: {
    container: 'border border-green-200 bg-green-50 text-foreground',
    icon: CheckCircle2,
    iconClass: 'text-green-600',
  },
  destructive: {
    container: 'border border-red-200 bg-red-50 text-foreground',
    icon: AlertCircle,
    iconClass: 'text-red-600',
  },
};

function ToastItem({ toast, onDismiss }: {
  toast: Toast;
  onDismiss: (id: string) => void;
}) {
  const variant = VARIANT_STYLES[toast.variant];
  const Icon = variant.icon;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 32, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 32, scale: 0.95 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className={cn(
        'pointer-events-auto relative flex w-full max-w-sm items-start gap-3 rounded-lg p-4 shadow-lg',
        variant.container,
      )}
      role="status"
    >
      <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', variant.iconClass)} />

      <div className="flex-1 space-y-1">
        {toast.title && (
          <p className="text-sm font-semibold leading-none">{toast.title}</p>
        )}
        {toast.description && (
          <p className="text-sm text-muted-foreground">{toast.description}</p>
        )}
      </div>

      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className="shrink-0 rounded-md p-1 text-muted-foreground opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring"
        aria-label="Fermer la notification"
      >
        <X className="h-4 w-4" />
      </button>
    </motion.div>
  );
}

export function Toaster() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2"
      aria-live="polite"
    >
      <AnimatePresence initial={false}>
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </AnimatePresence>
    </div>,
    document.body,
  );
}

let mounted = false;

/**
 * Monte le Toaster une seule fois dans un conteneur dédié de document.body.
 * Idempotent : les appels suivants sont sans effet.
 */
export function mountToaster(): void {
  if (mounted || typeof document === 'undefined') return;

  const container = document.getElementById('toaster-root');
  if (container) {
    mounted = true;
    return;
  }

  const root = document.createElement('div');
  root.id = 'toaster-root';
  document.body.appendChild(root);

  createRoot(root).render(<Toaster />);
  mounted = true;
}
