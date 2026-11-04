import { bus } from './events';
import { play } from './sound';
import type { AppManifest, MenuDef, Rect, WindowHandle } from './types';

/**
 * Window manager.
 * - Aero-style glass frames with macOS traffic-light controls
 * - Drag, 8-way resize, double-click to maximize
 * - Aero Snap: drag to left/right edge = half screen, top edge = maximize
 * - Genie-style minimize into the dock icon
 */

export type WinState = 'normal' | 'max' | 'left' | 'right';

export interface Win {
  id: string;
  appId: string;
  manifest: AppManifest;
  title: string;
  el: HTMLDivElement;
  body: HTMLDivElement;
  minimized: boolean;
  state: WinState;
  rect: Rect;
  restoreRect: Rect | null;
  menus: MenuDef[];
  z: number;
  cleanup?: () => void;
  beforeClose: Array<() => boolean>;
}

export const MENUBAR_H = 30;
export const DOCK_RESERVE = 70;
/** Height of the dock when it stretches into a full-width bar under a maximized window. */
/** A full-screen window ends exactly at the dock's top edge. */
export const DOCK_FULL_H = 64;
const SNAP_EDGE = 6;

let layer: HTMLElement;
let preview: HTMLDivElement;
const wins = new Map<string, Win>();
let zTop = 10;
let activeId: string | null = null;
let seq = 0;
let minimizeTarget: (appId: string) => DOMRect | null = () => null;

export function initWM(container: HTMLElement): void {
  layer = container;
  preview = document.createElement('div');
  preview.className = 'snap-preview';
  layer.appendChild(preview);
  window.addEventListener('resize', () => {
    for (const w of wins.values()) {
      if (w.state !== 'normal') applyState(w, false);
      else clampIntoView(w);
    }
  });
}

/** The dock calls this so minimized windows fly into their icon. */
export function setMinimizeTarget(fn: (appId: string) => DOMRect | null): void {
  minimizeTarget = fn;
}

export function workArea(): Rect {
  return { x: 0, y: MENUBAR_H, w: window.innerWidth, h: Math.max(200, window.innerHeight - MENUBAR_H - DOCK_RESERVE) };
}

export const allWindows = (): Win[] => [...wins.values()];
export const windowsOf = (appId: string): Win[] => allWindows().filter((w) => w.appId === appId);
export const activeWindow = (): Win | null => (activeId ? wins.get(activeId) ?? null : null);

/* ---------- geometry helpers ---------- */

function setRect(w: Win, r: Rect): void {
  w.rect = { ...r };
  const s = w.el.style;
  s.left = `${Math.round(r.x)}px`;
  s.top = `${Math.round(r.y)}px`;
  s.width = `${Math.round(r.w)}px`;
  s.height = `${Math.round(r.h)}px`;
}

function stateRect(state: WinState): Rect | null {
  const wa = workArea();
  switch (state) {
    case 'max':
      // Edge to edge between the top bar and the full-width dock: the title bar
      // merges into the top bar, so there is no gap anywhere.
      return { x: 0, y: MENUBAR_H, w: window.innerWidth, h: Math.max(200, window.innerHeight - MENUBAR_H - DOCK_FULL_H) };
    case 'left':
      return { x: 0, y: wa.y, w: Math.round(wa.w / 2), h: wa.h };
    case 'right':
      return { x: Math.round(wa.w / 2), y: wa.y, w: wa.w - Math.round(wa.w / 2), h: wa.h };
    default:
      return null;
  }
}

/**
 * State changes (full screen, snap, restore, center) animate with FLIP: the window jumps to its
 * final layout once, then a GPU transform carries it from the old rectangle — like Windows 7's
 * DWM. Animating left/top/width/height re-laid out the app every frame, which stuttered.
 */
