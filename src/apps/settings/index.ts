import { icons } from '../../assets/icons';
import type { AppManifest } from '../../core/types';
import { avatarPicker } from '../../shell/avatars';
import { wallpaperThumb, wallpapers } from '../../shell/wallpapers';
import { h } from '../../ui/dom';
import './settings.css';

export const settingsApp: AppManifest = {
  id: 'settings',
  name: 'Settings',
  icon: icons.settings,
  description: 'Personalize MWX 7',
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
            h('span', { class: 'set-wall-thumb', style: `background:${wallpaperThumb(w.id)}` }),
            h('span', {}, w.name),
          ),
        ),
      );
    };
    drawWalls();

    // User
    const name = h('input', { class: 'set-input', value: s.userName, maxLength: 24 });
    name.addEventListener('change', () => os.settings.set({ userName: name.value.trim() || 'User' }));

    const sounds = h('input', { type: 'checkbox', checked: s.sounds });
    sounds.addEventListener('change', () => os.settings.set({ sounds: sounds.checked }));

    const picture = avatarPicker(s.avatar, (url) => os.settings.set({ avatar: url }));

    const restart = h('button', { class: 'btn', onclick: () => location.reload() }, 'Restart MWX 7');

    win.body.append(
      h(
        'aside',
        { class: 'set-side' },
        h('div', { class: 'set-side-head', html: icons.settings }),
        h('a', { href: '#wall' }, 'Desktop'),
        h('a', { href: '#user' }, 'User'),
        h('a', { href: '#sound' }, 'Sound'),
        h('a', { href: '#system' }, 'System'),
      ),
      h(
        'div',
        { class: 'set-main' },
        h('div', { id: 'wall' }, section('Desktop background', grid)),
        h(
          'div',
          { id: 'user' },
          section(
            'User account',
            h('label', { class: 'set-row' }, h('span', {}, 'Display name'), name),
            h('div', { class: 'set-row set-col' }, h('span', {}, 'Account picture'), picture),
          ),
        ),
        h(
          'div',
          { id: 'sound' },
          section(
            'Sound',
            h('label', { class: 'set-row' }, h('span', {}, 'Play system sounds'), sounds),
          ),
        ),
        h(
          'div',
          { id: 'system' },
          section(
            'System',
            h('div', { class: 'set-row' }, h('span', {}, 'MWX 7 keeps nothing after you close or reload it.'), restart),
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
