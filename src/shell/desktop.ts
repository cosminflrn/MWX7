import { bus } from '../core/events';
import { launch } from '../core/os';
import { listApps } from '../core/registry';
import { settings } from '../core/settings';
import { h } from '../ui/dom';
import { openMenu } from '../ui/menu';
import { wallpaperBackground, wallpapers } from './wallpapers';

/** Wallpaper + XP-style desktop icons (left column) + desktop context menu. */
export function mountDesktop(desktop: HTMLElement, iconLayer: HTMLElement): void {
  let current = '';
  let token = 0;
  const applyWallpaper = async () => {
    const t = ++token;
    const bg = await wallpaperBackground(settings.get().wallpaper);
    if (t === token && bg !== current) desktop.style.background = current = bg;
  };
  void applyWallpaper();
  bus.on('settings:change', () => void applyWallpaper());
  let resizeTimer = 0;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => void applyWallpaper(), 400);
  });

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
    const current = settings.get().wallpaper;
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
