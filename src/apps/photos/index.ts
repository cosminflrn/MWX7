import { basename } from '../../core/fs';
import type { AppManifest, VFS } from '../../core/types';
import { h } from '../../ui/dom';
import './photos.css';

const PICTURES = '/Pictures';
const IMG_EXT = /\.(jpe?g|png|webp)$/i;
const POINTER = 'mwx-media:';
const BASE = import.meta.env.BASE_URL;
const SLIDE_MS = 4200;

/** Bundled sample pictures (see public/media/CREDITS.md). The VFS stores text, so each file holds a pointer to the asset. */
const BUNDLED = [
  { file: 'Cliffs and Bay.jpg', src: 'media/pictures/cliffs-and-bay.jpg' },
  { file: 'Alpine Lake.jpg', src: 'media/pictures/alpine-lake.jpg' },
  { file: 'Snowy Peaks and Moon.jpg', src: 'media/pictures/snowy-peaks-moon.jpg' },
  { file: 'Aurora over Snow.jpg', src: 'media/pictures/aurora-over-snow.jpg' },
  { file: 'Coastal Ridge.jpg', src: 'media/pictures/coastal-ridge.jpg' },
  { file: 'White Sand Beach.jpg', src: 'media/pictures/white-sand-beach.jpg' },
];

interface Pic {
  path: string;
  name: string;
  url: string;
}

const urlFromContent = (c: string): string | null => {
  if (c.startsWith(POINTER)) return BASE + c.slice(POINTER.length);
  if (c.startsWith('data:image') || c.startsWith('blob:') || /^https?:\/\//.test(c)) return c;
  return null;
};

async function ensureSeeded(fs: VFS): Promise<void> {
  if ((await fs.list(PICTURES)).some((f) => f.type !== 'dir' && IMG_EXT.test(f.name))) return;
  await fs.mkdir(PICTURES);
  for (const b of BUNDLED) await fs.write(`${PICTURES}/${b.file}`, POINTER + b.src);
}

async function loadPics(fs: VFS): Promise<Pic[]> {
  const out: Pic[] = [];
  for (const f of await fs.list(PICTURES)) {
    if (f.type === 'dir' || !IMG_EXT.test(f.name)) continue;
    const url = urlFromContent(f.content);
    if (url) out.push({ path: f.path, name: f.name, url });
  }
  return out.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
}

const svg = (d: string, fill = false) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}" ${fill ? 'fill="currentColor"' : 'fill="none"'} stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const I = {
  prev: svg('M15 5 8 12l7 7'),
  next: svg('m9 5 7 7-7 7'),
  play: svg('M8 5.500v13l11-6.500Z', true),
  rotL: svg('M5 9a8 8 0 1 1-.5 6M5 4v5h5'),
  rotR: svg('M19 9a8 8 0 1 0 .5 6M19 4v5h-5'),
  fit: svg('M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5'),
  actual: svg('M10 4H4v6M14 4h6v6M10 20H4v-6M14 20h6v-6M9 9l6 6M15 9l-6 6'),
  del: svg('M5 7h14M9 7V4.500h6V7M7 7l1 13h8l1-13M10 11v6M14 11v6'),
  close: svg('M6 6l12 12M18 6 6 18'),
};

