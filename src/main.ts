import './styles/tokens.css';
import './styles/base.css';
import './styles/window.css';
import './styles/shell.css';

import { registerAll } from './apps';
import { ICON_DEFS, icons } from './assets/icons';
import { seedFS } from './core/fs';
import { notify } from './core/os';
import { initWM } from './core/wm';
import { mountDesktop } from './shell/desktop';
import { mountDock } from './shell/dock';
import { mountMenubar } from './shell/menubar';
import { mountNotifications } from './shell/notifications';
import { startup } from './shell/screens';
import { mountSpotlight } from './shell/spotlight';
import { mountStartMenu } from './shell/startmenu';

async function start(): Promise<void> {
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
  mountNotifications($('notifications'));

  // Keep the browser's own context menu off the shell (apps' text fields keep theirs).
  document.addEventListener('contextmenu', (e) => {
    if (!(e.target as HTMLElement).closest('input, textarea, [contenteditable]')) e.preventDefault();
  });

  await startup();

  if (!localStorage.getItem('mwx7:welcomed')) {
    localStorage.setItem('mwx7:welcomed', '1');
    notify('Welcome to MWX 7', 'Press Ctrl+Space to search, or click the orb to start.', icons.orb);
  }
}

void start();
