// /learning/subjects — matières issues du Subject Registry (backend).
import { Link } from 'react-router-dom';
import { BookOpen, ChevronRight } from 'lucide-react';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useLearning } from '../../hooks/useLearning';
import { useSubjects } from '../../hooks/useSubjects';
import {
  EmptyState,
  PageHeader,
  ProgressBar,
  Surface,
} from '../../components/user/kit';

export function LearningSubjectsPage() {
  const { internal } = useCurrentUser();
  const { data } = useLearning(internal?.user_id ?? null);
  const { subjects, loading, error } = useSubjects();

  const learningById = new Map(data.subjects.map((s) => [s.id, s]));

  return (
    <>
      <PageHeader
        eyebrow="learning · subjects"
        title="Matières"
        description="Registre des matières configurées côté backend (Subject Registry)."
      />

      <div className="p-6">
        {loading ? (
          <Surface>
            <EmptyState icon={BookOpen} title="Chargement du registre…" />
          </Surface>
        ) : subjects.length === 0 ? (
          <Surface>
            <EmptyState
              icon={BookOpen}
              title="Aucune donnée disponible pour le moment."
              description={
                error ??
                'Aucune matière n’est enregistrée dans le registre.'
              }
            />
          </Surface>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {subjects.map((s) => {
              const learning = learningById.get(s.id);
              return (
                <Surface key={s.id} className="flex flex-col">
                  <Link
                    to={`/learning/subjects/${s.id}`}
                    className="hover:bg-muted/40 flex flex-1 flex-col gap-2 rounded-[var(--radius-surface)] p-4 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-foreground text-[14px] font-semibold tracking-tight">
                        {s.name}
                      </span>
                      <ChevronRight
                        size={14}
                        className="text-muted-foreground mt-0.5 shrink-0"
                      />
                    </div>
                    <p className="text-muted-foreground line-clamp-2 text-[12.5px] leading-relaxed">
                      {s.description}
                    </p>
                    <div className="mt-auto space-y-1.5 pt-2">
                      <div className="text-muted-foreground flex items-center justify-between font-mono text-[10px]">
                        <span>{s.domain}</span>
                        <span>
                          {s.topics.length} topic
                          {s.topics.length > 1 ? 's' : ''}
                        </span>
                      </div>
                      <ProgressBar
                        value={learning?.mastery ?? null}
                        label={s.name}
                      />
                    </div>
                  </Link>
                </Surface>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
