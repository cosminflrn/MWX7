import { blurWindows, showDesktop } from '../core/wm';
import { bus } from '../core/events';
import { launch } from '../core/os';
import { settings } from '../core/settings';
import { menuIcon, openMenu } from '../ui/menu';
import { openOverview } from './overview';
import { mountAmbience } from './ambience';
import { mountDeskIcons } from './deskicons';
import { gadgetsShown, toggleGadgets } from './gadgets';
import { fs } from '../core/fs';
import { createWallpaperLayer, resolveWallpaperId, wallpapers } from './wallpapers';

/** Creates "New folder", "New folder (2)", … on the desktop, like Windows. */
async function createOnDesktop(base: string, folder: boolean): Promise<void> {
  const dot = base.lastIndexOf('.');
  const [stem, ext] = !folder && dot > 0 ? [base.slice(0, dot), base.slice(dot)] : [base, ''];
  let name = base;
  for (let n = 2; await fs.exists(`/Desktop/${name}`); n++) name = `${stem} (${n})${ext}`;
  if (folder) await fs.mkdir(`/Desktop/${name}`);
  else await fs.write(`/Desktop/${name}`, '');
}

/** Live wallpaper + desktop icons + desktop context menu. */
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

  mountDeskIcons(iconLayer);



  // A click on the wallpaper or an icon takes focus away from the windows.
  for (const el of [desktop, iconLayer])
    el.addEventListener('pointerdown', (e) => {
      if (!(e.target as HTMLElement).closest('.win')) blurWindows();
    });

  desktop.addEventListener('contextmenu', (e) => {
    if ((e.target as HTMLElement).closest('.desk-icon, .win')) return;
    e.preventDefault();
    const current = resolveWallpaperId(settings.get().wallpaper);
    const idx = wallpapers.findIndex((w) => w.id === current);
    openMenu(
      [
        { label: 'Next Wallpaper', icon: menuIcon('wallpaper'), action: () => settings.set({ wallpaper: wallpapers[(idx + 1) % wallpapers.length].id }) },
        { label: 'Personalize…', icon: menuIcon('settings'), action: () => launch('settings') },
        { separator: true },
        { label: 'New Folder', icon: menuIcon('new-folder'), action: () => void createOnDesktop('New folder', true) },
        { label: 'New Text Document', icon: menuIcon('new-file'), action: () => void createOnDesktop('New Text Document.txt', false) },
        { label: gadgetsShown() ? 'Hide Widgets' : 'Show Widgets', icon: menuIcon('gadgets'), action: () => toggleGadgets() },
        { separator: true },
        { label: 'Show Desktop', icon: menuIcon('desktop'), action: () => showDesktop() },
        { label: 'Overview', icon: menuIcon('maximize'), action: () => openOverview() },
        { label: 'About MWX 7', icon: menuIcon('info'), action: () => launch('about') },
      ],
      { x: e.clientX, y: e.clientY },
    );
  });
}
