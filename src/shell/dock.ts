import { icons } from '../assets/icons';
import { bus } from '../core/events';
import { settings } from '../core/settings';
import { launch } from '../core/os';
import { getApp, listApps } from '../core/registry';
import type { MenuItem } from '../core/types';
import { activeWindow, closeWindow, focusWindow, minimizeWindow, setMinimizeTarget, windowsOf } from '../core/wm';
import { fs } from '../core/fs';
import { notify } from '../core/os';
import { play } from '../core/sound';
import { confirmDialog } from '../ui/dialog';
import { h } from '../ui/dom';
import { attachPeek } from './peek';
import { menuIcon, openMenu } from '../ui/menu';

/**
 * The MWX 7 dock: a macOS dock (magnification, bounce) with Win7 superbar
 * behaviour (click running app = focus / minimize, glow indicator, right-click
 * jump list) and the Start orb as its first item.
 */
const RANGE = 140;
const SIZES = { small: 40, medium: 48, large: 60 } as const;
let BASE: number = SIZES.medium;
const MAX_SCALE = 1.6;

export function mountDock(dock: HTMLElement): void {
  let magnify = true;
  const applySettings = () => {
    const s = settings.get();
    BASE = SIZES[s.dockSize];
    magnify = s.dockMagnify;
    document.documentElement.style.setProperty('--dock-icon', `${BASE}px`);
    if (!magnify) {
      pointerX = null;
      dock.classList.remove('hover');
      kick();
    }
  };
  const shelf = h('div', { class: 'dock-shelf' });
  dock.append(shelf);

  const orb = h('button', {
    class: 'dock-item dock-orb',
    'data-label': 'Start',
    'aria-label': 'Start',
    html: icons.orb,
    onclick: () => bus.emit('startmenu:toggle', { anchor: orb.getBoundingClientRect() }),
  });

  const sep = h('div', { class: 'dock-sep' });
  shelf.append(orb, sep);

  // Trash lives at the far end, after its own separator (like macOS).
  const trashIcon = h('span', { class: 'dock-icon', html: icons.trash });
  const trash = h(
    'button',
    {
      class: 'dock-item dock-trash',
      'data-label': 'Trash',
      'aria-label': 'Trash',
      onclick: () => openTrash(),
      oncontextmenu: (e: MouseEvent) => {
        e.preventDefault();
        void (async () => {
          const empty = !(await fs.list('/Trash')).length;
          const r = trash.getBoundingClientRect();
          openMenu(
            [
              { label: 'Open', icon: menuIcon('open'), action: openTrash },
              { separator: true },
              { label: 'Empty Trash…', icon: menuIcon('delete'), disabled: empty, action: () => void emptyTrash() },
            ],
            { x: r.left, y: r.top - 8 },
            { above: true, anchor: trash },
          );
        })();
      },
    },
    trashIcon,
  );
  shelf.append(h('div', { class: 'dock-sep' }), trash);

  const openTrash = () => {
    if (getApp('explorer')) launch('explorer', { path: '/Trash' });
    else notify('Trash', 'File Explorer is needed to browse the Trash.', icons.trash);
  };
  const emptyTrash = async () => {
    const items = await fs.list('/Trash');
    if (!items.length) return;
    const ok = await confirmDialog({
      title: 'Empty Trash',
      message: `Are you sure you want to permanently delete ${items.length === 1 ? `“${items[0].name}”` : `these ${items.length} items`}?`,
      detail: 'You can’t undo this action.',
      icon: icons.trashFull,
      okLabel: 'Yes',
      cancelLabel: 'No',
    });
    if (!ok) return;
    for (const it of items) await fs.remove(it.path);
    play('empty');
  };
  const refreshTrash = async () => {
    const full = (await fs.list('/Trash')).length > 0;
    trashIcon.innerHTML = full ? icons.trashFull : icons.trash;
    trash.dataset.label = full ? 'Trash (full)' : 'Trash';
  };
  void refreshTrash();
  // A move into or out of /Trash reports either path, so any change re-checks (cheap: memory only).
  bus.on('fs:change', () => void refreshTrash());
  const itemFor = new Map<string, HTMLElement>();

  const makeItem = (appId: string) => {
    const app = getApp(appId)!;
    const btn = h(
      'button',
      {
        class: 'dock-item',
        'data-label': app.name,
        'aria-label': app.name,
        onclick: () => onClick(app.id, btn),
        oncontextmenu: (e: MouseEvent) => {
          e.preventDefault();
          jumpList(app.id, btn);
        },
      },
      h('span', { class: 'dock-icon', html: app.icon }),
      h('span', { class: 'dock-dot' }),
    );
    attachPeek(btn, app.id);
    return btn;
  };

  /** Reconcile in place so animations (bounce, magnification) survive updates. */
  const render = () => {
    const pinned = listApps().filter((a) => a.pinned).map((a) => a.id);
    const running = listApps(true)
      .filter((a) => windowsOf(a.id).length && !pinned.includes(a.id))
      .map((a) => a.id);
    const wanted = [...pinned, ...running];
    for (const [id, el] of itemFor) {
      if (!wanted.includes(id)) {
        itemFor.delete(id);
        // The icon folds away instead of vanishing.
        el.classList.add('leaving');
        el.animate(
          [
            { width: `${el.offsetWidth}px`, opacity: 1, transform: 'none' },
            { width: '0px', opacity: 0, transform: 'scale(.4) translateY(10px)' },
          ],
          { duration: 260, easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' },
        ).onfinish = () => el.remove();
      }
    }
    let prev: Element = sep;
    for (const id of wanted) {
      let el = itemFor.get(id);
      if (!el) itemFor.set(id, (el = makeItem(id)));
      if (prev.nextElementSibling !== el) prev.after(el);
      el.classList.toggle('running', windowsOf(id).length > 0);
      el.classList.toggle('focused', activeWindow()?.appId === id);
      prev = el;
    }
  };

  const onClick = (appId: string, btn: HTMLElement) => {
    const wins = windowsOf(appId);
    if (!wins.length) {
      btn.classList.remove('bounce');
      void btn.offsetWidth;
      btn.classList.add('bounce');
      launch(appId);
      return;
    }
    const active = activeWindow();
    if (active?.appId === appId && !active.minimized) {
      // Win7: clicking the focused app minimizes it (cycle if several windows)
      const visible = wins.filter((w) => !w.minimized);
      if (visible.length > 1) {
        const sorted = visible.sort((a, b) => a.z - b.z);
        focusWindow(sorted[0].id);
      } else minimizeWindow(active.id);
      return;
    }
    const top = [...wins].sort((a, b) => b.z - a.z)[0];
    focusWindow(top.id);
  };

  const jumpList = (appId: string, btn: HTMLElement) => {
    const app = getApp(appId)!;
    const wins = windowsOf(appId);
    const items: MenuItem[] = wins.map((w) => ({ label: w.title, icon: app.icon, checked: activeWindow()?.id === w.id, action: () => focusWindow(w.id) }));
    if (items.length) items.push({ separator: true });
    if (!app.singleInstance || !wins.length)
      items.push({ label: wins.length ? 'New Window' : `Open ${app.name}`, icon: menuIcon(wins.length ? 'new-file' : 'open'), action: () => launch(appId) });
    if (wins.length)
      items.push({ label: wins.length > 1 ? 'Close All Windows' : 'Quit', icon: menuIcon('close'), action: () => wins.forEach((w) => closeWindow(w.id)) });
    const r = btn.getBoundingClientRect();
    openMenu(items, { x: r.left, y: r.top - 8 }, { above: true, anchor: btn });
  };

  /*
   * macOS magnification, smoothed. Distances are measured against each icon's
   * *resting* centre (measuring the already-grown icons made them wiggle), the
   * pointer position is eased toward the real one every frame, and each icon's
   * size eases toward its target — so uneven mouse movement still produces a
   * fluid wave.
   */
  let rest: Array<{ el: HTMLElement; cx: number }> | null = null;
  const scales = new WeakMap<HTMLElement, number>();
  let pointerX: number | null = null;
  let easedX: number | null = null;
  let raf = 0;
  const items = () => [...shelf.querySelectorAll<HTMLElement>('.dock-item:not(.leaving)')];
  const measureRest = () => {
    // Resting centre = current centre corrected for the icon's current growth on each side.
    rest = items().map((el) => {
      const r = el.getBoundingClientRect();
      return { el, cx: r.left + r.width / 2 };
    });
  };
  const tick = () => {
    raf = 0;
    if (!rest || rest.length !== items().length) measureRest();
    if (pointerX !== null) easedX = easedX === null ? pointerX : easedX + (pointerX - easedX) * 0.22;
    let moving = false;
    for (const { el, cx } of rest!) {
      const d = pointerX === null || easedX === null ? Infinity : Math.abs(easedX - cx);
      const want = 1 + (MAX_SCALE - 1) * Math.max(0, Math.cos(Math.min(d / RANGE, 1) * (Math.PI / 2)));
      const cur = scales.get(el) ?? 1;
      const next = cur + (want - cur) * 0.28;
      const settled = Math.abs(next - want) < 0.002;
      const val = settled ? want : next;
      scales.set(el, val);
      if (val === 1) el.style.removeProperty('--size');
      else el.style.setProperty('--size', `${(BASE * val).toFixed(2)}px`);
      if (!settled) moving = true;
    }
    if (pointerX !== null && easedX !== null && Math.abs(pointerX - easedX) > 0.3) moving = true;
    if (moving) raf = requestAnimationFrame(tick);
    else if (pointerX === null) {
      rest = null;
      easedX = null;
      shelf.classList.remove('magnify');
    }
  };
  const kick = () => {
    if (!raf) raf = requestAnimationFrame(tick);
  };
  shelf.addEventListener('pointerenter', (e) => {
    if (e.pointerType !== 'mouse' || !magnify) return;
    if (!shelf.classList.contains('magnify')) measureRest();
    shelf.classList.add('magnify');
    dock.classList.add('hover');
    pointerX = e.clientX;
    kick();
  });
  shelf.addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse' || !magnify) return;
    pointerX = e.clientX;
    kick();
  });
  shelf.addEventListener('pointerleave', () => {
    pointerX = null;
    dock.classList.remove('hover');
    kick();
  });

  applySettings();
  bus.on('settings:change', () => {
    applySettings();
    rest = null; // icon sizes changed: re-measure resting centres
  });

  setMinimizeTarget((appId) => itemFor.get(appId)?.getBoundingClientRect() ?? null);

  render();
  for (const ev of ['window:open', 'window:close', 'window:focus', 'window:minimize', 'window:restore'] as const) bus.on(ev, render);
}
