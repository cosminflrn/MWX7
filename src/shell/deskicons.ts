import { icons } from '../assets/icons';
import { bus } from '../core/events';
import { basename, fs } from '../core/fs';
import { launch } from '../core/os';
import { getApp, listApps } from '../core/registry';
import { MENUBAR_H } from '../core/wm';
import { confirmDialog } from '../ui/dialog';
import { h } from '../ui/dom';

/**
 * Desktop icons: apps flagged `desktop` plus everything in /Desktop.
 * Icons sit on an invisible grid, can be dragged (several at once when
 * selected) and snap to the nearest free cell. Positions live for the session.
 */
const CELL_W = 96;
const CELL_H = 92;
const ORIGIN_X = 10;
const ORIGIN_Y = MENUBAR_H + 10;
const DOCK_SPACE = 100;

interface Item {
  key: string;
  label: string;
  icon: string;
  open: () => void;
  /** VFS path for /Desktop files (deletable). */
  path?: string;
}

type Cell = { col: number; row: number };

const textExt = /\.(txt|md|log|json|csv)$/i;

export function mountDeskIcons(layer: HTMLElement): void {
  const positions = new Map<string, Cell>();
  const elements = new Map<string, HTMLElement>();

  const rows = () => Math.max(1, Math.floor((window.innerHeight - ORIGIN_Y - DOCK_SPACE) / CELL_H));
  const cols = () => Math.max(1, Math.floor((window.innerWidth - ORIGIN_X) / CELL_W));
  const cellKey = (c: Cell) => `${c.col}:${c.row}`;

  const place = (el: HTMLElement, c: Cell) => {
    el.style.left = `${ORIGIN_X + c.col * CELL_W}px`;
    el.style.top = `${ORIGIN_Y + c.row * CELL_H}px`;
  };

  const occupied = (except?: Set<string>) => {
    const s = new Set<string>();
    for (const [k, c] of positions) if (!except?.has(k)) s.add(cellKey(c));
    return s;
  };

  /** Column-major like Windows: fill the first column top to bottom, then the next. */
  const firstFree = (taken: Set<string>): Cell => {
    for (let col = 0; col < cols(); col++) for (let row = 0; row < rows(); row++) if (!taken.has(`${col}:${row}`)) return { col, row };
    return { col: 0, row: 0 };
  };

  const nearestFree = (x: number, y: number, taken: Set<string>): Cell => {
    const col0 = Math.round((x - ORIGIN_X) / CELL_W);
    const row0 = Math.round((y - ORIGIN_Y) / CELL_H);
    let best: Cell = firstFree(taken);
    let bestD = Infinity;
    for (let col = 0; col < cols(); col++)
      for (let row = 0; row < rows(); row++) {
        if (taken.has(`${col}:${row}`)) continue;
        const d = (col - col0) ** 2 + (row - row0) ** 2;
        if (d < bestD) {
          bestD = d;
          best = { col, row };
        }
      }
    return best;
  };

  const selected = () => [...layer.querySelectorAll<HTMLElement>('.desk-icon.selected')];

  const remove = async (items: Item[]) => {
    const files = items.filter((i) => i.path);
    if (!files.length) return;
    const ok = await confirmDialog({
      title: 'Delete',
      message: files.length === 1 ? `Move “${files[0].label}” to the Trash?` : `Move these ${files.length} items to the Trash?`,
      icon: icons.trashFull,
      okLabel: 'Yes',
      cancelLabel: 'No',
    });
    if (!ok) return;
    for (const f of files) {
      const name = basename(f.path!);
      // Keep names unique inside the Trash.
      let target = name;
      for (let n = 2; await fs.exists(`/Trash/${target}`); n++) target = name.replace(/(\.[^.]*)?$/, ` (${n})$1`);
      if (target !== name) await fs.rename(f.path!, `/Desktop/${target}`);
      await fs.move(`/Desktop/${target}`, '/Trash');
    }
  };

  const build = (item: Item): HTMLElement => {
    const el = h(
      'button',
      { class: 'desk-icon', title: item.label, 'data-key': item.key },
      h('span', { class: 'desk-icon-img', html: item.icon }),
      h('span', { class: 'desk-icon-label' }, item.label),
    );
    el.addEventListener('dblclick', () => item.open());
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') item.open();
      if (e.key === 'Delete') void remove(selected().map((n) => itemFor.get(n.dataset.key!)!).filter(Boolean));
    });
    el.addEventListener('pointerdown', (e) => startDrag(e, el));
    return el;
  };

  const itemFor = new Map<string, Item>();

  /* ---------- dragging ---------- */

  const startDrag = (e: PointerEvent, el: HTMLElement) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    if (!el.classList.contains('selected')) {
      if (!(e.ctrlKey || e.metaKey)) layer.querySelectorAll('.desk-icon.selected').forEach((n) => n.classList.remove('selected'));
      el.classList.add('selected');
    } else if (e.ctrlKey || e.metaKey) {
      el.classList.remove('selected');
      return;
    }
    el.focus({ preventScroll: true });
    const group = selected();
    const start = { x: e.clientX, y: e.clientY };
    const origin = group.map((g) => ({ g, x: parseFloat(g.style.left), y: parseFloat(g.style.top) }));
    let dragging = false;
    el.setPointerCapture(e.pointerId);

    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - start.x;
      const dy = ev.clientY - start.y;
      if (!dragging) {
        if (Math.hypot(dx, dy) < 5) return;
        dragging = true;
        group.forEach((g) => g.classList.add('dragging'));
      }
      for (const o of origin) {
        o.g.style.left = `${o.x + dx}px`;
        o.g.style.top = `${o.y + dy}px`;
      }
    };
    const up = () => {
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      if (!dragging) return;
      const keys = new Set(group.map((g) => g.dataset.key!));
      const taken = occupied(keys);
      for (const o of origin) {
        const c = nearestFree(parseFloat(o.g.style.left), parseFloat(o.g.style.top), taken);
        taken.add(cellKey(c));
        positions.set(o.g.dataset.key!, c);
        o.g.classList.remove('dragging');
        o.g.classList.add('snapping');
        place(o.g, c);
        window.setTimeout(() => o.g.classList.remove('snapping'), 200);
      }
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  };

  /* ---------- content ---------- */

  const appItems = (): Item[] =>
    listApps()
      .filter((a) => a.desktop)
      .map((a) => ({ key: `app:${a.id}`, label: a.name, icon: a.icon, open: () => launch(a.id) }));

  const fileItems = async (): Promise<Item[]> =>
    (await fs.list('/Desktop')).map((f) => ({
      key: `file:${f.path}`,
      label: f.name,
      path: f.path,
      icon: f.type === 'dir' ? icons.folder : icons.file,
      open: () => {
        if (f.type === 'dir') launch(getApp('explorer') ? 'explorer' : 'notepad', { path: f.path });
        else if (textExt.test(f.name)) launch('notepad', { path: f.path });
        else if (getApp('explorer')) launch('explorer', { path: '/Desktop' });
      },
    }));

  let token = 0;
  const render = async () => {
    const t = ++token;
    const items = [...appItems(), ...(await fileItems())];
    if (t !== token) return;
    const keys = new Set(items.map((i) => i.key));
    for (const [k, el] of elements)
      if (!keys.has(k)) {
        el.remove();
        elements.delete(k);
        positions.delete(k);
        itemFor.delete(k);
      }
    for (const item of items) {
      itemFor.set(item.key, item);
      let el = elements.get(item.key);
      if (!el) {
        el = build(item);
        elements.set(item.key, el);
        layer.append(el);
      }
      if (!positions.has(item.key)) positions.set(item.key, firstFree(occupied()));
      place(el, positions.get(item.key)!);
    }
  };

  void render();
  bus.on('fs:change', ({ path }) => {
    if (path === '/Desktop' || path.startsWith('/Desktop/')) void render();
  });
  window.addEventListener('resize', () => {
    // Icons that fall off-screen move back to the nearest free cell.
    const taken = new Set<string>();
    for (const [k, c] of positions) {
      const fits = c.col < cols() && c.row < rows() && !taken.has(cellKey(c));
      const cell = fits ? c : firstFree(new Set([...occupied(new Set([k])), ...taken]));
      positions.set(k, cell);
      taken.add(cellKey(cell));
      const el = elements.get(k);
      if (el) place(el, cell);
    }
  });
}
