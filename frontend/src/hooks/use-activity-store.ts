// Store d'activité — panneau latéral droit (spec FUNCTIONALITIES §38)
//
// Source de vérité UI des activités pédagogiques : alimenté par
//   - les événements SSE activity.started / activity.completed /
//     activity.failed du backend (spec §3), dispatchés par
//     assistant-ui/api.ts → assistant-ui/store.ts ;
//   - le déclenchement manuel (ActivityTrigger du Composer), qui
//     crée une activité optimiste en attendant l'événement backend.
//
// L'interface §38 (title / progress / data) prime sur le type
// ActivitySummary de types/activity.ts (champs backend V5.2, sans
// title/progress) — on ne duplique pas ce contrat ici, on expose la
// vue "panneau" demandée par la spec.
import { create } from 'zustand';
import { nextId } from '../assistant-ui/types';

/** Types d'activité affichables (spec §38). */
export type ActivityKind =
  | 'research'
  | 'quiz'
  | 'exercise'
  | 'evaluation'
  | 'coding'
  | 'document'
  | 'diagram'
  | 'video';

/** Cycle de vie d'une activité côté panneau (spec §38). */
export type ActivityStatus = 'pending' | 'running' | 'completed' | 'failed';

/** Une entrée du panneau d'activité (spec §38). */
export interface Activity {
  id: string;
  type: ActivityKind;
  title: string;
  status: ActivityStatus;
  /** 0..100 — optionnel (événements progress backend). */
  progress?: number;
  /** Charge utile brute de l'événement (spec §3 `data`). */
  data?: unknown;
}

/**
 * Préfixe des activités créées localement (ActivityTrigger) en
 * attente de la confirmation backend. Sert au store assistant-ui à
 * réconcilier l'optimiste avec le réel (cf. assistant-ui/store.ts).
 */
export const LOCAL_ACTIVITY_PREFIX = 'local-';

const KNOWN_KINDS: ActivityKind[] = [
  'research',
  'quiz',
  'exercise',
  'evaluation',
  'coding',
  'document',
  'diagram',
  'video',
];

/** Mapping des activity_type backend (V5.2) → kinds du panneau §38.
 *  Inconnu → 'exercise' (valeur par défaut raisonnable pour un tuteur ;
 *  les types futurs (document/diagram/video) sont déjà couverts par
 *  KNOWN_KINDS s'ils portent le même nom que la spec). */
export function mapActivityKind(raw?: string): ActivityKind {
  if (!raw) return 'exercise';
  if ((KNOWN_KINDS as string[]).includes(raw)) return raw as ActivityKind;
  switch (raw) {
    case 'understanding_check':
      return 'evaluation';
    case 'code_practice':
      return 'coding';
    default:
      return 'exercise';
  }
}

/**
 * Déduit le kind du panneau à partir du tool_name backend.
 *
 * Contexte : le payload des événements ACTIVITY_STARTED / QUIZ_STARTED
 * (pedagogical_tools.py) NE contient PAS `activity_type` — seulement
 * activity_id/subject/topic/status/source + le tool_name de log_event.
 * On dégrade donc gracieusement : activity_type spec §3 d'abord,
 * tool_name sinon (create_quiz → quiz, execute_code → coding…),
 * 'exercise' en dernier ressort.
 */
const TOOL_KINDS: Record<string, ActivityKind> = {
  // Pédagogique
  create_exercise: 'exercise',
  give_hint: 'exercise',
  evaluate_answer: 'evaluation',
  create_quiz: 'quiz',
  create_quiz_next: 'quiz',
  assess_understanding: 'evaluation',
  propose_review: 'exercise',
  // Code (sandbox §24-§30)
  execute_code: 'coding',
  run_tests: 'coding',
  analyze_code: 'coding',
  // Recherche / documents
  recherche_web: 'research',
  search_documents: 'document',
  search_user_memory: 'research',
};

export function kindFromToolName(toolName?: string): ActivityKind | null {
  if (!toolName) return null;
  return TOOL_KINDS[toolName] ?? null;
}

/** Détermination du kind : spec §3 `activity_type` prioritaire, puis
 *  tool_name backend, puis défaut. */
export function resolveActivityKind(
  activityType?: string,
  toolName?: string,
): ActivityKind {
  return mapActivityKind(activityType) === 'exercise' && !activityType
    ? kindFromToolName(toolName) ?? 'exercise'
    : mapActivityKind(activityType);
}

/** Construit un titre lisible : la spec §3 veut un `title`, mais le
 *  backend l'omet — on compose avec subject/topic (présents dans
 *  ACTIVITY_STARTED/QUIZ_STARTED) ou le tool_name. */
export function buildActivityTitle(parts: {
  title?: string;
  subject?: string;
  topic?: string;
  toolName?: string;
  kind?: ActivityKind;
}): string {
  if (parts.title) return parts.title;
  const scope = [parts.subject, parts.topic].filter(Boolean).join(' / ');
  if (scope) return `Activité ${parts.kind ?? 'pédagogique'} — ${scope}`;
  if (parts.toolName) return `Activité ${parts.toolName}`;
  return 'Activité pédagogique';
}

interface ActivityStore {
  activities: Activity[];
  activeActivityId: string | null;
  panelOpen: boolean;

  /** Insère ou remplace (par id) une activité. */
  upsertActivity: (activity: Activity) => void;
  /** Retire une activité par id (réconciliation optimiste→réel). */
  removeActivity: (id: string) => void;
  /** Active une activité dans le panneau (null = aucune). */
  setActive: (id: string | null) => void;
  /** Ouvre/ferme le panneau, ou bascule sans argument. */
  togglePanel: (open?: boolean) => void;
}

export const useActivityStore = create<ActivityStore>((set) => ({
  activities: [],
  activeActivityId: null,
  panelOpen: false,

  upsertActivity: (activity) =>
    set((s) => {
      const others = s.activities.filter((a) => a.id !== activity.id);
      return {
        activities: [activity, ...others].slice(0, 50),
      };
    }),

  removeActivity: (id) =>
    set((s) => ({
      activities: s.activities.filter((a) => a.id !== id),
      activeActivityId:
        s.activeActivityId === id ? null : s.activeActivityId,
    })),

  setActive: (id) => set({ activeActivityId: id }),

  togglePanel: (open) =>
    set((s) => ({ panelOpen: open ?? !s.panelOpen })),
}));

/** Crée l'activité optimiste déposée par le bouton Activité. */
export function createLocalActivity(
  kind: ActivityKind,
  title: string,
): Activity {
  return {
    id: nextId(LOCAL_ACTIVITY_PREFIX),
    type: kind,
    title,
    status: 'running',
  };
}