function withAnimation(w: Win, fn: () => void): void {
  const before = w.el.getBoundingClientRect();
  w.el.getAnimations().forEach((a) => a.id === 'flip' && a.cancel());
  fn();
  const after = w.el.getBoundingClientRect();
  if (!after.width || !after.height || reducedMotion()) return;
  const dx = before.left - after.left;
  const dy = before.top - after.top;
  const sx = before.width / after.width;
  const sy = before.height / after.height;
  if (Math.abs(dx) + Math.abs(dy) < 1 && Math.abs(sx - 1) + Math.abs(sy - 1) < 0.01) return;
  w.el.classList.add('anim');
  const a = w.el.animate(
    [
      { transformOrigin: '0 0', transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` },
      { transformOrigin: '0 0', transform: 'none' },
    ],
    { duration: 320, easing: 'cubic-bezier(.22,.9,.24,1)', id: 'flip' },
  );
  const done = () => w.el.classList.remove('anim');
  a.onfinish = done;
  a.oncancel = done;
}

function applyState(w: Win, animate = true): void {
  const run = () => {
    const r = stateRect(w.state);
    if (r) setRect(w, r);
    else if (w.restoreRect) {
      setRect(w, w.restoreRect);
      w.restoreRect = null;
    }
    w.el.classList.toggle('maximized', w.state === 'max');
    w.el.classList.toggle('snapped', w.state === 'left' || w.state === 'right');
    bus.emit('window:state', w);
  };
  if (animate) withAnimation(w, run);
  else run();
}

function setState(w: Win, state: WinState): void {
  if (w.state === state) return;
  if (w.state === 'normal') w.restoreRect = { ...w.rect };
  w.state = state;
  applyState(w);
}

function clampIntoView(w: Win): void {
  const r = { ...w.rect };
  r.x = Math.min(Math.max(r.x, -r.w + 120), window.innerWidth - 120);
  r.y = Math.min(Math.max(r.y, MENUBAR_H), window.innerHeight - 60);
  setRect(w, r);
}

export function toggleMaximize(id: string): void {
  const w = wins.get(id);
  if (!w || w.manifest.window?.resizable === false) return;
  setState(w, w.state === 'max' ? 'normal' : 'max');
}

export function snapWindow(id: string, state: WinState): void {
  const w = wins.get(id);
  if (w && w.manifest.window?.resizable !== false) setState(w, state);
}

/* ---------- lifecycle ---------- */

/** Default geometry: generous and always centered (windows never cascade). */
function initialRect(cfg: NonNullable<AppManifest['window']>): Rect {
  const wa = workArea();
  const resizable = cfg.resizable !== false;
  const baseW = cfg.width ?? 760;
  const baseH = cfg.height ?? 520;
  // Document-style windows grow with large screens; small utility windows (Task Manager, notes) keep their size.
  const grow = resizable && baseW >= 560;
  const width = Math.round(Math.min(grow ? Math.max(baseW, wa.w * 0.58) : baseW, wa.w - 40));
  const height = Math.round(Math.min(grow ? Math.max(baseH, wa.h * 0.72) : baseH, wa.h - 24));
  const x = Math.round((wa.w - width) / 2);
  const y = Math.round(wa.y + (wa.h - height) / 2);
  return {
    x: Math.min(Math.max(8, x), wa.w - width - 8),
    y: Math.min(Math.max(wa.y + 6, y), wa.y + wa.h - height),
    w: width,
    h: height,
  };
}

/** Double-click on the title bar: put the window back in the middle of the screen. */
export function centerWindow(id: string): void {
  const w = wins.get(id);
  if (!w) return;
  if (w.state !== 'normal') {
    w.state = 'normal';
    w.el.classList.remove('maximized', 'snapped');
  }
  const size = w.restoreRect ?? w.rect;
  w.restoreRect = null;
  const wa = workArea();
  const width = Math.min(size.w, wa.w - 16);
  const height = Math.min(size.h, wa.h - 8);
  withAnimation(w, () =>
    setRect(w, { x: Math.round((wa.w - width) / 2), y: Math.round(wa.y + (wa.h - height) / 2), w: width, h: height }),
  );
  bus.emit('window:state', w);
}

/** The window currently filling the screen (if any is visible). */
export function maximizedWindow(): Win | null {
  return allWindows().find((w) => w.state === 'max' && !w.minimized) ?? null;
}

export function openWindow(manifest: AppManifest, setup: (h: WindowHandle) => void | (() => void)): Win {
  const id = `w${++seq}`;
  const cfg = manifest.window ?? {};
  const { x, y, w: width, h: height } = initialRect(cfg);

  const el = document.createElement('div');
  el.className = 'win';
  el.setAttribute('role', 'dialog');
  el.tabIndex = -1;
  el.dataset.app = manifest.id;
  // Controls sit on the right (Windows placement) but keep the macOS traffic-light look.
  el.innerHTML = `
    <div class="win-titlebar">
      <div class="win-title"><span class="win-icon">${manifest.icon}</span><span class="win-title-text"></span></div>
      <div class="win-controls">
        <button class="wc wc-min" title="Minimize" aria-label="Minimize"></button>
        <button class="wc wc-max" title="Full screen" aria-label="Full screen"></button>
        <button class="wc wc-close" title="Close" aria-label="Close"></button>
      </div>
    </div>
    <div class="win-body"></div>`;

  const body = el.querySelector<HTMLDivElement>('.win-body')!;
  const titleText = el.querySelector<HTMLSpanElement>('.win-title-text')!;
  const titlebar = el.querySelector<HTMLDivElement>('.win-titlebar')!;

  const w: Win = {
    id,
    appId: manifest.id,
    manifest,
    title: manifest.name,
    el,
    body,
    minimized: false,
    state: 'normal',
    rect: { x, y, w: width, h: height },
    restoreRect: null,
    menus: [],
    z: 0,
    beforeClose: [],
  };
  titleText.textContent = w.title;
  setRect(w, w.rect);

  const resizable = cfg.resizable !== false;
  if (!resizable) el.classList.add('fixed');
  else addResizeHandles(w, cfg.minWidth ?? 280, cfg.minHeight ?? 180);

  el.querySelector('.wc-close')!.addEventListener('click', () => closeWindow(id));
  el.querySelector('.wc-min')!.addEventListener('click', () => minimizeWindow(id));
  el.querySelector('.wc-max')!.addEventListener('click', () => toggleMaximize(id));
  el.addEventListener('pointerdown', () => focusWindow(id), true);
  titlebar.addEventListener('dblclick', (e) => {
    if (!(e.target as HTMLElement).closest('.win-controls')) centerWindow(id);
  });
  enableDrag(w, titlebar);

  layer.appendChild(el);
  wins.set(id, w);

  const handle: WindowHandle = {
    id,
    body,
    setTitle(t) {
      w.title = t;
      titleText.textContent = t;
      bus.emit('window:title', w);
    },
    setMenus(m) {
      w.menus = m;
      bus.emit('window:menus', w);
    },
    close: () => closeWindow(id),
    focus: () => focusWindow(id),
    onBeforeClose(fn) {
      w.beforeClose.push(fn);
    },
  };

  try {
    const c = setup(handle);
    if (typeof c === 'function') w.cleanup = c;
  } catch (err) {
    console.error(`[wm] ${manifest.id} failed to mount`, err);
    body.innerHTML = `<div class="app-crash"><b>${manifest.name} stopped working.</b><br>${String(err)}</div>`;
  }

  el.animate(
    [
      { opacity: 0, transform: 'scale(.94) translateY(8px)' },
      { opacity: 1, transform: 'none' },
    ],
    { duration: 200, easing: 'cubic-bezier(.2,.8,.2,1)' },
  );

  bus.emit('window:open', w);
  focusWindow(id);
  return w;
}

export function focusWindow(id: string): void {
  const w = wins.get(id);
  if (!w) return;
  if (w.minimized) restore(w);
  w.z = ++zTop;
  w.el.style.zIndex = String(w.z);
  if (activeId !== id) {
    activeId = id;
    for (const v of wins.values()) v.el.classList.toggle('active', v.id === id);
    bus.emit('window:focus', w);
  }
}

/** Clicking the desktop takes focus away from every window, like Windows. */
export function blurWindows(): void {
  if (!activeId) return;
  activeId = null;
  for (const v of wins.values()) v.el.classList.remove('active');
  bus.emit('window:focus', null);
}

/**
 * Win7 "Show desktop": minimizes everything (a quick fade, no genie), and a
 * second press brings the same windows back in their original stacking order.
 */
let shownDesktop: Win[] = [];
export function showDesktop(): void {
  const visible = allWindows().filter((w) => !w.minimized);
  if (visible.length) {
    shownDesktop = visible.sort((a, b) => a.z - b.z);
    for (const w of visible) {
      w.minimized = true;
      w.el.classList.remove('active');
      bus.emit('window:minimize', w);
      void fade(w, false).then(() => {
        if (w.minimized) w.el.style.display = 'none';
      });
    }
    activeId = null;
    bus.emit('window:focus', null);
    play('minimize');
    return;
  }
  const back = shownDesktop.filter((w) => wins.has(w.id) && w.minimized);
  shownDesktop = [];
  for (const w of back) {
    w.minimized = false;
    bus.emit('window:restore', w);
    void fade(w, true);
    w.z = ++zTop;
    w.el.style.zIndex = String(w.z);
  }
  if (back.length) {
    play('restore');
    focusWindow(back[back.length - 1].id);
  }
}

function focusTopmost(): void {
  const next = allWindows()
    .filter((w) => !w.minimized)
    .sort((a, b) => b.z - a.z)[0];
  if (next) focusWindow(next.id);
  else {
    activeId = null;
    bus.emit('window:focus', null);
  }
}

/* ---------- genie ---------- */

const GENIE_MS = 540;
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const smooth = (x: number) => x * x * (3 - 2 * x);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
/** Room around the window so its drop shadow travels with it. */
const PAD = 56;

/** Scroll offsets of every scrolled element, by child-index path, so copies can be scrolled the same way. */
type ScrollMap = Array<{ path: number[]; t: number; l: number }>;
function readScroll(root: HTMLElement): ScrollMap {
  const out: ScrollMap = [];
  const walk = (el: Element, path: number[]) => {
    if (el.scrollTop || el.scrollLeft) out.push({ path, t: el.scrollTop, l: el.scrollLeft });
    for (let i = 0; i < el.children.length; i++) walk(el.children[i], [...path, i]);
  };
  walk(root, []);
  return out;
}
function applyScroll(root: Element, map: ScrollMap): void {
  for (const { path, t, l } of map) {
    let el: Element | undefined = root;
    for (const i of path) el = el?.children[i];
    if (el) {
      el.scrollTop = t;
      el.scrollLeft = l;
    }
  }
}
const scrolls = new WeakMap<Win, ScrollMap>();

/**
 * One live copy of the window — exactly as it looks right now: focus, scroll, typed text, canvas
 * pixels, frame and shadow. Real DOM, so text stays crisp, and nothing has to be rasterized first.
 */
function copyOf(w: Win, scroll: ScrollMap): HTMLElement {
  const c = w.el.cloneNode(true) as HTMLElement;
  c.querySelectorAll('.rz').forEach((n) => n.remove());
  // An iframe copy would reload its page; a blank page stands in for the few frames it is visible.
  c.querySelectorAll('iframe').forEach((f) => f.replaceWith(Object.assign(document.createElement('div'), { style: 'background:#fff;width:100%;height:100%' })));
  const srcF = w.el.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea');
  c.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea').forEach((f, i) => {
    if (srcF[i]) f.value = srcF[i].value;
  });
  const srcC = w.el.querySelectorAll('canvas');
  c.querySelectorAll('canvas').forEach((cv, i) => {
    try {
      cv.getContext('2d')?.drawImage(srcC[i], 0, 0);
    } catch {
      /* nothing drawn yet */
    }
  });
  c.removeAttribute('id');
  c.classList.remove('anim', 'peek-target');
  // Copies keep the real backdrop blur, so the glass looks exactly like the window's. Their strips add up
  // to one window's area, so the GPU cost is about that of the window itself.
  Object.assign(c.style, {
    left: `${PAD}px`, top: '0px', display: '', visibility: 'visible', opacity: '1', transform: 'none', zIndex: '0', transition: 'none',
  });
  c.dataset.scroll = JSON.stringify(scroll);
  return c;
}

/**
 * macOS genie on live copies of the window, cut into horizontal strips. Each strip gets its own
 * squeeze toward the dock icon and its own height (lower strips lead), and a clip-path trims it to
 * the exact funnel edge — so the window bends and pours into the icon as one surface. Only
 * transforms and clips change per frame: no rasterizing, no capture delay, no stutter.
 */
/**
 * CSS matrix3d that maps a w×h box (origin top-left) exactly onto the quad p0..p3 (clockwise from
 * top-left): a projective transform, so neighbouring strips share their edges and the funnel
 * outline is continuous — all on the compositor, nothing repainted.
 */
function quad(w: number, h: number, x0: number, y0: number, x1: number, y1: number, x2: number, y2: number, x3: number, y3: number): string {
  const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3;
  const dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3;
  let g = 0, k = 0;
  if (Math.abs(dx3) > 1e-6 || Math.abs(dy3) > 1e-6) {
    const det = dx1 * dy2 - dx2 * dy1 || 1e-6;
    g = (dx3 * dy2 - dx2 * dy3) / det;
    k = (dx1 * dy3 - dx3 * dy1) / det;
  }
  const a = x1 - x0 + g * x1, b = x3 - x0 + k * x3, c = x0;
  const d = y1 - y0 + g * y1, e = y3 - y0 + k * y3, f = y0;
  return `matrix3d(${a / w},${d / w},0,${g / w},${b / h},${e / h},0,${k / h},0,0,1,0,${c},${f},0,1)`;
}

/**
 * The window's glass, frozen: what its backdrop blur shows right now (the wallpaper under it), rendered
 * once into an image. The genie animates that like macOS animates its snapshot — a live blur on a moving
 * layer is recomputed every frame and shimmers.
 */
function bakeGlass(w: Win): Promise<string | null> {
  if (w.el.classList.contains('maximized')) return Promise.resolve(null);
  const layers = document.querySelectorAll<HTMLElement>('#desktop > .wp-layer');
  const L = layers[layers.length - 1];
  if (!L) return Promise.resolve(null);
  const { x, y, w: W, h: H } = w.rect;
  const M = 16; // margin, so the blur doesn't darken the edges
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const tmp = document.createElement('canvas');
  tmp.width = Math.round((W + M * 2) * dpr);
  tmp.height = Math.round((H + M * 2) * dpr);
  const g = tmp.getContext('2d')!;
  g.scale(dpr, dpr);
  g.translate(M - x, M - y);
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  try {
    const video = L.querySelector<HTMLVideoElement>('video.wp-video.on');
    const canvas = L.querySelector<HTMLCanvasElement>('canvas.wp-canvas-el');
    if (video && video.videoWidth) {
      const k = Math.max(vw / video.videoWidth, vh / video.videoHeight);
      const dw = video.videoWidth * k;
      const dh = video.videoHeight * k;
      g.drawImage(video, (vw - dw) / 2, (vh - dh) / 2, dw, dh);
    } else if (canvas) {
      g.drawImage(canvas, 0, 0, vw, vh);
      const glow = L.querySelector<HTMLCanvasElement>('canvas.wp-glow');
      if (glow) {
        g.globalCompositeOperation = 'lighter';
        g.filter = glow.style.filter || 'none';
        g.drawImage(glow, 0, 0, vw, vh);
      }
    } else return Promise.resolve(null);
  } catch {
    return Promise.resolve(null);
  }
  const out = document.createElement('canvas');
  out.width = Math.round(W * dpr);
  out.height = Math.round(H * dpr);
  const o = out.getContext('2d')!;
  const bf = getComputedStyle(w.el).backdropFilter;
  o.filter = bf && bf !== 'none' ? bf.replace(/blur\(([\d.]+)px\)/, (_, v) => `blur(${Number(v) * dpr}px)`) : 'none';
  o.drawImage(tmp, -M * dpr, -M * dpr);
  return new Promise((res) => out.toBlob((b) => res(b ? URL.createObjectURL(b) : null)));
}

interface GenieRun {
  /** Resolves true when it played to the end, false when another animation took over. */
  done: Promise<boolean>;
  /** Current progress (0 = window in place, 1 = inside the dock). */
  P(): number;
  /** Stop here; the layer stays on screen until the replacing animation shows its own (no blank frame). */
  interrupt(): () => void;
}
const genies = new Map<Win, GenieRun>();

function runGenie(w: Win, scroll: ScrollMap, t: DOMRect, from: number, to: number, onShown: () => void = () => {}, prevDispose?: () => void): GenieRun {
  const r = { x: w.rect.x - PAD, y: w.rect.y - PAD, w: w.rect.w + PAD * 2, h: w.rect.h + PAD * 2 };
  // End slightly in front of the icon centre, inside its lower half, fading as it slides under.
  // Funnel into the icon's width right at the dock's edge, so the window is already narrow when it slides
  // under the shelf (no wide, straight cut), and is fully faded by the time it is gone.
  const shelfTop = document.querySelector('#dock .dock-shelf')?.getBoundingClientRect().top ?? t.top;
  t = new DOMRect(t.left + t.width * 0.18, shelfTop - t.height * 0.25, t.width * 0.64, t.height * 0.6);
  const layer = document.createElement('div');
  layer.className = 'genie-layer';
  const n = Math.max(16, Math.min(28, Math.round(r.h / 26)));
  // Whole-pixel strip boundaries: every copy sits at an integer offset, so nothing shifts by a sub-pixel.
  // The whole title bar (and the shadow above it) is one strip, so no seam ever crosses the traffic lights
  // or the caption; the body below is split evenly.
  const top = PAD + 36;
  const B = [0, ...Array.from({ length: n }, (_, i) => Math.round(top + ((i + 1) * (r.h - top)) / n))];
  // Body strips reach 1px into the next one (identical pixels), so no hairline seam can open between them.
  const HS = B.slice(0, -1).map((b, i) => B[i + 1] - b + (i < n - 1 ? 1 : 0));
  const strips: HTMLElement[] = [];
  const copies: HTMLElement[] = [];
  const clipper = document.createElement('div');
  clipper.className = 'genie-clip';
  for (let i = 0; i < n; i++) {
    const s = document.createElement('div');
    s.className = 'genie-strip';
    Object.assign(s.style, { left: '0px', top: '0px', width: `${r.w}px`, height: `${HS[i]}px` });
    const c = copyOf(w, scroll);
    // The soft drop shadow is drawn once, by the shadow layer below; per-strip copies of it doubled up
    // where strips meet and flickered as they stretched. The crisp frame rings stay on the copies.
    c.style.boxShadow = w.el.classList.contains('maximized') ? 'none' : 'var(--glass-ring)';
    copies.push(c);
    // Only the title-bar strip keeps the live blur (the rest is the opaque body plus an 8px border).
    if (i > 0) Object.assign(c.style, { backdropFilter: 'none', webkitBackdropFilter: 'none' });
    c.style.top = `${PAD - B[i]}px`;
    s.append(c);

    clipper.append(s);
    strips.push(s);
  }
  // Hidden until every copied image has decoded: a copy shown a frame early drew icons as white boxes.
  layer.style.visibility = 'hidden';
  // Under the dock, and cut off at the shelf's top edge: through the dock's clear glass the window
  // would otherwise show as a pale blob. It pours down and vanishes beneath the icon.
  const shelf = document.querySelector('#dock .dock-shelf')?.getBoundingClientRect();
  // An overflow box, not clip-path or opacity on the layer: those would make it a backdrop root and the
  // copies' glass would stop blurring what is behind it.
  clipper.style.height = `${shelf ? shelf.top : window.innerHeight}px`;
  // One shadow for the whole window, exactly where the real one is; it fades as the window starts to bend.
  const shade = document.createElement('div');
  shade.className = 'genie-shadow';
  const cs = getComputedStyle(w.el);
  Object.assign(shade.style, {
    left: `${w.rect.x}px`, top: `${w.rect.y}px`, width: `${w.rect.w}px`, height: `${w.rect.h}px`,
    borderRadius: cs.borderRadius,
    boxShadow: w.el.classList.contains('maximized') ? 'none' : 'var(--shadow-win)',
  });
  layer.append(shade, clipper);
  document.body.append(layer);
  for (const s of strips) applyScroll(s.firstElementChild!, scroll);
  const imgs = [...layer.querySelectorAll('img')];
  imgs.forEach((im) => (im.loading = 'eager'));
  const glass = bakeGlass(w).then((url) => {
    if (!url) return;
    const cs0 = getComputedStyle(w.el);
    for (const c of copies) {
      Object.assign(c.style, {
        backdropFilter: 'none',
        webkitBackdropFilter: 'none',
        backgroundImage: `${cs0.backgroundImage}, url("${url}")`,
        backgroundSize: `${cs0.backgroundSize}, ${w.rect.w}px ${w.rect.h}px`,
        backgroundPosition: `${cs0.backgroundPosition}, 0 0`,
        backgroundRepeat: `${cs0.backgroundRepeat}, no-repeat`,
      });
    }
    void done.then(() => URL.revokeObjectURL(url));
  });
  const decoded = Promise.race([
    Promise.all([glass, ...imgs.map((im) => im.decode().catch(() => undefined))]),
    new Promise((res) => window.setTimeout(res, 160)),
  ]);

  const Y = (v: number, P: number) => lerp(r.y + v * r.h, t.top + v * t.height, smooth(clamp01(P * 1.6 - (1 - v) * 0.6)));
  const Q = (v: number, P: number) => smooth(clamp01(P * 2.2 - (1 - v) * 1.2));
  const edge = (v: number, P: number) => {
    const q = Q(v, P);
    return [lerp(r.x, t.left, q), lerp(r.x + r.w, t.right, q)];
  };
  const place = (P: number) => {
    const op = String(1 - smooth(clamp01((P - 0.5) / 0.5)));
    for (const c of copies) c.style.opacity = op;
    shade.style.opacity = String(1 - smooth(clamp01(P / 0.3)));
    // The title-bar strip moves as an affine parallelogram: backdrop blur on a perspective (matrix3d) layer
    // re-samples differently every frame and shimmered. The next strip starts exactly on its bottom edge.
    let carry: [number, number, number] | null = null;
    for (let i = 0; i < n; i++) {
      const y0 = Y(B[i] / r.h, P);
      // Neighbours share the exact same whole-pixel edge: no seam, no overlap, no doubled glass.
      const y1 = Y((B[i] + HS[i]) / r.h, P);
      const [lt, rt] = edge(B[i] / r.h, P);
      const [lb, rb] = edge((B[i] + HS[i]) / r.h, P);
      // Continuous (not pixel-snapped) corners: snapping made strips stretch in 1px steps, which made the
      // lights and shadows flicker. Content offsets are whole pixels, so the first frame is exact.
      if (i === 0) {
        const dx = (lb + rb - lt - rt) / 2;
        const sx = (rt - lt) / r.w;
        const sy = (y1 - y0) / HS[0];
        strips[0].style.transform = `matrix(${sx}, 0, ${dx / HS[0]}, ${sy}, ${lt}, ${y0})`;
        // where the next strip must begin (its top edge = this strip's bottom edge, minus the 1px overlap)
        const k = (HS[0] - 1) / HS[0];
        carry = [lt + dx * k, rt + dx * k, y0 + (y1 - y0) * k];
        continue;
      }
      if (carry) {
        const [cl, cr, cy] = carry;
        carry = null;
        strips[i].style.transform = quad(r.w, HS[i], cl, cy, cr, cy, rb, y1, lb, y1);
        continue;
      }
      strips[i].style.transform = quad(r.w, HS[i], lt, y0, rt, y0, rb, y1, lb, y1);
    }
  };
  let cur = from;
  let raf = 0;
  let stopped = false;
  let shown = false;
  let finish: (ok: boolean) => void = () => {};
  place(cur);
  // A click mid-animation turns it around from wherever it is, at the same speed.
  const ms = Math.max(140, GENIE_MS * Math.abs(to - from));
  const done = new Promise<boolean>((resolve) => (finish = resolve));
  void decoded.then(() => {
    if (stopped) return;
    layer.style.visibility = '';
    shown = true;
    prevDispose?.();
    onShown();
    const start = performance.now();
    const frame = (now: number) => {
      if (stopped) return;
      const p = Math.min(1, (now - start) / ms);
      const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      cur = from + (to - from) * e;
      place(cur);
      if (p < 1) raf = requestAnimationFrame(frame);
      else {
        layer.remove();
        finish(true);
      }
    };
    raf = requestAnimationFrame(frame);
  });
  return {
    done,
    P: () => cur,
    interrupt() {
      stopped = true;
      cancelAnimationFrame(raf);
      finish(false);
      // Not on screen yet: whatever it was going to replace is still showing and must go with it.
      return () => {
        if (!shown) prevDispose?.();
        layer.remove();
      };
    },
  };
}

function fade(w: Win, reverse: boolean): Promise<void> {
  const frames = [
    { opacity: 1, transform: 'none' },
    { opacity: 0, transform: 'translateY(30px) scale(.9)' },
  ];
  w.el.style.display = '';
  w.el.style.visibility = '';
  const a = w.el.animate(reverse ? [...frames].reverse() : frames, { duration: 220, easing: 'ease' });
  return a.finished.then(
    () => undefined,
    () => undefined,
  );
}

export function minimizeWindow(id: string): void {
  const w = wins.get(id);
  if (!w || w.minimized) return;
  w.minimized = true;
  const target = minimizeTarget(w.appId);
  // Interrupting a restore: turn around from where it is (its window copies are already on screen).
  const prev = genies.get(w);
  const from = prev ? prev.P() : 0;
  const dispose = prev?.interrupt();
  const scroll = prev ? scrolls.get(w) ?? [] : readScroll(w.el);
  scrolls.set(w, scroll);
  play('minimize');
  void (async () => {
    if (target && !reducedMotion()) {
      // visibility (not display) hides the real window: the copies' SVG icons take their gradients from
      // the original's <defs> (same ids), and display:none would paint those icons white.
      const g = runGenie(w, scroll, target, from, 1, () => (w.el.style.visibility = 'hidden'), dispose);
      genies.set(w, g);
      if (!(await g.done)) return; // a restore took over
      genies.delete(w);
      w.el.style.visibility = '';
    } else {
      dispose?.();
      await fade(w, false);
    }
    // Only now does the rest of the shell hear about it: the top bar keeps its full-screen look and the
    // window its focus for the whole animation.
    bus.emit('window:minimize', w);
    if (w.minimized) {
      w.el.style.display = 'none';
      w.el.classList.remove('active');
      if (activeId === id) {
        activeId = null;
        focusTopmost();
      }
    }
  })();
}

function restore(w: Win): void {
  w.minimized = false;
  play('restore');
  const target = minimizeTarget(w.appId);
  const scroll = scrolls.get(w) ?? [];
  bus.emit('window:restore', w);
  const prev = genies.get(w);
  const show = () => {
    w.el.style.display = '';
    w.el.style.visibility = '';
    // display:none drops scroll offsets; put them back.
    applyScroll(w.el, scroll);
  };
  if (!target || reducedMotion()) {
    prev?.interrupt()();
    genies.delete(w);
    show();
    void fade(w, true);
    return;
  }
  // Focused from the first frame: the copies wear the active look the window will have.
  w.el.classList.add('active');
  w.el.getAnimations().forEach((a) => a.cancel());
  // Restoring from an Aero Peek thumbnail: Peek is already showing the window in place, so (like Win7)
  // it simply stays.
  if (!prev && w.el.style.display !== 'none') {
    w.el.style.visibility = '';
    return;
  }
  // Interrupting a minimize: turn around from where it is.
  const from = prev ? prev.P() : 1;
  const dispose = prev?.interrupt();
  w.el.style.display = '';
  w.el.style.visibility = 'hidden';
  applyScroll(w.el, scroll);
  const g = runGenie(w, scroll, target, from, 0, () => {}, dispose);
  genies.set(w, g);
  void g.done.then((ok) => {
    if (!ok) return; // a minimize took over
    genies.delete(w);
    show();
  });
}

export function closeWindow(id: string, force = false): void {
  const w = wins.get(id);
  if (!w) return;
  if (!force && w.beforeClose.some((fn) => fn() === false)) return;
  wins.delete(id);
  try {
    w.cleanup?.();
  } catch (err) {
    console.error(err);
  }
  if (!force) play('close');
  w.el.style.pointerEvents = 'none';
  // Win7-style close: the window recedes and fades.
  const anim = w.el.animate(
    [
      { opacity: 1, transform: 'none' },
      { opacity: 0, transform: 'scale(.88) translateY(14px)' },
    ],
    { duration: 210, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' },
  );
  anim.onfinish = () => w.el.remove();
  bus.emit('window:close', w);
  if (activeId === id) {
    activeId = null;
    focusTopmost();
  }
}

/* ---------- drag + snap ---------- */

function enableDrag(w: Win, titlebar: HTMLElement): void {
  titlebar.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest('.win-controls')) return;
    const start = { x: e.clientX, y: e.clientY };
    const startRect = { ...w.rect };
    const grabRatio = (e.clientX - startRect.x) / startRect.w;
    let off = { x: e.clientX - startRect.x, y: e.clientY - startRect.y };
    let dragging = false;
    let snap: WinState = 'normal';
    titlebar.setPointerCapture(e.pointerId);

    const onMove = (ev: PointerEvent) => {
      if (!dragging) {
        if (Math.hypot(ev.clientX - start.x, ev.clientY - start.y) < 4) return;
        dragging = true;
        w.el.classList.add('dragging');
        if (w.state !== 'normal') {
          // Tear off a maximized / snapped window: restore its size under the cursor.
          const r = w.restoreRect ?? { ...startRect, w: 640, h: 440 };
          w.state = 'normal';
          w.restoreRect = null;
          w.el.classList.remove('maximized', 'snapped');
          off = { x: r.w * grabRatio, y: off.y };
          setRect(w, { x: ev.clientX - off.x, y: startRect.y, w: r.w, h: r.h });
        }
      }
      const x = ev.clientX - off.x;
      const y = Math.max(MENUBAR_H, ev.clientY - off.y);
      setRect(w, { ...w.rect, x, y });

      const resizable = w.manifest.window?.resizable !== false;
      snap = !resizable
        ? 'normal'
        : ev.clientX <= SNAP_EDGE
          ? 'left'
          : ev.clientX >= window.innerWidth - SNAP_EDGE
            ? 'right'
            : ev.clientY <= MENUBAR_H + 2
              ? 'max'
              : 'normal';
      showPreview(stateRect(snap));
    };

    const onUp = () => {
      titlebar.removeEventListener('pointermove', onMove);
      titlebar.removeEventListener('pointerup', onUp);
      titlebar.removeEventListener('pointercancel', onUp);
      w.el.classList.remove('dragging');
      showPreview(null);
      if (dragging && snap !== 'normal') setState(w, snap);
    };

    titlebar.addEventListener('pointermove', onMove);
    titlebar.addEventListener('pointerup', onUp);
    titlebar.addEventListener('pointercancel', onUp);
  });
}

function showPreview(r: Rect | null): void {
  if (!r) {
    preview.classList.remove('visible');
    return;
  }
  Object.assign(preview.style, {
    left: `${r.x + 6}px`,
    top: `${r.y + 6}px`,
    width: `${r.w - 12}px`,
    height: `${r.h - 12}px`,
  });
  preview.classList.add('visible');
}

/* ---------- resize ---------- */

function addResizeHandles(w: Win, minW: number, minH: number): void {
  for (const dir of ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']) {
    const h = document.createElement('div');
    h.className = `rz rz-${dir}`;
    w.el.appendChild(h);
    h.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      focusWindow(w.id);
      if (w.state !== 'normal') {
        w.state = 'normal';
        w.restoreRect = null;
        w.el.classList.remove('maximized', 'snapped');
      }
      const s = { ...w.rect };
      const sx = e.clientX;
      const sy = e.clientY;
      h.setPointerCapture(e.pointerId);
      w.el.classList.add('resizing');

      const onMove = (ev: PointerEvent) => {
        const dx = ev.clientX - sx;
        const dy = ev.clientY - sy;
        const r = { ...s };
        if (dir.includes('e')) r.w = Math.max(minW, s.w + dx);
        if (dir.includes('w')) {
          r.w = Math.max(minW, s.w - dx);
          r.x = s.x + (s.w - r.w);
        }
        if (dir.includes('s')) r.h = Math.max(minH, s.h + dy);
        if (dir.includes('n')) {
          r.h = Math.max(minH, s.h - dy);
          r.y = s.y + (s.h - r.h);
          if (r.y < MENUBAR_H) {
            r.h -= MENUBAR_H - r.y;
            r.y = MENUBAR_H;
          }
        }
        setRect(w, r);
      };
      const onUp = () => {
        h.removeEventListener('pointermove', onMove);
        h.removeEventListener('pointerup', onUp);
        h.removeEventListener('pointercancel', onUp);
        w.el.classList.remove('resizing');
      };
      h.addEventListener('pointermove', onMove);
      h.addEventListener('pointerup', onUp);
      h.addEventListener('pointercancel', onUp);
    });
  }
}
