// Mission Identité — confirmation d'email après réception du code.
//
// Neon Auth ( plugin email-otp ) : l'email contient un CODE, pas un
// lien magique unique. La validation exige l'email + le code via
// POST /email-otp/verify-email { email, otp }.
//
// Trois arrivées possibles :
//   1. /verify-email?email=…&otp=CODE ( lien mail si callbackURL actif )
//   2. /verify-email ( saisie manuelle du code reçu )
//   3. /verify-email?email=… depuis la CONnexion, quand Neon refuse
//      le sign-in avec EMAIL_NOT_VERIFIED. Ce chemin n'a pas de compte
//      à ré-inscrire : c'est pourquoi le renvoi doit vivre ici, et pas
//      seulement sur SignUpPage.
//
// États : idle → verifying → success | error ( code invalide / expiré ).
// L'erreur nomme toujours la cause et l'action possible.
'use client';

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { CheckCircle2, Loader2 } from 'lucide-react';

import { authClient, hasAuthCode } from '../../lib/neon';
import { refreshNeonSession } from '../../auth/NeonTokenBridge';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { AuthLayout } from './AuthLayout';

const RESEND_COOLDOWN = 60;

type Status = 'idle' | 'verifying' | 'success' | 'error';

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  // Lien mail : code et email peuvent arriver en query params.
  const initialEmail = params.get('email') ?? '';
  const initialOtp = params.get('otp') ?? params.get('token') ?? '';

  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState(initialOtp);
  const [status, setStatus] = useState<Status>(
    // Le lien mail fournit les DEUX params. Sans l'email ( /verify-email
    // ?otp=CODE seul ) l'effet ne démarre rien : initialiser
    // 'verifying' dans ce cas figeait l'écran sur un spinner éternel.
    initialOtp && initialEmail ? 'verifying' : 'idle'
  );
  const [err, setErr] = useState<string | null>(null);
  const { signedIn } = useCurrentUser();
  const navigate = useNavigate();
  const autoStarted = useRef(false);

  // Renvoi d'email. Cet écran est depuis peu devenu le point d'arrivée
  // de la CONnexion ( email existant mais non vérifié → renvoi depuis
  // SignInPage ). Or, arrivé par ce chemin, l'utilisateur n'a aucun
  // accès au bouton de renvoi de SignUpPage : sans ce mécanisme, la
  // page était un cul-de-sac — le code avait pu expiré, être perdu, ou
  // n'avoir jamais été reçu, et il n'existait aucun moyen d'en obtenir
  // un nouveau depuis cette page.
  const [resendBusy, setResendBusy] = useState(false);
  const [resendNote, setResendNote] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Anti-spam : chaque renvoi relance un email, on borne donc le débit
  // à un toutes les RESEND_COOLDOWN secondes ( même défaut que
  // SignUpPage — un compte email non vérifié est unroutable en spam ).
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

  const resend = async () => {
    if (cooldown > 0 || resendBusy) return;
    const target = email.trim();
    // Sans email on ne peut pas renvoyer : la saisie du code est
    // elle-même impossible ( POST /email-otp/verify-email exige les
    // deux ). Message explicite plutôt qu'un échec silencieux.
    if (!target) {
      setResendNote('Renseigne d\'abord l\'adresse email ci-dessus.');
      return;
    }
    setResendBusy(true);
    setResendNote(null);
    try {
      await authClient.sendVerificationEmail(target);
      startCooldown();
      setResendNote(`Nouveau code envoyé à ${target}.`);
    } catch {
      /* Silencieux : dire la cause ( transport, quota, email
         inexistant ) révélerait quels emails sont enregistrés. On ne
         confirme donc que le succès. */
    } finally {
      setResendBusy(false);
    }
  };

  const verify = async (verifyEmail: string, verifyOtp: string) => {
    setStatus('verifying');
    setErr(null);
    try {
      await authClient.verifyEmail(verifyEmail.trim(), verifyOtp.trim());
      await refreshNeonSession();
      setStatus('success');
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : '';
      setStatus('error');
      // Discrimination par le `code` machine, pas par le `message` :
      // Better Auth renomme et retraduit ses messages selon les
      // versions, alors que les codes sont stables. Un code expiré
      // et un code erroné n'appellent pas la même action — le premier
      // doit proposer un renvoi, le second une ressaisie.
      if (hasAuthCode(ex, 'OTP_EXPIRED')) {
        setErr(
          'Ce code a expiré. Demande un nouvel email de vérification.'
        );
      } else if (
        hasAuthCode(ex, 'INVALID_OTP') ||
        hasAuthCode(ex, 'INVALID_TOKEN')
      ) {
        setErr('Ce code de vérification est invalide.');
      } else {
        // Repli sur le texte seulement si le `code` est absent ou
        // inconnu : on préfère afficher un message que rien.
        setErr(
          /expire/i.test(msg)
            ? 'Ce code a expiré. Demande un nouvel email de vérification.'
            : /invalid|not.*found/i.test(msg)
              ? 'Ce code de vérification est invalide.'
              : msg || 'Vérification impossible. Réessaie dans un instant.'
        );
      }
    }
  };

  // Validation automatique si le lien mail a tout fourni.
  useEffect(() => {
    if (autoStarted.current) return;
    if (!initialOtp || !initialEmail) return;
    autoStarted.current = true;
    verify(initialEmail, initialOtp);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialOtp, initialEmail]);

  // Succès : on laisse 1.5s lire le message puis on bascule.
  useEffect(() => {
    if (status !== 'success') return;
    const t = setTimeout(() => {
      navigate(signedIn ? '/assistant' : '/sign-in', { replace: true });
    }, 1500);
    return () => clearTimeout(t);
  }, [status, signedIn, navigate]);

  if (status === 'verifying') {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center gap-3 text-center">
          <Loader2 className="size-9 animate-spin text-muted-foreground" />
          <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
            Vérification en cours…
          </h1>
          <p className="text-[13px] text-muted-foreground">
            On confirme ton adresse email.
          </p>
        </div>
      </AuthLayout>
    );
  }

  if (status === 'success') {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center gap-3 text-center">
          <CheckCircle2
            className="size-9 text-success"
            strokeWidth={1.75}
          />
          <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
            Email vérifié
          </h1>
          <p className="max-w-sm text-[13px] text-muted-foreground">
            Ton compte est activé. Tu vas être redirigé
            {signedIn ? ' vers l\'application.' : ' vers la connexion.'}
          </p>
        </div>
      </AuthLayout>
    );
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !code.trim()) return;
    verify(email, code);
  };

  return (
    <AuthLayout>
      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-2">
          <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
            Vérifie ton email
          </h1>
          <p className="text-[13px] text-muted-foreground">
            Saisis le code à 6 caractères reçu par email pour activer ton
            compte.
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
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="code">Code de vérification</Label>
            <Input
              id="code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="ABC123"
              autoComplete="one-time-code"
              required
              aria-invalid={!!err}
              className="font-mono tracking-[0.2em]"
            />
          </div>

          {err && (
            <p role="alert" className="text-[12px] text-destructive">
              {err}
            </p>
          )}

          <Button
            type="submit"
            size="lg"
            disabled={!email.trim() || !code.trim()}
          >
            Vérifier
          </Button>
        </form>

        <div className="flex flex-col gap-3 rounded-lg border border-border bg-secondary/50 p-4">
          <p className="text-[12px] text-muted-foreground">
            Pas reçu&nbsp;? Vérifie les spams, ou renvoie un nouveau code.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={cooldown > 0 || resendBusy}
            onClick={resend}
            className="w-fit"
          >
            {resendBusy
              ? 'Envoi…'
              : cooldown > 0
                ? `Renvoyer dans ${cooldown}s`
                : 'Renvoyer le code'}
          </Button>
          {resendNote && (
            <p
              role="status"
              className="text-[12px] text-muted-foreground"
            >
              {resendNote}
            </p>
          )}
        </div>
      </div>
    </AuthLayout>
  );
}
