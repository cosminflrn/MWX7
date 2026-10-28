import { icons } from '../../assets/icons';
import type { AppManifest } from '../../core/types';
import { wallpapers } from '../../shell/wallpapers';
import { h } from '../../ui/dom';
import './settings.css';

export const settingsApp: AppManifest = {
  id: 'settings',
  name: 'Settings',
  icon: icons.settings,
  description: 'Personalize MWX7',
  keywords: ['preferences', 'control panel', 'wallpaper', 'personalize', 'system'],
  pinned: true,
  singleInstance: true,
  window: { width: 640, height: 470, minWidth: 480, minHeight: 360 },

  mount({ win, os }) {
    win.body.classList.add('set');
    const s = os.settings.get();

    const section = (title: string, ...children: Node[]) => h('section', { class: 'set-section' }, h('h2', {}, title), ...children);

    // Wallpaper picker
    const grid = h('div', { class: 'set-walls' });
    const drawWalls = () => {
      grid.replaceChildren(
        ...wallpapers.map((w) =>
          h(
            'button',
            {
              class: `set-wall${os.settings.get().wallpaper === w.id ? ' sel' : ''}`,
              onclick: () => {
                os.settings.set({ wallpaper: w.id });
                drawWalls();
              },
            },
            h('span', { class: 'set-wall-thumb', style: `background:${w.css}` }),
            h('span', {}, w.name),
          ),
        ),
      );
    };
    drawWalls();

    // User
    const name = h('input', { class: 'set-input', value: s.userName, maxLength: 24 });
    name.addEventListener('change', () => os.settings.set({ userName: name.value.trim() || 'User' }));

    const boot = h('input', { type: 'checkbox', checked: s.showBootScreen });
    boot.addEventListener('change', () => os.settings.set({ showBootScreen: boot.checked }));

    const reset = h(
      'button',
      {
        class: 'btn danger',
        onclick: () => {
          if (confirm('Erase all MWX7 data in this browser (documents and settings)?')) {
            Object.keys(localStorage)
              .filter((k) => k.startsWith('mwx7:'))
              .forEach((k) => localStorage.removeItem(k));
            location.reload();
          }
        },
      },
      'Reset MWX7…',
    );

    win.body.append(
      h(
        'aside',
        { class: 'set-side' },
        h('div', { class: 'set-side-head', html: icons.settings }),
        h('a', { href: '#wall' }, 'Desktop'),
        h('a', { href: '#user' }, 'User'),
        h('a', { href: '#system' }, 'System'),
      ),
      h(
        'div',
        { class: 'set-main' },
        h('div', { id: 'wall' }, section('Desktop background', grid)),
        h('div', { id: 'user' }, section('User account', h('label', { class: 'set-row' }, h('span', {}, 'Display name'), name))),
        h(
          'div',
          { id: 'system' },
          section(
            'System',
            h('label', { class: 'set-row' }, h('span', {}, 'Show boot screen on start'), boot),
            h('div', { class: 'set-row' }, h('span', {}, 'Storage: this browser (localStorage)'), reset),
          ),
        ),
      ),
    );

    // keep side links inside the window instead of changing the page hash
    win.body.querySelectorAll<HTMLAnchorElement>('.set-side a').forEach((a) =>
      a.addEventListener('click', (e) => {
        e.preventDefault();
        win.body.querySelector(a.getAttribute('href')!)?.scrollIntoView({ behavior: 'smooth' });
      }),
    );
  },
};
