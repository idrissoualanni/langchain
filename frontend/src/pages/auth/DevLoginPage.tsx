// Mission Identité — page de connexion MODE DÉVELOPPEMENT local.
//
// Active UNIQUEMENT avec VITE_AUTH_MODE=dev ( backend AUTH_MODE=dev ) :
// le backend provisionne un utilisateur interne de test et renvoie un
// token "dev:<id>". En production ce mode est inerte — la page affiche
// un message explicite plutôt que de laisser un contournement dormant.
//
// Déplacée depuis src/auth/ : les PAGES vivent dans src/pages/, les
// composants de logique d'auth dans src/auth/.
'use client';

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Terminal } from 'lucide-react';

import { useCurrentUser } from '../../hooks/useCurrentUser';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { AuthLayout } from './AuthLayout';

export function DevLoginPage() {
  const { devLogin, devMode } = useCurrentUser();
  const [name, setName] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  // Mode dev inactif : on EXPLIQUE au lieu de simuler une auth.
  if (!devMode) {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center gap-3 text-center">
          <Terminal className="size-9 text-muted-foreground" strokeWidth={1.5} />
          <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
            Mode développement désactivé
          </h1>
          <p className="max-w-sm text-[13px] text-muted-foreground">
            Cette page nécessite <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[12px]">VITE_AUTH_MODE=dev</code> côté
            frontend et <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[12px]">AUTH_MODE=dev</code> côté backend.
          </p>
        </div>
      </AuthLayout>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await devLogin(name.trim());
      navigate('/assistant', { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Erreur de connexion');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout>
      <div className="flex flex-col gap-6">
        <div
          className="flex items-center gap-2.5 rounded-lg border border-dashed border-border bg-secondary/50 px-3.5 py-2.5"
          role="note"
        >
          <Terminal
            className="size-4 shrink-0 text-muted-foreground"
            strokeWidth={1.5}
          />
          <p className="text-[12px] text-muted-foreground">
            Mode développement — session simulée par le backend, aucune
            authentification réelle.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <h1 className="font-serif text-2xl font-medium tracking-tight text-foreground">
            Connexion (dev)
          </h1>
          <p className="text-[13px] text-muted-foreground">
            Le backend provisionne un utilisateur de test à partir du nom
            saisi.
          </p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">Nom d'utilisateur</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="alice"
              autoComplete="username"
              required
              aria-invalid={!!err}
            />
          </div>

          {err && (
            <p role="alert" className="text-[12px] text-destructive">
              {err}
            </p>
          )}

          <Button type="submit" size="lg" disabled={busy || !name.trim()}>
            {busy && <Loader2 className="animate-spin" />}
            {busy ? 'Connexion…' : 'Se connecter'}
          </Button>
        </form>
      </div>
    </AuthLayout>
  );
}
