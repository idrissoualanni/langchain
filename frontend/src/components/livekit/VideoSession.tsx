"use client";

import { useEffect, useState } from "react";
import {
  LiveKitRoom,
  useAgent,
  useConnectionState,
  useLocalParticipant,
  useMaybeRoomContext,
  useMaybeSessionContext,
  useTracks,
  type UseAgentReturn,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import { useTheme } from "@/hooks/useTheme";
import { AgentAudioVisualizerAura } from "@/components/agents-ui/agent-audio-visualizer-aura";
import { AgentControlBar } from "@/components/agents-ui/agent-control-bar";
import { AgentVideoTile } from "@/components/agents-ui/agent-video-tile";
import { Loader2, Sparkles } from "lucide-react";
import { apiFetch, ApiError } from "@/api/base";
import { useToast } from "@/hooks/use-toast";

interface LiveKitTokenResponse {
  token: string;
  url: string;
  room_name: string;
}

/**
 * PARTAGE D'ÉCRAN DÉSACTIVÉ.
 *
 * La capture d'écran ( RoomIO video_enabled + ScreenShareCapturer côté
 * worker ) reste lourde pour le plan Render free et peut déstabiliser la
 * session vocale. On coupe côté client : la piste ScreenShare n'est plus
 * publiquée et le worker ne la consomme plus. Le reste de la session
 * ( voix, vidéo caméra, agent ) est inchangé.
 */
// /** Résolution de capture du partage d'écran ( Full HD, priorité au détail ). */
// const SCREEN_SHARE_RESOLUTION = { width: 1920, height: 1080, frameRate: 30 };

interface VideoSessionProps {
  /** Nom de la salle LiveKit (utilisé pour la récupération autonome du token). */
  roomName: string;
  /** Token LiveKit pré-fourni (par ex. par la page parente). */
  token?: string;
  /** URL du serveur LiveKit pré-fournie. */
  url?: string;
}

const lkAudioProps = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
} as const;

/**
 * VideoSession component
 *
 * Robuste : détecte s'il existe déjà un `<LiveKitRoom>` ( ou un
 * `<SessionProvider>`, qui fournit aussi le RoomContext ) parent via
 * `useMaybeRoomContext()`. Si c'est le cas, on ne crée PAS de seconde
 * salle (évite 2 connexions concurrentes vers LiveKit) et on rend le
 * contenu directement à l'intérieur de la salle parente. Sinon, on
 * enveloppe soi-même le contenu dans un `<LiveKitRoom>` autonome, en
 * utilisant le token/URL fournis ou en les récupérant via
 * `POST /api/livekit/token`.
 *
 * `VideoSessionContent` utilise `useMaybeRoomContext()` (jamais le hook
 * strict `useRoomContext()` qui lève "No session provided" quand la salle
 * n'est pas encore prête au premier rendu).
 */
