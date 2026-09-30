// Mission Identité — page de CONNEXION ( production Neon Auth ).
//
// Page dédiée ( finie l'hybride sign-in / sign-up du même composant ) :
//   POST /sign-in/email → refreshNeonSession() → /assistant
//
// Design system Glace / Papier / Encre via Button / Input / Label.
'use client';

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';

import { authClient, hasAuthCode } from '../../lib/neon';
import { refreshNeonSession } from '../../auth/NeonTokenBridge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { AuthLayout } from './AuthLayout';

export function SignInPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
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
      // Neon distingue deux causes qu'il ne faut JAMAIS confondre :
      //   EMAIL_NOT_VERIFIED        → identifiants BONS, email non vérifié.
      //     Dire "mot de passe incorrect" enfermerait l'utilisateur, qui
      //     retaperait un mot de passe correct un nombre infini de fois.
      //   INVALID_EMAIL_OR_PASSWORD → identifiants réellement faux.
      //
      // On lit le `code` machine, plus le `message` : Better Auth place
      // EMAIL_NOT_VERIFIED dans `code`, jamais dans `message`, donc le
      // test sur le texte ne pouvait pas aboutir et tombait toujours
      // dans la branche "mot de passe incorrect".
      if (hasAuthCode(ex, 'EMAIL_NOT_VERIFIED')) {
        // Redirection et pas un bandeau : la page de saisie du code
        // existe déjà ( /verify-email ) et sait renvoyer l'email.
        // Rester ici avec un message ne donnait aucune issue à un
        // utilisateur bloqué dont le mot de passe est pourtant valide.
        navigate(`/verify-email?email=${encodeURIComponent(email.trim())}`, {
          replace: true,
        });
        return;
      }

      const msg = ex instanceof Error ? ex.message : '';
      setErr(
        hasAuthCode(ex, 'INVALID_EMAIL_OR_PASSWORD') ||
          hasAuthCode(ex, 'INVALID_EMAIL') ||
          hasAuthCode(ex, 'INVALID_PASSWORD') ||
          /invalid|incorrect|credentials/i.test(msg)
          ? 'Email ou mot de passe incorrect.'
          : msg || 'Connexion impossible. Réessaie dans un instant.'
      );
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
            Accède à ton tuteur IA personnel.
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
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                aria-invalid={!!err}
                className="pr-16"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={
                  showPassword
                    ? 'Masquer le mot de passe'
                    : 'Afficher le mot de passe'
                }
                aria-pressed={showPassword}
                className="text-muted-foreground hover:text-foreground absolute inset-y-0 right-0 flex items-center gap-1.5 rounded-[var(--radius-control)] px-3 text-[11px] transition-colors"
              >
                {showPassword ? (
                  <EyeOff className="size-3.5" />
                ) : (
                  <Eye className="size-3.5" />
                )}
                {showPassword ? 'Masquer' : 'Afficher'}
              </button>
            </div>
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

          {/* Un CTA grisé sans raison laisse l'utilisateur bloqué : on
              dit ce qu'il manque, dans le registre de l'app. */}
          {!busy && (disabled || err) && (
            <p className="-mt-2 text-center text-[11px] text-muted-foreground">
              {err
                ? 'Corrige l’erreur ci-dessus pour te connecter.'
                : 'Remplis ton email et ton mot de passe pour te connecter.'}
            </p>
          )}
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
