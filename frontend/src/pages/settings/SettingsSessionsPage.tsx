// /settings/sessions — sessions temps réel (LiveKit).
//
// État de la session agent de l'utilisateur :
//   - GET  /api/livekit/agent/status  (état, si l'endpoint répond)
//   - POST /api/livekit/agent/start   (démarrage)
//   - POST /api/livekit/agent/stop    (arrêt)
//
// Honnêteté : si l'endpoint de statut est indisponible (404 / backend
// ancien / serveur LiveKit éteint), on affiche explicitement l'état
// « Aucune session active » — JAMAIS d'état fabriqué.
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Radio, Video } from 'lucide-react';
import { apiFetch } from '../../api/base';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import {
  EmptyState,
  PageHeader,
  StatTile,
  Surface,
  SurfaceBody,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';
import { Button } from '../../components/ui/button';

interface AgentStatus {
  status?: string;
  room?: string;
  agent?: string;
  dispatch_id?: string;
}

type SessionState =
  | { kind: 'loading' }
  | { kind: 'active'; room: string; agent: string }
  | { kind: 'none'; reason?: string }
  | { kind: 'error'; reason: string };

export function SettingsSessionsPage() {
  const { signedIn } = useCurrentUser();
  const navigate = useNavigate();

  const [session, setSession] = useState<SessionState>({ kind: 'loading' });
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!signedIn) {
      setSession({ kind: 'none' });
      return;
    }
    setSession({ kind: 'loading' });
    try {
      const res = await apiFetch<AgentStatus>('/api/livekit/agent/status');
      if (res.status === 'started' && res.room) {
        setSession({
          kind: 'active',
          room: res.room,
          agent: res.agent ?? 'tutor',
        });
      } else {
        setSession({ kind: 'none' });
      }
    } catch (e) {
      // Endpoint absent (404) ou serveur LiveKit injoignable : état
      // « aucune session active » explicite, sans rien inventer.
      setSession({
        kind: 'none',
        reason:
          e instanceof Error
            ? `État de session indisponible — ${e.message}`
            : 'État de session indisponible.',
      });
    }
  }, [signedIn]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const startAgent = async () => {
    setBusy(true);
    try {
      await apiFetch('/api/livekit/agent/start', { method: 'POST' });
      await refresh();
    } catch {
      // Le démarrage échoue surtout si livekit-server est éteint (503) —
      // on rafraîchit pour afficher la réalité.
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const stopAgent = async () => {
    setBusy(true);
    try {
      await apiFetch('/api/livekit/agent/stop', { method: 'POST' });
      await refresh();
    } catch {
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="settings · sessions"
        title="Sessions"
        description="Sessions temps réel (voix / vidéo) avec l’agent tuteur."
      />

      <div className="max-w-2xl space-y-5 p-6">
        {session.kind === 'loading' ? (
          <Surface>
            <EmptyState icon={Radio} title="Chargement de l’état de session…" />
          </Surface>
        ) : session.kind === 'active' ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <StatTile label="état" value={'actif'} />
              <StatTile label="agent" value={session.agent} />
            </div>
            <Surface>
              <SurfaceHeader>
                <SurfaceTitle>Session en cours</SurfaceTitle>
                <span className="flex items-center gap-1.5 font-mono text-[10px] text-live">
                  <span className="size-1.5 animate-pulse rounded-full bg-live" />
                  live
                </span>
              </SurfaceHeader>
              <SurfaceBody className="space-y-3">
                <div className="font-mono text-[11px] text-muted-foreground">
                  room : <span className="text-foreground/90">{session.room}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => navigate('/video')}
                  >
                    <Video className="h-3.5 w-3.5" />
                    Reprendre la session vidéo
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => void stopAgent()}
                    disabled={busy}
                  >
                    {busy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Radio className="h-3.5 w-3.5" />
                    )}
                    Arrêter l’agent
                  </Button>
                </div>
              </SurfaceBody>
            </Surface>
          </>
        ) : (
          <Surface>
            <SurfaceBody>
              <EmptyState
                icon={Radio}
                title="Aucune session active"
                description={
                  session.kind === 'error'
                    ? session.reason
                    : session.reason ??
                      'Aucune session temps réel n’est en cours. Démarrez une session vidéo pour parler avec l’agent tuteur.'
                }
                action={
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => navigate('/video')}
                    >
                      <Video className="h-3.5 w-3.5" />
                      Démarrer une session vidéo
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => void startAgent()}
                      disabled={busy}
                    >
                      {busy ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Radio className="h-3.5 w-3.5" />
                      )}
                      Déployer l’agent tuteur
                    </Button>
                  </div>
                }
              />
            </SurfaceBody>
          </Surface>
        )}
      </div>
    </>
  );
}

export default SettingsSessionsPage;
