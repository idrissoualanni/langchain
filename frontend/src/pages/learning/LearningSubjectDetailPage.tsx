// /learning/subjects/:subjectId — détail d'une matière (registre + progression).
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, BookOpen } from 'lucide-react';
import { getSubject, getSubjectTopics, type SubjectTopic } from '../../api/subjects';
import type { SubjectInfo } from '../../types/agent';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useLearning } from '../../hooks/useLearning';
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

export function LearningSubjectDetailPage() {
  const { subjectId = '' } = useParams();
  const { internal } = useCurrentUser();
  const { data } = useLearning(internal?.user_id ?? null);

  const [subject, setSubject] = useState<SubjectInfo | null>(null);
  const [topics, setTopics] = useState<SubjectTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    Promise.all([
      getSubject(subjectId),
      getSubjectTopics(subjectId).catch(() => []),
    ])
      .then(([info, tps]) => {
        if (!alive) return;
        setSubject(info);
        setTopics(tps);
      })
      .catch((e) => {
        if (alive)
          setError(e instanceof Error ? e.message : 'Matière introuvable');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [subjectId]);

  const learning = data.subjects.find((s) => s.id === subjectId);
  const observations = data.observations.filter(
    (o) => o.subject === subjectId
  );
  const weakPoints = data.weakPoints.filter((w) => w.subject === subjectId);
  const learningTopics = new Map(
    (learning?.topics ?? []).map((t) => [t.id, t.data])
  );

  if (loading) {
    return (
      <Surface className="m-6">
        <EmptyState icon={BookOpen} title="Chargement de la matière…" />
      </Surface>
    );
  }

  if (error || !subject) {
    return (
      <Surface className="m-6">
        <EmptyState
          icon={BookOpen}
          title="Matière indisponible"
          description={error ?? 'Cette matière n’existe pas dans le registre.'}
          action={
            <Link
              to="/learning/subjects"
              className="text-live inline-flex items-center gap-1 text-sm"
            >
              <ArrowLeft size={13} /> Retour aux matières
            </Link>
          }
        />
      </Surface>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={`subject · ${subject.domain}`}
        title={subject.name}
        description={subject.description}
        actions={
          <Link
            to="/learning/subjects"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
          >
            <ArrowLeft size={13} /> Matières
          </Link>
        }
      />

      <div className="space-y-5 p-6">
        <Surface>
          <SurfaceHeader>
            <SurfaceTitle>Progression</SurfaceTitle>
          </SurfaceHeader>
          <SurfaceBody>
            {learning ? (
              <ProgressBar value={learning.mastery} label={subject.name} />
            ) : (
              <p className="text-muted-foreground text-sm">
                Aucune progression enregistrée pour cette matière.
              </p>
            )}
          </SurfaceBody>
        </Surface>

        <Surface>
          <SurfaceHeader>
            <SurfaceTitle>Topics</SurfaceTitle>
            <span className="text-muted-foreground font-mono text-[10px]">
              {topics.length} au registre
            </span>
          </SurfaceHeader>
          <SurfaceBody className="space-y-2">
            {topics.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Aucun topic configuré pour cette matière.
              </p>
            ) : (
              topics.map((t) => {
                const ld = learningTopics.get(t.id);
                return (
                  <div
                    key={t.id}
                    className="border-border flex items-center gap-3 border-b py-1.5 last:border-0"
                  >
                    <span className="text-foreground min-w-0 flex-1 truncate text-[12.5px]">
                      {t.name}
                    </span>
                    {ld ? (
                      <>
                        <span className="text-muted-foreground font-mono text-[10px]">
                          {ld.attempts} essai{ld.attempts > 1 ? 's' : ''}
                        </span>
                        <div className="w-32">
                          <ProgressBar
                            value={ld.mastery}
                            label={t.name}
                          />
                        </div>
                      </>
                    ) : (
                      <span className="text-muted-foreground/60 font-mono text-[10px]">
                        non évalué
                      </span>
                    )}
                  </div>
                );
              })
            )}
          </SurfaceBody>
        </Surface>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Surface>
            <SurfaceHeader>
              <SurfaceTitle>Activités récentes</SurfaceTitle>
            </SurfaceHeader>
            <SurfaceBody className="space-y-2">
              {observations.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  Aucune activité enregistrée pour cette matière.
                </p>
              ) : (
                observations.slice(0, 6).map((o, i) => (
                  <div
                    key={i}
                    className="border-border flex items-center gap-3 border-b py-1.5 last:border-0"
                  >
                    <Pill tone="live">{o.type}</Pill>
                    <span className="text-foreground min-w-0 flex-1 truncate text-[12.5px]">
                      {o.topic}
                    </span>
                    <span className="text-muted-foreground font-mono text-[10px]">
                      {fmtDate(o.created_at)}
                    </span>
                  </div>
                ))
              )}
            </SurfaceBody>
          </Surface>

          <Surface>
            <SurfaceHeader>
              <SurfaceTitle>Points à travailler</SurfaceTitle>
            </SurfaceHeader>
            <SurfaceBody className="space-y-2">
              {weakPoints.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  Aucun point faible enregistré.
                </p>
              ) : (
                weakPoints.map((w) => (
                  <div key={w.topic}>
                    <div className="text-muted-foreground font-mono text-[10px] uppercase">
                      {w.topic}
                    </div>
                    {w.points.map((p, i) => (
                      <div
                        key={i}
                        className="text-foreground flex items-start gap-1.5 py-0.5 text-[12.5px]"
                      >
                        <span className="text-warning mt-0.5 shrink-0">⚠</span>
                        {p}
                      </div>
                    ))}
                  </div>
                ))
              )}
            </SurfaceBody>
          </Surface>
        </div>
      </div>
    </>
  );
}
