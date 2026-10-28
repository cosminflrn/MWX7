import { icons } from '../assets/icons';
import { bus } from '../core/events';
import { launch } from '../core/os';
import { listApps } from '../core/registry';
import { settings } from '../core/settings';
import { h } from '../ui/dom';
import { logOff, shutDown } from './screens';

/**
 * XP two-column Start menu in Win7 glass. It is centered on the orb and glued
 * to it: when the orb grows under dock magnification, the menu rises with it.
 */
export function mountStartMenu(): void {
  let el: HTMLElement | null = null;
  let follow = 0;

  const orb = () => document.querySelector<HTMLElement>('.dock-orb');

  const place = () => {
    const o = orb();
    if (!el || !o) return;
    const r = o.getBoundingClientRect();
    const w = el.offsetWidth;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    el.style.left = `${Math.round(left)}px`;
    el.style.bottom = `${Math.round(window.innerHeight - r.top + 10)}px`;
  };

  const loop = () => {
    place();
    follow = requestAnimationFrame(loop);
  };

  const close = () => {
    if (!el) return;
    const node = el;
    el = null;
    cancelAnimationFrame(follow);
    orb()?.classList.remove('pressed');
    node.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(8px) scale(.98)' }], {
      duration: 120,
      easing: 'ease-in',
    }).onfinish = () => node.remove();
  };

  const run = (fn: () => void) => () => {
    close();
    fn();
  };

  const open = () => {
    const user = settings.get().userName;

    const appRow = (id: string, name: string, icon: string) =>
      h(
        'button',
        { class: 'sm-app', onclick: run(() => launch(id)) },
        h('span', { class: 'sm-app-icon', html: icon }),
        h('span', { class: 'sm-app-text' }, name),
      );

    const placeRow = (label: string, icon: string, action: () => void) =>
      h('button', { class: 'sm-place', onclick: run(action) }, h('span', { class: 'sm-place-icon', html: icon }), label);

    const search = h('input', { type: 'text', placeholder: 'Search programs and files', spellcheck: false });
    search.addEventListener('input', () => {
      const query = search.value;
      close();
      bus.emit('spotlight:open', { query });
    });

    el = h(
      'div',
      { class: 'start-menu', role: 'menu' },
      h('div', { class: 'sm-header' }, h('span', { class: 'sm-avatar', html: icons.avatar }), h('span', { class: 'sm-user' }, user)),
      h(
        'div',
        { class: 'sm-body' },
        h(
          'div',
          { class: 'sm-left' },
          ...listApps().map((a) => appRow(a.id, a.name, a.icon)),
          h('div', { class: 'sm-spacer' }),
          h('label', { class: 'sm-search' }, search, h('span', { html: icons.search })),
        ),
        h(
          'div',
          { class: 'sm-right' },
          placeRow(user, icons.avatar, () => launch('settings')),
          placeRow('Documents', icons.folder, () => launch('notepad', { openDialog: true })),
          h('div', { class: 'sm-sep' }),
          placeRow('Computer', icons.computer, () => launch('about')),
          placeRow('Settings', icons.settings, () => launch('settings')),
          h('div', { class: 'sm-sep' }),
          placeRow('Search', icons.search, () => bus.emit('spotlight:open', {})),
          placeRow('About MWX 7', icons.about, () => launch('about')),
        ),
      ),
      h(
        'div',
        { class: 'sm-footer' },
        h('button', { class: 'sm-foot-btn', onclick: run(() => void logOff()) }, h('span', { html: icons.logoff }), 'Log off'),
        h('button', { class: 'sm-foot-btn', onclick: run(() => void shutDown()) }, h('span', { html: icons.power }), 'Shut down'),
      ),
    );

    document.body.append(el);
    place();
    loop();
    orb()?.classList.add('pressed');
    el.animate([{ opacity: 0, transform: 'translateY(10px) scale(.98)' }, { opacity: 1, transform: 'none' }], {
      duration: 170,
      easing: 'cubic-bezier(.2,.8,.2,1)',
    });
    window.setTimeout(() => search.focus({ preventScroll: true }), 30);
  };

  bus.on('startmenu:toggle', () => (el ? close() : open()));

  document.addEventListener(
    'pointerdown',
    (e) => {
      const t = e.target as HTMLElement;
      if (el && !el.contains(t) && !t.closest('.dock-orb')) close();
    },
    true,
  );
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });
  bus.on('window:open', close);
}
