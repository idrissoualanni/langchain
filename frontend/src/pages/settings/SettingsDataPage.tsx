// /settings/data — transparence sur les données stockées.
// Aucune action fictive (pas d'export/suppression non supportés).
import { Link } from 'react-router-dom';
import { Database, ExternalLink, ShieldCheck } from 'lucide-react';
import {
  KeyValue,
  PageHeader,
  Surface,
  SurfaceBody,
  SurfaceHeader,
  SurfaceTitle,
} from '../../components/user/kit';

export function SettingsDataPage() {
  return (
    <>
      <PageHeader
        eyebrow="settings · data & privacy"
        title="Données et confidentialité"
        description="Ce que l’application stocke et où. Aucune action non supportée n’est proposée ici."
      />

      <div className="max-w-3xl space-y-5 p-6">
        <Surface>
          <SurfaceHeader>
            <SurfaceTitle className="flex items-center gap-2">
              <Database size={13} /> Données applicatives
            </SurfaceTitle>
          </SurfaceHeader>
          <SurfaceBody className="divide-border divide-y">
            <KeyValue
              label="Conversations"
              value="Threads et messages (backend LangGraph)"
            />
            <KeyValue
              label="Mémoire longue durée"
              value="Profil et souvenirs par catégorie"
            />
            <KeyValue
              label="Profil d’apprentissage"
              value="Mastery, objectifs et observations"
            />
            <KeyValue
              label="Historique des activités"
              value="50 observations les plus récentes"
            />
          </SurfaceBody>
        </Surface>

        <Surface>
          <SurfaceHeader>
            <SurfaceTitle className="flex items-center gap-2">
              <ShieldCheck size={13} /> Identité et confidentialité
            </SurfaceTitle>
          </SurfaceHeader>
          <SurfaceBody className="space-y-2">
            <p className="text-muted-foreground text-sm">
              L’identité (nom, email) est fournie par Clerk. Le backend
              ne stocke pas votre email : il ne conserve que les données
              nécessaires à l’application.
            </p>
            <p className="text-muted-foreground text-sm">
              La suppression d’une conversation est disponible directement
              depuis le menu de chaque conversation dans la barre latérale.
            </p>
          </SurfaceBody>
        </Surface>

        <Surface>
          <SurfaceHeader>
            <SurfaceTitle>Gérer vos données</SurfaceTitle>
          </SurfaceHeader>
          <SurfaceBody className="flex flex-wrap gap-2">
            <Link
              to="/settings/memory"
              className="border-border bg-background hover:bg-muted inline-flex items-center gap-2 rounded-[var(--radius-control)] border px-3 py-1.5 text-[12.5px] font-medium"
            >
              <Database size={13} /> Mémoire
            </Link>
            <Link
              to="/memory"
              className="border-border bg-background hover:bg-muted inline-flex items-center gap-2 rounded-[var(--radius-control)] border px-3 py-1.5 text-[12.5px] font-medium"
            >
              <ExternalLink size={13} /> Éditeur mémoire complet
            </Link>
          </SurfaceBody>
        </Surface>
      </div>
    </>
  );
}
