import { bus } from './events';
import type { Settings } from './types';

const KEY = 'mwx7:settings';

const defaults: Settings = {
  wallpaper: 'serenity',
  userName: 'User',
  bootSequence: true,
  sounds: true,
  volume: 0.7,
};

// Wallpapers retired in v0.2 → their closest successor.
const RENAMED: Record<string, string> = { aurora: 'wave', meadow: 'serenity' };

let current: Settings = { ...defaults };
try {
  const saved = JSON.parse(localStorage.getItem(KEY) || '{}') as Partial<Settings> & { showBootScreen?: boolean };
  if (saved.wallpaper && RENAMED[saved.wallpaper]) saved.wallpaper = RENAMED[saved.wallpaper];
  if (typeof saved.showBootScreen === 'boolean' && saved.bootSequence === undefined) saved.bootSequence = saved.showBootScreen;
  delete saved.showBootScreen;
  current = { ...defaults, ...saved };
} catch {
  /* keep defaults */
}

export const settings = {
  get(): Settings {
    return { ...current };
  },
  set(patch: Partial<Settings>): void {
    current = { ...current, ...patch };
    try {
      localStorage.setItem(KEY, JSON.stringify(current));
    } catch {
      /* ignore quota errors */
    }
    bus.emit('settings:change', { ...current });
  },
};
