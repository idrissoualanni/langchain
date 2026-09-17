// /learning/reviews — topics à réviser, dérivés des points faibles
// réellement enregistrés (aucun moteur de révision ici).
import { RotateCcw } from 'lucide-react';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useLearning } from '../../hooks/useLearning';
import { useSubjects } from '../../hooks/useSubjects';
import {
  EmptyState,
  PageHeader,
  ProgressBar,
  Surface,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('fr-FR');
}

export function LearningReviewsPage() {
  const { internal } = useCurrentUser();
  const { data, loading } = useLearning(internal?.user_id ?? null);
  const { byId } = useSubjects();

  const rows = data.weakPoints;

  return (
    <>
      <PageHeader
        eyebrow="learning · reviews"
        title="Révisions"
        description="Topics présentant des points faibles enregistrés, avec leur dernière activité et leur niveau actuel."
      />

      <div className="p-6">
        {loading && rows.length === 0 ? (
          <Surface>
            <EmptyState icon={RotateCcw} title="Chargement…" />
          </Surface>
        ) : rows.length === 0 ? (
          <Surface>
            <EmptyState
              icon={RotateCcw}
              title="Aucune donnée disponible pour le moment."
              description="Aucun point faible n’a été enregistré : rien à réviser pour l’instant."
            />
          </Surface>
        ) : (
          <Surface>
            <SurfaceHeader>
              <SurfaceTitle>À réviser</SurfaceTitle>
              <span className="text-muted-foreground font-mono text-[10px]">
                {rows.length} topic{rows.length > 1 ? 's' : ''}
              </span>
            </SurfaceHeader>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-[12.5px]">
                <thead>
                  <tr className="text-muted-foreground border-border border-b font-mono text-[10px] uppercase">
                    <th className="px-4 py-2 font-semibold">Topic</th>
                    <th className="px-4 py-2 font-semibold">Matière</th>
                    <th className="px-4 py-2 font-semibold">Dernière activité</th>
                    <th className="px-4 py-2 font-semibold">Mastery</th>
                    <th className="px-4 py-2 font-semibold">Points faibles</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((w) => (
                    <tr
                      key={`${w.subject}/${w.topic}`}
                      className="border-border border-b align-top last:border-0"
                    >
                      <td className="text-foreground px-4 py-2 font-medium">
                        {w.topic}
                      </td>
                      <td className="text-muted-foreground px-4 py-2">
                        {byId.get(w.subject)?.name ?? w.subject}
                      </td>
                      <td className="text-muted-foreground px-4 py-2 font-mono text-[11px]">
                        {fmtDate(w.lastAssessedAt)}
                      </td>
                      <td className="px-4 py-2">
                        <div className="w-32">
                          <ProgressBar value={w.mastery} label={w.topic} />
                        </div>
                      </td>
                      <td className="px-4 py-2">
                        <ul className="space-y-0.5">
                          {w.points.map((p, i) => (
                            <li
                              key={i}
                              className="text-muted-foreground flex items-start gap-1.5"
                            >
                              <span className="text-warning mt-0.5 shrink-0">
                                ⚠
                              </span>
                              {p}
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Surface>
        )}
      </div>
    </>
  );
}
