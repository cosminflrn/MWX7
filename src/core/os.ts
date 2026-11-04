import { bus } from './events';
import { fs } from './fs';
import { getApp, listApps } from './registry';
import { settings } from './settings';
import type { MenuItem, OSApi } from './types';
import { allWindows, closeWindow, focusWindow, openWindow, windowsOf } from './wm';

export function notify(title: string, body?: string, icon?: string): void {
  bus.emit('notify', { title, body, icon });
}

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
  openWindow(app, (win) => app.mount({ win, args, fs, os }));
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
};
