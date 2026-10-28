import { bus } from '../core/events';
import { launch } from '../core/os';
import { listApps } from '../core/registry';
import { settings } from '../core/settings';
import { h } from '../ui/dom';
import { openMenu } from '../ui/menu';
import { mountAmbience } from './ambience';
import { createWallpaperLayer, resolveWallpaperId, wallpapers } from './wallpapers';

/** Wallpaper + XP-style desktop icons (left column) + desktop context menu. */
export function mountDesktop(desktop: HTMLElement, iconLayer: HTMLElement): void {
  // Live wallpaper: the first child of #desktop, so icons and windows paint above it.
  let wallId = resolveWallpaperId(settings.get().wallpaper);
  let wall = createWallpaperLayer(wallId);
  desktop.prepend(wall.el);
  // Rewrite retired ids once so the Settings picker highlights the wallpaper actually showing.
  if (settings.get().wallpaper !== wallId) settings.set({ wallpaper: wallId });
  bus.on('settings:change', (s) => {
    const next = resolveWallpaperId(s.wallpaper);
    if (next === wallId) return;
    wallId = next;
    const old = wall;
    const fresh = (wall = createWallpaperLayer(next));
    fresh.el.classList.add('wp-enter');
    old.el.after(fresh.el);
    // Two frames so the starting opacity is committed before the transition begins.
    requestAnimationFrame(() => requestAnimationFrame(() => fresh.el.classList.add('wp-in')));
    window.setTimeout(() => old.destroy(), 650);
  });
  mountAmbience();

  const select = (el: HTMLElement | null) => {
    iconLayer.querySelectorAll('.desk-icon.selected').forEach((n) => n.classList.remove('selected'));
    el?.classList.add('selected');
  };

  for (const app of listApps().filter((a) => a.desktop)) {
    const icon = h(
      'button',
      {
        class: 'desk-icon',
        title: app.description ?? app.name,
        onclick: (e: MouseEvent) => {
          e.stopPropagation();
          select(e.currentTarget as HTMLElement);
        },
        ondblclick: () => launch(app.id),
        onkeydown: (e: KeyboardEvent) => {
          if (e.key === 'Enter') launch(app.id);
        },
      },
      h('span', { class: 'desk-icon-img', html: app.icon }),
      h('span', { class: 'desk-icon-label' }, app.name),
    );
    iconLayer.append(icon);
  }

  desktop.addEventListener('pointerdown', (e) => {
    if (e.target === desktop || e.target === iconLayer) select(null);
  });

  desktop.addEventListener('contextmenu', (e) => {
    if (e.target !== desktop && e.target !== iconLayer) return;
    e.preventDefault();
    const current = resolveWallpaperId(settings.get().wallpaper);
    const idx = wallpapers.findIndex((w) => w.id === current);
    openMenu(
      [
        { label: 'Next Wallpaper', action: () => settings.set({ wallpaper: wallpapers[(idx + 1) % wallpapers.length].id }) },
        { label: 'Personalize…', action: () => launch('settings') },
        { separator: true },
        { label: 'New Text Document', action: () => launch('notepad') },
        { separator: true },
        { label: 'About MWX 7', action: () => launch('about') },
      ],
      { x: e.clientX, y: e.clientY },
    );
  });
}
