import { bus } from './events';
import { fs } from './fs';
import { getApp, listApps } from './registry';
import { settings } from './settings';
import type { MenuItem, OSApi } from './types';
import { allWindows, closeWindow, focusWindow, openWindow, windowsOf } from './wm';

export function notify(title: string, body?: string, icon?: string): void {
  bus.emit('notify', { title, body, icon });
}

/** Session-only "Recent" files per app (newest first), shown in the dock jump list. */
const recents = new Map<string, string[]>();
const MAX_RECENT = 8;
export function addRecent(appId: string, path: string): void {
  if (!path || path === '/') return;
  const list = (recents.get(appId) ?? []).filter((p) => p !== path);
  list.unshift(path);
  recents.set(appId, list.slice(0, MAX_RECENT));
}
export const recentOf = (appId: string): string[] => [...(recents.get(appId) ?? [])];

export function launch(appId: string, args: Record<string, unknown> = {}): void {
  const app = getApp(appId);
  if (!app) {
    notify('Application not found', `No app with id "${appId}".`);
    return;
  }
  if (app.singleInstance) {
    const existing = windowsOf(appId)[0];
    if (existing) {
      focusWindow(existing.id);
      return;
    }
  }
  // Opening a file through launch (Explorer, jump list, Search) counts as recent for that app.
  if (typeof args.path === 'string' && args.path) addRecent(appId, args.path);
  openWindow(app, (win) => app.mount({ win, args, fs, os: { ...os, addRecent: (p: string) => addRecent(appId, p) } }));
}

const jumpLists = new Map<string, () => MenuItem[]>();
/** Dock reads this when building an app's right-click menu. */
export const getJumpList = (appId: string): MenuItem[] => jumpLists.get(appId)?.() ?? [];

export const os: OSApi = {
  setJumpList: (appId, provider) => void (provider ? jumpLists.set(appId, provider) : jumpLists.delete(appId)),
  launch,
  notify,
  apps: () => listApps(),
  windows: () =>
    allWindows()
      .sort((a, b) => a.z - b.z)
      .map((w) => ({ id: w.id, title: w.title, appId: w.appId, minimized: w.minimized })),
  focusWindow,
  closeWindow,
  settings,
  addRecent: () => {}, // apps get a per-app version bound in launch()
};
