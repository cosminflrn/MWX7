import { icons } from '../assets/icons';
import { bus } from '../core/events';
import { launch } from '../core/os';
import type { MenuDef } from '../core/types';
import { activeWindow, centerWindow, closeWindow, minimizeWindow, toggleMaximize } from '../core/wm';
import { h } from '../ui/dom';
import { closeMenu, isMenuOpen, openMenu } from '../ui/menu';
import { toggleCalendar } from './calendar';
import { openMissionControl } from './mission';
import { logOff, shutDown } from './screens';

/** macOS-style global menu bar with Win7 glass, showing the focused app's menus. */
export function mountMenubar(bar: HTMLElement): void {
  const left = h('div', { class: 'mb-left' });
  const right = h('div', { class: 'mb-right' });
  bar.append(left, right);

  let openLabel: string | null = null;

  const systemMenu: MenuDef = {
    label: '◆',
    items: [
      { label: 'About MWX 7', action: () => launch('about') },
      { separator: true },
      { label: 'Settings…', action: () => launch('settings') },
      { label: 'Spotlight Search', shortcut: 'Ctrl+Space', action: () => bus.emit('spotlight:open', {}) },
      { label: 'Mission Control', shortcut: 'F3', action: () => openMissionControl() },
      { separator: true },
      { label: 'Log Off…', action: () => void logOff() },
      { label: 'Shut Down…', action: () => void shutDown() },
    ],
  };

  const showMenu = (btn: HTMLElement, menu: MenuDef) => {
    const r = btn.getBoundingClientRect();
    openLabel = menu.label;
    btn.classList.add('open');
    openMenu(menu.items, { x: r.left, y: r.bottom + 2 }, {
      anchor: btn,
      onClose: () => {
        btn.classList.remove('open');
        if (openLabel === menu.label) openLabel = null;
      },
    });
  };

  const menuButton = (menu: MenuDef, extraClass = '', content?: Node | string) => {
    const btn = h('button', { class: `mb-item ${extraClass}` }, content ?? menu.label);
    btn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      if (openLabel === menu.label) closeMenu();
      else showMenu(btn, menu);
    });
    // Mac behaviour: once a menu is open, hovering another title switches to it.
    btn.addEventListener('pointerenter', () => {
      if (isMenuOpen() && openLabel && openLabel !== menu.label) showMenu(btn, menu);
    });
    return btn;
  };

  const render = () => {
    const w = activeWindow();
    left.replaceChildren();
    left.append(menuButton(systemMenu, 'mb-logo', h('span', { class: 'mb-orb', html: icons.orb })));
    const appName = w ? w.manifest.name : 'Desktop';
    const appMenu: MenuDef = {
      label: appName,
      items: w
        ? [
            { label: `About ${appName}`, action: () => launch('about', { app: w.appId }) },
            { separator: true },
            { label: 'Minimize', action: () => minimizeWindow(w.id) },
            { label: w.state === 'max' ? 'Restore' : 'Maximize', action: () => toggleMaximize(w.id) },
            { label: 'Center', action: () => centerWindow(w.id) },
            { separator: true },
            { label: `Close ${appName}`, action: () => closeWindow(w.id) },
          ]
        : [
            { label: 'Personalize…', action: () => launch('settings') },
            { label: 'About MWX 7', action: () => launch('about') },
          ],
    };
    left.append(menuButton(appMenu, 'mb-app'));
    for (const m of w?.menus ?? []) left.append(menuButton(m));
  };

  // Right side: Spotlight + clock
  const searchBtn = h('button', {
    class: 'mb-item mb-icon',
    title: 'Spotlight (Ctrl+Space)',
    html: icons.search,
    onclick: () => bus.emit('spotlight:open', {}),
  });
  // A button, not a label: it opens the calendar flyout and shows the pressed state while that is open.
  const clock: HTMLButtonElement = h('button', {
    class: 'mb-item mb-clock',
    type: 'button',
    'aria-haspopup': 'dialog',
    'aria-expanded': 'false',
    onclick: () => toggleCalendar(clock),
  });
  right.append(searchBtn, clock);

  const tick = () => {
    const d = new Date();
    const day = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
    const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    clock.textContent = `${day}  ${time}`;
    clock.title = d.toLocaleDateString(undefined, { dateStyle: 'full' });
  };
  tick();
  window.setInterval(tick, 10_000);

  render();
  bus.on('window:focus', render);
  bus.on('window:menus', (w) => {
    if (w === activeWindow()) render();
  });
}
