import { icons } from '../assets/icons';
import { bus } from '../core/events';
import { launch } from '../core/os';
import { listApps } from '../core/registry';
import { settings } from '../core/settings';
import { h } from '../ui/dom';
import { logOff, shutDown } from './screens';

/** Windows XP two-column Start menu, rendered in Aero glass. */
export function mountStartMenu(): void {
  let el: HTMLElement | null = null;

  const close = () => {
    if (!el) return;
    const node = el;
    el = null;
    document.querySelector('.dock-orb')?.classList.remove('pressed');
    node.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(10px) scale(.98)' }], {
      duration: 120,
      easing: 'ease-in',
    }).onfinish = () => node.remove();
  };

  const run = (fn: () => void) => () => {
    close();
    fn();
  };

  const open = (anchor?: DOMRect) => {
    const user = settings.get().userName;
    const apps = listApps();

    const appRow = (id: string, name: string, icon: string, desc?: string) =>
      h(
        'button',
        { class: 'sm-app', onclick: run(() => launch(id)) },
        h('span', { class: 'sm-app-icon', html: icon }),
        h('span', { class: 'sm-app-text' }, h('b', {}, name), desc ? h('small', {}, desc) : null),
      );

    const placeRow = (label: string, icon: string, action: () => void) =>
      h('button', { class: 'sm-place', onclick: run(action) }, h('span', { class: 'sm-place-icon', html: icon }), label);

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
          ...apps.map((a) => appRow(a.id, a.name, a.icon, a.description)),
          h('div', { class: 'sm-spacer' }),
          h(
            'button',
            { class: 'sm-all', onclick: run(() => bus.emit('spotlight:open')) },
            h('span', {}, 'Search apps and files'),
            h('span', { class: 'sm-all-key' }, 'Ctrl+Space'),
          ),
        ),
        h(
          'div',
          { class: 'sm-right' },
          placeRow('My Documents', icons.folder, () => launch('notepad', { openDialog: true })),
          h('div', { class: 'sm-sep' }),
          placeRow('Settings', icons.settings, () => launch('settings')),
          placeRow('Search', icons.search, () => bus.emit('spotlight:open')),
          placeRow('About MWX7', icons.about, () => launch('about')),
        ),
      ),
      h(
        'div',
        { class: 'sm-footer' },
        h('button', { class: 'sm-foot-btn', onclick: run(logOff) }, h('span', { html: icons.logoff }), 'Log Off'),
        h('button', { class: 'sm-foot-btn', onclick: run(shutDown) }, h('span', { html: icons.power }), 'Turn Off'),
      ),
    );

    document.body.append(el);
    const r = el.getBoundingClientRect();
    const left = anchor ? Math.min(Math.max(8, anchor.left), window.innerWidth - r.width - 8) : 8;
    el.style.left = `${left}px`;
    document.querySelector('.dock-orb')?.classList.add('pressed');
    el.animate([{ opacity: 0, transform: 'translateY(12px) scale(.98)' }, { opacity: 1, transform: 'none' }], {
      duration: 180,
      easing: 'cubic-bezier(.2,.8,.2,1)',
    });
  };

  bus.on('startmenu:toggle', ({ anchor }) => (el ? close() : open(anchor)));

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
