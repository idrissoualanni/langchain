// /settings/profile — informations modifiables réellement supportées.
//
// Le backend accepte PUT /api/users/{id}/profile avec { name, description }.
// Le nom Clerk (identité) n'est PAS modifiable ici : il est géré par Clerk.
import { useEffect, useState } from 'react';
import { Check, Loader2, Save } from 'lucide-react';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { getUserProfile, updateUserProfile } from '../../api/memory';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import {
  PageHeader,
  Surface,
  SurfaceBody,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';

export function SettingsProfilePage() {
  const { internal, clerkUser, devMode } = useCurrentUser();
  const userId = internal?.user_id ?? null;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    setLoading(true);
    getUserProfile(userId)
      .then((p) => {
        if (!alive) return;
        setName(p.name ?? '');
        setDescription(p.description ?? '');
      })
      .catch(() => {
        /* profil vide : champs vides */
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [userId]);

  const onSave = async () => {
    if (!userId) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const updated = await updateUserProfile(userId, {
        name: name.trim() || undefined,
        description: description.trim() || undefined,
      });
      setName(updated.name ?? '');
      setDescription(updated.description ?? '');
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Enregistrement impossible');
    } finally {
      setSaving(false);
    }
  };

  const clerkName =
    clerkUser?.fullName ||
    [clerkUser?.firstName, clerkUser?.lastName].filter(Boolean).join(' ');

  return (
    <>
      <PageHeader
        eyebrow="settings · profile"
        title="Profil"
        description="Gérez les informations que l’application peut réellement enregistrer."
      />

      <div className="max-w-2xl space-y-5 p-6">
        <Surface>
          <SurfaceHeader>
            <SurfaceTitle>Identité (gérée par Clerk)</SurfaceTitle>
          </SurfaceHeader>
          <SurfaceBody className="space-y-1">
            <p className="text-foreground text-sm">
              {clerkName || internal?.name || '—'}
            </p>
            <p className="text-muted-foreground text-[12px]">
              {clerkUser?.primaryEmailAddress?.emailAddress ??
                (devMode
                  ? 'Email non disponible en mode dev.'
                  : 'Email non disponible.')}
            </p>
            <p className="text-muted-foreground/70 text-[11.5px]">
              Le nom et l’email d’identité ne sont pas modifiables depuis
              cette page.
            </p>
          </SurfaceBody>
        </Surface>

        <Surface>
          <SurfaceHeader>
            <SurfaceTitle>Profil applicatif</SurfaceTitle>
          </SurfaceHeader>
          <SurfaceBody className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="profile-name"
                className="text-foreground text-[12.5px] font-medium"
              >
                Nom affiché
              </label>
              <Input
                id="profile-name"
                value={name}
                disabled={loading || !userId}
                maxLength={200}
                placeholder="Votre nom"
                onChange={(e) => {
                  setName(e.target.value);
                  setSaved(false);
                }}
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="profile-description"
                className="text-foreground text-[12.5px] font-medium"
              >
                Description
              </label>
              <Textarea
                id="profile-description"
                value={description}
                disabled={loading || !userId}
                maxLength={2000}
                rows={4}
                placeholder="Quelques mots sur vous, vos objectifs…"
                onChange={(e) => {
                  setDescription(e.target.value);
                  setSaved(false);
                }}
              />
            </div>

            {error && (
              <p className="text-destructive text-[12.5px]">{error}</p>
            )}

            <div className="flex items-center gap-3">
              <Button
                onClick={() => void onSave()}
                disabled={saving || loading || !userId}
                size="sm"
              >
                {saving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Save size={14} />
                )}
                Enregistrer
              </Button>
              {saved && (
                <span className="text-success flex items-center gap-1 text-[12.5px]">
                  <Check size={13} /> Enregistré
                </span>
              )}
            </div>
          </SurfaceBody>
        </Surface>
      </div>
    </>
  );
}
