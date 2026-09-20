// Layout /learning — navigation secondaire + <Outlet/>.
// Chaque page porte son propre en-tête (PageHeader).
import { Outlet } from 'react-router-dom';
import { SectionNav } from '../../components/user/kit';

const NAV = [
  { to: '/learning', label: 'Overview', end: true },
  { to: '/learning/progress', label: 'Progression' },
  { to: '/learning/subjects', label: 'Subjects' },
  { to: '/learning/topics', label: 'Topics' },
  { to: '/learning/goals', label: 'Goals' },
  { to: '/learning/reviews', label: 'Reviews' },
  { to: '/learning/history', label: 'History' },
  { to: '/learning/for-you', label: 'For You' },
];

export function LearningLayout() {
  return (
    <div className="flex h-full flex-col">
      <SectionNav items={NAV} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Outlet />
      </div>
    </div>
  );
}
