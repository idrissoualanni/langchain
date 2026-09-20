// /learning — Learning Overview (vue synthétique, données réelles).
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Goal,
  GraduationCap,
  Sparkles,
  Target,
} from 'lucide-react';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useLearning } from '../../hooks/useLearning';
import { useSubjects } from '../../hooks/useSubjects';
import {
  EmptyState,
  PageHeader,
  Pill,
  ProgressBar,
  StatTile,
  Surface,
  SurfaceBody,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('fr-FR', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
}

export function LearningOverviewPage() {
  const { internal } = useCurrentUser();
  const userId = internal?.user_id ?? null;
  const { data, loading } = useLearning(userId);
  const { byId } = useSubjects();

  const hasAny =
    data.subjectCount > 0 ||
    data.goals.length > 0 ||
    data.observations.length > 0;

  return (
    <>
      <PageHeader
        eyebrow="learning"
        title={internal ? `Bonjour, ${internal.name}` : 'Learning Overview'}
        description="Votre progression pédagogique, agrégée depuis les données réellement enregistrées par l’agent."
      />

      <div className="space-y-5 p-6">
        {loading && !hasAny ? (
          <Surface>
            <EmptyState
              icon={GraduationCap}
              title="Chargement de la progression…"
            />
          </Surface>
        ) : !hasAny ? (
          <Surface>
            <EmptyState
              icon={GraduationCap}
              title="Aucune donnée disponible pour le moment."
              description="Votre progression apparaîtra ici après vos premières interactions d’apprentissage avec l’assistant."
            />
          </Surface>
        ) : (
          <>
            {/* Progression globale — valeurs réelles, aucune extrapolation */}
            <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile
                label="matières suivies"
                value={data.subjectCount}
                hint={`${data.assessedSubjectCount} évaluée(s)`}
              />
              <StatTile
                label="topics suivis"
                value={data.topicCount}
                hint={`${data.assessedTopicCount} évalué(s)`}
              />
              <StatTile
                label="mastery moy."
                value={
                  data.globalMastery === null
                    ? '—'
                    : `${Math.round(data.globalMastery * 100)}%`
                }
                hint="matières évaluées"
              />
              <StatTile
                label="dernière activité"
                value={fmtDate(data.lastActivityAt)}
              />
            </section>

            {/* Sujets étudiés */}
            <Surface>
              <SurfaceHeader>
                <SurfaceTitle>Progression par matière</SurfaceTitle>
                <Link
                  to="/learning/subjects"
                  className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
                >
                  Toutes les matières <ArrowRight size={12} />
                </Link>
              </SurfaceHeader>
              <SurfaceBody className="space-y-3">
                {data.subjects.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    Aucune matière avec progression enregistrée.
                  </p>
                ) : (
                  data.subjects.map((s) => (
                    <div key={s.id} className="space-y-1.5">
                      <div className="flex items-center justify-between gap-3">
                        <Link
                          to={`/learning/subjects/${s.id}`}
                          className="text-foreground hover:text-live truncate text-[13px] font-medium"
                        >
                          {byId.get(s.id)?.name ?? s.id}
                        </Link>
                        <span className="text-muted-foreground font-mono text-[10px]">
                          {s.topics.length} topic
                          {s.topics.length > 1 ? 's' : ''}
                        </span>
                      </div>
                      <ProgressBar value={s.mastery} label={s.id} />
                    </div>
                  ))
                )}
              </SurfaceBody>
            </Surface>

            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              {/* Activités récentes */}
              <Surface>
                <SurfaceHeader>
                  <SurfaceTitle className="flex items-center gap-2">
                    <Activity size={13} /> Activités récentes
                  </SurfaceTitle>
                  <Link
                    to="/learning/history"
                    className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
                  >
                    Historique <ArrowRight size={12} />
                  </Link>
                </SurfaceHeader>
                <SurfaceBody className="space-y-2">
                  {data.observations.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      Aucune activité enregistrée.
                    </p>
                  ) : (
                    data.observations.slice(0, 5).map((o, i) => (
                      <div
                        key={i}
                        className="border-border flex items-center gap-3 border-b py-1.5 last:border-0"
                      >
                        <Pill tone="live">{o.type}</Pill>
                        <span className="text-foreground min-w-0 flex-1 truncate text-[12.5px]">
                          {byId.get(o.subject)?.name ?? o.subject}
                          <span className="text-muted-foreground">
                            {' · '}
                            {o.topic}
                          </span>
                        </span>
                        <span className="text-muted-foreground font-mono text-[10px]">
                          {fmtDate(o.created_at)}
                        </span>
                      </div>
                    ))
                  )}
                </SurfaceBody>
              </Surface>

              {/* Points à travailler */}
              <Surface>
                <SurfaceHeader>
                  <SurfaceTitle className="flex items-center gap-2">
                    <AlertTriangle size={13} /> À travailler
                  </SurfaceTitle>
                  <Link
                    to="/learning/reviews"
                    className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
                  >
                    Reviews <ArrowRight size={12} />
                  </Link>
                </SurfaceHeader>
                <SurfaceBody className="space-y-2">
                  {data.weakPoints.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      Aucun point faible identifié.
                    </p>
                  ) : (
                    data.weakPoints.slice(0, 5).map((w) => (
                      <div key={`${w.subject}/${w.topic}`} className="py-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-foreground truncate text-[12.5px] font-medium">
                            {w.topic}
                          </span>
                          <span className="text-muted-foreground font-mono text-[10px]">
                            {byId.get(w.subject)?.name ?? w.subject}
                          </span>
                        </div>
                        <p className="text-muted-foreground mt-0.5 text-[11.5px]">
                          {w.points.slice(0, 2).join(' · ')}
                        </p>
                      </div>
                    ))
                  )}
                </SurfaceBody>
              </Surface>

              {/* Objectifs */}
              <Surface>
                <SurfaceHeader>
                  <SurfaceTitle className="flex items-center gap-2">
                    <Target size={13} /> Objectifs
                  </SurfaceTitle>
                  <Link
                    to="/learning/goals"
                    className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
                  >
                    Tous les objectifs <ArrowRight size={12} />
                  </Link>
                </SurfaceHeader>
                <SurfaceBody className="space-y-2">
                  {data.goals.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      Aucun objectif enregistré.
                    </p>
                  ) : (
                    data.goals.slice(0, 4).map((g) => (
                      <div
                        key={g.id}
                        className="flex items-center gap-2 py-1 text-[12.5px]"
                      >
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
                        <span className="text-foreground min-w-0 flex-1 truncate">
                          {g.description}
                        </span>
                        <span className="text-muted-foreground font-mono text-[10px]">
                          {g.subject}
                        </span>
                      </div>
                    ))
                  )}
                </SurfaceBody>
              </Surface>

              {/* Recommandations disponibles */}
              <Surface>
                <SurfaceHeader>
                  <SurfaceTitle className="flex items-center gap-2">
                    <Sparkles size={13} /> Recommandations
                  </SurfaceTitle>
                </SurfaceHeader>
                <SurfaceBody>
                  <p className="text-muted-foreground text-sm">
                    Aucune recommandation disponible pour le moment.
                  </p>
                  <Link
                    to="/learning/for-you"
                    className="text-live mt-2 inline-flex items-center gap-1 text-xs font-medium"
                  >
                    <Goal size={12} /> Voir l’espace For You
                  </Link>
                </SurfaceBody>
              </Surface>
            </div>
          </>
        )}
      </div>
    </>
  );
}
