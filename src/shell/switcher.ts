import { bus } from '../core/events';
import { play } from '../core/sound';
import { activeWindow, allWindows, centerWindow, closeWindow, focusWindow, minimizeWindow, snapWindow } from '../core/wm';
import type { Win } from '../core/wm';
import '../styles/switcher.css';
import { h } from '../ui/dom';
import { closeMenu } from '../ui/menu';
import { closeCalendar } from './calendar';

/**
 * Aero-style window switcher (Win7 Alt+Tab) and keyboard window management.
 *
 * Browsers swallow Alt+Tab in a normal tab, so Ctrl+Tab is the primary trigger; Alt+Tab works too wherever the
 * browser delivers it (fullscreen, installed PWA). The panel stays open while the modifier is held.
 */

type Item = { kind: 'win'; win: Win } | { kind: 'desktop' };
type Mod = 'alt' | 'ctrl';

interface Session {
  mod: Mod;
  items: Item[];
  tiles: HTMLElement[];
  sel: number;
  root: HTMLElement;
  caption: HTMLElement;
}

const THUMB_W = 160;
const THUMB_H = 110;

let session: Session | null = null;
/** Most recently focused first. Windows missing from it (never focused) are appended at open time. */
let mru: string[] = [];
/** Windows hidden by "show desktop", bottom to top, so the same shortcut can bring them back. */
let stash: Win[] = [];
/** Last focused element inside each window, so the switcher can give keyboard focus back where it was. */
const lastFocus = new WeakMap<HTMLElement, HTMLElement>();

/* ---------- thumbnails ---------- */

const thumbs = new Map<string, string>();
const captured = new Map<string, number>();
const inflight = new Set<string>();

/** Rasterizes a window at low resolution (backdrop blur can't be captured, so the glass becomes a solid frame). */
async function capture(w: Win): Promise<boolean> {
  if (w.minimized || w.el.style.display === 'none' || inflight.has(w.id) || w.el.offsetWidth < 40) return false;
  inflight.add(w.id);
  try {
    const { toCanvas } = await import('html-to-image');
    const active = w.el.classList.contains('active');
    const job = toCanvas(w.el, {
      pixelRatio: 1,
      skipFonts: true,
      filter: (n) => !(n instanceof HTMLElement && n.classList.contains('rz')),
      style: {
        // html-to-image inlines every computed property, logical ones included, and they beat plain left/top.
        left: '0',
        top: '0',
        insetInlineStart: '0',
        insetBlockStart: '0',
        margin: '0',
        transform: 'none',
        backdropFilter: 'none',
        boxShadow: 'none',
        background: active ? 'linear-gradient(#c2d8ef, #9ebddf)' : 'linear-gradient(#dbe4ee, #c4d0dd)',
      },
    }).catch(() => null);
    const timeout = new Promise<null>((r) => window.setTimeout(() => r(null), 900));
    const canvas = await Promise.race([job, timeout]);
    if (!canvas || !canvas.width || !canvas.height) return false;
    const k = Math.min(1, (THUMB_W * 2) / canvas.width, (THUMB_H * 2) / canvas.height);
    const small = document.createElement('canvas');
    small.width = Math.max(1, Math.round(canvas.width * k));
    small.height = Math.max(1, Math.round(canvas.height * k));
    const ctx = small.getContext('2d')!;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(canvas, 0, 0, small.width, small.height);
    thumbs.set(w.id, small.toDataURL('image/png'));
    captured.set(w.id, performance.now());
    return true;
  } catch {
    return false;
  } finally {
    inflight.delete(w.id);
  }
}

/** Keeps the cache warm after focus changes so the panel rarely opens with empty tiles. */
function warm(w: Win | undefined): void {
  if (!w || performance.now() - (captured.get(w.id) ?? -1e9) < 2500) return;
  const run = () => void capture(w);
  const ric = (window as unknown as { requestIdleCallback?: (f: () => void, o: object) => void }).requestIdleCallback;
  if (ric) ric.call(window, run, { timeout: 800 });
  else window.setTimeout(run, 120);
}

/* ---------- focus bookkeeping ---------- */

let lastActiveId: string | null = null;

function trackFocus(w: Win | null): void {
  if (!w) return;
  const prev = lastActiveId ? allWindows().find((x) => x.id === lastActiveId) : undefined;
  lastActiveId = w.id;
  mru = [w.id, ...mru.filter((id) => id !== w.id)];
  warm(prev);
  warm(w);
}

function orderedWindows(): Win[] {
  const all = allWindows();
  const byId = new Map(all.map((w) => [w.id, w]));
  const ordered = mru.map((id) => byId.get(id)).filter((w): w is Win => !!w);
  const rest = all.filter((w) => !mru.includes(w.id)).sort((a, b) => b.z - a.z);
  return [...ordered, ...rest];
}

/* ---------- show desktop ---------- */

