// Système de toast — store zustand léger + montage auto du <Toaster />
//
// Avant, ce hook ne faisait que `console.log('Toast:', options)` : l'utilisateur
// ne voyait rien. Désormais, `toast({ title, description, variant })` pousse une
// entrée dans le store ci-dessous, et le composant <Toaster /> (cf.
// @/components/ui/toaster) affiche réellement les notifications via un portail
// React + framer-motion.
//
// L'API publique (`useToast().toast(...)`) est conservée à l'identique : elle est
// utilisée par ModelsPage, KnowledgePage et KnowledgeAccessPanel.
import { create } from 'zustand';

export type ToastVariant = 'default' | 'destructive' | 'success';

export interface ToastOptions {
  title?: string;
  description?: string;
  /** Variante visuelle (couleur/icône). Par défaut : 'default'. */
  variant?: ToastVariant;
  /** Durée d'affichage en ms. 0 = persistant (dismiss manuel). */
  duration?: number;
}

export interface Toast extends Required<Omit<ToastOptions, 'duration'>> {
  id: string;
  duration: number;
}

interface ToastState {
  toasts: Toast[];
  push: (options: ToastOptions) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

// Durées par défaut selon la variante : les erreurs restent plus longtemps.
const DEFAULT_DURATION: Record<ToastVariant, number> = {
  default: 5000,
  success: 4000,
  destructive: 8000,
};

let toastSeq = 0;
const timers = new Map<string, ReturnType<typeof setTimeout>>();

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],

  push: (options) => {
    const id = `toast-${++toastSeq}`;
    const variant = options.variant ?? 'default';
    const duration = options.duration ?? DEFAULT_DURATION[variant];

    const toast: Toast = {
      id,
      title: options.title ?? '',
      description: options.description ?? '',
      variant,
      duration,
    };

    set((state) => ({ toasts: [...state.toasts, toast] }));

    if (duration > 0) {
      const timer = setTimeout(() => get().dismiss(id), duration);
      timers.set(id, timer);
    }

    return id;
  },

  dismiss: (id) => {
    const timer = timers.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.delete(id);
    }
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },

  clear: () => {
    timers.forEach((timer) => clearTimeout(timer));
    timers.clear();
    set({ toasts: [] });
  },
}));

/**
 * Monte le <Toaster /> une seule fois dans le DOM (portail sur document.body).
 *
 * Le rendu est impératif (ReactDOM.createRoot) plutôt que déclaré dans App.tsx :
 * aucun fichier de l'arborescence existante n'a besoin d'être modifié, et le
 * portail s'affiche quel que soit l'endroit d'où `toast()` est appelé.
 */
let toasterMounted = false;
function ensureToasterMounted(): void {
  if (toasterMounted || typeof document === 'undefined') return;

  // Import dynamique pour éviter une dépendance circulaire à l'évaluation du
  // module : c'est toaster.tsx qui importe le store, pas l'inverse.
  void import('@/components/ui/toaster').then((mod) => {
    mod.mountToaster();
    toasterMounted = true;
  });
}

/**
 * API publique — inchangée. Affiche un toast à l'écran.
 */
export function toast(options: ToastOptions): string {
  ensureToasterMounted();
  return useToastStore.getState().push(options);
}

/**
 * Hook conservé pour la compatibilité avec le code existant.
 * `const { toast } = useToast();`
 */
export function useToast() {
  return { toast };
}
