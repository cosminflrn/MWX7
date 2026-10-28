import { bus } from './events';
import type { FileEntry, FileStat, VFS } from './types';

/**
 * VFS v2: an in-memory tree loaded once at boot, written through to IndexedDB.
 * Reads never touch IndexedDB, so apps get the same speed they had with localStorage.
 * If IndexedDB is unavailable (private mode, blocked storage) we keep working in memory only.
 */
const DB_NAME = 'mwx7';
const DB_VERSION = 1;
const STORE = 'nodes';
/** v0.1 kept the whole filesystem as one JSON blob under this key. */
const LEGACY_KEY = 'mwx7:fs';
/** Non-path key marking an initialised install, so deleting every folder never re-triggers first boot. */
const INSTALLED = '#installed';
const DEFAULT_DIRS = ['/Desktop', '/Documents', '/Pictures', '/Music', '/Trash'];

interface Node {
  type: 'file' | 'dir';
  content: string;
  modified: number;
}

const nodes = new Map<string, Node>();
let db: IDBDatabase | null = null;
/** True when this boot found no v2 data and no v0.1 data — the only case that gets Welcome.txt. */
let freshInstall = false;
let ready: Promise<void> | null = null;

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

/* ---------- IndexedDB plumbing ---------- */

function req<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

function openDB(): Promise<IDBDatabase | null> {
  return new Promise((resolve) => {
    let open: IDBOpenDBRequest;
    try {
      if (typeof indexedDB === 'undefined') return resolve(null);
      open = indexedDB.open(DB_NAME, DB_VERSION);
    } catch (err) {
      console.warn('[fs] IndexedDB unavailable, using memory only', err);
      return resolve(null);
    }
    open.onupgradeneeded = () => {
      if (!open.result.objectStoreNames.contains(STORE)) open.result.createObjectStore(STORE);
    };
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => {
      console.warn('[fs] IndexedDB unavailable, using memory only', open.error);
      resolve(null);
    };
    // Another tab holding an old version must not hang the boot.
    open.onblocked = () => resolve(null);
  });
}

/** One transaction per mutation keeps multi-node changes (rename of a folder) atomic on disk. */
function persist(puts: string[], dels: string[] = [], markInstalled = false): Promise<void> {
  if (!db || (!puts.length && !dels.length && !markInstalled)) return Promise.resolve();
  return new Promise((resolve) => {
    try {
      const tx = db!.transaction(STORE, 'readwrite');
      const store = tx.objectStore(STORE);
      for (const p of dels) store.delete(p);
      for (const p of puts) {
        const n = nodes.get(p);
        if (n) store.put(n, p);
      }
      if (markInstalled) store.put(1, INSTALLED);
      tx.oncomplete = () => resolve();
      tx.onerror = tx.onabort = () => {
        console.warn('[fs] could not persist', tx.error);
        resolve();
      };
    } catch (err) {
      console.warn('[fs] could not persist', err);
      resolve();
    }
  });
}

function readLegacy(): string | null {
  try {
    return localStorage.getItem(LEGACY_KEY);
  } catch {
    return null;
  }
}

async function init(): Promise<void> {
  db = await openDB();
  if (db) {
    try {
      const tx = db.transaction(STORE, 'readonly');
      const store = tx.objectStore(STORE);
      const [keys, values] = await Promise.all([req(store.getAllKeys()), req(store.getAll())]);
      let installed = false;
      keys.forEach((k, i) => {
        if (k === INSTALLED) installed = true;
        else nodes.set(String(k), values[i] as Node);
      });
      if (installed) return;
    } catch (err) {
      console.warn('[fs] could not load from IndexedDB, using memory only', err);
      db = null;
    }
  }

  const legacy = readLegacy();
  freshInstall = legacy === null;
  const now = Date.now();
  const touched = new Set<string>();
  for (const d of DEFAULT_DIRS) mkdirSync(d, now, touched);

  if (legacy !== null) {
    let old: Record<string, { content?: unknown; modified?: unknown }> = {};
    try {
      old = JSON.parse(legacy) || {};
    } catch (err) {
      console.warn('[fs] legacy data unreadable, skipping migration', err);
    }
    for (const [p, v] of Object.entries(old)) {
      const path = normalize(p);
      if (path === '/' || nodes.get(path)?.type === 'dir') continue;
      const modified = typeof v?.modified === 'number' ? v.modified : now;
      mkdirSync(dirname(path), modified, touched);
      nodes.set(path, { type: 'file', content: String(v?.content ?? ''), modified });
      touched.add(path);
    }
  }

  await persist([...touched], [], true);
  // Only drop the legacy blob once it is safely in IndexedDB; in memory-only mode it stays the source of truth.
  if (legacy !== null && db) {
    try {
      localStorage.removeItem(LEGACY_KEY);
    } catch {
      /* storage blocked — nothing to clean up */
    }
  }
}

