// Layout /settings — navigation secondaire + <Outlet/>.
import { Outlet } from 'react-router-dom';
import { SectionNav } from '../../components/user/kit';

// Onglets §34 : Profil / Préférences pédagogiques / Mémoire / Modèle /
// Notifications / Sessions (+ Appearance & Data existants).
const NAV = [
  { to: '/settings/profile', label: 'Profile' },
  { to: '/settings/appearance', label: 'Appearance' },
  { to: '/settings/learning', label: 'Learning Preferences' },
  { to: '/settings/memory', label: 'Memory' },
  { to: '/settings/model', label: 'Modèle' },
  { to: '/settings/notifications', label: 'Notifications' },
  { to: '/settings/sessions', label: 'Sessions' },
  { to: '/settings/data', label: 'Data & Privacy' },
];

export function SettingsLayout() {
  return (
    <div className="flex h-full flex-col">
      <SectionNav items={NAV} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Outlet />
      </div>
    </div>
  );
}
