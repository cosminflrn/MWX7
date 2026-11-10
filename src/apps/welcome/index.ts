import { icons } from '../../assets/icons';
import { getApp } from '../../core/registry';
import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import './welcome.css';

// Duplicated from apps/about (apps may not import each other); keep in sync on release.
const VERSION = '1.8.1';
const BASE = import.meta.env.BASE_URL;
// J.S. Bach, Aria da Capo (Goldberg Variations), Kimiko Ishizaka, CC0: a real piano recording, see media/CREDITS.md
const MUSIC = `${BASE}media/music/goldberg-aria-da-capo.ogg`;

const app = (id: string) => getApp(id)?.icon ?? icons.orb;
const png = (name: string) => `<img src="${BASE}media/icons/${name}.png" alt="" draggable="false">`;
const tile = (svg: string, label?: string, cls = '') =>
  `<div class="wl-gt ${cls}"><span class="wl-gi">${svg}</span>${label ? `<em>${label}</em>` : ''}</div>`;

interface Slide {
  title: string;
  lead: string;
  points?: Array<[string, string]>;
  art: string;
}

// Built at mount time: the app registry is not filled yet when this module loads.
const buildSlides = (): Slide[] => [
  {
    title: 'Welcome to MWX 7',
    lead: 'A dream desktop that blends the best of Windows XP, Windows 7 and macOS, running right here in your browser.',
    points: [['Nothing is saved', 'Every reload is a fresh machine, so feel free to explore.']],
    art: `<div class="wl-a1"><div class="wl-halo"></div><div class="wl-big-orb">${icons.orb}</div>
      <span class="wl-sat s1">${app('explorer')}</span><span class="wl-sat s2">${app('browser')}</span>
      <span class="wl-sat s3">${app('mediaplayer')}</span><span class="wl-sat s4">${app('pinball')}</span></div>`,
  },
  {
    title: 'Your desktop',
    lead: 'Everything is a click away, and every window is easy to find.',
    points: [
      ['Dock', 'Your apps at the bottom; icons grow as you point at them.'],
      ['Start', 'All programs and instant search in one menu.'],
      ['Overview', 'The button in the top bar lays every window out at once.'],
      ['Aero Peek', 'Point at a running app in the dock to preview its windows.'],
    ],
    art: `<div class="wl-a2"><div class="wl-mini"><div class="wl-mini-bar"><i></i><i></i><i></i></div>
      <div class="wl-mini-win w1"><b></b></div><div class="wl-mini-win w2"><b></b></div>
      <div class="wl-mini-dock"><span class="wl-mini-orb">${icons.orb}</span>${['explorer', 'browser', 'mediaplayer', 'photos', 'settings'].map((a) => `<span>${app(a)}</span>`).join('')}</div></div>
      <span class="wl-tag t1">Overview</span><span class="wl-tag t2">Dock</span><span class="wl-tag t3">Start</span></div>`,
  },
  {
    title: 'Files and apps',
    lead: 'The essentials are all here, and they work together.',
    points: [
      ['My Computer', 'Browse folders and drives.'],
      ['Internet', 'Surf the web inside the desktop.'],
      ['Media Player', 'Listen to Bach, recorded on a real piano.'],
      ['Photo Viewer', 'Flip through your pictures.'],
    ],
    art: `<div class="wl-a3">${tile(png('computer'), 'My Computer')}${tile(app('browser'), 'Internet')}${tile(app('mediaplayer'), 'Media Player')}${tile(app('photos'), 'Photo Viewer')}</div>`,
  },
  {
    title: 'Make it yours',
    lead: 'Open Settings to change how MWX 7 looks.',
    points: [
      ['Wallpapers', 'Live video backgrounds of meadow and mountains.'],
      ['Window Color', 'Tint the glass and set its intensity.'],
      ['Gadgets', 'Clock, calendar and more, right on the desktop.'],
    ],
    art: `<div class="wl-a4"><div class="wl-shot"><img src="${BASE}media/wallpapers/meadow-thumb.jpg" alt="" draggable="false"><img src="${BASE}media/wallpapers/sierra-thumb.jpg" alt="" draggable="false"></div>
      <div class="wl-sw"><i style="--c:#3d8ae0"></i><i style="--c:#35b0a0"></i><i style="--c:#8a63d2"></i><i style="--c:#e06a8a"></i><i style="--c:#e8a53a"></i></div>
      <div class="wl-clock"><b></b><u></u></div><span class="wl-gear">${app('settings')}</span></div>`,
  },
  {
    title: 'Have fun',
    lead: 'Take a break whenever you like.',
    points: [
      ['Space Pinball', 'A classic table with flippers.'],
      ['Solitaire', 'Klondike, the way you remember it.'],
      ['Mines', 'Clear the field without a blast.'],
    ],
    art: `<div class="wl-a5">${tile(app('pinball'), 'Space Pinball')}${tile(app('solitaire'), 'Solitaire')}${tile(app('mines'), 'Mines')}</div>`,
  },
];

