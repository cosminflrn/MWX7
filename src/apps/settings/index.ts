import { icons } from '../../assets/icons';
import type { AppManifest } from '../../core/types';
import { avatarHtml, avatarPicker } from '../../shell/avatars';
import { wallpaperThumb, wallpapers } from '../../shell/wallpapers';
import { h } from '../../ui/dom';
import './settings.css';

// Apps may not import each other, so this mirrors the About app's VERSION. Keep them in step on release.
const VERSION = '1.2.3';

type SectionId = 'themes' | 'wallpapers' | 'accounts' | 'wincolor' | 'desktop' | 'dock' | 'datetime' | 'sound' | 'system';

interface Section {
  id: SectionId;
  title: string;
  icon: string;
}

const SECTIONS: Section[] = [
  { id: 'themes', title: 'Themes', icon: icons.desktop },
  { id: 'wallpapers', title: 'Wallpapers', icon: icons.pictures },
  { id: 'accounts', title: 'User account', icon: icons.avatar },
  { id: 'wincolor', title: 'Window Color', icon: icons.settings },
  { id: 'desktop', title: 'Desktop', icon: icons.desktop },
  { id: 'dock', title: 'Dock', icon: icons.orb },
  { id: 'datetime', title: 'Date & time', icon: icons.about },
  { id: 'sound', title: 'Sound', icon: icons.music },
  { id: 'system', title: 'System', icon: icons.computer },
];

