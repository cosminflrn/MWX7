import { icons } from '../../assets/icons';
import { basename, dirname, normalize } from '../../core/fs';
import type { AppManifest, MenuItem } from '../../core/types';
import { h } from '../../ui/dom';
import { openMenu } from '../../ui/menu';
import { showSheet } from '../../ui/sheet';
import { driveIcon } from './art';
import { seedSamples } from './seed';
import {
  COMPUTER,
  DRIVE_CAPACITY,
  DRIVE_NAME,
  TRASH,
  extOf,
  formatDate,
  formatSize,
  formatSizeColumn,
  imageUrl,
  isImage,
  isProtected,
  isText,
  joinPath,
  kindOf,
  plural,
  toItem,
  type Item,
} from './util';
import './explorer.css';

type View = 'icons' | 'details';
type SortKey = 'name' | 'modified' | 'kind' | 'size';

/** Shared across Explorer windows so Copy in one and Paste in another works. */
let clipboard: { paths: string[]; cut: boolean } | null = null;
/** Where a trashed item came from, for "Restore". Session-only, like the file system itself. */
const trashOrigin = new Map<string, string>();
/** Paths being dragged; dataTransfer data is unreadable during dragover, so the drop target checks this. */
let dragPaths: string[] | null = null;

const MIME = 'application/x-mwx7-paths';
const BAD_NAME = /[\\/:*?"<>|]/;

const svgGlyph = (body: string, size = 16) =>
  `<svg viewBox="0 0 16 16" width="${size}" height="${size}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
const G = {
  back: svgGlyph('<path d="M9.5 3 4.5 8l5 5M5 8h8"/>', 18),
  forward: svgGlyph('<path d="m6.5 3 5 5-5 5M11 8H3"/>', 18),
  up: svgGlyph('<path d="M8 13V3M3.5 7.5 8 3l4.5 4.5"/>'),
  refresh: svgGlyph('<path d="M13 8a5 5 0 1 1-1.6-3.7M13 2.5V5h-2.5"/>', 14),
  search: svgGlyph('<circle cx="6.8" cy="6.8" r="4.3"/><path d="m10 10 3.8 3.8"/>', 14),
  clear: svgGlyph('<path d="m4.5 4.5 7 7m0-7-7 7"/>', 12),
  chevron: '<svg viewBox="0 0 8 8" width="8" height="8" aria-hidden="true"><path d="m2.5 1 3 3-3 3" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  caret: '<svg viewBox="0 0 8 8" width="8" height="8" aria-hidden="true"><path d="m1 2.5 3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  grid: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>',
  list: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor"><rect x="2" y="3" width="2" height="2" rx=".5"/><rect x="6" y="3.2" width="8" height="1.6" rx=".6"/><rect x="2" y="7" width="2" height="2" rx=".5"/><rect x="6" y="7.2" width="8" height="1.6" rx=".6"/><rect x="2" y="11" width="2" height="2" rx=".5"/><rect x="6" y="11.2" width="8" height="1.6" rx=".6"/></svg>',
  star: '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><defs><linearGradient id="exs" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe27a"/><stop offset="1" stop-color="#e0a21c"/></linearGradient></defs><path d="m8 1.4 2 4.3 4.6.5-3.4 3.1 1 4.6L8 11.5l-4.2 2.4 1-4.6L1.4 6.2 6 5.7Z" fill="url(#exs)" stroke="#b07a10" stroke-opacity=".7" stroke-width=".7" stroke-linejoin="round"/></svg>',
};

const NAV_FAVORITES = [
  { name: 'Desktop', path: '/Desktop' },
  { name: 'Documents', path: '/Documents' },
  { name: 'Pictures', path: '/Pictures' },
  { name: 'Music', path: '/Music' },
];

export const explorer: AppManifest = {
  id: 'explorer',
  name: 'Explorer',
  icon: icons.explorer,
  description: 'Browse files and folders',
  keywords: ['files', 'folders', 'file manager', 'documents', 'finder', 'computer', 'explorer'],
  pinned: true,
  desktop: true,
  window: { width: 920, height: 600, minWidth: 520, minHeight: 360 },

  mount({ win, args, fs, os }) {
    const root = win.body;
    root.classList.add('xp-ex');

    /* ---------- state ---------- */
    let loc = COMPUTER;
    const history: string[] = [];
    let hIdx = -1;
    let view: View = 'icons';
    let sortKey: SortKey = 'name';
    let sortAsc = true;
    let query = '';
    let items: Item[] = [];
    let shown: Item[] = [];
    const sel = new Set<string>();
    let anchor: string | null = null;
    let focused: string | null = null;
    let renaming: string | null = null;
    let signature = '';
    let trashCount = 0;
    let driveUsed = 0;
    let token = 0;
    let disposed = false;
    let els = new Map<string, HTMLElement>();

    /* ---------- skeleton ---------- */
    const mkNavBtn = (cls: string, label: string, html: string, onclick: () => void) =>
      h('button', { class: `ex-nav-btn ${cls}`, 'aria-label': label, title: label, html, onclick });

    const backBtn = mkNavBtn('back', 'Back (Alt+Left)', G.back, () => goBack());
    const fwdBtn = mkNavBtn('fwd', 'Forward (Alt+Right)', G.forward, () => goForward());
    const upBtn = h('button', { class: 'ex-up', 'aria-label': 'Up (Alt+Up)', title: 'Up to parent folder (Alt+Up)', html: G.up, onclick: () => goUp() });
    const addrIcon = h('span', { class: 'ex-addr-icon' });
    const crumbs = h('div', { class: 'ex-crumbs' });
    const addrInput = h('input', { class: 'ex-addr-input', spellcheck: false, 'aria-label': 'Address' });
    const refreshBtn = h('button', { class: 'ex-refresh', 'aria-label': 'Refresh (F5)', title: 'Refresh (F5)', html: G.refresh, onclick: () => void refresh(true) });
    const addr = h('div', { class: 'ex-addr' }, addrIcon, crumbs, addrInput, refreshBtn);
    const searchInput = h('input', { class: 'ex-search-input', type: 'text', spellcheck: false, 'aria-label': 'Search' });
    const searchClear = h('button', { class: 'ex-search-clear', 'aria-label': 'Clear search', html: G.clear, hidden: true });
    const search = h('div', { class: 'ex-search' }, h('span', { class: 'ex-search-ico', html: G.search }), searchInput, searchClear);
    const addrRow = h('div', { class: 'ex-addr-row' }, h('div', { class: 'ex-nav-pill' }, backBtn, fwdBtn), upBtn, addr, search);

    const cmdBar = h('div', { class: 'ex-cmd' });
    const nav = h('nav', { class: 'ex-nav', 'aria-label': 'Navigation pane' });
    const scroller = h('div', { class: 'ex-scroll', tabindex: 0, role: 'listbox', 'aria-multiselectable': true, 'aria-label': 'Files' });
    const details = h('div', { class: 'ex-details' });
    root.append(addrRow, cmdBar, h('div', { class: 'ex-main' }, nav, scroller), details);

    /* ---------- helpers ---------- */
    const notify = (text: string) => os.notify('Explorer', text, icons.explorer);
    const isReal = () => loc !== COMPUTER;
    const locName = (l: string) => (l === COMPUTER ? 'Computer' : l === '/' ? DRIVE_NAME : basename(l));
    const selected = (): Item[] => shown.filter((i) => sel.has(i.path));
    const inTrash = (p: string) => p === TRASH || p.startsWith(`${TRASH}/`);

    const folderIcon = (path: string): string => {
      switch (path) {
        case COMPUTER:
          return icons.computer;
        case '/':
          return driveIcon;
        case '/Documents':
          return icons.documents;
        case '/Pictures':
          return icons.pictures;
        case '/Music':
          return icons.music;
        case TRASH:
          return trashCount ? icons.trashFull : icons.trash;
        default:
          return icons.folder;
      }
    };
    const iconFor = (it: Item): string => (it.drive ? driveIcon : it.dir ? folderIcon(it.path) : icons.file);

    /** Icon (or image thumbnail) element; `.ex-ico` is sized by CSS per view. */
    const iconEl = (it: Item, thumb: boolean): HTMLElement => {
      if (thumb && !it.dir && isImage(it.name) && it.content) {
        return h('span', { class: 'ex-ico ex-thumb' }, h('img', { src: imageUrl(it), alt: '', draggable: false }));
      }
      return h('span', { class: 'ex-ico', html: iconFor(it) });
    };

    const uniquePath = async (dir: string, name: string, isDir: boolean, style: 'move' | 'copy'): Promise<string> => {
      const dot = isDir ? -1 : name.lastIndexOf('.');
      const stem = dot > 0 ? name.slice(0, dot) : name;
      const ext = dot > 0 ? name.slice(dot) : '';
      let candidate = joinPath(dir, name);
      for (let n = 1; await fs.exists(candidate); n++) {
        const suffix = style === 'copy' ? (n === 1 ? ' - Copy' : ` - Copy (${n})`) : ` (${n + 1})`;
        candidate = joinPath(dir, `${stem}${suffix}${ext}`);
      }
      return candidate;
    };

    const confirmSheet = (title: string, message: string, okLabel: string, onOk: () => void) =>
      showSheet(root, (close) =>
        h(
          'div',
          { class: 'sheet-form' },
          h('label', {}, title),
          h('div', { class: 'sheet-hint' }, message),
          h(
            'div',
            { class: 'sheet-actions' },
            h('button', { class: 'btn', onclick: close }, 'Cancel'),
            h('button', { class: 'btn primary', onclick: () => (close(), onOk()) }, okLabel),
          ),
        ),
      );

    /* ---------- navigation ---------- */
    const navigate = (to: string, push = true) => {
      if (push && to !== history[hIdx]) {
        history.length = hIdx + 1;
        history.push(to);
        hIdx = history.length - 1;
      }
      loc = to;
      query = '';
      searchInput.value = '';
      sel.clear();
      anchor = focused = renaming = null;
      signature = '';
      scroller.scrollTop = 0;
      void refresh(true);
    };
    const goBack = () => hIdx > 0 && navigate(history[--hIdx], false);
    const goForward = () => hIdx < history.length - 1 && navigate(history[++hIdx], false);
    const parentOf = (l: string) => (l === COMPUTER ? COMPUTER : dirname(l) === '/' || l === '/' ? COMPUTER : dirname(l));
    const goUp = () => loc !== COMPUTER && navigate(parentOf(loc));

    /* ---------- data ---------- */
    const refresh = async (force = false): Promise<void> => {
      if (disposed) return;
      const my = ++token;
      let list: Item[];
      if (loc === COMPUTER) {
        const all = await fs.all();
        const used = all.reduce((n, f) => n + new TextEncoder().encode(f.content).length, 0);
        const rootDirs = (await fs.list('/')).map(toItem);
        driveUsed = used;
        list = [{ path: '/', name: DRIVE_NAME, dir: true, modified: 0, size: used, kind: 'Local Disk', content: '', drive: true }, ...rootDirs];
      } else {
        const st = await fs.stat(loc);
        if (my !== token) return;
        if (!st || st.type !== 'dir') {
          let l = loc;
          while (l !== '/' && !(await fs.stat(l))) l = dirname(l);
          navigate(l === '/' ? COMPUTER : l);
          return;
        }
        list = (await fs.list(loc)).map(toItem);
      }
      const trash = await fs.list(TRASH);
      if (my !== token || disposed) return;
      const sig = `${loc}|${trash.length}|${list.map((i) => `${i.path}:${i.modified}:${i.size}`).join(',')}`;
      if (!force && (sig === signature || renaming)) return;
      signature = sig;
      items = list;
      trashCount = trash.length;
      renderAll();
    };

    const sortItems = (list: Item[]): Item[] => {
      const dirn = sortAsc ? 1 : -1;
      const byName = (a: Item, b: Item) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
      return [...list].sort((a, b) => {
        if (a.drive !== b.drive) return a.drive ? -1 : 1;
        if (a.dir !== b.dir) return a.dir ? -1 : 1;
        let c = 0;
        if (sortKey === 'modified') c = a.modified - b.modified;
        else if (sortKey === 'size') c = a.size - b.size;
        else if (sortKey === 'kind') c = a.kind.localeCompare(b.kind);
        return (c || byName(a, b)) * dirn;
      });
    };

    const applyFilter = () => {
      const q = query.trim().toLowerCase();
      shown = sortItems(q ? items.filter((i) => i.name.toLowerCase().includes(q)) : items);
      for (const p of [...sel]) if (!shown.some((i) => i.path === p)) sel.delete(p);
    };

    /* ---------- rendering ---------- */
    const renderAll = () => {
      applyFilter();
      renderAddress();
      renderNav();
      renderContent();
      renderCommands();
      win.setTitle(locName(loc));
      searchInput.placeholder = `Search ${locName(loc)}`;
      buildMenus();
    };

    const crumbList = (l: string): { name: string; loc: string }[] => {
      const out = [{ name: 'Computer', loc: COMPUTER }];
      if (l === COMPUTER) return out;
      if (l === '/') return [...out, { name: DRIVE_NAME, loc: '/' }];
      let acc = '';
      for (const part of l.split('/').filter(Boolean)) out.push({ name: part, loc: (acc += `/${part}`) });
      return out;
    };

    const childDirs = async (l: string): Promise<MenuItem[]> => {
      const dirs = (await fs.list(l === COMPUTER ? '/' : l)).filter((e) => e.type === 'dir');
      if (!dirs.length) return [{ label: '(Empty)', disabled: true }];
      return dirs.map((d) => ({ label: d.name, action: () => navigate(d.path) }));
    };

    const renderAddress = () => {
      addrIcon.innerHTML = folderIcon(loc);
      crumbs.replaceChildren();
      for (const c of crumbList(loc)) {
        const seg = h('button', { class: 'ex-crumb', onclick: () => navigate(c.loc), title: c.name }, c.name);
        bindDrop(seg, () => (c.loc === COMPUTER ? null : c.loc));
        const arrow = h('button', {
          class: 'ex-crumb-arrow',
          'aria-label': `Folders in ${c.name}`,
          html: G.chevron,
          onclick: async () => {
            const r = arrow.getBoundingClientRect();
            openMenu(await childDirs(c.loc), { x: r.left, y: r.bottom + 2 }, { anchor: arrow });
          },
        });
        crumbs.append(seg, arrow);
      }
      backBtn.disabled = hIdx <= 0;
      fwdBtn.disabled = hIdx >= history.length - 1;
      upBtn.disabled = loc === COMPUTER;
    };

    const renderNav = () => {
      nav.replaceChildren();
      const entry = (name: string, path: string, icon: string, mod = '') => {
        const el = h(
          'button',
          { class: `ex-nav-item${loc === path ? ' current' : ''}${mod ? ` ${mod}` : ''}`, onclick: () => navigate(path), 'data-nav': path },
          h('span', { class: 'ex-nav-ico', html: icon }),
          h('span', { class: 'ex-nav-label' }, name),
        );
        if (path !== COMPUTER) bindDrop(el, () => path);
        return el;
      };
      nav.append(
        h('div', { class: 'ex-nav-head' }, h('span', { html: G.star }), 'Favorites'),
        ...NAV_FAVORITES.map((f) => entry(f.name, f.path, f.path === '/Desktop' ? icons.folder : folderIcon(f.path))),
        entry('Computer', COMPUTER, icons.computer, 'group'),
        entry(DRIVE_NAME, '/', driveIcon, 'nested'),
        entry('Trash', TRASH, trashCount ? icons.trashFull : icons.trash, 'group'),
      );
    };

    const renderCommands = () => {
      const chosen = selected();
      const btn = (label: string, onclick: (e: MouseEvent) => void, opts: { disabled?: boolean; caret?: boolean } = {}) =>
        h(
          'button',
          { class: 'ex-btn', disabled: opts.disabled, onclick },
          label,
          opts.caret ? h('span', { class: 'ex-caret', html: G.caret }) : null,
        );
      const organize = btn(
        'Organize',
        () => {
          const r = organize.getBoundingClientRect();
          openMenu(organizeMenu(), { x: r.left, y: r.bottom + 1 }, { anchor: organize });
        },
        { caret: true },
      );
      const seg = (v: View, label: string, glyph: string) =>
        h('button', {
          class: `ex-seg${view === v ? ' on' : ''}`,
          'aria-label': label,
          'aria-pressed': String(view === v),
          title: label,
          html: glyph,
          disabled: loc === COMPUTER,
          onclick: () => setView(v),
        });

      const parts: Node[] = [organize];
      if (chosen.length) parts.push(btn('Open', () => void openSelection()));
      parts.push(h('span', { class: 'ex-cmd-sep' }), btn('New folder', () => void newFolder(), { disabled: !isReal() || inTrash(loc) }));
      if (loc === TRASH) parts.push(btn('Restore', () => void restore(), { disabled: !chosen.length }), btn('Empty Trash', emptyTrash, { disabled: !trashCount }));
      cmdBar.replaceChildren(
        ...parts,
        h('span', { class: 'ex-cmd-fill' }),
        h('div', { class: 'ex-segs' }, seg('icons', 'Large icons', G.grid), seg('details', 'Details', G.list)),
      );
    };

    const buildItemEl = (it: Item): HTMLElement => {
      const isRen = renaming === it.path;
      const label = isRen ? renameField(it) : h('span', { class: 'ex-name', title: it.name }, it.name);
      const common = {
        'data-path': it.path,
        role: 'option',
        'aria-selected': sel.has(it.path),
        draggable: !isRen && !it.drive,
      };
      const cut = clipboard?.cut && clipboard.paths.includes(it.path);
      const cls = `${sel.has(it.path) ? ' selected' : ''}${cut ? ' cut' : ''}${focused === it.path ? ' focus' : ''}`;
      if (view === 'details' && loc !== COMPUTER) {
        return h(
          'div',
          { ...common, class: `ex-row${cls}` },
          h('div', { class: 'ex-cell ex-c-name' }, iconEl(it, true), label),
          h('div', { class: 'ex-cell ex-c-date' }, formatDate(it.modified)),
          h('div', { class: 'ex-cell ex-c-kind' }, it.kind),
          h('div', { class: 'ex-cell ex-c-size' }, it.dir ? '' : formatSizeColumn(it.size)),
        );
      }
      if (it.drive) {
        const free = Math.max(0, DRIVE_CAPACITY - driveUsed);
        const pct = Math.max(1.5, (driveUsed / DRIVE_CAPACITY) * 100);
        return h(
          'div',
          { ...common, class: `ex-item ex-drive${cls}` },
          iconEl(it, false),
          h(
            'div',
            { class: 'ex-drive-info' },
            h('span', { class: 'ex-name' }, it.name),
            h('div', { class: 'ex-meter' }, h('i', { style: `width:${pct}%` })),
            h('span', { class: 'ex-drive-free' }, `${formatSize(free)} free of ${formatSize(DRIVE_CAPACITY)}`),
          ),
        );
      }
      return h('div', { ...common, class: `ex-item${cls}` }, iconEl(it, true), label);
    };

    const renderContent = () => {
      els = new Map();
      scroller.replaceChildren();
      scroller.className = `ex-scroll ${loc === COMPUTER ? 'computer' : view}`;
      scroller.setAttribute('aria-label', locName(loc));
      const frag = document.createDocumentFragment();
      const add = (it: Item, host: HTMLElement) => {
        const el = buildItemEl(it);
        els.set(it.path, el);
        host.append(el);
      };

      if (loc === COMPUTER) {
        const drives = shown.filter((i) => i.drive);
        const folders = shown.filter((i) => !i.drive);
        if (drives.length) {
          const g = h('div', { class: 'ex-group-items' });
          drives.forEach((i) => add(i, g));
          frag.append(h('div', { class: 'ex-group' }, `Hard Disk Drives (${drives.length})`), g);
        }
        if (folders.length) {
          const g = h('div', { class: 'ex-group-items' });
          folders.forEach((i) => add(i, g));
          frag.append(h('div', { class: 'ex-group' }, `Folders (${folders.length})`), g);
        }
      } else if (view === 'details') {
        const col = (key: SortKey, label: string, cls: string) =>
          h(
            'button',
            { class: `ex-col ${cls}${sortKey === key ? ' sorted' : ''}`, onclick: () => setSort(key) },
            h('span', {}, label),
            sortKey === key ? h('i', { class: `ex-sort ${sortAsc ? 'asc' : 'desc'}` }) : null,
          );
        frag.append(h('div', { class: 'ex-head' }, col('name', 'Name', 'ex-c-name'), col('modified', 'Date modified', 'ex-c-date'), col('kind', 'Type', 'ex-c-kind'), col('size', 'Size', 'ex-c-size')));
        const body = h('div', { class: 'ex-rows' });
        shown.forEach((i) => add(i, body));
        frag.append(body);
      } else {
        const g = h('div', { class: 'ex-grid' });
        shown.forEach((i) => add(i, g));
        frag.append(g);
      }
      if (!shown.length) {
        frag.append(h('div', { class: 'ex-empty' }, query.trim() ? 'No items match your search.' : 'This folder is empty.'));
      }
      scroller.append(frag);
      if (renaming) {
        const input = els.get(renaming)?.querySelector<HTMLInputElement | HTMLTextAreaElement>('.ex-rename');
        if (input) {
          input.focus();
          const dot = input.value.lastIndexOf('.');
          const it = shown.find((i) => i.path === renaming);
          input.setSelectionRange(0, it && !it.dir && dot > 0 ? dot : input.value.length);
        }
      }
      updateDetails();
    };

    const renderCommandsAndMenus = () => {
      renderCommands();
      buildMenus();
    };

    /* ---------- selection ---------- */
    const applySelection = () => {
      for (const [p, el] of els) {
        const on = sel.has(p);
        el.classList.toggle('selected', on);
        el.setAttribute('aria-selected', String(on));
        el.classList.toggle('focus', focused === p);
      }
      updateDetails();
      renderCommandsAndMenus();
    };
    const setSel = (paths: Iterable<string>, newAnchor?: string | null) => {
      sel.clear();
      for (const p of paths) sel.add(p);
      if (newAnchor !== undefined) anchor = newAnchor;
      applySelection();
    };
    const selectRange = (to: string) => {
      const a = shown.findIndex((i) => i.path === (anchor ?? to));
      const b = shown.findIndex((i) => i.path === to);
      if (a < 0 || b < 0) return setSel([to], to);
      const [lo, hi] = a < b ? [a, b] : [b, a];
      setSel(shown.slice(lo, hi + 1).map((i) => i.path));
    };

    const updateDetails = () => {
      const chosen = selected();
      let icon: HTMLElement;
      let title: string;
      const facts: [string, string][] = [];
      if (chosen.length === 0) {
        icon = h('span', { class: 'ex-ico', html: folderIcon(loc) });
        title = locName(loc);
        const n = shown.length;
        facts.push([plural(n, 'item'), '']);
      } else if (chosen.length === 1) {
        const it = chosen[0];
        icon = iconEl(it, true);
        title = it.name;
        facts.push(['Type', it.kind]);
        if (it.drive) facts.push(['Used', formatSize(driveUsed)]);
        else if (!it.dir) facts.push(['Size', formatSize(it.size)]);
        if (!it.drive) facts.push(['Date modified', formatDate(it.modified)]);
      } else {
        icon = h('span', { class: 'ex-ico', html: icons.documents });
        title = plural(chosen.length, 'item') + ' selected';
        const total = chosen.reduce((n, i) => n + i.size, 0);
        if (total) facts.push(['Total size', formatSize(total)]);
      }
      details.replaceChildren(
        icon,
        h(
          'div',
          { class: 'ex-d-text' },
          h('div', { class: 'ex-d-title' }, title),
          h(
            'div',
            { class: 'ex-d-facts' },
            ...facts.map(([k, v]) => h('span', {}, v ? h('b', {}, `${k}: `) : null, v || k)),
          ),
        ),
      );
    };

    /* ---------- view / sort ---------- */
    const setView = (v: View) => {
      if (view === v) return;
      view = v;
      renderContent();
      renderCommandsAndMenus();
    };
    const setSort = (key: SortKey) => {
      if (sortKey === key) sortAsc = !sortAsc;
      else {
        sortKey = key;
        sortAsc = true;
      }
      applyFilter();
      renderContent();
    };

    /* ---------- opening ---------- */
    const openItem = (it: Item) => {
      if (it.dir) return navigate(it.path);
      if (isImage(it.name)) return showPreview(it);
      if (isText(it.name) || !extOf(it.name)) return os.launch('notepad', { path: it.path });
      notify(`There is no app associated with ${kindOf(it.name, false)}s yet.`);
    };
    const openSelection = async () => {
      const chosen = selected();
      const folder = chosen.find((i) => i.dir);
      if (folder) return openItem(folder);
      chosen.forEach(openItem);
    };

    const showPreview = (start: Item) => {
      const images = shown.filter((i) => !i.dir && isImage(i.name) && i.content);
      let idx = Math.max(0, images.findIndex((i) => i.path === start.path));
      if (!images.length) return;
      const title = h('span', { class: 'ex-pv-title' });
      const count = h('span', { class: 'ex-pv-count' });
      const img = h('img', { class: 'ex-pv-img', alt: '', draggable: false });
      const overlay = h('div', { class: 'ex-preview', tabindex: -1, role: 'dialog', 'aria-label': 'Image preview' });
      const close = () => {
        overlay.remove();
        scroller.focus();
      };
      const show = (i: number) => {
        idx = (i + images.length) % images.length;
        const it = images[idx];
        title.textContent = it.name;
        count.textContent = images.length > 1 ? `${idx + 1} of ${images.length}` : '';
        img.src = imageUrl(it);
        setSel([it.path], it.path);
      };
      overlay.append(
        h('div', { class: 'ex-pv-bar' }, title, count, h('button', { class: 'ex-pv-close', 'aria-label': 'Close preview', html: G.clear, onclick: close })),
        h('div', { class: 'ex-pv-stage', onclick: (e: Event) => e.target === e.currentTarget && close() }, img),
      );
      if (images.length > 1) {
        overlay.append(
          h('button', { class: 'ex-pv-nav prev', 'aria-label': 'Previous image', html: G.back, onclick: () => show(idx - 1) }),
          h('button', { class: 'ex-pv-nav next', 'aria-label': 'Next image', html: G.forward, onclick: () => show(idx + 1) }),
        );
      }
      overlay.addEventListener('keydown', (e) => {
        e.stopPropagation();
        if (e.key === 'Escape' || e.key === ' ') close();
        else if (e.key === 'ArrowLeft') show(idx - 1);
        else if (e.key === 'ArrowRight') show(idx + 1);
      });
      root.append(overlay);
      show(idx);
      overlay.focus();
    };

    /* ---------- file operations ---------- */
    const guard = async (label: string, fn: () => Promise<void>) => {
      try {
        await fn();
      } catch (err) {
        console.warn(`[explorer] ${label} failed`, err);
        notify(`Couldn't ${label}. ${err instanceof Error ? err.message.replace('[fs] ', '') : ''}`);
      }
      await refresh(true);
    };

    const canDrop = (paths: string[], dest: string): boolean =>
      paths.every((p) => !isProtected(p) && dirname(p) !== dest && dest !== p && !dest.startsWith(`${p}/`));

    const moveInto = (paths: string[], dest: string) =>
      guard('move the items', async () => {
        const moved: string[] = [];
        for (const p of paths) {
          if (!canDrop([p], dest)) continue;
          const target = await uniquePath(dest, basename(p), (await fs.stat(p))?.type === 'dir', 'move');
          const origin = dirname(p);
          await fs.rename(p, target);
          if (dest === TRASH) trashOrigin.set(target, origin);
          moved.push(target);
        }
        if (dest === loc) {
          await refresh(true);
          setSel(moved, moved[0] ?? null);
        }
      });

    const copyTree = async (src: string, dst: string): Promise<void> => {
      const st = await fs.stat(src);
      if (!st) return;
      if (st.type === 'file') return fs.write(dst, (await fs.read(src)) ?? '');
      await fs.mkdir(dst);
      for (const child of await fs.list(src)) await copyTree(child.path, joinPath(dst, child.name));
    };

    const setClipboard = (cut: boolean) => {
      const chosen = selected().filter((i) => !i.drive);
      if (!chosen.length) return;
      if (cut && chosen.some((i) => isProtected(i.path))) return notify("System folders can't be moved.");
      clipboard = { paths: chosen.map((i) => i.path), cut };
      for (const [p, el] of els) el.classList.toggle('cut', cut && clipboard.paths.includes(p));
      renderCommandsAndMenus();
    };

    const paste = (dest = loc) => {
      if (!clipboard || dest === COMPUTER) return;
      const { paths, cut } = clipboard;
      void guard(cut ? 'move the items' : 'copy the items', async () => {
        const pasted: string[] = [];
        for (const p of paths) {
          const st = await fs.stat(p);
          if (!st) continue;
          if (dest.startsWith(`${p}/`) || dest === p) throw new Error("A folder can't be copied into itself.");
          const isDir = st.type === 'dir';
          if (cut) {
            if (dirname(p) === dest) continue;
            const target = await uniquePath(dest, basename(p), isDir, 'move');
            await fs.rename(p, target);
            if (dest === TRASH) trashOrigin.set(target, dirname(p));
            pasted.push(target);
          } else {
            const target = await uniquePath(dest, basename(p), isDir, 'copy');
            await copyTree(p, target);
            pasted.push(target);
          }
        }
        if (cut) clipboard = null;
        await refresh(true);
        if (dest === loc) setSel(pasted, pasted[0] ?? null);
      });
    };

    const newFolder = async () => {
      if (!isReal() || inTrash(loc)) return;
      let created = '';
      await guard('create the folder', async () => {
        created = await uniquePath(loc, 'New folder', true, 'move');
        await fs.mkdir(created);
      });
      if (created) {
        setSel([created], created);
        startRename(created);
      }
    };

    const startRename = (path: string | undefined = [...sel][0]) => {
      const it = shown.find((i) => i.path === path);
      if (!it || it.drive) return;
      if (isProtected(it.path)) return notify("System folders can't be renamed.");
      renaming = it.path;
      focused = it.path;
      renderContent();
      els.get(it.path)?.scrollIntoView({ block: 'nearest' });
    };

    const commitRename = async (it: Item, raw: string) => {
      if (renaming !== it.path) return;
      renaming = null;
      const name = raw.trim();
      if (!name || name === it.name) return renderContent();
      if (BAD_NAME.test(name)) {
        renderContent();
        return notify('A file name can\'t contain any of the following characters: \\ / : * ? " < > |');
      }
      const target = joinPath(dirname(it.path), name);
      if (await fs.exists(target)) {
        renderContent();
        return notify(`A file or folder named "${name}" already exists here.`);
      }
      await guard('rename the item', () => fs.rename(it.path, target));
      setSel([target], target);
    };

    const renameField = (it: Item): HTMLElement => {
      // A textarea in icon view (labels wrap), an input in details; both expose the bits used below.
      const field = (view === 'details' ? h('input', { class: 'ex-rename', type: 'text' }) : h('textarea', { class: 'ex-rename', rows: 2 })) as HTMLInputElement;
      field.value = it.name;
      field.spellcheck = false;
      field.addEventListener('keydown', (e) => {
        e.stopPropagation();
        if (e.key === 'Enter') {
          e.preventDefault();
          void commitRename(it, field.value);
        } else if (e.key === 'Escape') {
          renaming = null;
          renderContent();
          scroller.focus();
        }
      });
      field.addEventListener('blur', () => void commitRename(it, field.value));
      field.addEventListener('pointerdown', (e) => e.stopPropagation());
      field.addEventListener('dblclick', (e) => e.stopPropagation());
      return field;
    };

    const deleteSelection = () => {
      const chosen = selected().filter((i) => !i.drive);
      if (!chosen.length) return;
      if (chosen.some((i) => isProtected(i.path))) return notify("System folders can't be deleted.");
      if (inTrash(chosen[0].path)) {
        const what = chosen.length === 1 ? `"${chosen[0].name}"` : plural(chosen.length, 'item');
        confirmSheet('Delete permanently?', `${what} will be permanently deleted. This can't be undone.`, 'Delete', () =>
          void guard('delete the items', async () => {
            for (const i of chosen) await fs.remove(i.path);
          }),
        );
        return;
      }
      void moveInto(chosen.map((i) => i.path), TRASH);
    };

    const restore = () =>
      guard('restore the items', async () => {
        const restored: string[] = [];
        for (const i of selected()) {
          const origin = trashOrigin.get(i.path) ?? '/Documents';
          if (!(await fs.exists(origin))) await fs.mkdir(origin);
          const target = await uniquePath(origin, i.name, i.dir, 'move');
          await fs.rename(i.path, target);
          trashOrigin.delete(i.path);
          restored.push(target);
        }
        if (restored.length) notify(`Restored ${plural(restored.length, 'item')}.`);
      });

    const emptyTrash = () => {
      confirmSheet('Empty Trash?', `All ${plural(trashCount, 'item')} in the Trash will be permanently deleted.`, 'Empty Trash', () =>
        void guard('empty the Trash', async () => {
          for (const e of await fs.list(TRASH)) await fs.remove(e.path);
          trashOrigin.clear();
        }),
      );
    };

    const showProperties = async (target?: Item) => {
      const it = target ?? selected()[0];
      const info: [string, string][] = [];
      let title = locName(loc);
      let icon = folderIcon(loc);
      if (it) {
        title = it.name;
        icon = iconFor(it);
        info.push(['Type', it.kind]);
        if (it.drive) {
          info.push(['Used space', formatSize(driveUsed)], ['Free space', formatSize(Math.max(0, DRIVE_CAPACITY - driveUsed))], ['Capacity', formatSize(DRIVE_CAPACITY)]);
        } else {
          info.push(['Location', dirname(it.path)]);
          if (it.dir) {
            let files = 0;
            let dirs = 0;
            let bytes = 0;
            const walk = async (d: string) => {
              for (const c of await fs.list(d)) {
                if (c.type === 'dir') {
                  dirs++;
                  await walk(c.path);
                } else {
                  files++;
                  bytes += new TextEncoder().encode(c.content).length;
                }
              }
            };
            await walk(it.path);
            info.push(['Size', formatSize(bytes)], ['Contains', `${plural(files, 'file')}, ${plural(dirs, 'folder')}`]);
          } else info.push(['Size', `${formatSize(it.size)} (${it.size.toLocaleString()} bytes)`]);
          info.push(['Modified', formatDate(it.modified)]);
        }
      } else {
        info.push(['Type', loc === COMPUTER ? 'System' : 'File folder'], ['Contains', plural(items.length, 'item')]);
        if (isReal()) info.push(['Location', loc]);
      }
      showSheet(root, (close) =>
        h(
          'div',
          { class: 'sheet-form ex-props' },
          h('div', { class: 'ex-props-head' }, h('span', { class: 'ex-ico', html: icon }), h('b', {}, title)),
          h('dl', {}, ...info.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])),
          h('div', { class: 'sheet-actions' }, h('button', { class: 'btn primary', onclick: close }, 'OK')),
        ),
      );
    };

    /* ---------- menus ---------- */
    const organizeMenu = (): MenuItem[] => {
      const has = selected().length > 0;
      return [
        { label: 'Cut', shortcut: 'Ctrl+X', disabled: !has, action: () => setClipboard(true) },
        { label: 'Copy', shortcut: 'Ctrl+C', disabled: !has, action: () => setClipboard(false) },
        { label: 'Paste', shortcut: 'Ctrl+V', disabled: !clipboard || !isReal(), action: () => paste() },
        { separator: true },
        { label: 'Select all', shortcut: 'Ctrl+A', action: () => setSel(shown.map((i) => i.path), shown[0]?.path ?? null) },
        { separator: true },
        { label: 'Rename', shortcut: 'F2', disabled: sel.size !== 1, action: () => startRename() },
        { label: inTrash(loc) ? 'Delete permanently' : 'Delete', shortcut: 'Del', disabled: !has, action: deleteSelection },
        { separator: true },
        { label: 'Properties', disabled: !isReal() && !has, action: () => void showProperties() },
      ];
    };

    const buildMenus = () => {
      const has = selected().length > 0;
      win.setMenus([
        {
          label: 'File',
          items: [
            { label: 'New folder', shortcut: 'Ctrl+Shift+N', disabled: !isReal() || inTrash(loc), action: () => void newFolder() },
            { label: 'Open', disabled: !has, action: () => void openSelection() },
            { label: 'Rename', shortcut: 'F2', disabled: sel.size !== 1, action: () => startRename() },
            { label: 'Properties', action: () => void showProperties() },
            { separator: true },
            { label: 'Close', action: () => win.close() },
          ],
        },
        {
          label: 'Edit',
          items: [
            { label: 'Cut', shortcut: 'Ctrl+X', disabled: !has, action: () => setClipboard(true) },
            { label: 'Copy', shortcut: 'Ctrl+C', disabled: !has, action: () => setClipboard(false) },
            { label: 'Paste', shortcut: 'Ctrl+V', disabled: !clipboard || !isReal(), action: () => paste() },
            { separator: true },
            { label: 'Select all', shortcut: 'Ctrl+A', action: () => setSel(shown.map((i) => i.path), shown[0]?.path ?? null) },
          ],
        },
        {
          label: 'View',
          items: [
            { label: 'Large icons', checked: view === 'icons', action: () => setView('icons') },
            { label: 'Details', checked: view === 'details', action: () => setView('details') },
            { separator: true },
            { label: 'Refresh', shortcut: 'F5', action: () => void refresh(true) },
          ],
        },
      ]);
    };

    const itemMenu = (it: Item): MenuItem[] => {
      const many = sel.size > 1;
      const prot = selected().some((i) => i.drive || isProtected(i.path));
      const trashed = inTrash(it.path);
      return [
        { label: 'Open', action: () => void openSelection() },
        ...(trashed ? [{ label: 'Restore', action: () => void restore() }] : []),
        { separator: true },
        { label: 'Cut', shortcut: 'Ctrl+X', disabled: prot, action: () => setClipboard(true) },
        { label: 'Copy', shortcut: 'Ctrl+C', disabled: selected().some((i) => i.drive), action: () => setClipboard(false) },
        ...(it.dir && !many ? [{ label: 'Paste', shortcut: 'Ctrl+V', disabled: !clipboard, action: () => paste(it.path) }] : []),
        { separator: true },
        { label: trashed ? 'Delete permanently' : 'Delete', shortcut: 'Del', disabled: prot, action: deleteSelection },
        { label: 'Rename', shortcut: 'F2', disabled: many || prot, action: () => startRename() },
        { separator: true },
        { label: 'Properties', disabled: many, action: () => void showProperties(it) },
      ];
    };

    const spaceMenu = (): MenuItem[] => [
      { label: 'Large icons', checked: view === 'icons', disabled: !isReal(), action: () => setView('icons') },
      { label: 'Details', checked: view === 'details', disabled: !isReal(), action: () => setView('details') },
      { label: 'Refresh', shortcut: 'F5', action: () => void refresh(true) },
      { separator: true },
      { label: 'Paste', shortcut: 'Ctrl+V', disabled: !clipboard || !isReal(), action: () => paste() },
      { separator: true },
      { label: 'New folder', shortcut: 'Ctrl+Shift+N', disabled: !isReal() || inTrash(loc), action: () => void newFolder() },
      { separator: true },
      { label: 'Properties', action: () => void showProperties() },
    ];

    /* ---------- pointer interaction ---------- */
    const itemOf = (target: EventTarget | null): Item | undefined => {
      const el = (target as HTMLElement | null)?.closest<HTMLElement>('[data-path]');
      return el ? shown.find((i) => i.path === el.dataset.path) : undefined;
    };

    scroller.addEventListener('mousedown', (e) => {
      const it = itemOf(e.target);
      if (!it || e.button !== 0 || renaming) return;
      focused = it.path;
      if (e.shiftKey) selectRange(it.path);
      else if (e.ctrlKey || e.metaKey) {
        if (sel.has(it.path)) sel.delete(it.path);
        else sel.add(it.path);
        anchor = it.path;
        applySelection();
      } else if (!sel.has(it.path)) setSel([it.path], it.path);
    });
    scroller.addEventListener('click', (e) => {
      const it = itemOf(e.target);
      // A plain click on one of several selected items collapses the selection (after any drag had its chance).
      if (it && !e.shiftKey && !e.ctrlKey && !e.metaKey && sel.size > 1 && sel.has(it.path)) setSel([it.path], it.path);
    });
    scroller.addEventListener('dblclick', (e) => {
      const it = itemOf(e.target);
      if (it) openItem(it);
    });
    scroller.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      if (renaming) return;
      const it = itemOf(e.target);
      if (it) {
        focused = it.path;
        if (!sel.has(it.path)) setSel([it.path], it.path);
        openMenu(itemMenu(it), { x: e.clientX, y: e.clientY });
      } else {
        setSel([]);
        openMenu(spaceMenu(), { x: e.clientX, y: e.clientY });
      }
    });

    // Rubber-band selection, started on empty space only.
    scroller.addEventListener('pointerdown', (e) => {
      const target = e.target as HTMLElement;
      if (e.button !== 0 || target.closest('[data-path], .ex-head, input, textarea')) return;
      const box = scroller.getBoundingClientRect();
      if (e.clientX - box.left >= scroller.clientWidth || e.clientY - box.top >= scroller.clientHeight) return; // scrollbar
      const additive = e.ctrlKey || e.metaKey || e.shiftKey;
      const base = additive ? new Set(sel) : new Set<string>();
      if (!additive) setSel([]);
      const maxX = scroller.scrollWidth;
      const maxY = scroller.scrollHeight;
      const clamp = (v: number, hi: number) => Math.max(0, Math.min(hi, v));
      const startX = clamp(e.clientX - box.left + scroller.scrollLeft, maxX);
      const startY = clamp(e.clientY - box.top + scroller.scrollTop, maxY);
      let band: HTMLElement | null = null;
      scroller.setPointerCapture(e.pointerId);

      const move = (ev: PointerEvent) => {
        if (ev.clientY > box.bottom - 18) scroller.scrollTop += 14;
        else if (ev.clientY < box.top + 18) scroller.scrollTop -= 14;
        const x = clamp(ev.clientX - box.left + scroller.scrollLeft, maxX);
        const y = clamp(ev.clientY - box.top + scroller.scrollTop, maxY);
        if (!band && Math.hypot(x - startX, y - startY) < 4) return;
        if (!band) {
          band = h('div', { class: 'ex-band' });
          scroller.append(band);
        }
        const [l, t, r, b] = [Math.min(x, startX), Math.min(y, startY), Math.max(x, startX), Math.max(y, startY)];
        band.style.cssText = `left:${l}px;top:${t}px;width:${r - l}px;height:${b - t}px`;
        const hit = new Set(base);
        for (const [p, el] of els) {
          const rc = el.getBoundingClientRect();
          const il = rc.left - box.left + scroller.scrollLeft;
          const it = rc.top - box.top + scroller.scrollTop;
          if (il < r && il + rc.width > l && it < b && it + rc.height > t) hit.add(p);
        }
        const same = hit.size === sel.size && [...hit].every((p) => sel.has(p));
        if (!same) setSel(hit, hit.size ? [...hit][0] : null);
      };
      const up = () => {
        band?.remove();
        scroller.removeEventListener('pointermove', move);
        scroller.removeEventListener('pointerup', up);
        scroller.removeEventListener('pointercancel', up);
      };
      scroller.addEventListener('pointermove', move);
      scroller.addEventListener('pointerup', up);
      scroller.addEventListener('pointercancel', up);
    });

    /* ---------- drag & drop ---------- */
    const clearDrop = () => root.querySelectorAll('.drop').forEach((n) => n.classList.remove('drop'));

    /** Makes `el` accept dragged items; `dest()` returns the folder it stands for (or null to refuse). */
    function bindDrop(el: HTMLElement, dest: () => string | null) {
      el.addEventListener('dragover', (e) => {
        const d = dest();
        if (!dragPaths || !d || !canDrop(dragPaths, d)) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer!.dropEffect = 'move';
        clearDrop();
        el.classList.add('drop');
      });
      el.addEventListener('dragleave', (e) => {
        if (!el.contains(e.relatedTarget as Node | null)) el.classList.remove('drop');
      });
      el.addEventListener('drop', (e) => {
        const d = dest();
        if (!dragPaths || !d || !canDrop(dragPaths, d)) return;
        e.preventDefault();
        e.stopPropagation();
        clearDrop();
        void moveInto(dragPaths, d);
      });
    }

    scroller.addEventListener('dragstart', (e) => {
      const it = itemOf(e.target);
      if (!it || !e.dataTransfer) return e.preventDefault();
      if (!sel.has(it.path)) setSel([it.path], it.path);
      dragPaths = [...sel];
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData(MIME, JSON.stringify(dragPaths));
      e.dataTransfer.setData('text/plain', dragPaths.join('\n'));
      const ghost = h('div', { class: 'ex-ghost' }, h('span', { class: 'ex-ico', html: iconFor(it) }), dragPaths.length > 1 ? h('b', {}, String(dragPaths.length)) : null);
      root.append(ghost);
      e.dataTransfer.setDragImage(ghost, 24, 24);
      setTimeout(() => ghost.remove(), 0);
    });
    scroller.addEventListener('dragend', () => {
      dragPaths = null;
      clearDrop();
    });
    // Folders inside the pane, or the pane itself (= the current folder).
    scroller.addEventListener('dragover', (e) => {
      const it = itemOf(e.target);
      const d = it ? (it.dir && !it.drive ? it.path : null) : isReal() ? loc : null;
      if (!dragPaths || !d || !canDrop(dragPaths, d)) return;
      e.preventDefault();
      e.dataTransfer!.dropEffect = 'move';
      clearDrop();
      (it ? els.get(it.path) : scroller)?.classList.add('drop');
    });
    scroller.addEventListener('dragleave', (e) => {
      if (!scroller.contains(e.relatedTarget as Node | null)) clearDrop();
    });
    scroller.addEventListener('drop', (e) => {
      const it = itemOf(e.target);
      const d = it ? (it.dir && !it.drive ? it.path : null) : isReal() ? loc : null;
      if (!dragPaths || !d || !canDrop(dragPaths, d)) return;
      e.preventDefault();
      clearDrop();
      void moveInto(dragPaths, d);
    });

    /* ---------- keyboard ---------- */
    const moveFocus = (key: string, extend: boolean) => {
      if (!shown.length) return;
      const cur = focused && els.has(focused) ? focused : [...sel][0] ?? null;
      let next: string;
      if (!cur) next = shown[0].path;
      else if (key === 'Home') next = shown[0].path;
      else if (key === 'End') next = shown[shown.length - 1].path;
      else {
        const i = shown.findIndex((x) => x.path === cur);
        const step = key === 'ArrowLeft' || key === 'ArrowUp' ? -1 : 1;
        if (view === 'details' && loc !== COMPUTER) {
          if (key === 'ArrowLeft' || key === 'ArrowRight') return;
          next = shown[Math.max(0, Math.min(shown.length - 1, i + step))].path;
        } else if (key === 'ArrowLeft' || key === 'ArrowRight') {
          next = shown[Math.max(0, Math.min(shown.length - 1, i + step))].path;
        } else {
          const from = els.get(cur)!.getBoundingClientRect();
          const cx = from.left + from.width / 2;
          let best = Infinity;
          next = cur;
          for (const [p, el] of els) {
            const r = el.getBoundingClientRect();
            const dy = (r.top - from.top) * step;
            if (dy < 4) continue;
            const score = dy * 1000 + Math.abs(r.left + r.width / 2 - cx);
            if (score < best) {
              best = score;
              next = p;
            }
          }
        }
      }
      focused = next;
      if (extend) selectRange(next);
      else setSel([next], next);
      els.get(next)?.scrollIntoView({ block: 'nearest' });
    };

    root.addEventListener('keydown', (e) => {
      const t = e.target as HTMLElement;
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key;
      if (t === searchInput) {
        if (key === 'Escape') {
          searchInput.value = '';
          onSearch();
          scroller.focus();
        }
        return;
      }
      if (t === addrInput || t.closest('.sheet-backdrop, .ex-preview')) return;
      // Enter / Space on a toolbar or sidebar button belongs to that button.
      if ((key === 'Enter' || key === ' ') && t.closest('.ex-nav, .ex-cmd, .ex-addr-row')) return;
      if (mod && key.toLowerCase() === 'f') {
        e.preventDefault();
        searchInput.focus();
      } else if (mod && key.toLowerCase() === 'l') {
        e.preventDefault();
        editAddress();
      } else if (e.altKey && key === 'ArrowLeft') goBack();
      else if (e.altKey && key === 'ArrowRight') goForward();
      else if ((e.altKey && key === 'ArrowUp') || key === 'Backspace') goUp();
      else if (mod && key.toLowerCase() === 'a') {
        e.preventDefault();
        setSel(shown.map((i) => i.path), shown[0]?.path ?? null);
      } else if (mod && key.toLowerCase() === 'c') setClipboard(false);
      else if (mod && key.toLowerCase() === 'x') setClipboard(true);
      else if (mod && key.toLowerCase() === 'v') paste();
      else if (mod && e.shiftKey && key.toLowerCase() === 'n') {
        e.preventDefault();
        void newFolder();
      } else if (key === 'F2') startRename();
      else if (key === 'F5') {
        e.preventDefault();
        void refresh(true);
      } else if (key === 'Delete') deleteSelection();
      else if (key === 'Enter') void openSelection();
      else if (key === ' ' && selected().length === 1 && isImage(selected()[0].name)) {
        e.preventDefault();
        openItem(selected()[0]);
      } else if (key === 'Escape') setSel([]);
      else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(key) && !e.altKey) {
        e.preventDefault();
        moveFocus(key, e.shiftKey);
      }
    });

    /* ---------- address + search ---------- */
    function editAddress() {
      addr.classList.add('editing');
      addrInput.value = loc === COMPUTER ? 'Computer' : loc;
      addrInput.focus();
      addrInput.select();
    }
    const endEditAddress = () => addr.classList.remove('editing');
    addr.addEventListener('mousedown', (e) => {
      if (e.target === addr || e.target === crumbs || e.target === addrIcon) {
        e.preventDefault();
        editAddress();
      }
    });
    addrInput.addEventListener('keydown', async (e) => {
      e.stopPropagation();
      if (e.key === 'Escape') {
        endEditAddress();
        scroller.focus();
      } else if (e.key === 'Enter') {
        const raw = addrInput.value.trim();
        const path = normalize(raw.replace(/\\/g, '/'));
        if (/^computer$/i.test(raw)) navigate(COMPUTER);
        else if ((await fs.stat(path))?.type === 'dir') navigate(path);
        else notify(`Explorer can't find "${raw}". Check the spelling and try again.`);
        endEditAddress();
        scroller.focus();
      }
    });
    addrInput.addEventListener('blur', endEditAddress);

    const onSearch = () => {
      query = searchInput.value;
      searchClear.hidden = !query;
      applyFilter();
      renderContent();
      renderCommands();
    };
    searchInput.addEventListener('input', onSearch);
    searchClear.addEventListener('click', () => {
      searchInput.value = '';
      onSearch();
      searchInput.focus();
    });

    /* ---------- live refresh ---------- */
    // Apps have no bus access, so re-list on focus and poll cheaply; refresh() ignores unchanged listings.
    root.addEventListener('focusin', () => void refresh());
    const poll = window.setInterval(() => !document.hidden && void refresh(), 1200);

    /* ---------- go ---------- */
    void (async () => {
      await seedSamples(fs);
      const raw = typeof args.path === 'string' ? normalize(args.path) : '/Documents';
      const start = raw === '/' ? COMPUTER : (await fs.stat(raw))?.type === 'dir' ? raw : '/Documents';
      navigate(start);
      setTimeout(() => scroller.focus(), 50);
    })();

    return () => {
      disposed = true;
      clearInterval(poll);
    };
  },
};