function boot(): Promise<void> {
  return (ready ??= init());
}

/* ---------- tree helpers (synchronous, cache only) ---------- */

function isDir(p: string): boolean {
  return p === '/' || nodes.get(p)?.type === 'dir';
}

/** mkdir -p into the cache; records created paths in `touched`. */
function mkdirSync(path: string, modified: number, touched: Set<string>): void {
  const p = normalize(path);
  if (isDir(p)) return;
  if (nodes.has(p)) throw new Error(`[fs] not a directory: ${p}`);
  mkdirSync(dirname(p), modified, touched);
  nodes.set(p, { type: 'dir', content: '', modified });
  touched.add(p);
}

/** The node itself plus everything below it. */
function subtree(p: string): string[] {
  const prefix = p === '/' ? '/' : p + '/';
  return [...nodes.keys()].filter((k) => k === p || k.startsWith(prefix));
}

function entry(path: string, n: Node): FileEntry {
  return { path, name: basename(path), content: n.content, modified: n.modified, type: n.type };
}

function emit(paths: Iterable<string>): void {
  for (const path of paths) bus.emit('fs:change', { path });
}

const encoder = new TextEncoder();

/* ---------- public API ---------- */

export const fs: VFS = {
  async list(dir) {
    await boot();
    const d = normalize(dir);
    return [...nodes]
      .filter(([p]) => p !== '/' && dirname(p) === d)
      .map(([p, n]) => entry(p, n))
      .sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === 'dir' ? -1 : 1));
  },
  async all() {
    await boot();
    // Files only: Spotlight indexes `.content`, and folders have none.
    return [...nodes].filter(([, n]) => n.type === 'file').map(([p, n]) => entry(p, n));
  },
  async read(path) {
    await boot();
    const n = nodes.get(normalize(path));
    return n?.type === 'file' ? n.content : null;
  },
  async write(path, content) {
    await boot();
    const p = normalize(path);
    if (isDir(p)) throw new Error(`[fs] is a directory: ${p}`);
    const now = Date.now();
    const touched = new Set<string>();
    mkdirSync(dirname(p), now, touched);
    nodes.set(p, { type: 'file', content, modified: now });
    touched.add(p);
    await persist([...touched]);
    emit(touched);
  },
  async remove(path) {
    await boot();
    const p = normalize(path);
    // Never wipe the root; v0.1 also emitted for missing paths, so keep that.
    const gone = p === '/' ? [] : subtree(p);
    for (const k of gone) nodes.delete(k);
    await persist([], gone);
    emit([p]);
  },
  async exists(path) {
    await boot();
    return isDir(normalize(path)) || nodes.has(normalize(path));
  },
  async mkdir(path) {
    await boot();
    const touched = new Set<string>();
    mkdirSync(path, Date.now(), touched);
    await persist([...touched]);
    emit(touched);
  },
  async rename(from, to) {
    await boot();
    const src = normalize(from);
    const dst = normalize(to);
    if (src === dst) return;
    if (src === '/' || !nodes.has(src)) throw new Error(`[fs] no such file or directory: ${src}`);
    if (isDir(dst) || nodes.has(dst)) throw new Error(`[fs] already exists: ${dst}`);
    if (dst.startsWith(src + '/')) throw new Error(`[fs] cannot move ${src} into itself`);
    const touched = new Set<string>();
    mkdirSync(dirname(dst), Date.now(), touched);
    const moved = subtree(src);
    for (const k of moved) {
      const target = dst + k.slice(src.length);
      nodes.set(target, nodes.get(k)!);
      nodes.delete(k);
      touched.add(target);
    }
    await persist([...touched], moved);
    emit([src, ...touched]);
  },
  async move(from, toDir) {
    await fs.rename(from, normalize(toDir) + '/' + basename(from));
  },
  async stat(path): Promise<FileStat | null> {
    await boot();
    const p = normalize(path);
    if (p === '/') return { type: 'dir', modified: 0, size: 0 };
    const n = nodes.get(p);
    if (!n) return null;
    return { type: n.type, modified: n.modified, size: n.type === 'file' ? encoder.encode(n.content).length : 0 };
  },
};

export async function seedFS(): Promise<void> {
  await boot();
  if (!freshInstall) return;
  freshInstall = false;
  await fs.write(
    '/Documents/Welcome.txt',
    [
      'Welcome to MWX 7!',
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
