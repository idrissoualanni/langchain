// /profile — identité (Neon Auth) + données applicatives (backend) +
// résumé d'apprentissage. Le backend reste la source de vérité des
// données applicatives ; Neon Auth reste la source d'identité.
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CalendarDays,
  GraduationCap,
  IdCard,
  Mail,
  Settings as SettingsIcon,
  User as UserIcon,
} from 'lucide-react';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { useLearning } from '../hooks/useLearning';
import { getUserProfile } from '../api/memory';
import type { UserProfile } from '../types/agent';
import {
  EmptyState,
  KeyValue,
  PageHeader,
  ProgressBar,
  StatTile,
  Surface,
  SurfaceBody,
  SurfaceHeader,
  SurfaceTitle,
} from '../components/user/kit';

function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('fr-FR');
}

function Avatar({
  imageUrl,
  name,
}: {
  imageUrl?: string | null;
  name: string;
}) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('');
  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt=""
        className="border-border size-16 shrink-0 rounded-full border object-cover"
      />
    );
  }
  return (
    <div className="bg-muted text-foreground border-border flex size-16 shrink-0 items-center justify-center rounded-full border text-lg font-semibold">
      {initials || <UserIcon size={22} />}
    </div>
  );
}

export function ProfilePage() {
  const { internal, neonUser, devMode } = useCurrentUser();
  const userId = internal?.user_id ?? null;
  const { data } = useLearning(userId);

  const [profile, setProfile] = useState<UserProfile | null>(null);

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    getUserProfile(userId)
      .then((p) => {
        if (alive) setProfile(p);
      })
      .catch(() => {
        if (alive) setProfile(null);
      });
    return () => {
      alive = false;
    };
  }, [userId]);

  const displayName = internal?.name || neonUser?.name || 'Utilisateur';
  const email = neonUser?.email ?? null;
  const imageUrl = null;

  return (
    <>
      <PageHeader
        eyebrow="profil"
        title="Profil"
        description="Vos informations d’identité et le résumé de votre activité."
        actions={
          <Link
            to="/settings/profile"
            className="border-border bg-background hover:bg-muted inline-flex items-center gap-2 rounded-[var(--radius-control)] border px-3 py-1.5 text-[12.5px] font-medium"
          >
            <SettingsIcon size={13} /> Modifier
          </Link>
        }
      />

      <div className="space-y-5 p-6">
        {/* En-tête identité */}
        <Surface>
          <SurfaceBody className="flex items-center gap-4">
            <Avatar imageUrl={imageUrl} name={displayName} />
            <div className="min-w-0">
              <div className="text-foreground truncate text-lg font-semibold tracking-tight">
                {displayName}
              </div>
              {email ? (
                <div className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-[12.5px]">
                  <Mail size={12} /> {email}
                </div>
              ) : (
                <div className="text-muted-foreground mt-0.5 text-[12px]">
                  Email non disponible (mode {devMode ? 'dev' : 'Neon Auth'}).
                </div>
              )}
            </div>
          </SurfaceBody>
        </Surface>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* Informations personnelles */}
          <Surface>
            <SurfaceHeader>
              <SurfaceTitle className="flex items-center gap-2">
                <IdCard size={13} /> Informations personnelles
              </SurfaceTitle>
            </SurfaceHeader>
            <SurfaceBody className="divide-border divide-y">
              <KeyValue
                label="Prénom"
                value={internal?.name?.split(/\s+/)[0] ?? '—'}
              />
              <KeyValue
                label="Nom"
                value={internal?.name?.split(/\s+/).slice(1).join(' ') ?? '—'}
              />
              <KeyValue label="Email" value={email ?? '—'} />
              <KeyValue
                label="Bio"
                value={profile?.description || '—'}
              />
            </SurfaceBody>
          </Surface>

          {/* Informations de compte */}
          <Surface>
            <SurfaceHeader>
              <SurfaceTitle className="flex items-center gap-2">
                <CalendarDays size={13} /> Informations de compte
              </SurfaceTitle>
            </SurfaceHeader>
            <SurfaceBody className="divide-border divide-y">
              <KeyValue
                label="Identifiant"
                value={internal?.user_id ?? '—'}
                mono
              />
              <KeyValue label="Rôle" value={internal?.role ?? 'user'} />
              <KeyValue
                label="Membre depuis"
                value={fmtDate(internal?.created_at)}
              />
              <KeyValue
                label="Fournisseur d’identité"
                value={devMode ? 'dev (session locale)' : 'Neon Auth'}
              />
            </SurfaceBody>
          </Surface>
        </div>

        {/* Résumé d'apprentissage */}
        <Surface>
          <SurfaceHeader>
            <SurfaceTitle className="flex items-center gap-2">
              <GraduationCap size={13} /> Résumé d’apprentissage
            </SurfaceTitle>
            <Link
              to="/learning"
              className="text-muted-foreground hover:text-foreground text-xs"
            >
              Voir le détail
            </Link>
          </SurfaceHeader>
          <SurfaceBody>
            {data.subjectCount === 0 && data.goals.length === 0 ? (
              <EmptyState
                icon={GraduationCap}
                title="Aucune donnée disponible pour le moment."
                description="Aucune progression d’apprentissage n’est encore enregistrée."
              />
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                  <StatTile
                    label="matières suivies"
                    value={data.subjectCount}
                  />
                  <StatTile label="topics suivis" value={data.topicCount} />
                  <StatTile label="objectifs" value={data.goals.length} />
                </div>
                <div className="space-y-2">
                  {data.subjects.slice(0, 4).map((s) => (
                    <div key={s.id} className="space-y-1">
                      <span className="text-foreground text-[12.5px] font-medium">
                        {s.id}
                      </span>
                      <ProgressBar value={s.mastery} label={s.id} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </SurfaceBody>
        </Surface>
      </div>
    </>
  );
}
