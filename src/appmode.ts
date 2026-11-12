import './styles/appmode.css';
import { registerAll } from './apps';
import { ICON_DEFS } from './assets/icons';
import { bus } from './core/events';
import { seedFS } from './core/fs';
import { getApp } from './core/registry';
import { launch, os } from './core/os';
import { allWindows, initWM } from './core/wm';
import type { MenuDef } from './core/types';
import { mountNotifications } from './shell/notifications';
import { h } from './ui/dom';
import { closeMenu, isMenuOpen, openMenu } from './ui/menu';

/**
 * "App mode": index.html?app=<id> shows one app filling the whole viewport, with no desktop around it. The real OS
 * (MWX 7 on Debian) opens these pages in a bare Chrome window and draws the frame itself, so the app only needs its
 * body, its menus (the concept shows them in the top bar, here they sit in a thin strip) and the page title.
 * Unlike the concept this keeps what the app saves (ctx.fs): a note written today is still there tomorrow.
 */
export async function runAppMode(id: string): Promise<void> {
  document.documentElement.classList.add('appmode');
  document.getElementById('curtain')?.remove();
  document.body.insertAdjacentHTML('afterbegin', ICON_DEFS);
  registerAll();
  const app = getApp(id);
  const root = document.getElementById('app')!;
  if (!app) {
    root.textContent = `No app with id "${id}".`;
    return;
  }
  document.title = app.name;
  await seedFS();

  root.innerHTML = '<div id="windows"></div><div id="notifications"></div>';
  initWM(document.getElementById('windows')!);
  mountNotifications(document.getElementById('notifications')!);
  document.addEventListener('contextmenu', (e) => {
    if (!(e.target as HTMLElement).closest('input, textarea, [contenteditable]')) e.preventDefault();
  });

  // Other windows an app asks for (a new Sticky Note, Open in Notepad...) become their own pages, i.e. their own windows.
  os.launch = (appId, args = {}) => {
    const q = new URLSearchParams({ app: appId });
    if (Object.keys(args).length) q.set('args', JSON.stringify(args));
    window.open(`${location.pathname}?${q}`, '_blank', 'popup');
  };

  const strip = h('div', { class: 'am-menus' });
  let openLabel: string | null = null;
  const renderMenus = (menus: MenuDef[]) => {
    strip.replaceChildren();
    strip.hidden = menus.length === 0;
    for (const m of menus) {
      const btn = h('button', { class: 'am-menu' }, m.label);
      const show = () => {
        const r = btn.getBoundingClientRect();
        openLabel = m.label;
        btn.classList.add('open');
        openMenu(m.items, { x: r.left, y: r.bottom }, {
          anchor: btn,
          onClose: () => {
            btn.classList.remove('open');
            if (openLabel === m.label) openLabel = null;
          },
        });
      };
      btn.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        if (openLabel === m.label) closeMenu();
        else show();
      });
      btn.addEventListener('pointerenter', () => isMenuOpen() && openLabel && openLabel !== m.label && show());
      strip.append(btn);
    }
  };

  bus.on('window:open', (w) => {
    w.el.insertBefore(strip, w.body);
    renderMenus(w.menus);
    document.title = w.title;
  });
  bus.on('window:menus', (w) => renderMenus(w.menus));
  bus.on('window:title', (w) => (document.title = w.title));
  // The real OS owns the window: when the app has closed its own, the page has nothing left to show.
  bus.on('window:close', () => allWindows().length === 0 && window.close());

  let args: Record<string, unknown> = {};
  try {
    args = JSON.parse(new URLSearchParams(location.search).get('args') ?? '{}');
  } catch {
    /* ignore a malformed args value */
  }
  launch(id, args);
}
