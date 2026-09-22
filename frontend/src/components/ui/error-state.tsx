// ErrorState — erreur compréhensible (§24) : humain + retry + détails techniques collapsible
import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

interface ErrorStateProps {
  title?: string;
  message: string;
  details?: string;
  onRetry?: () => void;
  retryLabel?: string;
  onDismiss?: () => void;
  className?: string;
}

function humanizeError(raw: string): string {
  // Map technique → humain (§24) : pas de "ApiError 422"
  if (/422|validation/i.test(raw)) return 'Vos données n’ont pas pu être validées. Vérifiez les champs et réessayez.';
  if (/401|unauthorized|session/i.test(raw)) return 'Votre session a expiré. Reconnectez-vous.';
  if (/403|forbidden/i.test(raw)) return 'Vous n’avez pas les droits pour cette action.';
  if (/404|not found/i.test(raw)) return 'Ressource introuvable.';
  if (/500|timeout|network|fetch/i.test(raw)) return 'Le service est temporairement indisponible. Réessayez dans un instant.';
  return raw;
}

export function ErrorState({
  title = 'Impossible de terminer cette action',
  message,
  details,
  onRetry,
  retryLabel = 'Réessayer',
  onDismiss,
  className,
}: ErrorStateProps) {
  const [showDetails, setShowDetails] = useState(false);
  const human = humanizeError(message);

  return (
    <div
      role="alert"
      className={cn(
        'rounded-[var(--radius-document)] border border-destructive/20 bg-destructive/5 px-4 py-3',
        className
      )}
    >
      <div className="flex gap-3">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-destructive" strokeWidth={1.8} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-destructive">{title}</p>
          <p className="mt-1 text-sm leading-relaxed text-foreground/80">{human}</p>
          {details && (
            <button
              type="button"
              onClick={() => setShowDetails((v) => !v)}
              className="mt-2 font-mono text-[11px] text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              {showDetails ? 'Masquer les détails' : 'Voir les détails'}
            </button>
          )}
          {showDetails && details && (
            <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-background p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
              {details}
            </pre>
          )}
          {(onRetry || onDismiss) && (
            <div className="mt-3 flex gap-2">
              {onRetry && (
                <Button size="sm" variant="outline" onClick={onRetry}>
                  {retryLabel}
                </Button>
              )}
              {onDismiss && (
                <Button size="sm" variant="ghost" onClick={onDismiss}>
                  Fermer
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Inline compact pour bandeaux (RunErrorBanner)
export function InlineError({
  message,
  onDismiss,
  className,
}: {
  message: string;
  onDismiss?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-2 rounded-[var(--radius-document)] border-s-2 border-destructive/40 bg-destructive/5 px-3 py-2 text-sm',
        className
      )}
    >
      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-destructive" />
      <span className="min-w-0 flex-1 break-words text-destructive">{humanizeError(message)}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 text-xs text-destructive/70 underline hover:text-destructive"
        >
          masquer
        </button>
      )}
    </div>
  );
}