function showDesktop(): void {
  const visible = allWindows()
    .filter((w) => !w.minimized)
    .sort((a, b) => b.z - a.z);
  if (visible.length) {
    stash = [...visible].reverse();
    // Topmost first: each minimize hands focus to the next one down, which is minimized in turn.
    for (const w of visible) minimizeWindow(w.id);
    return;
  }
  const back = stash.filter((w) => allWindows().includes(w));
  stash = [];
  for (const w of back) focusWindow(w.id);
}

/* ---------- panel ---------- */

const DESKTOP_ICON = `<svg viewBox="0 0 32 32" aria-hidden="true"><defs><linearGradient id="swd1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fd0ff"/><stop offset="1" stop-color="#2d78c8"/></linearGradient></defs><rect x="3" y="5" width="26" height="18" rx="2" fill="#1c2a3d" stroke="#d9e6f5" stroke-width="1.2"/><rect x="5" y="7" width="22" height="14" rx="1" fill="url(#swd1)"/><path d="M5 7h22v6C20 11 12 12 5 15z" fill="#fff" opacity=".28"/><path d="M12 27h8l-1-4h-6z" fill="#b8c7d9"/><rect x="9" y="26.5" width="14" height="2" rx="1" fill="#d9e6f5"/></svg>`;

function thumbFor(item: Item): HTMLElement {
  if (item.kind === 'desktop') return h('div', { class: 'sw-fallback sw-desktop', html: DESKTOP_ICON });
  const url = thumbs.get(item.win.id);
  if (url) return h('img', { class: 'sw-img', src: url, alt: '', draggable: false });
  return h('div', { class: 'sw-fallback', html: item.win.manifest.icon });
}

function buildTile(item: Item, i: number): HTMLElement {
  const title = item.kind === 'desktop' ? 'Desktop' : item.win.title;
  const icon = item.kind === 'desktop' ? DESKTOP_ICON : item.win.manifest.icon;
  const tile = h(
    'div',
    { class: `sw-tile${item.kind === 'win' && item.win.minimized ? ' is-min' : ''}`, role: 'option', title },
    h('div', { class: 'sw-thumb', style: `width:${THUMB_W}px;height:${THUMB_H}px` }, thumbFor(item)),
    h('div', { class: 'sw-label' }, h('span', { class: 'sw-ico', html: icon }), h('span', { class: 'sw-name' }, title)),
  );
  tile.addEventListener('click', () => {
    if (session) session.sel = i;
    commit();
  });
  return tile;
}

function titleOf(item: Item): string {
  return item.kind === 'desktop' ? 'Desktop' : item.win.title;
}

function select(i: number): void {
  if (!session) return;
  const n = session.items.length;
  session.sel = ((i % n) + n) % n;
  session.tiles.forEach((t, k) => {
    t.classList.toggle('sel', k === session!.sel);
    t.setAttribute('aria-selected', String(k === session!.sel));
  });
  session.caption.textContent = titleOf(session.items[session.sel]!);
  session.tiles[session.sel]!.scrollIntoView({ block: 'nearest' });
}

function moveVertical(dir: 1 | -1): void {
  if (!session) return;
  const cur = session.tiles[session.sel]!.getBoundingClientRect();
  const cx = cur.left + cur.width / 2;
  let best = -1;
  let score = Infinity;
  session.tiles.forEach((t, k) => {
    const r = t.getBoundingClientRect();
    const dy = (r.top - cur.top) * dir;
    if (dy < 4) return;
    const s = dy * 1000 + Math.abs(r.left + r.width / 2 - cx);
    if (s < score) {
      score = s;
      best = k;
    }
  });
  if (best >= 0) select(best);
}

function openSwitcher(mod: Mod, backwards: boolean): void {
  const wins = orderedWindows();
  if (!wins.length) return;
  closeMenu();
  closeCalendar();
  const items: Item[] = [...wins.map((win): Item => ({ kind: 'win', win })), { kind: 'desktop' }];

  const caption = h('div', { class: 'sw-caption' });
  const grid = h('div', { class: 'sw-grid', role: 'listbox', 'aria-label': 'Open windows' });
  const tiles = items.map((it, i) => buildTile(it, i));
  grid.append(...tiles);
  const panel = h('div', { class: 'sw-panel' }, caption, grid);
  const root = h('div', { class: 'sw-overlay', role: 'dialog', 'aria-label': 'Switch windows' }, panel);
  root.addEventListener('pointerdown', (e) => {
    if (e.target === root) cancel();
  });
  document.body.append(root);

  session = { mod, items, tiles, sel: 0, root, caption };
  // Like Windows, the first press lands on the previous window, not the one already in front.
  select(backwards ? items.length - 1 : wins.length > 1 && activeWindow() ? 1 : 0);
  play('menuOpen');

  // Refresh the live thumbnails: visible windows first, front-most first. Tiles swap in as each finishes.
  const visible = wins.filter((w) => !w.minimized).sort((a, b) => b.z - a.z);
  void (async () => {
    for (const w of visible) {
      if (!session || session.root !== root) return;
      if (!(await capture(w))) continue;
      const i = items.findIndex((it) => it.kind === 'win' && it.win === w);
      const thumb = tiles[i]?.querySelector('.sw-thumb');
      if (thumb && root.isConnected) thumb.replaceChildren(thumbFor(items[i]!));
    }
  })();
}

