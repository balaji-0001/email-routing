// The look of the app: a light one, the glass design ("Custom"), or a dark one.
// The choice is a per-browser convenience, so it lives in this browser's storage.
import { useEffect, useState } from 'react';
import { Moon, Sparkles, Sun, type LucideIcon } from 'lucide-react';

export type Theme = 'light' | 'dark' | 'current';

const KEY = 'theme';
const THEMES: { value: Theme; label: string; icon: LucideIcon }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  // The glass design. Stored as 'current', the name it had first, so earlier choices still apply.
  { value: 'current', label: 'Custom', icon: Sparkles },
  { value: 'dark', label: 'Dark', icon: Moon },
];
const listeners = new Set<(theme: Theme) => void>();

function storedTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark' || saved === 'current') return saved;
  } catch {
    // Storage can be blocked; the default look still works.
  }
  return 'current';
}

/** Put the look on the page. Called once before the app draws, so there is no flash of the wrong one. */
export function applyTheme(theme: Theme = storedTheme()) {
  document.documentElement.dataset.theme = theme;
}

function setTheme(theme: Theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Not remembered for next time, but applied now.
  }
  applyTheme(theme);
  listeners.forEach((listener) => listener(theme));
}

function useTheme(): Theme {
  const [theme, set] = useState<Theme>(storedTheme);
  useEffect(() => {
    listeners.add(set);
    return () => { listeners.delete(set); };
  }, []);
  return theme;
}

export function ThemePicker() {
  const theme = useTheme();
  return (
    <div className="theme-picker" role="radiogroup" aria-label="Appearance" data-testid="theme-picker">
      {THEMES.map(({ value, label, icon: Icon }) => (
        <button key={value} type="button" role="radio" aria-checked={theme === value} className={theme === value ? 'picked' : ''} onClick={() => setTheme(value)} data-testid={`theme-${value}`}>
          <Icon size={15} /> {label}
        </button>
      ))}
    </div>
  );
}
