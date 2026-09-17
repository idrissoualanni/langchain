// Thème — préférence utilisateur : clair / sombre / système.
// Persistance localStorage `dsh_theme` ; la classe `.dark` est posée
// sur <html> (voir aussi le script anti-flash dans index.html).
// 'system' suit `prefers-color-scheme` et reste synchronisé.
import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

const LS_THEME = 'dsh_theme';

function readTheme(): Theme {
  try {
    const v = localStorage.getItem(LS_THEME);
    if (v === 'dark' || v === 'light' || v === 'system') return v;
  } catch {
    /* ignore */
  }
  return 'light';
}

function systemPrefersDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function resolveTheme(theme: Theme): ResolvedTheme {
  return theme === 'system'
    ? systemPrefersDark()
      ? 'dark'
      : 'light'
    : theme;
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readTheme);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    resolveTheme(readTheme())
  );

  useEffect(() => {
    const apply = (resolved: ResolvedTheme) => {
      setResolvedTheme(resolved);
      document.documentElement.classList.toggle(
        'dark',
        resolved === 'dark'
      );
    };

    apply(resolveTheme(theme));
    try {
      localStorage.setItem(LS_THEME, theme);
    } catch {
      /* ignore */
    }

    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () =>
      apply(mq.matches ? 'dark' : 'light');
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
  }, []);

  // Bascule rapide clair/sombre (n'altère pas la préférence explicite
  // si elle est 'system' : elle fixe le choix opposé au rendu courant).
  const toggle = useCallback(() => {
    setThemeState((t) => (resolveTheme(t) === 'dark' ? 'light' : 'dark'));
  }, []);

  return { theme, resolvedTheme, setTheme, toggle };
}