export function VideoSession({ roomName, token: tokenProp, url: urlProp }: VideoSessionProps) {
  // Context room fourni par un éventuel <LiveKitRoom> ou <SessionProvider>
  // parent ( en v2, SessionProvider fournit session ET room ).
  // `useMaybeRoomContext()` retourne undefined sans crasher quand on n'est
  // pas dans une salle — c'est le garde qui évite (a) l'erreur stricte au
  // premier rendu et (b) la double connexion.
  const parentProvidesRoom = Boolean(useMaybeRoomContext());
  const provided = Boolean(tokenProp && urlProp);

  const [fetchedToken, setFetchedToken] = useState<string>("");
  const [fetchedUrl, setFetchedUrl] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(!provided);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (provided || parentProvidesRoom) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function fetchToken() {
      try {
        // POST authentifié via apiFetch (§19) — la route est POST-only.
        const data = await apiFetch<LiveKitTokenResponse>(
          "/api/livekit/token",
          {
            method: "POST",
            body: JSON.stringify({ room_name: roomName }),
          }
        );
        if (cancelled) return;
        setFetchedToken(data.token);
        setFetchedUrl(data.url);
      } catch (e) {
        if (cancelled) return;
        console.error("Erreur de récupération du token LiveKit:", e);
        setError(e instanceof Error ? e.message : "Erreur inconnue");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchToken();
    return () => {
      cancelled = true;
    };
  }, [provided, parentProvidesRoom, roomName]);

  const content = <VideoSessionContent />;

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto" />
          <p className="text-muted-foreground">Initialisation de la session vidéo…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-red-500 bg-background">
        Erreur de connexion LiveKit : {error}
      </div>
    );
  }

  // Si un parent fournit déjà la room, on rend le contenu directement
  // (aucune seconde salle, aucune 2e connexion).
  if (parentProvidesRoom) {
    return content;
  }

  // Sinon on crée notre propre salle : token/URL fournis ou fetchés.
  const token = tokenProp || fetchedToken;
  const serverUrl = urlProp || fetchedUrl;

  if (!token || !serverUrl) {
    return (
      <div className="p-4 text-red-500 bg-background">
        Session vidéo indisponible : aucun token LiveKit reçu.
      </div>
    );
  }

  return (
    <LiveKitRoom
      token={token}
      serverUrl={serverUrl}
      connect={true}
      video={true}
      audio={lkAudioProps}
      // dynacast : met en pause les couches vidéo non consommées.
      // adaptiveStream : adapte la qualité reçue à la taille de la tuile.
      options={{
        dynacast: true,
        adaptiveStream: true,
      }}
      data-lk-theme="default"
      className="h-screen w-full bg-background"
    >
      {content}
    </LiveKitRoom>
  );
}

