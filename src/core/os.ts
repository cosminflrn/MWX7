import { bus } from './events';
import { fs } from './fs';
import { getApp, listApps } from './registry';
import { settings } from './settings';
import type { OSApi } from './types';
import { focusWindow, openWindow, windowsOf } from './wm';

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

export const os: OSApi = {
  launch,
  notify,
  apps: () => listApps(),
  settings,
};