export const impl: Pick<AppManifest, 'mount'> = {
  mount({ win, args, os }) {
    win.body.classList.add('set');
    const s = os.settings.get();

    const side = h('aside', { class: 'set-side' });
    const content = h('div', { class: 'set-content' });

    const heading = (text: string) => h('h1', { class: 'set-h1' }, text);
    const lead = (text: string) => h('p', { class: 'set-lead' }, text);
    const sub = (text: string) => h('h2', { class: 'set-h2' }, text);
    const section = (id: SectionId, ...kids: (HTMLElement | string)[]) => h('section', { class: 'set-section', id: `set-${id}`, 'data-sec': id }, ...kids);

    // ---- Themes: wallpaper + window colour in one click ----
    const THEMES = [
      { id: 'mwx7', name: 'MWX 7', wallpaper: 'meadow', glassColor: '#1e64dc', glassIntensity: 0 },
      { id: 'aurora', name: 'Aurora', wallpaper: 'aurora', glassColor: '#1b3f9e', glassIntensity: 60 },
      { id: 'sierra', name: 'Sierra', wallpaper: 'sierra', glassColor: '#5f6b78', glassIntensity: 45 },
      { id: 'dusk', name: 'Dusk', wallpaper: 'dusk', glassColor: '#7d4cc4', glassIntensity: 55 },
    ];
    const themesSection = () => {
      const grid = h('div', { class: 'set-walls set-themes', role: 'listbox' });
      const draw = () => {
        const cur = os.settings.get();
        grid.replaceChildren(
          ...THEMES.map((t) => {
            const on = cur.wallpaper === t.wallpaper && cur.glassColor.toLowerCase() === t.glassColor && cur.glassIntensity === t.glassIntensity;
            return h(
              'button',
              {
                class: `set-wall set-theme${on ? ' sel' : ''}`,
                role: 'option',
                'data-theme': t.id,
                'aria-selected': String(on),
                title: t.name,
                onclick: () => {
                  os.settings.set({ wallpaper: t.wallpaper, glassColor: t.glassColor, glassIntensity: t.glassIntensity });
                  draw();
                },
              },
              h('span', { class: 'set-wall-thumb', style: `background:${wallpaperThumb(t.wallpaper)}` }, h('span', { class: 'set-theme-glass', style: `background:${t.glassColor}` })),
              h('span', { class: 'set-wall-name' }, t.name),
            );
          }),
        );
      };
      draw();
      // Other categories change the wallpaper/colour too; keep the ring honest.
      content.addEventListener('click', () => setTimeout(draw));
      return section('themes', heading('Change the visuals and sounds on your computer'), lead('Click a theme to set the desktop background and window color together.'), grid);
    };

    // ---- Personalization -------------------------------------------------
    const wallpapersSection = () => {
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
        'wallpapers',
        heading('Choose your desktop background'),
        lead('Click a picture to use it as your desktop background.'),
        grid,
      );
    };

    // ---- Window colour (Win7 "Window Color and Appearance") ----
    const SWATCHES: [string, string][] = [
      ['Sky', '#1e64dc'], ['Twilight', '#4a4f8f'], ['Sea', '#1d9aa5'], ['Leaf', '#3f9a3f'],
      ['Lime', '#9ac93a'], ['Sun', '#e8c52b'], ['Pumpkin', '#e8812a'], ['Ruby', '#c42b3a'],
      ['Fuchsia', '#c23a9a'], ['Blush', '#ee9fb4'], ['Violet', '#7d4cc4'], ['Lavender', '#a99bd6'],
      ['Taupe', '#8a7f73'], ['Chocolate', '#6b4630'], ['Slate', '#5f6b78'], ['Frost', '#b9d3e8'],
    ];
    const windowColor = () => {
      const cur = () => os.settings.get();
      const swatches = h('div', { class: 'set-swatches', role: 'listbox', 'aria-label': 'Window color' });
      const picker = h('input', { type: 'color', class: 'set-colorinput', 'aria-label': 'Custom color', value: cur().glassColor });
      const slider = h('input', { type: 'range', class: 'set-range', min: '0', max: '100', step: '1', value: String(cur().glassIntensity), 'aria-label': 'Color intensity' });
      const val = h('span', { class: 'set-muted set-range-val' }, String(cur().glassIntensity));
      const draw = () => {
        const c = cur().glassColor.toLowerCase();
        swatches.replaceChildren(
          ...SWATCHES.map(([name, hex]) =>
            h('button', {
              class: `set-swatch${c === hex ? ' sel' : ''}`,
              type: 'button',
              role: 'option',
              'aria-selected': String(c === hex),
              title: name,
              style: `background:${hex}`,
              onclick: () => {
                os.settings.set({ glassColor: hex });
                picker.value = hex;
                draw();
              },
            }),
          ),
        );
      };
      draw();
      slider.addEventListener('input', () => {
        val.textContent = slider.value;
        os.settings.set({ glassIntensity: Number(slider.value) });
      });
      picker.addEventListener('input', () => {
        os.settings.set({ glassColor: picker.value });
        draw();
      });
      const mixer = h('div', { class: 'set-mixer', hidden: true }, h('label', { class: 'set-mixer-row' }, h('span', {}, 'Custom color'), picker));
      const toggle = h('button', { class: 'set-disclosure', type: 'button', 'aria-expanded': 'false' }, h('span', { class: 'set-disclosure-arrow' }, '\u25B8'), 'Show color mixer');
      toggle.addEventListener('click', () => {
        mixer.hidden = !mixer.hidden;
        toggle.setAttribute('aria-expanded', String(!mixer.hidden));
        toggle.classList.toggle('open', !mixer.hidden);
        toggle.lastChild!.textContent = mixer.hidden ? 'Show color mixer' : 'Hide color mixer';
      });
      return section(
        'wincolor',
        heading('Change the color of your windows'),
        lead('Change the color of your window borders, Start menu and taskbar.'),
        swatches,
        h('div', { class: 'set-intensity' }, h('span', {}, 'Color intensity:'), slider, val),
        toggle,
        mixer,
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

    // ---- Desktop / Dock / Date & time (every control applies live) ----
    let uid = 0;
    const toggle = (label: string, key: 'showDesktopIcons' | 'dockMagnify' | 'clock24' | 'clockSeconds') => {
      const id = `set-t${uid++}`;
      const box = h('input', { type: 'checkbox', id, checked: os.settings.get()[key] });
      box.addEventListener('change', () => os.settings.set({ [key]: box.checked }));
      return h('label', { class: 'set-check', for: id }, box, h('span', {}, label));
    };
    const desktopSec = () =>
      section('desktop', heading('Customize your desktop'), lead('Choose what appears on the desktop.'), toggle('Show desktop icons', 'showDesktopIcons'));
    const dockSec = () => {
      const seg = h('div', { class: 'set-seg', role: 'radiogroup', 'aria-label': 'Icon size' });
      const draw = () => {
        const cur = os.settings.get().dockSize;
        seg.replaceChildren(
          ...(['small', 'medium', 'large'] as const).map((k) =>
            h('button', { class: `set-segbtn${cur === k ? ' sel' : ''}`, type: 'button', role: 'radio', 'aria-checked': String(cur === k),
              onclick: () => { os.settings.set({ dockSize: k }); draw(); } }, k[0].toUpperCase() + k.slice(1)),
          ),
        );
      };
      draw();
      return section('dock', heading('Change how the dock behaves'), lead('Icons grow under the pointer when magnification is on.'),
        toggle('Magnification', 'dockMagnify'), sub('Icon size'), seg);
    };
    const dateSec = () =>
      section('datetime', heading('Set the date and time format'), lead('Changes the clock in the menu bar.'),
        toggle('Use 24-hour clock', 'clock24'), toggle('Show seconds', 'clockSeconds'));

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

    const builders: Record<SectionId, () => HTMLElement> = { themes: themesSection, wallpapers: wallpapersSection, accounts, wincolor: windowColor, desktop: desktopSec, dock: dockSec, datetime: dateSec, sound, system };
    const sections = SECTIONS.map((x) => builders[x.id]());
    content.append(...sections);

    const links = new Map<SectionId, HTMLElement>();
    const mark = (id: SectionId) => links.forEach((el, k) => el.classList.toggle('cur', k === id));

    // The current section is the last one whose top has reached the top of the viewport (computed from scroll position).
    const compute = (): SectionId => {
      const max = content.scrollHeight - content.clientHeight;
      if (content.scrollTop >= max - 2 && max > 0) return SECTIONS[SECTIONS.length - 1].id;
      const y = content.scrollTop + 8;
      let cur = SECTIONS[0].id;
      sections.forEach((el, i) => {
        if (el.offsetTop - content.offsetTop <= y) cur = SECTIONS[i].id;
      });
      return cur;
    };
    // After a click the highlight stays on the clicked item until the user scrolls by hand (short last sections can't reach the top).
    let pinned: SectionId | null = null;
    let pinTimer = 0;
    const jump = (id: SectionId) => {
      const target = sections[SECTIONS.findIndex((x) => x.id === id)];
      mark(id);
      pinned = id;
      window.clearTimeout(pinTimer);
      pinTimer = window.setTimeout(() => (pinned = null), 700);
      const top = id === SECTIONS[0].id ? 0 : target.offsetTop - content.offsetTop;
      content.scrollTo({ top, behavior: 'smooth' });
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
    mark('themes');

    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        // A hidden window (minimized) has no layout; measuring it would pick the wrong category.
        if (!content.clientHeight) return;
        if (pinned) {
          window.clearTimeout(pinTimer);
          pinTimer = window.setTimeout(() => (pinned = null), 150); // released shortly after the smooth scroll settles
          return;
        }
        mark(compute());
      });
    };
    content.addEventListener('scroll', onScroll, { passive: true });

    const wanted = typeof args.page === 'string' ? (args.page as SectionId) : undefined;
    if (wanted && SECTIONS.some((x) => x.id === wanted)) requestAnimationFrame(() => jump(wanted));

    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(pinTimer);
    };
  },
};
