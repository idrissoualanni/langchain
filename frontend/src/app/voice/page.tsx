"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  SessionProvider,
  useAgent,
  useConnectionState,
  useLocalParticipant,
  useSession,
  useTrackTranscription,
  useTracks,
  type UseAgentReturn,
} from "@livekit/components-react";
import { Track, TokenSource } from "livekit-client";
import { Loader2, Mic, MicOff, PhoneOff, Send } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAui } from "@assistant-ui/react";

import { apiFetch, ApiError } from "@/api/base";
import { useAssistantStore } from "@/assistant-ui/store";
import { AgentAudioVisualizerAura } from "@/components/agents-ui/agent-audio-visualizer-aura";
import { useToast } from "@/hooks/use-toast";
import { useLiveKitToken } from "@/hooks/useLiveKitToken";

interface UserOut {
  user_id: string;
  name: string;
}

interface MemoryOverview {
  identity: { name: string | null; description: string | null };
  facts_by_category: Record<string, Array<{ id: string; content: string }>>;
  total_facts: number;
}

/**
 * État agent → état du visualizer ( l'API LiveKit expose plus d'états
 * que l'aura n'en anime ; on ne garde que les trois gérés ).
 */
function auraStateFor(
  agentState: UseAgentReturn["state"] | undefined,
): "speaking" | "listening" | "idle" {
  if (agentState === "speaking") return "speaking";
  if (agentState === "listening") return "listening";
  return "idle";
}

function stateLabel(agentState: UseAgentReturn["state"] | undefined): string {
  switch (agentState) {
    case "speaking":
      return "Le tuteur parle…";
    case "listening":
      return "Le tuteur écoute…";
    case "thinking":
      return "Le tuteur réfléchit…";
    case "connecting":
      return "Connexion à l'agent…";
    case "disconnected":
      return "Agent déconnecté";
    default:
      return "En attente";
  }
}

/**
 * Panneau de dictée : retranscrit la parole de l'utilisateur via le STT
 * Inference. Le worker publie les transcriptions utilisateur sur la piste
 * micro ( RoomIO, transcription activée par défaut ) — on les lit côté
 * client avec useTrackTranscription.
 *
 * Pas de Web Speech navigateur : la transcription vient de LiveKit, donc la
 * même que celle qu'entend l'agent ( mêmes modèles, mêmes langues ).
 */
function DictationPanel({ onInsert }: { onInsert: (text: string) => void }) {
  const tracks = useTracks();
  const micTrack = tracks.find(
    (t) => t.source === Track.Source.Microphone && t.participant.isLocal,
  );
  const { segments } = useTrackTranscription(micTrack, { bufferSize: 50 });

  // Les segments sont mis à jour en place ( id stable, texte qui s'affine
  // au fur et à mesure ) : on ne garde que la dernière version de chaque
  // id, puis on concatène dans l'ordre.
  const dictated = useMemo(() => {
    const latest = new Map<string, string>();
    for (const segment of segments) latest.set(segment.id, segment.text);
    return [...latest.values()].filter(Boolean).join(" ").trim();
  }, [segments]);

  const hasFinal = segments.some((s) => s.final);

  return (
    <div className="bg-muted/30 max-w-md rounded-lg border p-4">
      <p className="text-muted-foreground mb-2 text-xs tracking-wide uppercase">
        Dictée {hasFinal ? "— prêt à insérer" : "en cours…"}
      </p>
      <p className="min-h-16 text-sm leading-relaxed">
        {dictated ? (
          dictated
        ) : (
          <span className="text-muted-foreground italic">
            Parlez — votre texte apparaîtra ici.
          </span>
        )}
      </p>
      <button
        type="button"
        onClick={() => dictated && onInsert(dictated)}
        disabled={!dictated}
        className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Send className="h-3.5 w-3.5" />
        Insérer dans le message
      </button>
    </div>
  );
}

/**
 * Contenu de session — monté SOUS <SessionProvider>.
 *
 * useAgent lit le SessionContext, pas le RoomContext : c'est exactement
 * le bug qui crashait VideoSession ( "No session provided" ). Tous les
 * hooks consommant une session doivent vivre sous le provider.
 *
 * La session elle-même est créée par useSession ( token littéral ) puis
 * démarrée explicitement : useSession ne connecte PAS tout seul, il
 * faut appeler session.start().
 */
