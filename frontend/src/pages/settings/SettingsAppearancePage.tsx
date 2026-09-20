// /settings/appearance — Light / Dark / System via le thème existant.
import { Check, Monitor, Moon, Sun } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTheme, type Theme } from '../../hooks/useTheme';
import { PageHeader, Surface, SurfaceBody } from '../../components/user/kit';
import { cn } from '../../lib/utils';

const OPTIONS: {
  value: Theme;
  label: string;
  description: string;
  icon: LucideIcon;
}[] = [
  {
    value: 'light',
    label: 'Clair',
    description: 'Papier glacé, encre foncée.',
    icon: Sun,
  },
  {
    value: 'dark',
    label: 'Sombre',
    description: 'Encre profonde, texte clair.',
    icon: Moon,
  },
  {
    value: 'system',
    label: 'Système',
    description: 'Suit les préférences de votre appareil.',
    icon: Monitor,
  },
];

export function SettingsAppearancePage() {
  const { theme, resolvedTheme, setTheme } = useTheme();

  return (
    <>
      <PageHeader
        eyebrow="settings · appearance"
        title="Apparence"
        description="Choisissez le thème de l’application. Le thème clair/sombre existe déjà — cette page l’expose."
      />

      <div className="max-w-2xl p-6">
        <Surface>
          <SurfaceBody className="space-y-2">
            {OPTIONS.map(({ value, label, description, icon: Icon }) => {
              const active = theme === value;
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setTheme(value)}
                  className={cn(
                    'border-border flex w-full items-center gap-3 rounded-[var(--radius-control)] border px-3 py-3 text-left transition-colors',
                    active
                      ? 'bg-muted'
                      : 'hover:bg-muted/50'
                  )}
                >
                  <Icon
                    size={16}
                    strokeWidth={1.8}
                    className="text-muted-foreground shrink-0"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="text-foreground block text-[13px] font-medium">
                      {label}
                    </span>
                    <span className="text-muted-foreground block text-[12px]">
                      {description}
                    </span>
                  </span>
                  {value === 'system' && (
                    <span className="text-muted-foreground font-mono text-[10px]">
                      {resolvedTheme}
                    </span>
                  )}
                  {active && (
                    <Check size={15} className="text-live shrink-0" />
                  )}
                </button>
              );
            })}
          </SurfaceBody>
        </Surface>
      </div>
    </>
  );
}
