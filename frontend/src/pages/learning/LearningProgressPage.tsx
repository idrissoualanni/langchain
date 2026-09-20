// /learning/progress — mastery, confidence, forces/faiblesses, évaluations.
import { Check, TrendingUp } from 'lucide-react';
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

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('fr-FR');
}

export function LearningProgressPage() {
  const { internal } = useCurrentUser();
  const { data, loading } = useLearning(internal?.user_id ?? null);
  const { byId } = useSubjects();

  const rows = data.subjects.flatMap((s) =>
    s.topics.map((t) => ({ subject: s.id, ...t }))
  );

  const assessments = data.observations.filter((o) => o.score !== null);

  return (
    <>
      <PageHeader
        eyebrow="learning · progression"
        title="Progression"
        description="Mastery, confiance, forces et points faibles, tels qu’enregistrés pour chaque topic."
      />

      <div className="space-y-5 p-6">
        {loading && data.subjectCount === 0 ? (
          <Surface>
            <EmptyState icon={TrendingUp} title="Chargement…" />
          </Surface>
        ) : rows.length === 0 ? (
          <Surface>
            <EmptyState
              icon={TrendingUp}
              title="Aucune donnée disponible pour le moment."
              description="Aucun topic n’a encore été évalué pour votre profil."
            />
          </Surface>
        ) : (
          <>
            {/* Progression par matière */}
            <Surface>
              <SurfaceHeader>
                <SurfaceTitle>Progression par matière</SurfaceTitle>
              </SurfaceHeader>
              <SurfaceBody className="space-y-3">
                {data.subjects.map((s) => (
                  <div key={s.id} className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-foreground text-[13px] font-medium">
                        {byId.get(s.id)?.name ?? s.id}
                      </span>
                    </div>
                    <ProgressBar value={s.mastery} label={s.id} />
                  </div>
                ))}
              </SurfaceBody>
            </Surface>

            {/* Détail par topic */}
            <Surface>
              <SurfaceHeader>
                <SurfaceTitle>Détail par topic</SurfaceTitle>
              </SurfaceHeader>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-[12.5px]">
                  <thead>
                    <tr className="text-muted-foreground border-border border-b font-mono text-[10px] uppercase">
                      <th className="px-4 py-2 font-semibold">Matière</th>
                      <th className="px-4 py-2 font-semibold">Topic</th>
                      <th className="px-4 py-2 font-semibold">Mastery</th>
                      <th className="px-4 py-2 font-semibold">Confiance</th>
                      <th className="px-4 py-2 font-semibold">Essais</th>
                      <th className="px-4 py-2 font-semibold">Évalué le</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr
                        key={`${r.subject}/${r.id}`}
                        className="border-border border-b last:border-0"
                      >
                        <td className="text-muted-foreground px-4 py-2">
                          {byId.get(r.subject)?.name ?? r.subject}
                        </td>
                        <td className="text-foreground px-4 py-2 font-medium">
                          {r.id}
                        </td>
                        <td className="px-4 py-2">
                          <span className="font-mono tabular-nums">
                            {r.data.mastery === null
                              ? '—'
                              : `${Math.round(r.data.mastery * 100)}%`}
                          </span>
                        </td>
                        <td className="px-4 py-2 font-mono tabular-nums">
                          {r.data.confidence === null
                            ? '—'
                            : `${Math.round(r.data.confidence * 100)}%`}
                        </td>
                        <td className="px-4 py-2 font-mono tabular-nums">
                          {r.data.attempts}
                        </td>
                        <td className="text-muted-foreground px-4 py-2 font-mono text-[11px]">
                          {fmtDate(r.data.last_assessed_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Surface>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              {/* Forces */}
              <Surface>
                <SurfaceHeader>
                  <SurfaceTitle>Forces</SurfaceTitle>
                </SurfaceHeader>
                <SurfaceBody className="space-y-2">
                  {data.strengths.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      Aucune force enregistrée.
                    </p>
                  ) : (
                    data.strengths.map((s) => (
                      <div key={`${s.subject}/${s.topic}`}>
                        <div className="text-muted-foreground font-mono text-[10px] uppercase">
                          {s.topic}
                        </div>
                        {s.points.map((p, i) => (
                          <div
                            key={i}
                            className="text-foreground flex items-start gap-1.5 py-0.5 text-[12.5px]"
                          >
                            <Check
                              size={12}
                              className="text-success mt-0.5 shrink-0"
                            />
                            {p}
                          </div>
                        ))}
                      </div>
                    ))
                  )}
                </SurfaceBody>
              </Surface>

              {/* Points faibles */}
              <Surface>
                <SurfaceHeader>
                  <SurfaceTitle>Points à travailler</SurfaceTitle>
                </SurfaceHeader>
                <SurfaceBody className="space-y-2">
                  {data.weakPoints.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      Aucun point faible enregistré.
                    </p>
                  ) : (
                    data.weakPoints.map((w) => (
                      <div key={`${w.subject}/${w.topic}`}>
                        <div className="text-muted-foreground font-mono text-[10px] uppercase">
                          {w.topic}
                        </div>
                        {w.points.map((p, i) => (
                          <div
                            key={i}
                            className="text-foreground flex items-start gap-1.5 py-0.5 text-[12.5px]"
                          >
                            <span className="text-warning mt-0.5 shrink-0">
                              ⚠
                            </span>
                            {p}
                          </div>
                        ))}
                      </div>
                    ))
                  )}
                </SurfaceBody>
              </Surface>
            </div>

            {/* Évaluations */}
            <Surface>
              <SurfaceHeader>
                <SurfaceTitle>Évaluations</SurfaceTitle>
                <span className="text-muted-foreground font-mono text-[10px]">
                  observations avec score
                </span>
              </SurfaceHeader>
              <SurfaceBody className="space-y-2">
                {assessments.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    Aucune évaluation avec score enregistrée.
                  </p>
                ) : (
                  assessments.map((o, i) => (
                    <div
                      key={i}
                      className="border-border flex items-center gap-3 border-b py-1.5 last:border-0"
                    >
                      <Pill tone="live">{o.type}</Pill>
                      <span className="text-foreground min-w-0 flex-1 truncate text-[12.5px]">
                        {o.topic}
                      </span>
                      <span className="text-foreground font-mono text-[11px] tabular-nums">
                        {o.score === null
                          ? '—'
                          : `${Math.round(o.score * 100)}%`}
                      </span>
                      <span className="text-muted-foreground font-mono text-[10px]">
                        {fmtDate(o.created_at)}
                      </span>
                    </div>
                  ))
                )}
              </SurfaceBody>
            </Surface>
          </>
        )}
      </div>
    </>
  );
}
