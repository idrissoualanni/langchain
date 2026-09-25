// Mission Identité — page de CONNEXION ( production Neon Auth ).
//
// Page dédiée ( finie l'hybride sign-in / sign-up du même composant ) :
//   POST /sign-in/email → refreshNeonSession() → /assistant
//
// Design system Glace / Papier / Encre via Button / Input / Label.
'use client';

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { authClient } from '../../lib/neon';
import { refreshNeonSession } from '../../auth/NeonTokenBridge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { AuthLayout } from './AuthLayout';

export function SignInPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const navigate = useNavigate();

  const disabled = busy || !email.trim() || !password;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled) return;
    setBusy(true);
    setErr(null);
    try {
      await authClient.signInEmail(email.trim(), password);
      // Rafraîchit window.__neonGetToken + le contexte user réactif.
      await refreshNeonSession();
      navigate('/assistant', { replace: true });
    } catch (ex) {
      // Neon renvoie des codes explicites qu'on traduit en actions.
      // Cas critiques à ne JAMAIS confondre :
      //   EMAIL_NOT_VERIFIED → identifiants BONS mais email non vérifié.
      //     Dire "mot de passe incorrect" enfermerait l'utilisateur.
      //   INVALID_PASSWORD / INVALID_EMAIL → identifiants faux.
      const msg = ex instanceof Error ? ex.message : '';
      if (/EMAIL_NOT_VERIFIED/i.test(msg)) {
        setErr(
          'Email non vérifié. Ouvre l\'email de confirmation reçu à l\'inscription, ou renvoie un code.'
        );
      } else if (/invalid|incorrect|credentials|INVALID_PASSWORD|INVALID_EMAIL/i.test(msg)) {
        setErr('Email ou mot de passe incorrect.');
      } else {
        setErr(msg || 'Connexion impossible. Réessaie dans un instant.');
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
            Reprendre une session
          </h1>
          <p className="text-[13px] text-muted-foreground">
            Accédez à votre tuteur IA personnel.
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

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">Mot de passe</Label>
              <Link
                to="/forgot-password"
                className="text-[12px] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              >
                Mot de passe oublié&nbsp;?
              </Link>
            </div>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              aria-invalid={!!err}
            />
          </div>

          {err && (
            <p
              role="alert"
              className="text-[12px] text-destructive"
            >
              {err}
            </p>
          )}

          <Button type="submit" disabled={disabled} size="lg">
            {busy && <Loader2 className="animate-spin" />}
            {busy ? 'Connexion…' : 'Se connecter'}
          </Button>
        </form>

        <p className="text-center text-[13px] text-muted-foreground">
          Pas encore de compte&nbsp;?{' '}
          <Link
            to="/sign-up"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            Créer un compte
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
