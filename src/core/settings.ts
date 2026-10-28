import { bus } from './events';
import type { Settings } from './types';

const KEY = 'mwx7:settings';

const defaults: Settings = {
  wallpaper: 'aurora',
  userName: 'User',
  showBootScreen: true,
};

let current: Settings = { ...defaults };
try {
  current = { ...defaults, ...JSON.parse(localStorage.getItem(KEY) || '{}') };
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