function VoiceSessionContent({
  memory,
  duration,
  mode,
  returnTo,
  onDisconnect,
}: {
  memory: MemoryOverview | null;
  duration: number;
  mode: "voice" | "dictate";
  returnTo: string;
  onDisconnect: () => void;
}) {
  const { state } = useAgent();
  // Clic "Terminer" pendant connecting → le SDK annule la connexion en
  // cours ( ConnectionError "Client initiated disconnect" ). On désactive
  // le bouton jusqu'à connected.
  const connectionState = useConnectionState();
  const { localParticipant } = useLocalParticipant();
  const navigate = useNavigate();
  const aui = useAui();
  const [micEnabled, setMicEnabled] = useState(true);

  const toggleMic = useCallback(async () => {
    const next = !micEnabled;
    await localParticipant.setMicrophoneEnabled(next);
    setMicEnabled(next);
  }, [localParticipant, micEnabled]);

  // En mode dictée, le texte retranscrit est inséré dans le composer
  // officiel ( setText + send — même mécanisme que ActivityTrigger ) puis
  // on revient à la page d'origine. La session est arrêtée proprement
  // avant de partir ( dispatch stoppé, pas d'agent orphelin ).
  const insertDictation = useCallback(
    (text: string) => {
      aui.composer.setText(text);
      aui.composer.send();
      apiFetch("/api/livekit/agent/stop", { method: "POST" }).finally(() =>
        navigate(returnTo),
      );
    },
    [aui, navigate, returnTo],
  );

  const mm = String(Math.floor(duration / 60)).padStart(2, "0");
  const ss = String(duration % 60).padStart(2, "0");

  return (
    <div className="flex flex-col items-center gap-8">
      <div className="flex flex-col items-center gap-4">
        <AgentAudioVisualizerAura
          size="xl"
          state={auraStateFor(state)}
          themeMode="dark"
        />
        <p
          className="text-lg font-medium tracking-tight"
          aria-live="polite"
        >
          {mode === "dictate" ? "Dictée vocale…" : stateLabel(state)}
        </p>
        <p className="text-muted-foreground font-mono text-sm">
          {mm}:{ss}
        </p>
      </div>

      {mode === "dictate" ? (
        <DictationPanel onInsert={insertDictation} />
      ) : memory && memory.total_facts > 0 ? (
        <div className="bg-muted/30 max-w-md rounded-lg border p-4">
          <p className="text-muted-foreground mb-2 text-xs tracking-wide uppercase">
            Ce que le tuteur sait de vous
          </p>
          <ul className="space-y-1 text-sm">
            {memory.identity.name ? (
              <li>
                <span className="text-muted-foreground">Nom :</span>{" "}
                {memory.identity.name}
              </li>
            ) : null}
            {Object.entries(memory.facts_by_category).map(([cat, facts]) =>
              facts.slice(0, 3).map((fact) => (
                <li key={fact.id} className="text-muted-foreground">
                  <span className="text-foreground">[{cat}]</span>{" "}
                  {fact.content}
                </li>
              )),
            )}
          </ul>
        </div>
      ) : null}

      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={toggleMic}
          className={`flex h-12 w-12 items-center justify-center rounded-full text-white transition-colors hover:opacity-80 ${
            micEnabled ? "bg-primary" : "bg-red-500"
          }`}
          aria-label={micEnabled ? "Couper le micro" : "Activer le micro"}
        >
          {micEnabled ? (
            <Mic className="h-5 w-5" />
          ) : (
            <MicOff className="h-5 w-5" />
          )}
        </button>
        <button
          type="button"
          onClick={onDisconnect}
          disabled={connectionState !== "connected"}
          className="flex h-12 w-12 items-center justify-center rounded-full bg-red-500 text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Terminer la session"
        >
          <PhoneOff className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}

export default function VoicePage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchParams] = useSearchParams();

  // mode=dictate → la session vocale sert de dictée vers le composer
  // ( ouverte par le bouton micro du composer ). return = page de retour.
  const mode = searchParams.get("mode") === "dictate" ? "dictate" : "voice";
  const returnTo = searchParams.get("return") || "/assistant";

  const [memory, setMemory] = useState<MemoryOverview | null>(null);
  const [duration, setDuration] = useState(0);

  // Token LiveKit avec renouvellement automatique avant expiration
  // ( sinon le client boucle en 401 /rtc/v1/validate au-delà d'1 heure ).
  const { data: tokenData, loading, error } = useLiveKitToken("voice");
  const token = tokenData?.token ?? "";
  const url = tokenData?.url ?? "";
  const roomName = tokenData?.roomName ?? "";

  // Token : la salle est calculée côté serveur ( session_{user_id} ),
  // identique à celle du dispatch — sinon l'agent rejoindrait le vide.
  // ( renouvellement géré par useLiveKitToken )

  // Démarre l'agent ( dispatch ) dès que la room est connue.
  // thread_id : transmis au worker via le metadata du dispatch — sans
  // lui, le transcript de la session n'est JAMAIS persisté dans le
  // thread ( thread_id_from_metadata ne le trouve pas ). Lu dans le
  // store assistant-ui ( source centrale du thread actif ).
  useEffect(() => {
    if (!roomName) return;
    const controller = new AbortController();
    async function startAgent() {
      const threadId = useAssistantStore.getState().currentThreadId;
      try {
        await apiFetch("/api/livekit/agent/start", {
          method: "POST",
          body: JSON.stringify(threadId ? { thread_id: threadId } : {}),
          signal: controller.signal,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        const apiError = error instanceof ApiError ? error : null;
        toast({
          title: "Agent indisponible",
          description:
            apiError?.message ??
            (error instanceof Error ? error.message : "Erreur inconnue"),
          variant: apiError?.status === 503 ? "default" : "destructive",
        });
      }
    }
    startAgent();
    return () => controller.abort();
  }, [roomName, toast]);

  // Chronomètre de session.
  useEffect(() => {
    if (!token) return;
    const started = Date.now();
    const id = window.setInterval(
      () => setDuration(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(id);
  }, [token]);

  // Panneau mémoire : /api/users/{id}/memory ( il n'existe pas de
  // raccourci /me/memory ; on passe par l'utilisateur courant ).
  useEffect(() => {
    async function fetchMemory() {
      try {
        const me = await apiFetch<UserOut>("/api/users/me", { method: "GET" });
        const overview = await apiFetch<MemoryOverview>(
          `/api/users/${me.user_id}/memory`,
          { method: "GET" },
        );
        setMemory(overview);
      } catch {
        // Non-fatal : le panneau mémoire est cosmétique.
      }
    }
    fetchMemory();
  }, []);

  const handleDisconnect = () => {
    // Arrêt honnête : on stoppe le dispatch avant de quitter, pour ne
    // pas laisser un agent orphelin consommer de l'inference.
    apiFetch("/api/livekit/agent/stop", { method: "POST" }).finally(() =>
      navigate("/assistant"),
    );
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="space-y-4 text-center">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">
            Initialisation de la session vocale…
          </p>
        </div>
      </div>
    );
  }

  if (error || !token || !url) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="max-w-md space-y-4 text-center">
          <p className="font-medium text-destructive">
            Session vocale indisponible
          </p>
          <p className="text-muted-foreground text-sm">
            {error || "Aucun token LiveKit reçu."}
          </p>
          <button
            type="button"
            onClick={() => navigate("/assistant")}
            className="text-primary text-sm underline"
          >
            Retour à l'assistant
          </button>
        </div>
      </div>
    );
  }

  return (
    <VoiceSession
      token={token}
      url={url}
      memory={memory}
      duration={duration}
      mode={mode}
      returnTo={returnTo}
      onDisconnect={handleDisconnect}
    />
  );
}

