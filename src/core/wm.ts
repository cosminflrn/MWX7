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
  const width = Math.round(Math.min(resizable ? Math.max(baseW, wa.w * 0.58) : baseW, wa.w - 40));
  const height = Math.round(Math.min(resizable ? Math.max(baseH, wa.h * 0.72) : baseH, wa.h - 24));
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
  el.querySelector('.wc-min')!.addEventListener('pointerdown', (e) => (e as PointerEvent).button === 0 && prepareMinimize(id));
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
    refreshSnapshot(w);
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

const GENIE_MS = 520;
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const smooth = (x: number) => x * x * (3 - 2 * x);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/**
 * Rasterizes the window once (DOM → canvas). The glass is replaced by a solid
 * frame colour because backdrop blur can't be captured.
 */
let toCanvasFn: typeof import('html-to-image').toCanvas | null = null;
const loadRasterizer = async () => (toCanvasFn ??= (await import('html-to-image')).toCanvas);

/** Backdrop blur can't be captured, so the snapshot gets an opaque version of the current glass colour. */
function solidGlass(active = true): string {
  const cs = getComputedStyle(document.documentElement);
  const [r, g, b] = cs.getPropertyValue('--glass-rgb').split(',').map((v) => Number(v) || 0);
  const a = Math.min(0.9, Number(cs.getPropertyValue('--glass-a')) || 0.46);
  // Translucent like the real frame (the canvas keeps alpha), just without the blur.
  const k = active ? 1 : 0.55;
  return `linear-gradient(rgba(255,255,255,.4), rgba(255,255,255,.14) 34px, rgba(255,255,255,.08)), rgba(${r},${g},${b},${Math.min(0.92, (a + 0.18) * k).toFixed(2)})`;
}

/** Room around the window in the snapshot, so its drop shadow travels with it. */
const SNAP_PAD = 36;

/**
 * Clones don't keep scroll positions, so a scrolled pane would be captured at its top. While
 * rasterizing, each scrolled element is reset to 0 and its children are shifted by the same
 * amount — pixel-identical on screen — then everything is put back.
 */
function freezeScroll(root: HTMLElement): () => void {
  const undo: Array<() => void> = [];
  root.querySelectorAll<HTMLElement>('*').forEach((el) => {
    const { scrollTop: t, scrollLeft: l } = el;
    if (!t && !l) return;
    const kids = [...el.children] as HTMLElement[];
    const prev = kids.map((k) => k.style.transform);
    el.scrollTop = 0;
    el.scrollLeft = 0;
    kids.forEach((k, i) => (k.style.transform = `translate(${-l}px, ${-t}px) ${prev[i]}`.trim()));
    undo.push(() => {
      kids.forEach((k, i) => (k.style.transform = prev[i]));
      el.scrollTop = t;
      el.scrollLeft = l;
    });
  });
  return () => undo.reverse().forEach((f) => f());
}

/** The window exactly as it looks now — focus, scroll position, frame and shadow — as a canvas. */
async function snapshot(w: Win, budget = 4000, exact = true): Promise<HTMLCanvasElement | null> {
  const toCanvas = await loadRasterizer();
  const r = w.el.getBoundingClientRect();
  const thaw = exact ? freezeScroll(w.el) : () => {};
  const job = toCanvas(w.el, {
    pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
    skipFonts: true,
    width: Math.round(r.width) + SNAP_PAD * 2,
    height: Math.round(r.height) + SNAP_PAD * 2,
    filter: (n) => !(n instanceof HTMLElement && n.classList.contains('rz')),
    style: {
      // html-to-image also inlines the logical inset properties, which would win over left/top.
      left: '0',
      top: '0',
      insetInlineStart: '0',
      insetBlockStart: '0',
      margin: `${SNAP_PAD}px`,
      // html-to-image sizes the clone to the canvas (which includes the shadow padding); pin the window to its real size.
      width: `${Math.round(r.width)}px`,
      height: `${Math.round(r.height)}px`,
      boxSizing: 'border-box',
      transform: 'none',
      opacity: '1',
      // Backdrop blur can't be captured; the glass keeps its tint and stays see-through.
      backdropFilter: 'none',
      background: solidGlass(w.el.classList.contains('active')),
    },
  }).catch(() => null);
  void job.then(thaw);
  const timeout = new Promise<null>((res) => window.setTimeout(() => res(null), budget));
  return Promise.race([job, timeout]);
}

/**
 * The first rasterization is slow (module load, image embedding), which made
 * the first genie of a session stutter. Warm everything up in idle time and
 * keep a recent snapshot of each window so minimizing always starts instantly.
 */
const idle = (fn: () => void) => {
  const ric = (window as unknown as { requestIdleCallback?: (f: () => void, o: object) => number }).requestIdleCallback;
  if (ric) ric.call(window, fn, { timeout: 1500 });
  else window.setTimeout(fn, 300);
};

