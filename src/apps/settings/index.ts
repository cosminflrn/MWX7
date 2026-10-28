import { icons } from '../../assets/icons';
import type { AppManifest } from '../../core/types';
import { avatarHtml, avatarPicker } from '../../shell/avatars';
import { wallpaperThumb, wallpapers } from '../../shell/wallpapers';
import { h } from '../../ui/dom';
import './settings.css';

// Apps may not import each other, so this mirrors the About app's VERSION. Keep them in step on release.
const VERSION = '0.4.0';

type PageId = 'home' | 'personalization' | 'accounts' | 'sound' | 'system';

interface Page {
  id: PageId;
  title: string;
  icon: string;
  blurb: string;
}

const PAGES: Page[] = [
  { id: 'personalization', title: 'Personalization', icon: icons.pictures, blurb: 'Change the desktop background' },
  { id: 'accounts', title: 'User Accounts', icon: icons.avatar, blurb: 'Change your account name and picture' },
  { id: 'sound', title: 'Sound', icon: icons.music, blurb: 'Turn system sounds on or off' },
  { id: 'system', title: 'System', icon: icons.computer, blurb: 'View basic information about this computer' },
];

export const settingsApp: AppManifest = {
  id: 'settings',
  name: 'Settings',
  icon: icons.settings,
  description: 'Personalize MWX 7',
  keywords: ['preferences', 'control panel', 'wallpaper', 'personalize', 'system', 'sound', 'account'],
  pinned: true,
  singleInstance: true,
  window: { width: 700, height: 500, minWidth: 520, minHeight: 380 },

  mount({ win, args, os }) {
    win.body.classList.add('set');
    const s = os.settings.get();

    const side = h('aside', { class: 'set-side' });
    const crumbs = h('div', { class: 'set-crumbs' });
    const content = h('div', { class: 'set-content' });

    const heading = (text: string) => h('h1', { class: 'set-h1' }, text);
    const lead = (text: string) => h('p', { class: 'set-lead' }, text);
    const sub = (text: string) => h('h2', { class: 'set-h2' }, text);

    // ---- Personalization -------------------------------------------------
    const personalization = () => {
      const grid = h('div', { class: 'set-walls', role: 'listbox' });
      const draw = () => {
        const current = os.settings.get().wallpaper;
        grid.replaceChildren(
          ...wallpapers.map((w) =>
            h(
              'button',
              {
                class: `set-wall${current === w.id ? ' sel' : ''}`,
                role: 'option',
                'aria-selected': String(current === w.id),
                title: w.name,
                onclick: () => {
                  os.settings.set({ wallpaper: w.id });
                  draw();
                },
              },
              h('span', { class: 'set-wall-thumb', style: `background:${wallpaperThumb(w.id)}` }),
              h('span', { class: 'set-wall-name' }, w.name),
            ),
          ),
        );
      };
      draw();
      return h(
        'div',
        {},
        heading('Change the visuals and sounds on your computer'),
        lead('Click a picture to use it as your desktop background.'),
        sub('Desktop Background'),
        grid,
      );
    };

    // ---- User Accounts ---------------------------------------------------
    const accounts = () => {
      const big = h('div', { class: 'set-avatar-big', html: avatarHtml(os.settings.get().avatar) });
      const shownName = h('div', { class: 'set-user-name' }, os.settings.get().userName);
      const name = h('input', { class: 'set-input', value: os.settings.get().userName, maxLength: 24, 'aria-label': 'Account name' });
      name.addEventListener('change', () => {
        const next = name.value.trim() || 'User';
        name.value = next;
        os.settings.set({ userName: next });
        shownName.textContent = next;
      });
      const picker = avatarPicker(s.avatar, (url) => {
        os.settings.set({ avatar: url });
        big.innerHTML = avatarHtml(url);
      });
      return h(
        'div',
        {},
        heading('Make changes to your user account'),
        h('div', { class: 'set-user' }, big, h('div', { class: 'set-user-info' }, shownName, h('div', { class: 'set-muted' }, 'Local account'))),
        sub('Change your account name'),
        lead('Type a new name for your account. It appears on the Welcome screen and in the Start menu.'),
        name,
        sub('Change your picture'),
        lead('Select a new picture for your account.'),
        picker,
      );
    };

    // ---- Sound -----------------------------------------------------------
    const sound = () => {
      const box = h('input', { type: 'checkbox', id: 'set-sounds', checked: os.settings.get().sounds });
      box.addEventListener('change', () => os.settings.set({ sounds: box.checked }));
      return h(
        'div',
        {},
        heading('Change how MWX 7 sounds'),
        lead('Choose whether the system plays sounds for events such as starting up, notifications and minimizing windows.'),
        sub('System sounds'),
        h('label', { class: 'set-check', for: 'set-sounds' }, box, h('span', {}, 'Play system sounds')),
      );
    };

    // ---- System ----------------------------------------------------------
    const system = () => {
      const row = (k: string, v: string) => h('div', { class: 'set-spec' }, h('dt', {}, k), h('dd', {}, v));
      const threads = navigator.hardwareConcurrency;
      return h(
        'div',
        {},
        heading('View basic information about your computer'),
        sub('MWX 7 edition'),
        h(
          'div',
          { class: 'set-about' },
          h(
            'dl',
            {},
            row('Edition', 'MWX 7'),
            row('Version', VERSION),
            row('Processor', threads ? `${threads} logical processors` : 'Not reported by the browser'),
            row('Memory', 'Session only'),
          ),
          h('div', { class: 'set-about-logo', html: icons.orb }),
        ),
        sub('Restart'),
        lead('Restarting reloads MWX 7 and returns to the Welcome screen.'),
        h('button', { class: 'btn', onclick: () => location.reload() }, 'Restart MWX 7'),
      );
    };

    // ---- Control Panel Home ---------------------------------------------
    const home = () =>
      h(
        'div',
        {},
        heading('Adjust your computer’s settings'),
        h(
          'div',
          { class: 'set-cats' },
          ...PAGES.map((p) =>
            h(
              'a',
              { class: 'set-cat', href: `#${p.id}`, onclick: (e: Event) => (e.preventDefault(), go(p.id)) },
              h('span', { class: 'set-cat-icon', html: p.icon }),
              h('span', { class: 'set-cat-text' }, h('span', { class: 'set-cat-title' }, p.title), h('span', { class: 'set-cat-sub' }, p.blurb)),
            ),
          ),
        ),
      );

    const builders: Record<PageId, () => HTMLElement> = { home, personalization, accounts, sound, system };

    const go = (id: PageId) => {
      const page = PAGES.find((p) => p.id === id);
      win.setTitle(page ? page.title : 'Control Panel');
      content.replaceChildren(builders[id]());
      content.scrollTop = 0;
      crumbs.replaceChildren(
        h('a', { class: 'set-crumb', href: '#home', onclick: (e: Event) => (e.preventDefault(), go('home')) }, 'Control Panel'),
        ...(page ? [h('span', { class: 'set-crumb-sep' }, '▸'), h('span', { class: 'set-crumb cur' }, page.title)] : []),
      );
      side.querySelectorAll('a').forEach((a) => a.classList.toggle('cur', a.dataset.page === id));
    };

    const sideLink = (id: PageId, label: string) =>
      h('a', { class: 'set-link', href: `#${id}`, 'data-page': id, onclick: (e: Event) => (e.preventDefault(), go(id)) }, label);

    side.append(
      sideLink('home', 'Control Panel Home'),
      h('div', { class: 'set-side-rule' }),
      ...PAGES.map((p) => sideLink(p.id, p.title)),
    );

    win.body.append(side, h('div', { class: 'set-right' }, crumbs, content));

    const wanted = typeof args.page === 'string' ? (args.page as PageId) : 'home';
    go(wanted in builders ? wanted : 'home');
  },
};
