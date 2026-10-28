import './styles/tokens.css';
import './styles/base.css';
import './styles/window.css';
import './styles/shell.css';

import { registerAll } from './apps';
import { ICON_DEFS, icons } from './assets/icons';
import { seedFS } from './core/fs';
import { forgetPersistedData, settings } from './core/settings';
import { play } from './core/sound';
import { notify } from './core/os';
import { initWM } from './core/wm';
import { mountDesktop } from './shell/desktop';
import { mountDock } from './shell/dock';
import { mountMenubar } from './shell/menubar';
import { mountNotifications } from './shell/notifications';
import { mountMissionControl } from './shell/mission';
import { mountSelection } from './shell/selection';
import { startup } from './shell/screens';
import { mountSpotlight } from './shell/spotlight';
import { mountStartMenu } from './shell/startmenu';
import { mountSwitcher } from './shell/switcher';

/** Selawik (OFL): Microsoft's open-source, metric-compatible companion to Segoe UI. */
function loadFonts(): void {
  const base = `${import.meta.env.BASE_URL}fonts/selawik/`;
  const faces = [
    ['light', 300],
    ['regular', 400],
    ['semibold', 600],
    ['bold', 700],
  ] as const;
  const css = faces
    .map(([file, weight]) => `@font-face{font-family:'Selawik';src:url('${base}selawik-${file}.woff2') format('woff2');font-weight:${weight};font-display:swap}`)
    .join('');
  document.head.insertAdjacentHTML('beforeend', `<style>${css}</style>`);
}

async function start(): Promise<void> {
  forgetPersistedData();
  loadFonts();
  document.body.insertAdjacentHTML('afterbegin', ICON_DEFS);
  registerAll();
  await seedFS();

  const root = document.getElementById('app')!;
  root.innerHTML = `
    <main id="desktop">
      <div id="desktop-icons"></div>
      <div id="windows"></div>
    </main>
    <header id="menubar"></header>
    <nav id="dock"></nav>
    <div id="notifications"></div>`;

  const $ = (id: string) => document.getElementById(id)!;
  initWM($('windows'));
  mountDesktop($('desktop'), $('desktop-icons'));
  mountMenubar($('menubar'));
  mountDock($('dock'));
  mountStartMenu();
  mountSpotlight();
  mountSwitcher();
  mountNotifications($('notifications'));

  // Keep the browser's own context menu off the shell (apps' text fields keep theirs).
  document.addEventListener('contextmenu', (e) => {
    if (!(e.target as HTMLElement).closest('input, textarea, [contenteditable]')) e.preventDefault();
  });

  // A soft, satisfying click for every left / right mouse press.
  document.addEventListener(
    'pointerdown',
    (e) => {
      if (e.pointerType !== 'mouse') return;
      if (e.button === 0) play('click');
      else if (e.button === 2) play('rclick');
    },
    true,
  );

  mountSelection($('desktop'), $('desktop-icons'));
  mountMissionControl();
  await startup();

  notify(`Welcome, ${settings.get().userName}`, 'Press Ctrl+Space to search, or click the orb to start.', icons.orb);
}

void start();
