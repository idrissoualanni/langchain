// /learning/goals — objectifs pédagogiques (LECTURE SEULE).
//
// Le backend n'expose ni création, ni modification, ni suppression via
// REST (les écritures passent par les tools de l'agent). Cette page
// affiche donc uniquement les objectifs réellement enregistrés, sans
// simuler de sauvegarde.
import { CheckCircle2, PauseCircle, Target } from 'lucide-react';
import type { LearningGoalData } from '../../types/learning';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useLearning } from '../../hooks/useLearning';
import { useSubjects } from '../../hooks/useSubjects';
import {
  EmptyState,
  PageHeader,
  Pill,
  ProgressBar,
  Surface,
  SurfaceBody,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('fr-FR');
}

function GoalList({
  goals,
  labelOf,
  masteryOf,
}: {
  goals: LearningGoalData[];
  labelOf: (id: string) => string;
  masteryOf: (subject: string, topic: string | null) => number | null;
}) {
  if (goals.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        Aucun objectif dans cette catégorie.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {goals.map((g) => {
        const mastery = g.topic ? masteryOf(g.subject, g.topic) : null;
        return (
          <div
            key={g.id}
            className="border-border border-b pb-3 last:border-0 last:pb-0"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-foreground min-w-0 flex-1 text-[13px] font-medium">
                {g.description}
              </span>
              <Pill
                tone={
                  g.status === 'active'
                    ? 'live'
                    : g.status === 'completed'
                      ? 'success'
                      : 'neutral'
                }
              >
                {g.status}
              </Pill>
            </div>
            <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px]">
              <span>{labelOf(g.subject)}</span>
              {g.topic && <span>· {g.topic}</span>}
              <span>· créé le {fmtDate(g.created_at)}</span>
            </div>
            {g.topic && (
              <div className="mt-2 max-w-xs">
                {mastery === null ? (
                  <span className="text-muted-foreground/70 font-mono text-[10px]">
                    progression du topic : non évaluée
                  </span>
                ) : (
                  <ProgressBar value={mastery} label={g.topic} />
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function LearningGoalsPage() {
  const { internal } = useCurrentUser();
  const { data, loading } = useLearning(internal?.user_id ?? null);
  const { byId } = useSubjects();

  const labelOf = (id: string) => byId.get(id)?.name ?? id;
  const masteryOf = (subject: string, topic: string | null) => {
    if (!topic) return null;
    const s = data.subjects.find((x) => x.id === subject);
    return s?.topics.find((t) => t.id === topic)?.data.mastery ?? null;
  };

  const active = data.goals.filter((g) => g.status === 'active');
  const completed = data.goals.filter((g) => g.status === 'completed');
  const paused = data.goals.filter((g) => g.status === 'paused');

  return (
    <>
      <PageHeader
        eyebrow="learning · goals"
        title="Objectifs"
        description="Objectifs pédagogiques enregistrés. Lecture seule : la création et la mise à jour sont gérées par l’agent."
      />

      <div className="space-y-5 p-6">
        {loading && data.goals.length === 0 ? (
          <Surface>
            <EmptyState icon={Target} title="Chargement…" />
          </Surface>
        ) : data.goals.length === 0 ? (
          <Surface>
            <EmptyState
              icon={Target}
              title="Aucune donnée disponible pour le moment."
              description="Aucun objectif n’a encore été enregistré. L’assistant peut en définir pendant une conversation."
            />
          </Surface>
        ) : (
          <>
            <Surface>
              <SurfaceHeader>
                <SurfaceTitle className="flex items-center gap-2">
                  <Target size={13} /> Objectifs actifs
                </SurfaceTitle>
                <span className="text-muted-foreground font-mono text-[10px]">
                  {active.length}
                </span>
              </SurfaceHeader>
              <SurfaceBody>
                <GoalList
                  goals={active}
                  labelOf={labelOf}
                  masteryOf={masteryOf}
                />
              </SurfaceBody>
            </Surface>

            <Surface>
              <SurfaceHeader>
                <SurfaceTitle className="flex items-center gap-2">
                  <CheckCircle2 size={13} /> Objectifs terminés
                </SurfaceTitle>
                <span className="text-muted-foreground font-mono text-[10px]">
                  {completed.length}
                </span>
              </SurfaceHeader>
              <SurfaceBody>
                <GoalList
                  goals={completed}
                  labelOf={labelOf}
                  masteryOf={masteryOf}
                />
              </SurfaceBody>
            </Surface>

            {paused.length > 0 && (
              <Surface>
                <SurfaceHeader>
                  <SurfaceTitle className="flex items-center gap-2">
                    <PauseCircle size={13} /> En pause
                  </SurfaceTitle>
                  <span className="text-muted-foreground font-mono text-[10px]">
                    {paused.length}
                  </span>
                </SurfaceHeader>
                <SurfaceBody>
                  <GoalList
                    goals={paused}
                    labelOf={labelOf}
                    masteryOf={masteryOf}
                  />
                </SurfaceBody>
              </Surface>
            )}
          </>
        )}
      </div>
    </>
  );
}