export const impl: Pick<AppManifest, 'mount'> = {
  mount({ win, args, fs, os }) {
    win.body.classList.add('ph');
    let pics: Pic[] = [];
    let index = -1;
    let rot = 0;
    let actual = false;
    let panX = 0;
    let panY = 0;
    let cur: HTMLImageElement | null = null;
    let token = 0;
    let slide: { el: HTMLElement; timer: number; hide: number; flip: boolean; i: number } | null = null;

    const stage = h('div', { class: 'ph-stage' });
    const nameTag = h('div', { class: 'ph-name' });
    const count = h('div', { class: 'ph-count' });
    const btn = (cls: string, label: string, html: string, onclick: () => void) => h('button', { class: `ph-b ${cls}`.trim(), 'aria-label': label, title: label, html, onclick });
    const prev = btn('', 'Previous', I.prev, () => step(-1));
    const next = btn('', 'Next', I.next, () => step(1));
    const zoom = btn('', 'Actual size', I.actual, () => toggleZoom());
    const show = btn('big', 'Play slideshow', I.play, () => startSlide());
    const rotL = btn('', 'Rotate counterclockwise', I.rotL, () => rotate(-90));
    const rotR = btn('', 'Rotate clockwise', I.rotR, () => rotate(90));
    const del = btn('del', 'Delete', I.del, () => void remove());
    // 3-column grid (1fr auto 1fr) keeps the slideshow button dead-centre whatever the side groups hold.
    const bar = h('div', { class: 'ph-bar' },
      h('div', { class: 'ph-side l' }, count, prev, zoom),
      show,
      h('div', { class: 'ph-side r' }, rotL, rotR, next, h('span', { class: 'ph-sep' }), del));
    win.body.append(stage, bar);
    stage.append(nameTag);

    /** Scale that makes the (rotated) image fit the stage; never upscales past 100% like Win7. */
    const fitScale = (img: HTMLImageElement): number => {
      const odd = Math.abs(rot / 90) % 2 === 1;
      const iw = odd ? img.naturalHeight : img.naturalWidth;
      const ih = odd ? img.naturalWidth : img.naturalHeight;
      return Math.min(1, (stage.clientWidth - 40) / iw, (stage.clientHeight - 40) / ih) || 1;
    };
    const clampPan = (img: HTMLImageElement, s: number) => {
      const odd = Math.abs(rot / 90) % 2 === 1;
      const w = (odd ? img.naturalHeight : img.naturalWidth) * s;
      const hh = (odd ? img.naturalWidth : img.naturalHeight) * s;
      const mx = Math.max(0, (w - stage.clientWidth) / 2 + 20);
      const my = Math.max(0, (hh - stage.clientHeight) / 2 + 20);
      panX = Math.max(-mx, Math.min(mx, panX));
      panY = Math.max(-my, Math.min(my, panY));
    };
    const apply = () => {
      if (!cur) return;
      const s = actual ? 1 : fitScale(cur);
      if (actual) clampPan(cur, s);
      else panX = panY = 0;
      cur.style.transform = `translate(${panX}px, ${panY}px) translate(-50%, -50%) rotate(${rot}deg) scale(${s})`;
      const canPan = actual && (cur.naturalWidth > stage.clientWidth || cur.naturalHeight > stage.clientHeight);
      stage.classList.toggle('pan', canPan);
    };
    const animated = (fn: () => void) => {
      cur?.classList.add('tx');
      fn();
      apply();
    };
    const toggleZoom = () => {
      animated(() => {
        actual = !actual;
        panX = panY = 0;
      });
      zoom.innerHTML = actual ? I.fit : I.actual;
      zoom.title = actual ? 'Fit to window' : 'Actual size';
      zoom.setAttribute('aria-label', zoom.title);
    };
    const rotate = (deg: number) => animated(() => (rot += deg));

    const refreshUi = () => {
      const n = pics.length;
      const p = pics[index];
      win.setTitle(p ? `${p.name} — Photo Viewer` : 'Photo Viewer');
      nameTag.textContent = p?.name ?? '';
      count.textContent = n ? `${index + 1} of ${n}` : '';
      [prev, next].forEach((b) => (b.disabled = n < 2));
      [zoom, show, rotL, rotR, del].forEach((b) => (b.disabled = !n));
      show.disabled = n < 2;
    };

    const showEmpty = () => {
      cur = null;
      stage.querySelectorAll('.ph-img').forEach((n) => n.remove());
      stage.querySelector('.ph-empty')?.remove();
      stage.append(h('div', { class: 'ph-empty' }, h('b', {}, 'No pictures to show'), h('small', {}, 'Add .jpg, .png or .webp files to your Pictures folder.')));
      refreshUi();
    };

    const go = async (i: number) => {
      if (!pics.length) return showEmpty();
      index = (i + pics.length) % pics.length;
      const my = ++token;
      const p = pics[index];
      refreshUi();
      const img = h('img', { class: 'ph-img', alt: p.name, draggable: false });
      img.src = p.url;
      try {
        await img.decode();
      } catch {
        if (my !== token) return;
        os.notify('Photo Viewer', `Couldn't open ${p.name}`);
      }
      if (my !== token) return;
      stage.querySelector('.ph-empty')?.remove();
      const old = cur;
      rot = 0;
      actual = false;
      panX = panY = 0;
      zoom.innerHTML = I.actual;
      zoom.title = 'Actual size';
      img.style.width = `${img.naturalWidth}px`;
      img.style.height = `${img.naturalHeight}px`;
      cur = img;
      stage.insertBefore(img, nameTag);
      apply();
      requestAnimationFrame(() => img.classList.add('in'));
      if (old) {
        old.classList.remove('in');
        setTimeout(() => old.remove(), 260);
      }
    };
    const step = (d: number) => void go(index + d);

    const remove = async () => {
      const p = pics[index];
      if (!p) return;
      await fs.mkdir('/Trash');
      let target = p.name;
      for (let n = 2; await fs.exists(`/Trash/${target}`); n++) target = p.name.replace(/(\.[^.]*)?$/, ` (${n})$1`);
      if (target !== p.name) await fs.rename(p.path, `${PICTURES}/${target}`).catch(() => undefined);
      await fs.move(target !== p.name ? `${PICTURES}/${target}` : p.path, '/Trash');
      pics.splice(index, 1);
      void go(Math.min(index, pics.length - 1));
    };

    /* ---------- slideshow ---------- */
    const layer = (): HTMLImageElement => h('img', { class: 'ph-show-img', alt: '', draggable: false });
    const startSlide = () => {
      if (slide || pics.length < 2) return;
      const a = layer();
      const b = layer();
      const x = h('button', { class: 'ph-show-x', 'aria-label': 'End slideshow', title: 'End slideshow', html: I.close, onclick: (e: Event) => {
        e.stopPropagation();
        stopSlide();
      } });
      const el = h('div', { class: 'ph-show', onclick: () => stopSlide() }, a, b, x);
      win.body.append(el);
      const s = { el, timer: 0, hide: 0, flip: false, i: index };
      slide = s;
      const layers = [a, b];
      const showAt = async (i: number) => {
        s.i = (i + pics.length) % pics.length;
        const next = layers[s.flip ? 1 : 0];
        const old = layers[s.flip ? 0 : 1];
        s.flip = !s.flip;
        next.src = pics[s.i].url;
        try {
          await next.decode();
        } catch {
          /* show whatever loaded */
        }
        if (slide !== s) return;
        // Restart the drift animation by toggling the class on a reflow boundary.
        next.classList.remove('in');
        void next.offsetWidth;
        next.classList.add('in');
        old.classList.remove('in');
      };
      const poke = () => {
        el.classList.add('hot');
        clearTimeout(s.hide);
        s.hide = window.setTimeout(() => el.classList.remove('hot'), 2200);
      };
      el.addEventListener('mousemove', poke);
      poke();
      requestAnimationFrame(() => el.classList.add('on'));
      void showAt(index);
      s.timer = window.setInterval(() => void showAt(s.i + 1), SLIDE_MS);
    };
    const stopSlide = () => {
      const s = slide;
      if (!s) return;
      slide = null;
      clearInterval(s.timer);
      clearTimeout(s.hide);
      s.el.classList.remove('on');
      setTimeout(() => s.el.remove(), 340);
      if (s.i !== index) void go(s.i);
    };

    // Dragging pans an image shown at 100%.
    stage.addEventListener('mousedown', (e) => {
      if (!stage.classList.contains('pan') || e.button !== 0) return;
      e.preventDefault();
      cur?.classList.remove('tx');
      stage.classList.add('panning');
      const sx = e.clientX - panX;
      const sy = e.clientY - panY;
      const move = (m: MouseEvent) => {
        panX = m.clientX - sx;
        panY = m.clientY - sy;
        apply();
      };
      const up = () => {
        stage.classList.remove('panning');
        removeEventListener('mousemove', move);
        removeEventListener('mouseup', up);
      };
      addEventListener('mousemove', move);
      addEventListener('mouseup', up);
    });
    stage.addEventListener('dblclick', () => pics.length && toggleZoom());

    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        cur?.classList.remove('tx');
        apply();
      });
    });
    ro.observe(stage);

    win.setMenus([
      { label: 'File', items: [
        { label: 'Open Pictures Folder', action: () => os.launch('explorer', { path: PICTURES }) },
        { separator: true },
        { label: 'Move to Trash', action: () => void remove() },
      ] },
      { label: 'View', items: [
        { label: 'Slideshow', action: startSlide },
        { label: 'Fit to Window / Actual Size', action: toggleZoom },
        { separator: true },
        { label: 'Rotate Counterclockwise', action: () => rotate(-90) },
        { label: 'Rotate Clockwise', action: () => rotate(90) },
      ] },
    ]);

    refreshUi();
    void (async () => {
      await ensureSeeded(fs);
      pics = await loadPics(fs);
      // A picture opened from elsewhere (e.g. the Desktop) joins the list so it still opens.
      if (typeof args.path === 'string' && IMG_EXT.test(args.path) && !pics.some((p) => p.path === args.path)) {
        const c = await fs.read(args.path);
        const url = c ? urlFromContent(c) : null;
        if (url) pics.unshift({ path: args.path, name: basename(args.path), url });
      }
      const want = typeof args.path === 'string' ? pics.findIndex((p) => p.path === args.path) : -1;
      void go(want >= 0 ? want : 0);
      if (typeof args.path === 'string' && want < 0 && args.path) os.notify('Photo Viewer', `Couldn't open ${basename(args.path)}`);
    })();

    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
      if (slide) {
        clearInterval(slide.timer);
        clearTimeout(slide.hide);
        slide = null;
      }
    };
  },
};
