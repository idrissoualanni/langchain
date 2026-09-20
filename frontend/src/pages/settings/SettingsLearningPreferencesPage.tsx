// /settings/learning — préférences d'apprentissage.
//
// Aucune API de préférences côté backend : on n'affiche donc aucun
// contrôle factice. On expose uniquement ce qui existe réellement.
import { Link } from 'react-router-dom';
import { GraduationCap, SlidersHorizontal } from 'lucide-react';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useLearning } from '../../hooks/useLearning';
import {
  EmptyState,
  PageHeader,
  StatTile,
  Surface,
  SurfaceBody,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';

export function SettingsLearningPreferencesPage() {
  const { internal } = useCurrentUser();
  const { data } = useLearning(internal?.user_id ?? null);

  return (
    <>
      <PageHeader
        eyebrow="settings · learning"
        title="Préférences d’apprentissage"
        description="Réglages pédagogiques de votre compte."
      />

      <div className="max-w-2xl space-y-5 p-6">
        <Surface>
          <SurfaceBody>
            <EmptyState
              icon={SlidersHorizontal}
              title="Aucune préférence d’apprentissage disponible pour le moment."
              description="Le backend n’expose pas encore de réglages pédagogiques modifiables. La progression est pilotée par l’agent pendant vos conversations."
              action={
                <Link
                  to="/learning"
                  className="border-border bg-background hover:bg-muted inline-flex items-center gap-2 rounded-[var(--radius-control)] border px-3 py-1.5 text-[12.5px] font-medium"
                >
                  <GraduationCap size={13} /> Voir ma progression
                </Link>
              }
            />
          </SurfaceBody>
        </Surface>

        {(data.subjectCount > 0 || data.goals.length > 0) && (
          <Surface>
            <SurfaceHeader>
              <SurfaceTitle>Données disponibles</SurfaceTitle>
            </SurfaceHeader>
            <SurfaceBody className="grid grid-cols-2 gap-3">
              <StatTile label="matières suivies" value={data.subjectCount} />
              <StatTile label="objectifs" value={data.goals.length} />
            </SurfaceBody>
          </Surface>
        )}
      </div>
    </>
  );
}
