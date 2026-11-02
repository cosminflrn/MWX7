import { icons } from '../../assets/icons';
import type { AppManifest } from '../../core/types';
import { avatarHtml, avatarPicker } from '../../shell/avatars';
import { wallpaperThumb, wallpapers } from '../../shell/wallpapers';
import { h } from '../../ui/dom';
import './settings.css';

// Apps may not import each other, so this mirrors the About app's VERSION. Keep them in step on release.
const VERSION = '0.5.0';

type SectionId = 'personalization' | 'accounts' | 'sound' | 'system';

interface Section {
  id: SectionId;
  title: string;
  icon: string;
}

const SECTIONS: Section[] = [
  { id: 'personalization', title: 'Personalization', icon: icons.pictures },
  { id: 'accounts', title: 'User account', icon: icons.avatar },
  { id: 'sound', title: 'Sound', icon: icons.music },
  { id: 'system', title: 'System', icon: icons.computer },
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
    const content = h('div', { class: 'set-content' });

    const heading = (text: string) => h('h1', { class: 'set-h1' }, text);
    const lead = (text: string) => h('p', { class: 'set-lead' }, text);
    const sub = (text: string) => h('h2', { class: 'set-h2' }, text);
    const section = (id: SectionId, ...kids: (HTMLElement | string)[]) => h('section', { class: 'set-section', id: `set-${id}`, 'data-sec': id }, ...kids);

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
      return section(
        'personalization',
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
      return section(
        'accounts',
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
      return section(
        'sound',
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
      return section(
        'system',
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

    const builders: Record<SectionId, () => HTMLElement> = { personalization, accounts, sound, system };
    const sections = SECTIONS.map((x) => builders[x.id]());
    content.append(...sections);

    const links = new Map<SectionId, HTMLElement>();
    const mark = (id: SectionId) => links.forEach((el, k) => el.classList.toggle('cur', k === id));

    const jump = (id: SectionId) => {
      const target = sections[SECTIONS.findIndex((x) => x.id === id)];
      content.scrollTo({ top: target.offsetTop - content.offsetTop, behavior: 'smooth' });
      mark(id);
    };

    for (const sec of SECTIONS) {
      const el = h(
        'button',
        { class: 'set-link', type: 'button', onclick: () => jump(sec.id) },
        h('span', { class: 'set-link-icon', html: sec.icon }),
        h('span', { class: 'set-link-text' }, sec.title),
      );
      links.set(sec.id, el);
      side.append(el);
    }

    win.setTitle('Settings');
    win.body.append(side, content);
    mark('personalization');

    // Highlight whichever section occupies the top band of the scroll area.
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) mark((e.target as HTMLElement).dataset.sec as SectionId);
      },
      { root: content, rootMargin: '0px 0px -70% 0px', threshold: 0 },
    );
    sections.forEach((el) => io.observe(el));

    const wanted = typeof args.page === 'string' ? (args.page as SectionId) : undefined;
    if (wanted && SECTIONS.some((x) => x.id === wanted)) requestAnimationFrame(() => jump(wanted));

    return () => io.disconnect();
  },
};
