import { icons } from '../assets/icons';
import { bus } from '../core/events';
import { settings } from '../core/settings';
import { launch } from '../core/os';
import type { MenuDef } from '../core/types';
import { activeWindow, allWindows, centerWindow, closeWindow, minimizeWindow, prepareMinimize, showDesktop, toggleMaximize } from '../core/wm';
import { h } from '../ui/dom';
import { closeMenu, isMenuOpen, menuIcon, openMenu } from '../ui/menu';
import { toggleCalendar } from './calendar';
import { openOverview } from './overview';

/** Two overlapping windows: the Overview (all windows at once) glyph. */
const DESKTOP_GLYPH =
  '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="2.5" y="4" width="19" height="13" rx="1.8"/><path d="M8 20.5h8M12 17v3.5"/></svg>';
const OVERVIEW_GLYPH =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="5" width="12" height="9" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="9.5" y="10" width="12" height="9" rx="1.6" fill="currentColor" fill-opacity=".18" stroke="currentColor" stroke-width="1.8"/></svg>';

/** macOS-style global menu bar with Win7 glass, showing the focused app's menus. */
export function mountMenubar(bar: HTMLElement): void {
  const left = h('div', { class: 'mb-left' });
  const right = h('div', { class: 'mb-right' });
  bar.append(left, right);

  let openLabel: string | null = null;

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

  // The logo slot holds the MWX orb on an empty desktop and the focused app's own icon whenever an app is in
  // front; they crossfade. It is a plain badge, not a button: Start lives in the dock.
  const appIcon = h('span', { class: 'mb-appicon' });
  const logo = h('span', { class: 'mb-logo-stack' }, h('span', { class: 'mb-orb', html: icons.orb }), appIcon);

  const render = () => {
    const w = activeWindow();
    left.replaceChildren();
    left.append(h('span', { class: 'mb-logo', 'aria-hidden': 'true' }, logo));
    const appName = w ? w.manifest.name : 'Desktop';
    const appMenu: MenuDef = {
      label: appName,
      items: w
        ? [
            { label: `About ${appName}`, icon: menuIcon('info'), action: () => launch('about', { app: w.appId }) },
            { separator: true },
            { label: 'Minimize', icon: menuIcon('minimize'), action: () => minimizeWindow(w.id) },
            {
              label: w.state === 'max' ? 'Exit Full Screen' : 'Full Screen',
              icon: menuIcon(w.state === 'max' ? 'restore' : 'maximize'),
              disabled: w.manifest.window?.resizable === false,
              action: () => toggleMaximize(w.id),
            },
            { label: 'Center', icon: menuIcon('restore'), disabled: w.state === 'max', action: () => centerWindow(w.id) },
            { separator: true },
            { label: `Close ${appName}`, icon: menuIcon('close'), action: () => closeWindow(w.id) },
          ]
        : [
            { label: 'Personalize…', icon: menuIcon('wallpaper'), action: () => launch('settings') },
            { label: 'About MWX 7', icon: menuIcon('info'), action: () => launch('about') },
          ],
    };
    left.append(menuButton(appMenu, 'mb-app'));
    for (const m of w?.menus ?? []) left.append(menuButton(m));
    morph();
  };

  /**
   * Full screen: the focused window's title bar merges into this bar. Its icon
   * replaces the orb, and its traffic lights slide in at the right edge,
   * pushing the clock aside.
   */
  const wcMin = h('button', { class: 'wc wc-min', title: 'Minimize', 'aria-label': 'Minimize' });
  const wcMax = h('button', { class: 'wc wc-max', title: 'Exit full screen', 'aria-label': 'Exit full screen' });
  const wcClose = h('button', { class: 'wc wc-close', title: 'Close', 'aria-label': 'Close' });
  const controls = h('div', { class: 'mb-wc' }, h('div', { class: 'mb-wc-inner win-controls' }, wcMin, wcMax, wcClose));
  // The full-screen window keeps its place in the top bar while unfocused (Start menu, desktop click):
  // only the lights go grey, like an inactive window's.
  const target = () => {
    const a = activeWindow();
    if (a) return a.state === 'max' && !a.minimized ? a : null;
    const top = allWindows()
      .filter((w) => !w.minimized)
      .sort((x, y) => y.z - x.z)[0];
    return top && top.state === 'max' ? top : null;
  };
  wcMin.addEventListener('pointerdown', (e) => {
    const w = target();
    if (w && e.button === 0) prepareMinimize(w.id);
  });
  wcMin.addEventListener('click', () => {
    const w = target();
    if (w) minimizeWindow(w.id);
  });
  wcMax.addEventListener('click', () => {
    const w = target();
    if (w) toggleMaximize(w.id);
  });
  wcClose.addEventListener('click', () => {
    const w = target();
    if (w) closeWindow(w.id);
  });
  let fsApp = '';
  const morph = () => {
    const w = target();
    const front = activeWindow() ?? w;
    if (front && fsApp !== front.appId) {
      appIcon.innerHTML = front.manifest.icon;
      fsApp = front.appId;
    }
    bar.classList.toggle('app-front', !!front);
    bar.classList.toggle('fs', !!w);
    bar.classList.toggle('fs-inactive', !!w && w !== activeWindow());
  };

  // Right side: Search, Overview + clock
  const searchBtn = h('button', {
    class: 'mb-item mb-icon',
    title: 'Search',
    html: icons.search,
    onclick: () => bus.emit('search:open', {}),
  });
  // A button, not a label: it opens the calendar flyout and shows the pressed state while that is open.
  const clock: HTMLButtonElement = h('button', {
    class: 'mb-item mb-clock',
    type: 'button',
    'aria-haspopup': 'dialog',
    'aria-expanded': 'false',
    onclick: () => toggleCalendar(clock),
  });
  const overviewBtn = h('button', {
    class: 'mb-item mb-icon',
    title: 'Overview',
    'aria-label': 'Overview',
    html: OVERVIEW_GLYPH,
    onclick: () => openOverview(),
  });
  // Show desktop: click minimizes every window (again = bring them back).
  const showDesk = h('button', {
    class: 'mb-item mb-icon',
    title: 'Show desktop',
    'aria-label': 'Show desktop',
    html: DESKTOP_GLYPH,
    onclick: () => showDesktop(),
  });
  right.append(searchBtn, overviewBtn, showDesk, clock, controls);

  const tick = () => {
    const d = new Date();
    const day = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
    const st = settings.get();
    const time = d.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: st.clockSeconds ? '2-digit' : undefined,
      hour12: st.clock24 ? false : undefined,
    });
    clock.textContent = `${day}  ${time}`;
    clock.title = d.toLocaleDateString(undefined, { dateStyle: 'full' });
  };
  tick();
  // Seconds need a 1s beat; otherwise a slow one is enough.
  let beat = 0;
  const schedule = () => {
    window.clearInterval(beat);
    beat = window.setInterval(tick, settings.get().clockSeconds ? 1000 : 10_000);
  };
  schedule();
  bus.on('settings:change', () => {
    tick();
    schedule();
  });

  render();
  bus.on('window:focus', render);
  bus.on('window:state', (w) => {
    if (w === activeWindow()) render();
  });
  bus.on('window:minimize', morph);
  bus.on('window:close', () => window.setTimeout(morph, 0));
  bus.on('window:menus', (w) => {
    if (w === activeWindow()) render();
  });
}
