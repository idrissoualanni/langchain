// Mission Identité — demande de réinitialisation de mot de passe.
//
// Route : /forgot-password
//
// ÉTAT RÉEL ( tests e2e 2026-09-25 ) : Neon Managed Auth n'envoie PAS
// d'email de réinitialisation — seulement des emails de vérification.
// Plutôt que d'afficher un faux "email envoyé" qui ne viendra jamais,
// la page explique la situation et propose une issue : si l'email n'est
// pas vérifié, l'utilisateur peut redemander un code de vérification.
//
// Honnêteté : un écran qui promet un mail qui n'arrive jamais est pire
// qu'un écran qui dit la vérité. L'utilisateur n'est pas enfermé.
'use client';

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Info, Loader2 } from 'lucide-react';

import { authClient } from '../../lib/neon';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { AuthLayout } from './AuthLayout';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy || !email.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await authClient.forgetPassword(email.trim());
      // Pas de "sent" ici : forgetPassword lève toujours ( voir neon.ts ).
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : '';
      if (msg.startsWith('RESET_UNAVAILABLE')) {
        setErr(
          'La réinitialisation automatique n\'est pas activée sur ce service. Tu peux redemander un code de vérification si ton email n\'est pas encore confirmé, ou contacter un administrateur.'
        );
      } else {
        setErr(msg || 'Demande impossible. Réessaie dans un instant.');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout>
      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-2">
          <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
            Mot de passe oublié
          </h1>
          <p className="text-[13px] text-muted-foreground">
            On envoie un lien de réinitialisation à ton adresse email.
          </p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Adresse email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="eleve@exemple.fr"
              autoComplete="email"
              required
              aria-invalid={!!err}
            />
          </div>

          {err && (
            <div
              role="alert"
              className="flex gap-2.5 rounded-lg border border-border bg-secondary/50 p-3.5 text-[12px] text-muted-foreground"
            >
              <Info className="size-4 shrink-0 translate-y-0.5" strokeWidth={1.5} />
              <span>{err}</span>
            </div>
          )}

          <Button
            type="submit"
            size="lg"
            disabled={busy || !email.trim()}
          >
            {busy && <Loader2 className="animate-spin" />}
            {busy ? 'Envoi…' : 'Envoyer le lien'}
          </Button>
        </form>

        {err && (
          <Link
            to={`/verify-email?email=${encodeURIComponent(email.trim())}`}
            className="self-center"
          >
            <Button type="button" variant="outline" size="sm">
              Redemander un code de vérification
            </Button>
          </Link>
        )}

        <Link
          to="/sign-in"
          className="self-center text-[13px] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          <ArrowLeft className="mr-1 inline size-3.5" />
          Retour à la connexion
        </Link>
      </div>
    </AuthLayout>
  );
}
