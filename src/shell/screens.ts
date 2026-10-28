import { icons } from '../assets/icons';
import { settings } from '../core/settings';
import { h } from '../ui/dom';

/** Full-screen moments: boot, welcome (log off) and shut down. */

const fadeOut = (el: HTMLElement) =>
  new Promise<void>((resolve) => {
    el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 400, easing: 'ease' }).onfinish = () => {
      el.remove();
      resolve();
    };
  });

/** XP-style boot: logo + marching progress bar. Click or any key skips it. */
export function bootScreen(): Promise<void> {
  if (!settings.get().showBootScreen) return Promise.resolve();
  return new Promise((resolve) => {
    const screen = h(
      'div',
      { class: 'screen boot' },
      h('div', { class: 'boot-logo', html: icons.orb }),
      h('div', { class: 'boot-name' }, 'MWX', h('sup', {}, '7')),
      h('div', { class: 'boot-bar' }, h('span'), h('span'), h('span')),
      h('div', { class: 'boot-hint' }, 'Starting up… (click to skip)'),
    );
    document.body.append(screen);
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      window.removeEventListener('keydown', finish);
      void fadeOut(screen).then(resolve);
    };
    screen.addEventListener('click', finish);
    window.addEventListener('keydown', finish);
    window.setTimeout(finish, 2200);
  });
}

/** XP "Welcome" screen: click your user tile to log back in. */
export function logOff(): void {
  const user = settings.get().userName;
  const screen = h(
    'div',
    { class: 'screen welcome' },
    h('div', { class: 'welcome-left' }, h('div', { class: 'welcome-logo', html: icons.orb }), h('h1', {}, 'welcome'), h('p', {}, 'To begin, click your user name')),
    h('div', { class: 'welcome-divider' }),
    h(
      'div',
      { class: 'welcome-right' },
      h('button', { class: 'user-tile', onclick: () => void fadeOut(screen) }, h('span', { class: 'user-tile-pic', html: icons.avatar }), h('span', {}, user)),
    ),
  );
  document.body.append(screen);
  screen.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 400 });
}

/** Win7 "Shutting down…" then a cheeky final screen. */
export function shutDown(): void {
  const screen = h('div', { class: 'screen shutdown' }, h('div', { class: 'spinner' }), h('p', {}, 'Shutting down…'));
  document.body.append(screen);
  screen.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 500 });
  window.setTimeout(() => {
    screen.replaceChildren(
      h('p', { class: 'safe' }, 'It’s now safe to close this tab.'),
      h('button', { class: 'restart-btn', onclick: () => location.reload() }, 'Restart'),
    );
    screen.classList.add('off');
  }, 1800);
}
