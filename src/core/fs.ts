import { bus } from './events';
import type { FileEntry, VFS } from './types';

/**
 * Phase-1 VFS backed by localStorage. The API is async on purpose so it can be
 * swapped for IndexedDB later without touching any app.
 */
const KEY = 'mwx7:fs';

type Store = Record<string, { content: string; modified: number }>;

function load(): Store {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}') as Store;
  } catch {
    return {};
  }
}

function save(store: Store): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(store));
  } catch (err) {
    console.warn('[fs] could not persist', err);
  }
}

export function normalize(path: string): string {
  const parts = path.split('/').filter((p) => p && p !== '.');
  return '/' + parts.join('/');
}

export function basename(path: string): string {
  return normalize(path).split('/').pop() || '';
}

export function dirname(path: string): string {
  const parts = normalize(path).split('/');
  parts.pop();
  return parts.join('/') || '/';
}

function entry(path: string, v: { content: string; modified: number }): FileEntry {
  return { path, name: basename(path), content: v.content, modified: v.modified };
}

export const fs: VFS = {
  async list(dir) {
    const d = normalize(dir);
    const store = load();
    return Object.entries(store)
      .filter(([p]) => dirname(p) === d)
      .map(([p, v]) => entry(p, v))
      .sort((a, b) => a.name.localeCompare(b.name));
  },
  async all() {
    return Object.entries(load()).map(([p, v]) => entry(p, v));
  },
  async read(path) {
    return load()[normalize(path)]?.content ?? null;
  },
  async write(path, content) {
    const p = normalize(path);
    const store = load();
    store[p] = { content, modified: Date.now() };
    save(store);
    bus.emit('fs:change', { path: p });
  },
  async remove(path) {
    const p = normalize(path);
    const store = load();
    delete store[p];
    save(store);
    bus.emit('fs:change', { path: p });
  },
  async exists(path) {
    return normalize(path) in load();
  },
};

export async function seedFS(): Promise<void> {
  if (localStorage.getItem(KEY)) return;
  await fs.write(
    '/Documents/Welcome.txt',
    [
      'Welcome to MWX7!',
      '',
      'The dream desktop: the polish of macOS, the warmth of Windows XP',
      'and the glass of Windows 7 — all in one browser tab.',
      '',
      'Tips',
      '  • Ctrl+Space opens Spotlight search.',
      '  • Drag a window to the left/right edge to snap it, or to the top to maximize.',
      '  • Double-click a title bar to maximize.',
      '  • Right-click the desktop or a dock icon for more options.',
      '',
      'Everything you save lives in this browser only.',
    ].join('\n'),
  );
}
