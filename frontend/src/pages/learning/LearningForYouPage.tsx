// /learning/for-you — préparé pour les futures recommandations.
//
// Aucun endpoint backend ne fournit de flux de recommandations : on
// n'en invente donc pas. La page expose les données réelles (profil
// d'apprentissage, points faibles, matières suivies) et affiche un
// état vide explicite pour la partie recommandations.
import { Link } from 'react-router-dom';
import { MessageSquare, Sparkles } from 'lucide-react';
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

export function LearningForYouPage() {
  const { internal } = useCurrentUser();
  const { data } = useLearning(internal?.user_id ?? null);
  const { byId } = useSubjects();

  const focus = data.weakPoints.slice(0, 5);

  return (
    <>
      <PageHeader
        eyebrow="learning · for you"
        title="For You"
        description="Espace réservé aux futures recommandations du Learning Engine."
      />

      <div className="space-y-5 p-6">
        <Surface>
          <SurfaceBody>
            <EmptyState
              icon={Sparkles}
              title="Aucune recommandation disponible pour le moment."
              description="Le flux de recommandations n’est pas encore exposé par le backend. En attendant, voici ce que vos données réelles indiquent."
              action={
                <Link
                  to="/assistant"
                  className="border-border bg-background hover:bg-muted inline-flex items-center gap-2 rounded-[var(--radius-control)] border px-3 py-1.5 text-[12.5px] font-medium"
                >
                  <MessageSquare size={13} /> Demander une séance à l’assistant
                </Link>
              }
            />
          </SurfaceBody>
        </Surface>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Surface>
            <SurfaceHeader>
              <SurfaceTitle>À prioriser</SurfaceTitle>
              <span className="text-muted-foreground font-mono text-[10px]">
                points faibles enregistrés
              </span>
            </SurfaceHeader>
            <SurfaceBody className="space-y-2">
              {focus.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  Aucune donnée disponible pour le moment.
                </p>
              ) : (
                focus.map((w) => (
                  <div key={`${w.subject}/${w.topic}`} className="py-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-foreground truncate text-[12.5px] font-medium">
                        {w.topic}
                      </span>
                      <span className="text-muted-foreground font-mono text-[10px]">
                        {byId.get(w.subject)?.name ?? w.subject}
                      </span>
                    </div>
                    <div className="mt-1.5">
                      <ProgressBar value={w.mastery} label={w.topic} />
                    </div>
                  </div>
                ))
              )}
            </SurfaceBody>
          </Surface>

          <Surface>
            <SurfaceHeader>
              <SurfaceTitle>Activités disponibles</SurfaceTitle>
            </SurfaceHeader>
            <SurfaceBody className="space-y-2">
              {data.observations.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  Aucune activité enregistrée pour le moment.
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