function dismiss(): Session | null {
  const s = session;
  if (!s) return null;
  session = null;
  s.root.classList.add('closing');
  window.setTimeout(() => s.root.remove(), 110);
  return s;
}

function cancel(): void {
  dismiss();
}

function giveFocusBack(w: Win): void {
  const remembered = lastFocus.get(w.el);
  const target = remembered && remembered.isConnected && w.el.contains(remembered) ? remembered : w.el;
  target.focus({ preventScroll: true });
}

function commit(): void {
  const s = dismiss();
  if (!s) return;
  const item = s.items[s.sel]!;
  if (item.kind === 'desktop') {
    showDesktop();
    return;
  }
  if (!allWindows().includes(item.win)) return;
  focusWindow(item.win.id);
  giveFocusBack(item.win);
}

/* ---------- keyboard ---------- */

const modHeld = (e: KeyboardEvent, mod: Mod) => (mod === 'alt' ? e.altKey : e.ctrlKey);

function eat(e: Event): void {
  e.preventDefault();
  e.stopImmediatePropagation();
}

function onKeyDownOpen(e: KeyboardEvent, s: Session): void {
  // Lost the keyup somewhere (devtools, alert, OS shortcut): treat the next key as the release.
  if (!modHeld(e, s.mod)) {
    commit();
    return;
  }
  eat(e);
  switch (e.key) {
    case 'Tab':
      select(s.sel + (e.shiftKey ? -1 : 1));
      break;
    case 'ArrowRight':
      select(s.sel + 1);
      break;
    case 'ArrowLeft':
      select(s.sel - 1);
      break;
    case 'ArrowDown':
      moveVertical(1);
      break;
    case 'ArrowUp':
      moveVertical(-1);
      break;
    case 'Home':
      select(0);
      break;
    case 'End':
      select(s.items.length - 1);
      break;
    case 'Enter':
      commit();
      break;
    case 'Escape':
      cancel();
      break;
  }
}

/** Ctrl+Alt+… window management. Returns true when the key was ours. */
function windowShortcut(e: KeyboardEvent): boolean {
  const w = activeWindow();
  switch (e.code) {
    case 'KeyD':
      showDesktop();
      return true;
    case 'ArrowLeft':
      if (w) snapWindow(w.id, 'left');
      return true;
    case 'ArrowRight':
      if (w) snapWindow(w.id, 'right');
      return true;
    case 'ArrowUp':
      if (w) snapWindow(w.id, 'max');
      return true;
    case 'ArrowDown':
      if (!w) return true;
      // Restore first; a window that is already in its normal state goes to the dock.
      if (w.state !== 'normal' && w.manifest.window?.resizable !== false) snapWindow(w.id, 'normal');
      else minimizeWindow(w.id);
      return true;
    case 'KeyC':
      if (w) centerWindow(w.id);
      return true;
    case 'KeyW':
      if (w) closeWindow(w.id);
      return true;
    default:
      return false;
  }
}

function onKeyDown(e: KeyboardEvent): void {
  if (session) {
    onKeyDownOpen(e, session);
    return;
  }
  if (e.metaKey || e.isComposing) return;

  if (e.key === 'Tab' && (e.ctrlKey || e.altKey)) {
    if (!allWindows().length) return;
    eat(e);
    openSwitcher(e.altKey ? 'alt' : 'ctrl', e.shiftKey);
    return;
  }

  // AltGr reports as Ctrl+Alt on Windows; those key presses are typing (e.g. AltGr+C), not shortcuts.
  if (e.ctrlKey && e.altKey && !e.getModifierState('AltGraph') && windowShortcut(e)) eat(e);
}

function onKeyUp(e: KeyboardEvent): void {
  const s = session;
  if (!s) return;
  if (!modHeld(e, s.mod)) {
    // Stops the browser from focusing its own menu on the Alt release.
    if (e.key === 'Alt') e.preventDefault();
    commit();
  }
}

export function mountSwitcher(): void {
  window.addEventListener('keydown', onKeyDown, true);
  window.addEventListener('keyup', onKeyUp, true);
  // The panel can't know about a modifier released while the tab was not looking.
  window.addEventListener('blur', cancel);
  document.addEventListener('visibilitychange', () => document.hidden && cancel());

  document.addEventListener('focusin', (e) => {
    const t = e.target as HTMLElement | null;
    const win = t?.closest?.('.win') as HTMLElement | null;
    if (win && t !== win) lastFocus.set(win, t!);
  });

  bus.on('window:focus', trackFocus);
  bus.on('window:close', (w) => {
    mru = mru.filter((id) => id !== w.id);
    thumbs.delete(w.id);
    captured.delete(w.id);
    stash = stash.filter((x) => x !== w);
    if (session) {
      // A window vanished while the panel is up (e.g. an app closing itself): rebuild is overkill, just drop out.
      cancel();
    }
  });
  bus.on('window:open', () => {
    stash = [];
  });
}
