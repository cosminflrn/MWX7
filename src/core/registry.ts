import type { AppManifest } from './types';

const apps = new Map<string, AppManifest>();

/**
 * Icons that carry their own <defs> become <img> data URIs: inline SVGs share
 * one id namespace, and a gradient defined inside a hidden copy (a minimized
 * window's title bar) stops rendering everywhere else.
 */
export function toIconImg(markup: string): string {
  if (!markup.trim().startsWith('<svg') || !markup.includes('<defs')) return markup;
  const svg = markup.includes('xmlns=') ? markup : markup.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
  return `<img class="icon-img" alt="" draggable="false" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}">`;
}

export function registerApp(app: AppManifest): void {
  if (apps.has(app.id)) throw new Error(`App "${app.id}" registered twice`);
  apps.set(app.id, { ...app, icon: toIconImg(app.icon) });
}

export function getApp(id: string): AppManifest | undefined {
  return apps.get(id);
}

export function listApps(includeHidden = false): AppManifest[] {
  return [...apps.values()].filter((a) => includeHidden || !a.hidden);
}
