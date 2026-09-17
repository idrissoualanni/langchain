// /learning/history — historique pédagogique (backend, pas localStorage).
import { History } from 'lucide-react';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useLearning } from '../../hooks/useLearning';
import { useSubjects } from '../../hooks/useSubjects';
import {
  EmptyState,
  PageHeader,
  Pill,
  Surface,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString('fr-FR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
}

export function LearningHistoryPage() {
  const { internal } = useCurrentUser();
  const { data, loading } = useLearning(internal?.user_id ?? null);
  const { byId } = useSubjects();

  const rows = data.observations;

  return (
    <>
      <PageHeader
        eyebrow="learning · history"
        title="Historique"
        description="Activités pédagogiques réellement enregistrées par l’agent (50 plus récentes)."
      />

      <div className="p-6">
        {loading && rows.length === 0 ? (
          <Surface>
            <EmptyState icon={History} title="Chargement…" />
          </Surface>
        ) : rows.length === 0 ? (
          <Surface>
            <EmptyState
              icon={History}
              title="Aucune donnée disponible pour le moment."
              description="Aucune activité pédagogique n’a encore été enregistrée."
            />
          </Surface>
        ) : (
          <Surface>
            <SurfaceHeader>
              <SurfaceTitle>Activités</SurfaceTitle>
              <span className="text-muted-foreground font-mono text-[10px]">
                {rows.length} entrée{rows.length > 1 ? 's' : ''}
              </span>
            </SurfaceHeader>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-[12.5px]">
                <thead>
                  <tr className="text-muted-foreground border-border border-b font-mono text-[10px] uppercase">
                    <th className="px-4 py-2 font-semibold">Date</th>
                    <th className="px-4 py-2 font-semibold">Matière</th>
                    <th className="px-4 py-2 font-semibold">Topic</th>
                    <th className="px-4 py-2 font-semibold">Activité</th>
                    <th className="px-4 py-2 font-semibold">Résultat</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((o, i) => {
                    const result =
                      o.score !== null
                        ? `${Math.round(o.score * 100)}%`
                        : [
                            ...o.strengths.map((s) => `+ ${s}`),
                            ...o.weak_points.map((w) => `− ${w}`),
                          ].join(' · ') || '—';
                    return (
                      <tr
                        key={i}
                        className="border-border border-b align-top last:border-0"
                      >
                        <td className="text-muted-foreground px-4 py-2 font-mono text-[11px] whitespace-nowrap">
                          {fmtDateTime(o.created_at)}
                        </td>
                        <td className="text-muted-foreground px-4 py-2">
                          {byId.get(o.subject)?.name ?? o.subject}
                        </td>
                        <td className="text-foreground px-4 py-2 font-medium">
                          {o.topic}
                        </td>
                        <td className="px-4 py-2">
                          <Pill tone="live">{o.type}</Pill>
                        </td>
                        <td className="text-foreground px-4 py-2">{result}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Surface>
        )}
      </div>
    </>
  );
}
