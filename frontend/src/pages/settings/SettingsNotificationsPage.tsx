// /settings/notifications — aucune API de notifications côté backend :
// aucun contrôle factice n'est affiché.
import { BellOff } from 'lucide-react';
import { EmptyState, PageHeader, Surface, SurfaceBody } from '../../components/user/kit';

export function SettingsNotificationsPage() {
  return (
    <>
      <PageHeader
        eyebrow="settings · notifications"
        title="Notifications"
        description="Préférences de notification de votre compte."
      />

      <div className="max-w-2xl p-6">
        <Surface>
          <SurfaceBody>
            <EmptyState
              icon={BellOff}
              title="Aucune préférence de notification disponible pour le moment."
              description="Le backend n’expose pas encore de réglages de notification. Aucun contrôle n’est affiché tant que ce n’est pas réellement supporté."
            />
          </SurfaceBody>
        </Surface>
      </div>
    </>
  );
}
