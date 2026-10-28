import { icons } from '../assets/icons';
import { bus } from '../core/events';
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
import { openMenu } from '../ui/menu';

/**
 * The MWX 7 dock: a macOS dock (magnification, bounce) with Win7 superbar
 * behaviour (click running app = focus / minimize, glow indicator, right-click
 * jump list) and the Start orb as its first item.
 */
const BASE = 48;
const MAX_SCALE = 1.6;
const RANGE = 140;

export function mountDock(dock: HTMLElement): void {
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
              { label: 'Open', action: openTrash },
              { separator: true },
              { label: 'Empty Trash…', disabled: empty, action: () => void emptyTrash() },
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
    const items: MenuItem[] = wins.map((w) => ({ label: w.title, checked: activeWindow()?.id === w.id, action: () => focusWindow(w.id) }));
    if (items.length) items.push({ separator: true });
    if (!app.singleInstance || !wins.length) items.push({ label: wins.length ? 'New Window' : `Open ${app.name}`, action: () => launch(appId) });
    if (wins.length) items.push({ label: wins.length > 1 ? 'Close All Windows' : 'Quit', action: () => wins.forEach((w) => closeWindow(w.id)) });
    const r = btn.getBoundingClientRect();
    openMenu(items, { x: r.left, y: r.top - 8 }, { above: true, anchor: btn });
  };

  // macOS magnification
  shelf.addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse') return;
    shelf.classList.add('magnify');
    for (const item of shelf.querySelectorAll<HTMLElement>('.dock-item')) {
      const r = item.getBoundingClientRect();
      const d = Math.abs(e.clientX - (r.left + r.width / 2));
      const s = 1 + (MAX_SCALE - 1) * Math.max(0, Math.cos(Math.min(d / RANGE, 1) * (Math.PI / 2)));
      item.style.setProperty('--size', `${Math.round(BASE * s)}px`);
    }
  });
  shelf.addEventListener('pointerleave', () => {
    shelf.classList.remove('magnify');
    shelf.querySelectorAll<HTMLElement>('.dock-item').forEach((i) => i.style.removeProperty('--size'));
  });

  setMinimizeTarget((appId) => itemFor.get(appId)?.getBoundingClientRect() ?? null);

  render();
  for (const ev of ['window:open', 'window:close', 'window:focus', 'window:minimize', 'window:restore'] as const) bus.on(ev, render);
}
