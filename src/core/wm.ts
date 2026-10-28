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

export const MENUBAR_H = 28;
export const DOCK_RESERVE = 82;
const SNAP_EDGE = 6;

let layer: HTMLElement;
let preview: HTMLDivElement;
const wins = new Map<string, Win>();
let zTop = 10;
let activeId: string | null = null;
let seq = 0;
let cascade = 0;
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
      return wa;
    case 'left':
      return { x: 0, y: wa.y, w: Math.round(wa.w / 2), h: wa.h };
    case 'right':
      return { x: Math.round(wa.w / 2), y: wa.y, w: wa.w - Math.round(wa.w / 2), h: wa.h };
    default:
      return null;
  }
}

function withAnimation(w: Win, fn: () => void): void {
  w.el.classList.add('anim');
  fn();
  window.setTimeout(() => w.el.classList.remove('anim'), 230);
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

/** Default geometry: generous and centered; extra windows cascade gently from the center. */
function initialRect(cfg: NonNullable<AppManifest['window']>): Rect {
  const wa = workArea();
  const resizable = cfg.resizable !== false;
  const baseW = cfg.width ?? 760;
  const baseH = cfg.height ?? 520;
  const width = Math.round(Math.min(resizable ? Math.max(baseW, wa.w * 0.58) : baseW, wa.w - 40));
  const height = Math.round(Math.min(resizable ? Math.max(baseH, wa.h * 0.72) : baseH, wa.h - 24));
  const visible = allWindows().filter((w) => !w.minimized).length;
  const off = visible ? ((cascade++ % 6) + 1) * 24 : ((cascade = 0), 0);
  const x = Math.round((wa.w - width) / 2) + off;
  const y = Math.round(wa.y + (wa.h - height) / 2) + off;
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
        <button class="wc wc-max" title="Maximize" aria-label="Maximize"></button>
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
async function snapshot(w: Win): Promise<HTMLCanvasElement | null> {
  const { toCanvas } = await import('html-to-image');
  const active = w.el.classList.contains('active');
  const job = toCanvas(w.el, {
    pixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
    skipFonts: true,
    filter: (n) => !(n instanceof HTMLElement && n.classList.contains('rz')),
    style: {
      left: '0',
      top: '0',
      margin: '0',
      transform: 'none',
      backdropFilter: 'none',
      boxShadow: 'none',
      background: active ? 'linear-gradient(#c2d8ef, #9ebddf)' : 'linear-gradient(#dbe4ee, #c4d0dd)',
    },
  }).catch(() => null);
  const timeout = new Promise<null>((r) => window.setTimeout(() => r(null), 450));
  return Promise.race([job, timeout]);
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
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  cv.width = Math.round(window.innerWidth * dpr);
  cv.height = Math.round(window.innerHeight * dpr);
  const ctx = cv.getContext('2d')!;
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
      ctx.globalAlpha = 1 - 0.35 * Math.pow(P, 3);
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

export function minimizeWindow(id: string): void {
  const w = wins.get(id);
  if (!w || w.minimized) return;
  w.minimized = true;
  w.el.classList.remove('active');
  bus.emit('window:minimize', w);
  if (activeId === id) {
    activeId = null;
    focusTopmost();
  }
  const target = minimizeTarget(w.appId);
  void (async () => {
    const snap = target && !reducedMotion() ? await snapshot(w) : null;
    if (!w.minimized) return;
    play('minimize');
    if (snap && target) {
      snaps.set(w, snap);
      w.el.style.display = 'none';
      await runGenie(snap, w.rect, target, false);
    } else await fade(w, false);
    if (w.minimized) w.el.style.display = 'none';
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
  void runGenie(snap, w.rect, target, true).then(() => {
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
