// Mission Identité — page d'INSCRIPTION ( production Neon Auth ).
//
// Flux :
//   POST /sign-up/email
//     → l'utilisateur est connecté MAIS email non vérifié
//     → bannière "vérifiez ta boîte mail" + bouton renvoyer
//       ( avec compte à rebours 60s anti-spam )
//     → GET /verify-email?token=… confirme, puis /sign-in
//
// NB : la réception effective de l'email suppose un transport mail
// configuré côté projet Neon. Voir README_AUTH.
'use client';

import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { CheckCircle2, Loader2, MailCheck, X } from 'lucide-react';

import { authClient } from '../../lib/neon';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { AuthLayout } from './AuthLayout';

const RESEND_COOLDOWN = 60;

type Step = 'form' | 'verify';

/** Critères de robustesse du mot de passe ( exigences affichées ). */
const RULES: { label: string; test: (p: string) => boolean }[] = [
  { label: '8 caractères minimum', test: (p) => p.length >= 8 },
  { label: 'Une lettre minuscule', test: (p) => /[a-z]/.test(p) },
  { label: 'Une lettre majuscule', test: (p) => /[A-Z]/.test(p) },
  { label: 'Un chiffre', test: (p) => /\d/.test(p) },
];

export function SignUpPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [step, setStep] = useState<Step>('form');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Compte à rebours du renvoi d'email ( = le "recherchage" du token ).
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const navigate = useNavigate();

  const valid = RULES.every((r) => r.test(password));
  const disabled = busy || !email.trim() || !valid;

  // Démarre le compte à rebours de renvoi.
  const startCooldown = () => {
    setCooldown(RESEND_COOLDOWN);
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setCooldown((c) => {
        if (c <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled) return;
    setBusy(true);
    setErr(null);
    try {
      await authClient.signUpEmail(email.trim(), password, name.trim());
      // NB : Neon ne crée PAS de session à l'inscription ( get-session
      // reste null, /token 401 ). Aucun refresh à faire ici — l'utilisateur
      // devra confirmer son email puis se connecter.
      // Envoi du code de vérification ( marche même sans session ).
      try {
        await authClient.sendVerificationEmail(email.trim());
      } catch {
        /* transport mail possiblement inactif — la bannière l'indique */
      }
      startCooldown();
      setStep('verify');
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : '';
      setErr(
        /already|exists/i.test(msg)
          ? 'Un compte existe déjà avec cet email. Connecte-toi.'
          : msg || 'Inscription impossible. Réessaie dans un instant.'
      );
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    if (cooldown > 0) return;
    setBusy(true);
    try {
      await authClient.sendVerificationEmail(email.trim());
      startCooldown();
    } catch {
      /* silencieux : on ne dévoile rien sur l'état du transport */
    } finally {
      setBusy(false);
    }
  };

  // L'utilisateur a vérifié son email depuis un autre onglet ( la
  // session refresh au focus ) → on le laisse continuer.
  if (step === 'verify') {
    return (
      <AuthLayout>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col items-center gap-3 text-center">
            <MailCheck className="size-10 text-foreground" strokeWidth={1.5} />
            <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
              Vérifie ta boîte mail
            </h1>
            <p className="max-w-sm text-[13px] text-muted-foreground">
              Un code de confirmation a été envoyé à{' '}
              <span className="font-medium text-foreground">
                {email.trim()}
              </span>
              . Saisis-le pour activer ton compte.
            </p>
          </div>

          <Link
            to={`/verify-email?email=${encodeURIComponent(email.trim())}`}
            className="self-center"
          >
            <Button type="button" size="lg">
              Saisir le code
            </Button>
          </Link>

          <div className="flex flex-col gap-2 rounded-lg border border-border bg-secondary/50 p-4">
            <p className="text-[12px] text-muted-foreground">
              Pas reçu&nbsp;? Vérifie les spams, ou renvoie l'email.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={cooldown > 0 || busy}
              onClick={resend}
              className="w-fit"
            >
              {cooldown > 0 ? (
                <>Renvoyer dans {cooldown}s</>
              ) : (
                'Renvoyer l\'email'
              )}
            </Button>
          </div>

          <p className="text-center text-[12px] text-muted-foreground">
            Code validé&nbsp;?{' '}
            <button
              type="button"
              onClick={() => navigate('/sign-in', { replace: true })}
              className="font-medium text-foreground underline-offset-4 hover:underline"
            >
              Aller à la connexion
            </button>
          </p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-2">
          <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
            Créer un compte
          </h1>
          <p className="text-[13px] text-muted-foreground">
           inscription à Agent Tutor.
          </p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">
              Nom <span className="text-muted-foreground">(optionnel)</span>
            </Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Prénom Nom"
              autoComplete="name"
            />
          </div>

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
            <Label htmlFor="password">Mot de passe</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
            {/* Exigences : validées en temps réel, pas de liste morte. */}
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1.5 pt-0.5">
              {RULES.map((r) => {
                const ok = r.test(password);
                return (
                  <li
                    key={r.label}
                    className="flex items-center gap-1.5 text-[11px] transition-colors"
                    aria-live="polite"
                  >
                    {ok ? (
                      <CheckCircle2 className="size-3 shrink-0 text-success" />
                    ) : (
                      <X className="size-3 shrink-0 text-muted-foreground/50" />
                    )}
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

          {err && (
            <p role="alert" className="text-[12px] text-destructive">
              {err}
            </p>
          )}

          <Button type="submit" disabled={disabled} size="lg">
            {busy && <Loader2 className="animate-spin" />}
            {busy ? 'Inscription…' : 'S\'inscrire'}
          </Button>
        </form>

        <p className="text-center text-[13px] text-muted-foreground">
          Déjà un compte&nbsp;?{' '}
          <Link
            to="/sign-in"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            Se connecter
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
