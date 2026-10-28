import type { AppManifest } from './types';

const apps = new Map<string, AppManifest>();

export function registerApp(app: AppManifest): void {
  if (apps.has(app.id)) throw new Error(`App "${app.id}" registered twice`);
  apps.set(app.id, app);
}

export function getApp(id: string): AppManifest | undefined {
  return apps.get(id);
}

export function listApps(includeHidden = false): AppManifest[] {
  return [...apps.values()].filter((a) => includeHidden || !a.hidden);
}
