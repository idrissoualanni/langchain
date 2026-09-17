// /learning/topics — topics étudiés + filtres (subject, statut, progression).
import { useMemo, useState } from 'react';
import { ListFilter } from 'lucide-react';
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
  type Tone,
} from '../../components/user/kit';

type Status = 'not_assessed' | 'learning' | 'mastered';

function statusOf(
  mastery: number | null,
  attempts: number
): Status {
  if (mastery === null && attempts === 0) return 'not_assessed';
  return (mastery ?? 0) >= 0.7 ? 'mastered' : 'learning';
}

const STATUS_LABEL: Record<Status, string> = {
  not_assessed: 'non évalué',
  learning: 'en cours',
  mastered: 'maîtrisé',
};

const STATUS_TONE: Record<Status, Tone> = {
  not_assessed: 'neutral',
  learning: 'warning',
  mastered: 'success',
};

function selectCls() {
  return 'border-input bg-background text-foreground h-8 rounded-[var(--radius-control)] border px-2 text-[12.5px]';
}

export function LearningTopicsPage() {
  const { internal } = useCurrentUser();
  const { data, loading } = useLearning(internal?.user_id ?? null);
  const { byId } = useSubjects();

  const [subject, setSubject] = useState('all');
  const [status, setStatus] = useState<'all' | Status>('all');
  const [progression, setProgression] = useState('all');

  const allRows = useMemo(
    () =>
      data.subjects.flatMap((s) =>
        s.topics.map((t) => ({
          subject: s.id,
          topic: t.id,
          ...t.data,
          status: statusOf(t.data.mastery, t.data.attempts),
        }))
      ),
    [data.subjects]
  );

  const subjectIds = data.subjects.map((s) => s.id);

  const rows = allRows.filter((r) => {
    if (subject !== 'all' && r.subject !== subject) return false;
    if (status !== 'all' && r.status !== status) return false;
    if (progression !== 'all') {
      if (r.mastery === null) return false;
      if (progression === 'low' && r.mastery >= 0.4) return false;
      if (
        progression === 'mid' &&
        (r.mastery < 0.4 || r.mastery >= 0.7)
      )
        return false;
      if (progression === 'high' && r.mastery < 0.7) return false;
    }
    return true;
  });

  return (
    <>
      <PageHeader
        eyebrow="learning · topics"
        title="Topics"
        description="Topics pour lesquels une progression a été enregistrée. Filtrez par matière, statut ou niveau."
      />

      <div className="space-y-5 p-6">
        <Surface>
          <SurfaceHeader>
            <SurfaceTitle className="flex items-center gap-2">
              <ListFilter size={13} /> Filtres
            </SurfaceTitle>
            <span className="text-muted-foreground font-mono text-[10px]">
              {rows.length} / {allRows.length}
            </span>
          </SurfaceHeader>
          <SurfaceBody className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-[12px]">
              <span className="text-muted-foreground">Matière</span>
              <select
                className={selectCls()}
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
              >
                <option value="all">Toutes</option>
                {subjectIds.map((id) => (
                  <option key={id} value={id}>
                    {byId.get(id)?.name ?? id}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex items-center gap-2 text-[12px]">
              <span className="text-muted-foreground">Statut</span>
              <select
                className={selectCls()}
                value={status}
                onChange={(e) =>
                  setStatus(e.target.value as 'all' | Status)
                }
              >
                <option value="all">Tous</option>
                <option value="not_assessed">Non évalué</option>
                <option value="learning">En cours</option>
                <option value="mastered">Maîtrisé</option>
              </select>
            </label>

            <label className="flex items-center gap-2 text-[12px]">
              <span className="text-muted-foreground">Progression</span>
              <select
                className={selectCls()}
                value={progression}
                onChange={(e) => setProgression(e.target.value)}
              >
                <option value="all">Toutes</option>
                <option value="low">&lt; 40%</option>
                <option value="mid">40–70%</option>
                <option value="high">≥ 70%</option>
              </select>
            </label>
          </SurfaceBody>
        </Surface>

        {loading && allRows.length === 0 ? (
          <Surface>
            <EmptyState icon={ListFilter} title="Chargement…" />
          </Surface>
        ) : allRows.length === 0 ? (
          <Surface>
            <EmptyState
              icon={ListFilter}
              title="Aucune donnée disponible pour le moment."
              description="Aucun topic n’a encore été étudié pour votre profil."
            />
          </Surface>
        ) : rows.length === 0 ? (
          <Surface>
            <EmptyState
              icon={ListFilter}
              title="Aucun topic ne correspond aux filtres."
            />
          </Surface>
        ) : (
          <Surface>
            <SurfaceBody className="space-y-2">
              {rows.map((r) => (
                <div
                  key={`${r.subject}/${r.topic}`}
                  className="border-border flex flex-wrap items-center gap-3 border-b py-2 last:border-0"
                >
                  <span className="text-foreground min-w-0 flex-1 truncate text-[13px] font-medium">
                    {r.topic}
                  </span>
                  <span className="text-muted-foreground font-mono text-[10px]">
                    {byId.get(r.subject)?.name ?? r.subject}
                  </span>
                  <Pill tone={STATUS_TONE[r.status]}>
                    {STATUS_LABEL[r.status]}
                  </Pill>
                  <span className="text-muted-foreground font-mono text-[10px]">
                    {r.attempts} essai{r.attempts > 1 ? 's' : ''}
                  </span>
                  <div className="w-32">
                    <ProgressBar value={r.mastery} label={r.topic} />
                  </div>
                </div>
              ))}
            </SurfaceBody>
          </Surface>
        )}
      </div>
    </>
  );
}