export const impl: Pick<AppManifest, 'mount'> = {
  mount({ win, os }) {
    win.body.classList.add('welcome');
    const SLIDES = buildSlides();
    let idx = 0;

    // ----- background music: fade in on open, fade out on close -----
    let audio: HTMLAudioElement | null = null;
    let fadeRaf = 0;
    const target = () => 0.5 * os.settings.get().volume;
    const fade = (to: number, ms: number, done?: () => void) => {
      cancelAnimationFrame(fadeRaf);
      if (!audio) return;
      const a = audio;
      const from = a.volume;
      const t0 = performance.now();
      const step = (now: number) => {
        const k = Math.min(1, (now - t0) / ms);
        a.volume = Math.max(0, Math.min(1, from + (to - from) * k));
        if (k < 1) fadeRaf = requestAnimationFrame(step);
        else done?.();
      };
      fadeRaf = requestAnimationFrame(step);
    };
    if (os.settings.get().sounds) {
      audio = new Audio(MUSIC);
      audio.loop = true;
      audio.volume = 0;
      audio.play().then(() => fade(target(), 2500)).catch(() => {
        audio = null; // autoplay refused: the tour stays silent
      });
    }
    let closing = false;
    win.onBeforeClose(() => {
      if (!closing) {
        closing = true;
        const a = audio;
        fade(0, 1200, () => {
          a?.pause();
        });
      }
      return true;
    });

    // ----- slides -----
    const track = h('div', { class: 'wl-track' });
    SLIDES.forEach((s, i) => {
      track.append(
        h(
          'section',
          { class: 'wl-slide' },
          h('div', { class: 'wl-art', html: s.art }),
          h(
            'div',
            { class: 'wl-copy' },
            h('small', {}, `${i + 1} of ${SLIDES.length}`),
            h('h1', {}, s.title),
            h('p', {}, s.lead),
            s.points ? h('ul', {}, ...s.points.map(([b, t]) => h('li', {}, h('b', {}, b), ' ', t))) : '',
          ),
        ),
      );
    });

    const back = h('button', { class: 'wl-btn', onclick: () => go(idx - 1) }, 'Back');
    const next = h('button', { class: 'wl-btn wl-primary', onclick: () => (idx === SLIDES.length - 1 ? win.close() : go(idx + 1)) }, 'Next');
    const skip = h('button', { class: 'wl-link', onclick: () => win.close() }, 'Skip tour');
    const dots = SLIDES.map((s, i) => h('button', { class: 'wl-dot', title: s.title, 'aria-label': s.title, onclick: () => go(i) }));

    function go(n: number) {
      idx = Math.max(0, Math.min(SLIDES.length - 1, n));
      track.style.transform = `translate3d(${-idx * 100}%,0,0)`;
      dots.forEach((d, i) => d.classList.toggle('on', i === idx));
      track.querySelectorAll('.wl-slide').forEach((el, i) => el.classList.toggle('cur', i === idx));
      back.style.visibility = idx === 0 ? 'hidden' : 'visible';
      skip.style.visibility = idx === SLIDES.length - 1 ? 'hidden' : 'visible';
      next.textContent = idx === SLIDES.length - 1 ? 'Begin' : 'Next';
    }

    win.body.append(
      h('div', { class: 'wl-stage' }, track),
      h(
        'div',
        { class: 'wl-foot' },
        h('div', { class: 'wl-nav' }, skip),
        h('div', { class: 'wl-dots' }, ...dots),
        h('div', { class: 'wl-nav r' }, back, next),
        h('span', { class: 'wl-ver' }, `MWX 7 · Version ${VERSION}`),
      ),
    );
    go(0);
  },
};