function VideoSessionContent() {
  // Thème résolu (clair/sombre) fourni par le hook projet.
  const { resolvedTheme } = useTheme();
  const { toast } = useToast();

  // LiveKit hooks for agent state and tracks.
  // NB : `useAgent()` SANS argument lit le SessionContext, qui n'est fourni
  // que par <SessionProvider>. En v2, <LiveKitRoom> ne fournit QUE le
  // RoomContext → l'appeler ici sans garde-feu lève "No session provided".
  // On récupère donc la session de façon optionnelle et on ne monte le hook
  // strict que si elle existe (composant enfant).
  const session = useMaybeSessionContext();
  const [agentState, setAgentState] = useState<UseAgentReturn["state"] | undefined>(undefined);
  const tracks = useTracks();
  // Participant local : états réels ( micro, caméra, partage ) — l'UI ne
  // peut plus se désynchroniser de la room, y compris quand le partage est
  // arrêté côté système ( barre Chrome, onglet fermé, raccourci ).
  const { localParticipant } = useLocalParticipant();
  // Room courante (pour la déconnexion et l'invitation du tuteur).
  // `useMaybeRoomContext()` ne crash jamais si le contexte n'est pas prêt.
  const room = useMaybeRoomContext();
  // Clic raccrocher pendant connecting → "Client initiated disconnect".
  // On désactive le bouton tant que la room n'est pas pleinement jointe.
  const connectionState = useConnectionState(room ?? undefined);

  // Inviter le tuteur dans cette salle : la room est calculée côté serveur
  // ( session_{user_id} ), identique à celle du token — l'agent rejoint
  // donc bien la nôtre.
  const [inviting, setInviting] = useState(false);
  const [agentInvited, setAgentInvited] = useState(false);

  // Tant que la salle n'est pas rattachée au contexte (connexion en cours),
  // on garde un état stable — jamais d'erreur stricte.
  if (!room) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto" />
          <p className="text-muted-foreground">Connexion à la session vidéo…</p>
        </div>
      </div>
    );
  }

  // Filter video and audio tracks.
  // PARTAGE D'ÉCRAN DÉSACTIVÉ — la piste ScreenShare n'est plus publiée ni
  // consommée, on ne la filtre donc plus ( voir note en tête de fichier ).
  const videoTracks = tracks.filter(
    (trackRef) => trackRef.source === Track.Source.Camera
  );

  // État agent réel ( et non une heuristique sur les pistes audio ) :
  // AgentStateListener n'est plus du code mort depuis que la page fournit
  // un <SessionProvider>.
  const visualState: "speaking" | "listening" | "idle" =
    agentState === "speaking"
      ? "speaking"
      : agentState === "listening"
        ? "listening"
        : "idle";

  const agentLive =
    agentState === "connecting" ||
    agentState === "listening" ||
    agentState === "thinking" ||
    agentState === "speaking";

  const inviteTutor = async () => {
    setInviting(true);
    try {
      await apiFetch("/api/livekit/agent/start", {
        method: "POST",
        body: JSON.stringify({}),
      });
      setAgentInvited(true);
    } catch (error) {
      const apiError = error instanceof ApiError ? error : null;
      toast({
        title: "Agent indisponible",
        description:
          apiError?.message ??
          (error instanceof Error ? error.message : "Erreur inconnue"),
        variant: apiError?.status === 503 ? "default" : "destructive",
      });
    } finally {
      setInviting(false);
    }
  };

  // PARTAGE D'ÉCRAN DÉSACTIVÉ ( voir note en tête de fichier ).
  // const toggleScreenShare = async (enabled: boolean) => {
  //   if (!enabled) {
  //     await localParticipant.setScreenShareEnabled(false);
  //     return;
  //   }
  //   try {
  //     // contentHint 'detail' : préserve la lisibilité du texte et des UI,
  //     // priorité au détail plutôt qu'au framerate ( doc livekit-client ).
  //     await localParticipant.setScreenShareEnabled(
  //       true,
  //       {
  //         resolution: SCREEN_SHARE_RESOLUTION,
  //         contentHint: "detail",
  //         audio: false,
  //       },
  //       {
  //         screenShareEncoding: { maxBitrate: 3_000_000, maxFramerate: 30 },
  //       }
  //     );
  //   } catch (e) {
  //     // Toutes les erreurs sont signalées clairement : avant, un refus
  //     // laissait le bouton sur "Arrêter le partage" alors que rien n'était
  //     // partagé.
  //     const dom = e as { name?: string; message?: string };
  //     if (dom?.name === "NotAllowedError") {
  //       toast({
  //         title: "Partage refusé",
  //         description:
  //           "Vous avez refusé l'accès à l'écran. Autorisez-le dans les permissions du navigateur, puis réessayez.",
  //         variant: "destructive",
  //       });
  //     } else if (dom?.name === "NotFoundError") {
  //       toast({
  //         title: "Aucun écran disponible",
  //         description:
  //           "Aucune source d'affichage n'a été trouvée sur cet appareil.",
  //         variant: "destructive",
  //       });
  //     } else {
  //       toast({
  //         title: "Partage d'écran impossible",
  //         description:
  //           (e instanceof Error ? e.message : "Erreur inconnue") +
  //           " — vérifiez votre connexion et réessayez.",
  //         variant: "destructive",
  //       });
  //     }
  //   }
  // };

  return (
    <div className="flex flex-col h-full w-full space-y-4 p-4">
      {/*
        Hook strict `useAgent` : ne peut être appelé QUE si une session
        existe ( SessionProvider au-dessus ). Monté via un composant enfant
        pour que l'appel de hook reste inconditionnel au niveau de ce
        composant — sinon React casse l'ordre des hooks.
      */}
      {session ? (
        <AgentStateListener session={session} onState={setAgentState} />
      ) : null}

      {/* Bandeau d'état : invitation du tuteur + état agent en direct. */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        {agentLive ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
            <Sparkles className="h-3.5 w-3.5" />
            Tuteur connecté · {agentState}
          </span>
        ) : agentInvited ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 px-3 py-1 text-xs font-medium text-amber-600 dark:text-amber-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Le tuteur rejoint la salle…
          </span>
        ) : (
          <button
            type="button"
            onClick={inviteTutor}
            disabled={inviting}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {inviting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            Inviter le tuteur
          </button>
        )}
      </div>

      {/* Main video area — grille responsive : 1 colonne jusqu'à md. */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4 min-h-[400px]">
        {/* Local video tile */}
        <div className="relative bg-muted rounded-lg overflow-hidden flex items-center justify-center min-h-[220px]">
          {videoTracks.some((t) => t.participant.isLocal) ? (
            <AgentVideoTile
              trackRef={videoTracks.find((t) => t.participant.isLocal)!}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="text-muted-foreground text-sm">Caméra désactivée</div>
          )}
          <div className="absolute bottom-2 left-2 bg-black/50 text-white text-xs px-2 py-1 rounded">
            Moi
          </div>
        </div>

        {/* Remote or screen‑share tile */}
        <div className="relative bg-muted rounded-lg overflow-hidden flex items-center justify-center min-h-[220px]">
          {/* PARTAGE D'ÉCRAN DÉSACTIVÉ — la piste ScreenShare n'est plus
              publiée ; la tuile n'affiche donc que la vidéo distante. */}
          {videoTracks.filter((t) => !t.participant.isLocal).length > 0 ? (
            <AgentVideoTile
              trackRef={videoTracks.find((t) => !t.participant.isLocal)!}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="text-muted-foreground text-sm">En attente d'un participant</div>
          )}
        </div>
      </div>

      {/* Bottom audio visualizer and controls */}
      <div className="flex flex-col items-center justify-center space-y-4 py-4">
        <div className="relative w-32 h-32">
          <AgentAudioVisualizerAura
            size="lg"
            color="#1FD5F9"
            colorShift={0.3}
            state={visualState}
            themeMode={resolvedTheme}
            className="aspect-square w-full"
          />
          <div className="absolute bottom-0 left-0 right-0 text-center text-xs font-medium text-muted-foreground">
            {visualState === "speaking"
              ? "Je parle..."
              : visualState === "listening"
              ? "Je t'écoute..."
              : "En attente"}
          </div>
        </div>

        <AgentControlBar
          // États contrôlés par les drapeaux réels du participant : le
          // bouton partage ne peut plus rester sur "Arrêter" après une fin
          // de partage déclenchée hors de l'UI.
          microphoneEnabled={localParticipant.isMicrophoneEnabled}
          cameraEnabled={localParticipant.isCameraEnabled}
          screenShareEnabled={localParticipant.isScreenShareEnabled}
          onToggleMicrophone={async (muted) => {
            // `muted` = nouvel état coupé → on active le micro si non coupé
            await localParticipant.setMicrophoneEnabled(!muted);
          }}
          onToggleCamera={async (muted) => {
            await localParticipant.setCameraEnabled(!muted);
          }}
          // PARTAGE D'ÉCRAN DÉSACTIVÉ — handler neutre, le bouton est masqué
          // ci-dessous ( showScreenShareButton=false ).
          onToggleScreenShare={async () => {}}
          onDisconnect={() => {
            room.disconnect();
          }}
          // Raccrocher pendant connecting annule la connexion en cours
          // ( ConnectionError "Client initiated disconnect" ).
          disconnectDisabled={connectionState !== "connected"}
          className="backdrop-blur-md bg-background/50 rounded-full p-2"
          // PARTAGE D'ÉCRAN DÉSACTIVÉ : bouton masqué pour ne pas offrir une
          // fonctionnalité qui n'est plus câblée ( stabilité en prod ).
          showScreenShareButton={false}
        />
      </div>
    </div>
  );
}

/**
 * AgentStateListener
 *
 * Monté uniquement quand `useMaybeSessionContext()` a trouvé une session
 * ( c'est-à-dire qu'un <SessionProvider> est présent au-dessus ). C'est le
 * SEUL endroit où `useAgent()` peut être appelé sans risque : en
 * @livekit/components-react v2, `useAgent()` sans argument lit le
 * SessionContext — fourni par SessionProvider, PAS par LiveKitRoom — et
 * lève "No session provided" quand il est absent. Ne rend rien ; il
 * remonte juste l'état de l'agent ( speaking / listening / idle ) au
 * parent pour piloter le visualiseur audio.
 */
function AgentStateListener({
  session,
  onState,
}: {
  session: NonNullable<ReturnType<typeof useMaybeSessionContext>>;
  onState: (state: UseAgentReturn["state"] | undefined) => void;
}) {
  const { state } = useAgent(session);

  useEffect(() => {
    onState(state);
  }, [state, onState]);

  return null;
}
