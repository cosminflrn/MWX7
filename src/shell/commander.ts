import { basename, dirname, fs, normalize } from '../core/fs';
import { h } from '../ui/dom';
import '../styles/commander.css';

/**
 * MWX Commander: a full-screen, DOS-era two-panel file manager shown from the BIOS.
 * The whole UI is an 80x25 character buffer (like a VGA text screen) painted into row <div>s,
 * so box-drawing, colours and mouse hit-testing all work in cell coordinates.
 * Everything goes through the real VFS, so changes persist.
 */

const COLS = 80;
const ROWS = 25;
const PANEL_W = 40;
const LIST_TOP = 3; // first file row inside a panel
const LIST_ROWS = 17;
const COL_NAME = 13;
const COL_SIZE = 9;
const COL_DATE = 8;
const COL_TIME = 5;

/* EGA colour indexes (see commander.css). */
const BLACK = 0;
const BLUE = 1;
const CYAN = 3;
const RED = 4;
const GREY = 7;
const DGREY = 8;
const LCYAN = 11;
const YELLOW = 14;
const WHITE = 15;

const at = (fg: number, bg: number) => (bg << 4) | fg;

/* ---------- text-mode screen buffer ---------- */

class Buffer {
  ch: string[] = new Array(COLS * ROWS).fill(' ');
  at: number[] = new Array(COLS * ROWS).fill(at(GREY, BLACK));

  clear(a: number): void {
    this.ch.fill(' ');
    this.at.fill(a);
  }
  put(x: number, y: number, text: string, a: number): void {
    if (y < 0 || y >= ROWS) return;
    for (let i = 0; i < text.length; i++) {
      const cx = x + i;
      if (cx < 0 || cx >= COLS) continue;
      this.ch[y * COLS + cx] = text[i]!;
      this.at[y * COLS + cx] = a;
    }
  }
  fill(x: number, y: number, w: number, hh: number, a: number): void {
    for (let r = 0; r < hh; r++) this.put(x, y + r, ' '.repeat(w), a);
  }
  /** Recolours without touching the characters (used for dialog shadows). */
  tint(x: number, y: number, a: number): void {
    if (x < 0 || x >= COLS || y < 0 || y >= ROWS) return;
    this.at[y * COLS + x] = a;
  }
  box(x: number, y: number, w: number, hh: number, a: number): void {
    this.put(x, y, '╔' + '═'.repeat(w - 2) + '╗', a);
    for (let r = 1; r < hh - 1; r++) {
      this.put(x, y + r, '║', a);
      this.put(x + w - 1, y + r, '║', a);
    }
    this.put(x, y + hh - 1, '╚' + '═'.repeat(w - 2) + '╝', a);
  }
  rowHtml(y: number): string {
    let html = '';
    let x = 0;
    while (x < COLS) {
      const a = this.at[y * COLS + x]!;
      let end = x + 1;
      while (end < COLS && this.at[y * COLS + end] === a) end++;
      let text = '';
      for (let i = x; i < end; i++) text += this.ch[y * COLS + i]!;
      text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
      html += `<span class="f${a & 15} b${a >> 4}" style="width:calc(var(--cw)*${end - x})">${text}</span>`;
      x = end;
    }
    return html;
  }
}

/* ---------- state ---------- */

interface Item {
  name: string;
  path: string;
  dir: boolean;
  up: boolean;
  size: number;
  modified: number;
}
interface Panel {
  path: string;
  items: Item[];
  sel: number;
  top: number;
}
interface Dialog {
  title: string;
  lines: string[];
  red: boolean;
  input?: string;
  buttons: string[];
  focus: number;
  /** `button` is the picked index, or -1 on Esc. */
  done: (button: number, value: string) => void | Promise<void>;
}
interface Viewer {
  title: string;
  lines: string[];
  top: number;
  size: number;
}

const FKEYS = ['Help', 'Menu', 'View', 'Edit', 'Copy', 'RenMov', 'Mkdir', 'Delete', 'PullDn', 'Quit'];
const encoder = new TextEncoder();