/**
 * Crée la session LiveKit ( useSession ) et la démarre.
 *
 * Séparé de VoicePage car useSession nécessite un tokenSource stable :
 * on ne le construit qu'une fois le token disponible, et on ne le
 * recrée pas à chaque render ( TokenSource.literal mémoïsé ).
 */
function VoiceSession({
  token,
  url,
  memory,
  duration,
  mode,
  returnTo,
  onDisconnect,
}: {
  token: string;
  url: string;
  memory: MemoryOverview | null;
  duration: number;
  mode: "voice" | "dictate";
  returnTo: string;
  onDisconnect: () => void;
}) {
  // TokenSource.literal attend { serverUrl, participantToken } —
  // les noms du proto LiveKit ( pas token/wsUrl ).
  const tokenSource = useState(
    () => TokenSource.literal({ serverUrl: url, participantToken: token }),
  )[0];

  const session = useSession(tokenSource);

  // useSession ne connecte PAS automatiquement : start() publie aussi
  // le micro ( obligatoire pour que l'agent entende l'utilisateur ).
  useEffect(() => {
    void session.start({
      tracks: {
        microphone: {
          enabled: true,
          publishOptions: { preConnectBuffer: true },
        },
      },
    });
    return () => {
      void session.end();
    };
  }, [session]);

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-background">
      <SessionProvider session={session}>
        <VoiceSessionContent
          memory={memory}
          duration={duration}
          mode={mode}
          returnTo={returnTo}
          onDisconnect={onDisconnect}
        />
      </SessionProvider>
    </div>
  );
}