// One throwaway rasterization per window in idle time loads html-to-image's caches (embedded
// icons, styles), so the real capture at minimize time is quick. The result is never shown.
const primed = new WeakSet<Win>();
function refreshSnapshot(w: Win): void {
  if (primed.has(w)) return;
  primed.add(w);
  idle(() => {
    if (wins.has(w.id) && !w.minimized) void snapshot(w, 4000, false);
  });
}

export function warmUpGenie(): void {
  idle(() => void loadRasterizer());
}

/**
 * macOS-style genie: the snapshot is redrawn every frame in 2px rows. Each row
 * gets its own horizontal squeeze (an S-curve funnel toward the dock icon) and
 * its own vertical position, with lower rows leading — so the window bends and
 * pours into the icon as one continuous surface.
 */
function runGenie(snap: HTMLCanvasElement, r: Rect, t: DOMRect, reverse: boolean): Promise<void> {
  const cv = document.createElement('canvas');
  cv.className = 'genie-layer';
  // The window ends up *behind* the dock icon: start slightly in front of the
  // icon centre and finish inside its lower half, fading as it slides under.
  t = new DOMRect(t.left + t.width * 0.18, t.top + t.height * 0.35, t.width * 0.64, t.height * 0.55);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  cv.width = Math.round(window.innerWidth * dpr);
  cv.height = Math.round(window.innerHeight * dpr);
  const out = cv.getContext('2d')!;
  // Rows are drawn opaque into a scratch canvas (overlapping rows with alpha
  // would show stripes); the fade is applied once, when compositing.
  const scratch = document.createElement('canvas');
  scratch.width = cv.width;
  scratch.height = cv.height;
  const ctx = scratch.getContext('2d')!;
  ctx.scale(dpr, dpr);
  ctx.imageSmoothingQuality = 'high';
  document.body.append(cv);

  const rows = Math.max(40, Math.ceil(r.h / 2));
  const srcRow = snap.height / rows;
  const Y = (v: number, P: number) => lerp(r.y + v * r.h, t.top + v * t.height, smooth(clamp01(P * 1.6 - (1 - v) * 0.6)));

  return new Promise((resolve) => {
    const start = performance.now();
    const frame = (now: number) => {
      const p = Math.min(1, (now - start) / GENIE_MS);
      const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      const P = reverse ? 1 - e : e;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      const alpha = 1 - 0.92 * smooth(clamp01((P - 0.45) / 0.55));
      let y0 = Y(0, P);
      for (let i = 0; i < rows; i++) {
        const v1 = (i + 1) / rows;
        const y1 = Y(v1, P);
        const qh = smooth(clamp01(P * 2.2 - (1 - (i + 0.5) / rows) * 1.2));
        const left = lerp(r.x, t.left, qh);
        const right = lerp(r.x + r.w, t.right, qh);
        if (y1 - y0 > 0.02) ctx.drawImage(snap, 0, i * srcRow, snap.width, srcRow, left, y0, right - left, y1 - y0 + 0.6);
        y0 = y1;
      }
      out.clearRect(0, 0, cv.width, cv.height);
      out.globalAlpha = alpha;
      out.drawImage(scratch, 0, 0);
      if (p < 1) requestAnimationFrame(frame);
      else {
        cv.remove();
        resolve();
      }
    };
    requestAnimationFrame(frame);
  });
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

const snaps = new WeakMap<Win, HTMLCanvasElement>();
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * Pressing the minimize button starts the capture right away (a click takes ~100 ms between
 * press and release), so the genie can begin sooner after the click.
 */
const pending = new Map<string, { at: number; job: Promise<HTMLCanvasElement | null> }>();
export function prepareMinimize(id: string): void {
  const w = wins.get(id);
  if (!w || w.minimized || reducedMotion()) return;
  pending.set(id, { at: performance.now(), job: snapshot(w) });
}

const padded = (r: Rect): Rect => ({ x: r.x - SNAP_PAD, y: r.y - SNAP_PAD, w: r.w + SNAP_PAD * 2, h: r.h + SNAP_PAD * 2 });

export function minimizeWindow(id: string): void {
  const w = wins.get(id);
  if (!w || w.minimized) return;
  w.minimized = true;
  const target = minimizeTarget(w.appId);
  void (async () => {
    // Capture the window exactly as it is right now and only then start: it stays on screen,
    // focused, until the genie takes over, and focus moves on only after it has gone.
    const pre = pending.get(id);
    pending.delete(id);
    const job = pre && performance.now() - pre.at < 1200 ? pre.job : snapshot(w);
    const snap = target && !reducedMotion() ? await job : null;
    if (!w.minimized) return;
    bus.emit('window:minimize', w);
    play('minimize');
    if (snap && target) {
      snaps.set(w, snap);
      w.el.style.display = 'none';
      await runGenie(snap, padded(w.rect), target, false);
    } else await fade(w, false);
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
  const snap = snaps.get(w);
  const target = minimizeTarget(w.appId);
  bus.emit('window:restore', w);
  if (!snap || !target || reducedMotion()) {
    void fade(w, true);
    return;
  }
  w.el.style.display = 'none';
  void runGenie(snap, padded(w.rect), target, true).then(() => {
    if (!w.minimized) w.el.style.display = '';
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
