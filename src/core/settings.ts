import { bus } from './events';
import type { Settings } from './types';

/**
 * Settings live in memory only: by design MWX 7 remembers nothing between
 * sessions — every reload is a fresh machine that goes through setup again.
 */
const defaults: Settings = {
  wallpaper: 'meadow',
  userName: 'User',
  avatar: '',
  bootSequence: true,
  sounds: true,
  volume: 0.8,
};

let current: Settings = { ...defaults };

export const settings = {
  get(): Settings {
    return { ...current };
  },
  set(patch: Partial<Settings>): void {
    current = { ...current, ...patch };
    bus.emit('settings:change', { ...current });
  },
};

/** Wipe anything older versions persisted, so the browser keeps nothing from MWX 7. */
export function forgetPersistedData(): void {
  try {
    Object.keys(localStorage)
      .filter((k) => k.startsWith('mwx7:'))
      .forEach((k) => localStorage.removeItem(k));
  } catch {
    /* storage blocked */
  }
  try {
    indexedDB.deleteDatabase('mwx7');
  } catch {
    /* not available */
  }
}
