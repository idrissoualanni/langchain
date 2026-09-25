// Mission Identité — réinitialisation du mot de passe ( après clic lien ).
//
// Route : /reset-password?token=…
//   POST /reset-password { token, newPassword }
//
// Le token arrive dans l'URL ( route protégée par possession du lien ).
// États : loading ( token attendu ) → form → success | error.
'use client';

import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CheckCircle2, Loader2 } from 'lucide-react';

import { authClient } from '../../lib/neon';
import { refreshNeonSession } from '../../auth/NeonTokenBridge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { AuthLayout } from './AuthLayout';

const RULES: { label: string; test: (p: string) => boolean }[] = [
  { label: '8 caractères minimum', test: (p) => p.length >= 8 },
  { label: 'Une lettre minuscule', test: (p) => /[a-z]/.test(p) },
  { label: 'Une lettre majuscule', test: (p) => /[A-Z]/.test(p) },
  { label: 'Un chiffre', test: (p) => /\d/.test(p) },
];

type Status = 'form' | 'success' | 'error';

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [status, setStatus] = useState<Status>(token ? 'form' : 'error');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const valid = RULES.every((r) => r.test(password));
  const mismatch = confirm.length > 0 && password !== confirm;
  const disabled = busy || !valid || !!mismatch;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled || !token) return;
    setBusy(true);
    setErr(null);
    try {
      await authClient.resetPassword(token, password);
      // Une réinitialisation déconnecte les autres sessions : on
      // rafraîchit la nôtre avant de rebasculer.
      await refreshNeonSession();
      setStatus('success');
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : '';
      setStatus('error');
      setErr(
        msg.startsWith('RESET_UNAVAILABLE')
          ? 'La réinitialisation automatique n\'est pas activée sur ce service. Contacte un administrateur.'
          : /expire/i.test(msg)
            ? 'Ce lien a expiré. Demande une nouvelle réinitialisation.'
            : /invalid|invalid_token/i.test(msg)
              ? 'Ce lien est invalide.'
              : msg || 'Réinitialisation impossible. Réessaie dans un instant.'
      );
    } finally {
      setBusy(false);
    }
  };

  if (status === 'success') {
    return (
      <AuthLayout>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col items-center gap-3 text-center">
            <CheckCircle2
              className="size-9 text-success"
              strokeWidth={1.75}
            />
            <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
              Mot de passe modifié
            </h1>
            <p className="max-w-sm text-[13px] text-muted-foreground">
              Tu peux maintenant te connecter avec ton nouveau mot de
              passe.
            </p>
          </div>

          <Link to="/sign-in" className="self-center">
            <Button type="button" size="lg">
              Se connecter
            </Button>
          </Link>
        </div>
      </AuthLayout>
    );
  }

  if (status === 'error') {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center gap-3 text-center">
          <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
            Lien invalide
          </h1>
          <p className="max-w-sm text-[13px] text-muted-foreground">
            {err ??
              (token
                ? 'Ce lien de réinitialisation est invalide ou expiré.'
                : 'Aucun jeton de réinitialisation dans le lien.')}
          </p>
          <Link to="/forgot-password" className="mt-2">
            <Button type="button" variant="outline">
              Demander un nouveau lien
            </Button>
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-2">
          <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
            Nouveau mot de passe
          </h1>
          <p className="text-[13px] text-muted-foreground">
            Choisis un mot de passe pour tes prochaines connexions.
          </p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Mot de passe</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1.5 pt-0.5">
              {RULES.map((r) => {
                const ok = r.test(password);
                return (
                  <li
                    key={r.label}
                    className="flex items-center gap-1.5 text-[11px]"
                    aria-live="polite"
                  >
                    <span
                      className={
                        ok
                          ? 'text-foreground'
                          : 'text-muted-foreground'
                      }
                    >
                      {ok ? '✓' : '○'}
                    </span>
                    <span
                      className={
                        ok
                          ? 'text-foreground'
                          : 'text-muted-foreground'
                      }
                    >
                      {r.label}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="confirm">Confirmer le mot de passe</Label>
            <Input
              id="confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              required
              aria-invalid={mismatch}
            />
            {mismatch && (
              <p className="text-[12px] text-destructive">
                Les mots de passe ne correspondent pas.
              </p>
            )}
          </div>

          {err && (
            <p role="alert" className="text-[12px] text-destructive">
              {err}
            </p>
          )}

          <Button type="submit" size="lg" disabled={disabled}>
            {busy && <Loader2 className="animate-spin" />}
            {busy ? 'Enregistrement…' : 'Enregistrer le mot de passe'}
          </Button>
        </form>
      </div>
    </AuthLayout>
  );
}