const dosPath = (p: string) => (normalize(p) === '/' ? 'C:\\' : 'C:' + normalize(p).replace(/\//g, '\\').toUpperCase());
const padR = (s: string, n: number) => (s.length >= n ? s.slice(0, n) : s + ' '.repeat(n - s.length));
const padL = (s: string, n: number) => (s.length >= n ? s.slice(0, n) : ' '.repeat(n - s.length) + s);
const center = (s: string, n: number) => {
  const left = Math.max(0, Math.floor((n - s.length) / 2));
  return padR(' '.repeat(left) + s, n);
};
const two = (n: number) => String(n).padStart(2, '0');

function fmtSize(n: number): string {
  const s = n.toLocaleString('en-US');
  return s.length <= COL_SIZE ? s : Math.round(n / 1024) + 'K';
}
function fmtDate(ms: number): string {
  const d = new Date(ms);
  return `${two(d.getDate())}-${two(d.getMonth() + 1)}-${two(d.getFullYear() % 100)}`;
}
function fmtTime(ms: number): string {
  const d = new Date(ms);
  return `${two(d.getHours())}:${two(d.getMinutes())}`;
}

/** DOS-style path input to a VFS path; segment names match case-insensitively since we display uppercase. */
async function resolvePath(base: string, input: string): Promise<string> {
  let s = input.trim().replace(/\//g, '\\');
  let cur = normalize(base);
  if (/^[a-z]:/i.test(s)) {
    s = s.slice(2);
    cur = '/';
  }
  if (s.startsWith('\\')) {
    cur = '/';
    s = s.slice(1);
  }
  for (const seg of s.split('\\').filter(Boolean)) {
    if (seg === '.') continue;
    if (seg === '..') {
      cur = dirname(cur);
      continue;
    }
    const match = (await fs.list(cur)).find((e) => e.name.toLowerCase() === seg.toLowerCase());
    cur = normalize(cur + '/' + (match ? match.name : seg));
  }
  return cur;
}

async function isDirectory(path: string): Promise<boolean> {
  return (await fs.stat(path))?.type === 'dir';
}

async function copyTree(src: string, dst: string): Promise<void> {
  const st = await fs.stat(src);
  if (!st) throw new Error('Source no longer exists');
  if (st.type === 'dir') {
    await fs.mkdir(dst);
    for (const e of await fs.list(src)) await copyTree(e.path, normalize(dst + '/' + e.name));
  } else {
    await fs.write(dst, (await fs.read(src)) ?? '');
  }
}

let running: Promise<void> | null = null;

/** Full-screen two-panel file manager shown from the BIOS. Resolves when the user exits (F10 / Esc). */
export function openCommander(): Promise<void> {
  return (running ??= run().finally(() => {
    running = null;
  }));
}

function run(): Promise<void> {
  return new Promise<void>((resolve) => {
    const buf = new Buffer();
    const screen = h('div', { class: 'cmdr-screen' });
    const probe = h('span', { class: 'cmdr-probe' }, 'M'.repeat(40));
    const root = h('div', { class: 'mwx-cmdr', tabindex: -1 }, screen, probe);
    const rowEls: HTMLElement[] = [];
    const rowCache: string[] = [];
    for (let y = 0; y < ROWS; y++) {
      const r = h('div', { class: 'cmdr-row' });
      rowEls.push(r);
      screen.append(r);
    }
    document.body.append(root);

    const panels: Panel[] = [
      { path: '/Documents', items: [], sel: 0, top: 0 },
      { path: '/', items: [], sel: 0, top: 0 },
    ];
    let active = 0;
    let mode: 'main' | 'view' | 'console' | 'exit' = 'main';
    let cmd = '';
    let blink = true;
    let busy = false;
    let dialog: Dialog | null = null;
    let dialogBtns: { x: number; y: number; w: number }[] = [];
    let viewer: Viewer | null = null;
    let consoleLines: string[] = [];
    let lastClick = { t: 0, panel: -1, idx: -1 };

    const cur = () => panels[active]!;
    const other = () => panels[1 - active]!;
    const selected = (): Item | undefined => cur().items[cur().sel];

    /* ----- layout: fit the 80x25 grid to the viewport ----- */
    function layout(): void {
      const ratio = probe.getBoundingClientRect().width / 4000 || 0.6;
      const cw = window.innerWidth / COLS;
      const fsz = cw / ratio;
      // Whole-pixel rows: fractional row heights leave dark seams between rows of the same colour.
      const lh = Math.max(8, Math.floor(window.innerHeight / ROWS));
      root.style.setProperty('--cw', cw + 'px');
      const fs = Math.min(fsz, lh / 1.05);
      root.style.setProperty('--fs', fs + 'px');
      // Pin every glyph to exactly one cell, whatever font the browser picked.
      root.style.setProperty('--ls', cw - fs * ratio + 'px');
      root.style.setProperty('--lh', lh + 'px');
      screen.style.top = Math.floor((window.innerHeight - lh * ROWS) / 2) + 'px';
    }

    /* ----- drawing ----- */
    function drawPanel(i: number): void {
      const p = panels[i]!;
      const x0 = i * PANEL_W;
      const isActive = i === active;
      const base = at(LCYAN, BLUE);
      const sepX = [1 + COL_NAME, 2 + COL_NAME + COL_SIZE, 3 + COL_NAME + COL_SIZE + COL_DATE].map((s) => x0 + s);
      buf.fill(x0, 1, PANEL_W, 22, base);

      // Top border with the path.
      buf.put(x0, 1, '╔' + '═'.repeat(PANEL_W - 2) + '╗', base);
      for (const sx of sepX) buf.put(sx, 1, '╤', base);
      let title = dosPath(p.path);
      if (title.length > PANEL_W - 8) title = '..' + title.slice(title.length - (PANEL_W - 10));
      buf.put(x0 + Math.floor((PANEL_W - title.length - 2) / 2), 1, ' ' + title + ' ', isActive ? at(BLACK, CYAN) : at(WHITE, BLUE));

      // Column header.
      buf.put(x0, 2, '║', base);
      buf.put(x0 + PANEL_W - 1, 2, '║', base);
      const head = [
        center('Name', COL_NAME),
        center('Size', COL_SIZE),
        center('Date', COL_DATE),
        center('Time', COL_TIME),
      ];
      buf.put(x0 + 1, 2, head.join('│'), at(YELLOW, BLUE));
      for (const sx of sepX) buf.put(sx, 2, '│', base);

      // File rows.
      for (let r = 0; r < LIST_ROWS; r++) {
        const y = LIST_TOP + r;
        buf.put(x0, y, '║', base);
        buf.put(x0 + PANEL_W - 1, y, '║', base);
        for (const sx of sepX) buf.put(sx, y, '│', base);
        const it = p.items[p.top + r];
        if (!it) continue;
        const name = it.up ? '..' : it.name.toUpperCase();
        const shown = name.length > COL_NAME ? name.slice(0, COL_NAME - 1) + '»' : name;
        const size = it.up ? 'UP--DIR' : it.dir ? '<DIR>' : fmtSize(it.size);
        const line = [
          padR(shown, COL_NAME),
          padL(size, COL_SIZE),
          it.up ? ' '.repeat(COL_DATE) : fmtDate(it.modified),
          it.up ? ' '.repeat(COL_TIME) : fmtTime(it.modified),
        ].join('│');
        const isSel = isActive && p.top + r === p.sel;
        const a = isSel ? at(BLACK, CYAN) : it.dir ? at(WHITE, BLUE) : at(YELLOW, BLUE);
        buf.put(x0 + 1, y, line, a);
        if (isSel) for (const sx of sepX) buf.put(sx, y, '│', a);
      }

      // Separator + mini status line.
      buf.put(x0, 20, '╟' + '─'.repeat(PANEL_W - 2) + '╢', base);
      for (const sx of sepX) buf.put(sx, 20, '┴', base);
      buf.put(x0, 21, '║', base);
      buf.put(x0 + PANEL_W - 1, 21, '║', base);
      const it = p.items[p.sel];
      if (it) {
        const left = it.up ? 'UP--DIR' : it.name.toUpperCase();
        const right = it.up ? '' : it.dir ? 'SUB-DIR' : fmtSize(it.size) + ' bytes';
        const room = PANEL_W - 2 - right.length - 1;
        buf.put(x0 + 1, 21, padR(left.length > room ? left.slice(0, room - 1) + '»' : left, room) + ' ' + right, at(WHITE, BLUE));
      }
      buf.put(x0, 22, '╚' + '═'.repeat(PANEL_W - 2) + '╝', base);
    }

    function drawFKeys(y: number, only?: number[]): void {
      buf.fill(0, y, COLS, 1, at(GREY, BLACK));
      FKEYS.forEach((label, i) => {
        if (only && !only.includes(i + 1)) return;
        const num = String(i + 1);
        const x = i * 8;
        buf.put(x, y, num, at(WHITE, BLACK));
        buf.put(x + num.length, y, padR(label, 8 - num.length - 1), at(BLACK, CYAN));
      });
    }

    function drawDialog(d: Dialog): void {
      const bg = d.red ? RED : GREY;
      const fg = d.red ? WHITE : BLACK;
      const body = at(fg, bg);
      const btnText = d.buttons.map((b) => `[ ${b} ]`);
      const btnsW = btnText.join('  ').length;
      const inner = Math.max(30, d.title.length + 2, btnsW, ...d.lines.map((l) => l.length));
      const w = inner + 6;
      const hh = d.lines.length + (d.input !== undefined ? 1 : 0) + 6;
      const x = Math.floor((COLS - w) / 2);
      const y = Math.floor((ROWS - hh) / 2);

      // Shadow first so the box paints over its own corner.
      for (let r = 1; r <= hh; r++) {
        buf.tint(x + w, y + r, at(DGREY, BLACK));
        buf.tint(x + w + 1, y + r, at(DGREY, BLACK));
      }
      for (let c = 2; c < w + 2; c++) buf.tint(x + c, y + hh, at(DGREY, BLACK));

      buf.fill(x, y, w, hh, body);
      buf.box(x, y, w, hh, at(WHITE, bg));
      buf.put(x + Math.floor((w - d.title.length - 2) / 2), y, ' ' + d.title + ' ', d.red ? at(YELLOW, RED) : at(BLACK, GREY));
      let ly = y + 2;
      for (const line of d.lines) buf.put(x + 3, ly++, line, body);
      if (d.input !== undefined) {
        buf.put(x + 3, ly, ' '.repeat(inner), at(BLACK, CYAN));
        const room = inner - 1;
        const shown = d.input.length > room ? d.input.slice(d.input.length - room) : d.input;
        buf.put(x + 3, ly, shown, at(BLACK, CYAN));
        if (blink) buf.put(x + 3 + shown.length, ly, ' ', at(CYAN, BLACK));
        ly++;
      }
      ly++;
      dialogBtns = [];
      let bx = x + Math.floor((w - btnsW) / 2);
      btnText.forEach((t, i) => {
        const focused = d.input !== undefined ? i === 0 : i === d.focus;
        buf.put(bx, ly, t, focused ? at(BLACK, CYAN) : at(BLACK, GREY));
        dialogBtns.push({ x: bx, y: ly, w: t.length });
        bx += t.length + 2;
      });
    }

    function drawMain(): void {
      buf.clear(at(GREY, BLACK));
      buf.fill(0, 0, COLS, 1, at(BLACK, CYAN));
      buf.put(2, 0, 'Left', at(BLACK, CYAN));
      buf.put(12, 0, 'Files', at(BLACK, CYAN));
      buf.put(23, 0, 'Commands', at(BLACK, CYAN));
      buf.put(36, 0, 'Options', at(BLACK, CYAN));
      buf.put(COLS - 7, 0, 'Right', at(BLACK, CYAN));
      drawPanel(0);
      drawPanel(1);
      let prompt = dosPath(cur().path) + '>';
      if (prompt.length > COLS - 4) prompt = '..' + prompt.slice(prompt.length - (COLS - 6));
      buf.put(0, 23, prompt + cmd, at(GREY, BLACK));
      if (blink && !dialog) buf.put(Math.min(COLS - 1, prompt.length + cmd.length), 23, '_', at(GREY, BLACK));
      drawFKeys(24);
      if (dialog) drawDialog(dialog);
    }

    function drawViewer(v: Viewer): void {
      buf.clear(at(WHITE, BLUE));
      buf.fill(0, 0, COLS, 1, at(BLACK, CYAN));
      const pct = v.lines.length <= ROWS - 2 ? 100 : Math.round(((v.top + ROWS - 2) / v.lines.length) * 100);
      const tail = `${fmtSize(v.size)} bytes  ${Math.min(100, pct)}%`;
      buf.put(1, 0, v.title.length > COLS - tail.length - 4 ? '..' + v.title.slice(-(COLS - tail.length - 8)) : v.title, at(BLACK, CYAN));
      buf.put(COLS - tail.length - 1, 0, tail, at(BLACK, CYAN));
      for (let r = 0; r < ROWS - 2; r++) buf.put(0, 1 + r, v.lines[v.top + r] ?? '', at(WHITE, BLUE));
      drawFKeys(24, [1, 3, 10]);
      if (dialog) drawDialog(dialog);
    }

    function drawConsole(): void {
      buf.clear(at(GREY, BLACK));
      consoleLines.slice(-(ROWS - 2)).forEach((l, i) => buf.put(0, i, l.slice(0, COLS), at(GREY, BLACK)));
      buf.put(0, ROWS - 1, 'Press any key to return to MWX Commander...', at(BLACK, GREY));
    }

    function render(): void {
      if (mode === 'exit') {
        buf.clear(at(GREY, BLACK));
        buf.put(0, 0, 'Exiting MWX Commander...', at(GREY, BLACK));
      } else if (mode === 'view' && viewer) drawViewer(viewer);
      else if (mode === 'console') drawConsole();
      else drawMain();
      for (let y = 0; y < ROWS; y++) {
        const html = buf.rowHtml(y);
        if (rowCache[y] !== html) {
          rowCache[y] = html;
          rowEls[y]!.innerHTML = html;
        }
      }
    }

    /* ----- panels ----- */
    async function load(i: number, keepName?: string): Promise<void> {
      const p = panels[i]!;
      if (!(await isDirectory(p.path))) p.path = '/';
      const list = await fs.list(p.path);
      const items: Item[] = [];
      if (normalize(p.path) !== '/') {
        items.push({ name: '..', path: dirname(p.path), dir: true, up: true, size: 0, modified: 0 });
      }
      for (const e of list) {
        items.push({
          name: e.name,
          path: e.path,
          dir: e.type === 'dir',
          up: false,
          size: e.type === 'dir' ? 0 : encoder.encode(e.content).length,
          modified: e.modified,
        });
      }
      p.items = items;
      const idx = keepName === undefined ? -1 : items.findIndex((it) => it.name === keepName);
      p.sel = idx >= 0 ? idx : Math.min(p.sel, items.length - 1);
      fit(p);
    }

    function fit(p: Panel): void {
      p.sel = Math.max(0, Math.min(p.sel, p.items.length - 1));
      if (p.sel < p.top) p.top = p.sel;
      if (p.sel >= p.top + LIST_ROWS) p.top = p.sel - LIST_ROWS + 1;
      p.top = Math.max(0, Math.min(p.top, Math.max(0, p.items.length - LIST_ROWS)));
    }

    const reloadBoth = async (name?: string) => {
      const keep = selected()?.name;
      await Promise.all([load(active, name ?? keep), load(1 - active, other().items[other().sel]?.name)]);
    };

    async function enter(): Promise<void> {
      const it = selected();
      if (!it) return;
      if (it.dir) {
        const from = it.up ? basename(cur().path) : undefined;
        cur().path = it.path;
        cur().sel = 0;
        cur().top = 0;
        await load(active, from);
      } else await view(it);
    }

    async function view(it: Item): Promise<void> {
      if (it.dir) return;
      const text = await fs.read(it.path);
      if (text === null) return message('Error', ['Cannot read this file.'], true);
      const lines: string[] = [];
      for (const raw of text.replace(/\r/g, '').replace(/\t/g, '    ').split('\n')) {
        if (raw.length === 0) lines.push('');
        for (let i = 0; i < raw.length; i += COLS) lines.push(raw.slice(i, i + COLS));
      }
      viewer = { title: dosPath(it.path), lines, top: 0, size: it.size };
      mode = 'view';
    }

    /* ----- dialogs ----- */
    function message(title: string, lines: string[], red = false): void {
      dialog = { title, lines, red, buttons: ['OK'], focus: 0, done: () => undefined };
    }
    function prompt(title: string, line: string, value: string, run: (v: string) => Promise<void>): void {
      dialog = {
        title,
        lines: [line],
        red: false,
        input: value,
        buttons: ['OK', 'Cancel'],
        focus: 0,
        done: (b, v) => (b === 0 ? run(v) : undefined),
      };
    }

    /** Runs a VFS operation, then refreshes both panels; failures become an error box. */
    async function guarded(fn: () => Promise<string | void>): Promise<void> {
      try {
        const name = await fn();
        await reloadBoth(name || undefined);
      } catch (err) {
        message('Error', [String((err as Error).message ?? err).replace(/^\[fs\]\s*/, '')], true);
        await reloadBoth();
      }
    }

    /** Where a copy/move of `it` should land for the typed destination. */
    async function destination(it: Item, typed: string): Promise<string> {
      const p = await resolvePath(cur().path, typed);
      const dst = (await isDirectory(p)) ? normalize(p + '/' + it.name) : p;
      if (dst === it.path) throw new Error('Source and destination are the same');
      if (dst.startsWith(it.path + '/')) throw new Error('Cannot copy a folder into itself');
      if (await fs.exists(dst)) throw new Error(dosPath(dst) + ' already exists');
      return dst;
    }

    /* ----- F-keys ----- */
    function fkey(n: number): void {
      const it = selected();
      switch (n) {
        case 1:
          message('MWX Commander', [
            'Tab        switch panel',
            'Enter      open folder / view file',
            'F3         view    F5  copy    F6  move or rename',
            'F7         new folder    F8  delete',
            'F10 / Esc  quit',
            'Type cd, dir, cls or exit on the command line.',
          ]);
          break;
        case 2:
        case 4:
        case 9:
          message('Not available', [`${n === 4 ? 'Editing' : 'Menus'} are not available in this version.`]);
          break;
        case 3:
          if (it && !it.dir) void run1(() => view(it));
          break;
        case 5:
          if (it && !it.up) {
            prompt('Copy', `Copy "${it.name.toUpperCase()}" to:`, dosPath(other().path), (v) =>
              guarded(async () => {
                const dst = await destination(it, v);
                await copyTree(it.path, dst);
                return basename(dst);
              }),
            );
          }
          break;
        case 6:
          if (it && !it.up) {
            prompt('Rename / Move', `Rename or move "${it.name.toUpperCase()}" to:`, dosPath(other().path), (v) =>
              guarded(async () => {
                const dst = await destination(it, v);
                await fs.rename(it.path, dst);
                return basename(dst);
              }),
            );
          }
          break;
        case 7:
          prompt('Make directory', 'Create the directory:', '', (v) =>
            guarded(async () => {
              if (!v.trim()) return;
              const p = await resolvePath(cur().path, v);
              if (await fs.exists(p)) throw new Error(dosPath(p) + ' already exists');
              await fs.mkdir(p);
              return dirname(p) === normalize(cur().path) ? basename(p) : undefined;
            }),
          );
          break;
        case 8:
          if (it && !it.up) {
            dialog = {
              title: 'Delete',
              lines: [`Do you wish to delete the ${it.dir ? 'directory' : 'file'}`, `"${it.name.toUpperCase()}"?`],
              red: true,
              buttons: ['Delete', 'Cancel'],
              focus: 0,
              done: (b) => (b === 0 ? guarded(() => fs.remove(it.path)) : undefined),
            };
          }
          break;
        case 10:
          void quit();
          break;
      }
    }

    async function run1(fn: () => Promise<void>): Promise<void> {
      busy = true;
      try {
        await fn();
      } finally {
        busy = false;
        render();
      }
    }

    /* ----- command line ----- */
    async function execute(line: string): Promise<void> {
      const [word = '', ...rest] = line.trim().split(/\s+/);
      const arg = rest.join(' ');
      const echo = dosPath(cur().path) + '>' + line;
      const w = word.toLowerCase();
      if (w === 'exit') return quit();
      if (w === 'cls') return;
      if (w === 'cd' || w === 'cd..' || w === 'cd\\' || /^[a-z]:$/i.test(w)) {
        const target = w === 'cd..' ? '..' : w === 'cd\\' ? '\\' : /^[a-z]:$/i.test(w) ? '\\' : arg || '';
        if (!target) return console_([echo, dosPath(cur().path)]);
        const p = await resolvePath(cur().path, target);
        if (!(await isDirectory(p))) return console_([echo, 'Invalid directory']);
        const from = dirname(cur().path) === p ? basename(cur().path) : undefined;
        cur().path = p;
        cur().sel = 0;
        cur().top = 0;
        return load(active, from);
      }
      if (w === 'dir') {
        const p = arg ? await resolvePath(cur().path, arg) : cur().path;
        if (!(await isDirectory(p))) return console_([echo, 'File not found']);
        const list = await fs.list(p);
        const out = [echo, '', ' Volume in drive C is MWX7', ' Directory of ' + dosPath(p), ''];
        let bytes = 0;
        for (const e of list) {
          const size = e.type === 'dir' ? 0 : encoder.encode(e.content).length;
          bytes += size;
          const nm = e.name.toUpperCase();
          out.push(`${padR(nm, 18)}${padL(e.type === 'dir' ? '<DIR>' : fmtSize(size), 10)}  ${fmtDate(e.modified)}  ${fmtTime(e.modified)}`);
        }
        out.push('', `${list.length} item(s)   ${fmtSize(bytes)} bytes`);
        return console_(out);
      }
      console_([echo, 'Bad command or file name']);
    }

    function console_(lines: string[]): void {
      consoleLines = lines;
      mode = 'console';
    }

    /* ----- quit ----- */
    let closed = false;
    async function quit(): Promise<void> {
      if (closed) return;
      closed = true;
      mode = 'exit';
      dialog = null;
      render();
      await new Promise((r) => window.setTimeout(r, 750));
      window.clearInterval(timer);
      window.removeEventListener('keydown', onKey, true);
      window.removeEventListener('resize', layout);
      root.remove();
      resolve();
    }

    /* ----- keyboard ----- */
    function move(delta: number): void {
      const p = cur();
      p.sel = Math.max(0, Math.min(p.items.length - 1, p.sel + delta));
      fit(p);
    }

    function dialogKey(e: KeyboardEvent, d: Dialog): void {
      const pick = (b: number) => {
        dialog = null;
        void run1(async () => {
          await d.done(b, d.input ?? '');
        });
      };
      if (e.key === 'Escape') return pick(-1);
      if (e.key === 'Enter') return pick(d.input !== undefined ? 0 : d.focus);
      if (d.input !== undefined) {
        if (e.key === 'Backspace') d.input = d.input.slice(0, -1);
        else if (e.key === 'Delete') d.input = '';
        else if (e.key.length === 1) d.input += e.key;
        return;
      }
      if (['ArrowLeft', 'ArrowRight', 'Tab'].includes(e.key)) d.focus = (d.focus + 1) % d.buttons.length;
      else if (e.key.toLowerCase() === 'y') pick(0);
      else if (e.key.toLowerCase() === 'n') pick(d.buttons.length - 1);
    }

    function viewerKey(e: KeyboardEvent, v: Viewer): void {
      const page = ROWS - 2;
      const max = Math.max(0, v.lines.length - page);
      const step: Record<string, number> = { ArrowUp: -1, ArrowDown: 1, PageUp: -page, PageDown: page };
      if (['Escape', 'F3', 'F10', 'q', 'Q'].includes(e.key)) {
        mode = 'main';
        viewer = null;
      } else if (e.key === 'F1') message('Viewer', ['Up/Down/PgUp/PgDn/Home/End  scroll', 'Esc / F3 / F10            back']);
      else if (e.key === 'Home') v.top = 0;
      else if (e.key === 'End') v.top = max;
      else if (e.key in step) v.top = Math.max(0, Math.min(max, v.top + step[e.key]!));
    }

    function onKey(e: KeyboardEvent): void {
      if (e.ctrlKey || e.metaKey || e.altKey || e.key === 'F12') return;
      // Swallow everything else so the BIOS underneath and the browser (F5 reload, F3 find...) never see it.
      e.preventDefault();
      e.stopImmediatePropagation();
      blink = true;
      if (busy || mode === 'exit') return;
      if (mode === 'console') {
        if (!['Shift', 'Control', 'Alt', 'Meta'].includes(e.key)) mode = 'main';
      } else if (dialog) dialogKey(e, dialog);
      else if (mode === 'view' && viewer) viewerKey(e, viewer);
      else mainKey(e);
      render();
    }

    function mainKey(e: KeyboardEvent): void {
      const fm = /^F(\d{1,2})$/.exec(e.key);
      if (fm) return fkey(Number(fm[1]));
      switch (e.key) {
        case 'Tab':
          active = 1 - active;
          return;
        case 'ArrowUp':
          return move(-1);
        case 'ArrowDown':
          return move(1);
        case 'PageUp':
          return move(-LIST_ROWS);
        case 'PageDown':
          return move(LIST_ROWS);
        case 'Home':
          return move(-1e9);
        case 'End':
          return move(1e9);
        case 'Escape':
          if (cmd) cmd = '';
          else void quit();
          return;
        case 'Backspace':
          cmd = cmd.slice(0, -1);
          return;
        case 'Enter': {
          if (cmd.trim()) {
            const line = cmd;
            cmd = '';
            void run1(() => execute(line));
          } else void run1(enter);
          return;
        }
        default:
          if (e.key.length === 1 && cmd.length < COLS - 20) cmd += e.key;
      }
    }

    /* ----- mouse ----- */
    root.addEventListener('pointerdown', (ev) => {
      ev.stopPropagation();
      if (busy || mode === 'exit') return;
      const rect = screen.getBoundingClientRect();
      const col = Math.floor(((ev.clientX - rect.left) / rect.width) * COLS);
      const row = Math.floor(((ev.clientY - rect.top) / rect.height) * ROWS);
      if (mode === 'console') {
        mode = 'main';
      } else if (dialog) {
        const d = dialog;
        const b = dialogBtns.findIndex((r) => row === r.y && col >= r.x && col < r.x + r.w);
        if (b >= 0) {
          dialog = null;
          void run1(async () => {
            await d.done(b, d.input ?? '');
          });
        }
      } else if (mode === 'main') {
        if (row === 24) fkey(Math.min(10, Math.floor(col / 8) + 1));
        else if (row === 0) fkey(2);
        else if (row >= LIST_TOP && row < LIST_TOP + LIST_ROWS) {
          const pi = col < PANEL_W ? 0 : 1;
          const idx = panels[pi]!.top + row - LIST_TOP;
          if (idx < panels[pi]!.items.length) {
            active = pi;
            panels[pi]!.sel = idx;
            const now = performance.now();
            const dbl = lastClick.panel === pi && lastClick.idx === idx && now - lastClick.t < 450;
            lastClick = { t: now, panel: pi, idx };
            if (dbl) void run1(enter);
          }
        }
      } else if (mode === 'view' && row === 24) {
        fkey(Math.min(10, Math.floor(col / 8) + 1));
        if (Math.floor(col / 8) === 9 || Math.floor(col / 8) === 2) {
          mode = 'main';
          viewer = null;
        }
      }
      render();
    });
    root.addEventListener(
      'wheel',
      (ev) => {
        if (mode === 'view' && viewer) {
          viewer.top = Math.max(0, Math.min(Math.max(0, viewer.lines.length - (ROWS - 2)), viewer.top + Math.sign(ev.deltaY) * 3));
        } else if (mode === 'main' && !dialog) {
          const rect = screen.getBoundingClientRect();
          active = ev.clientX - rect.left < rect.width / 2 ? 0 : 1;
          move(Math.sign(ev.deltaY) * 3);
        }
        render();
      },
      { passive: true },
    );

    /* ----- go ----- */
    // Capture phase on window: runs before the BIOS screen's own key handlers.
    window.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', layout);
    const timer = window.setInterval(() => {
      blink = !blink;
      render();
    }, 530);
    layout();
    render();
    void Promise.all([load(0), load(1)]).then(render);
  });
}
