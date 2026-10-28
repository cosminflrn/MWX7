import type { AppManifest, VFS } from '../../core/types';
import { h } from '../../ui/dom';
import { terminalIcon } from './icon';
import './terminal.css';

const VERSION = '0.2.0';
const ROOTS = ['/', '/Desktop', '/Documents', '/Pictures', '/Music', '/Trash'];
const COMMANDS = [
  'cat', 'cd', 'clear', 'date', 'echo', 'help', 'history', 'ls', 'mkdir', 'mwx7fetch', 'open', 'pwd', 'rm', 'touch', 'whoami',
];
const startedAt = Date.now();

/* ---------- path + directory helpers ---------- */

function resolve(cwd: string, p: string): string {
  const out: string[] = [];
  const src = p.startsWith('/') ? p : `${cwd}/${p}`;
  for (const part of src.replace(/^~/, '/Documents').split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') out.pop();
    else out.push(part);
  }
  return '/' + out.join('/');
}
const dirOf = (p: string) => p.slice(0, p.lastIndexOf('/')) || '/';
const baseOf = (p: string) => p.slice(p.lastIndexOf('/') + 1);

interface Entry { name: string; isDir: boolean; size: number; modified: number }

/**
 * All directory knowledge lives here. Today folders are implied by path prefixes (plus a session-only set for
 * `mkdir`); once the VFS grows real folders, the `mkdir` feature-detect below picks them up. Simplify then.
 */
function makeDirs(fs: VFS) {
  const session = new Set<string>();
  const native = fs as VFS & { mkdir?: (path: string) => Promise<void> };

  const isDir = async (p: string): Promise<boolean> => {
    if (ROOTS.includes(p) || session.has(p)) return true;
    return (await fs.all()).some((f) => f.path.startsWith(p + '/'));
  };

  const list = async (dir: string): Promise<Entry[]> => {
    const all = await fs.all();
    const out = new Map<string, Entry>();
    const prefix = dir === '/' ? '/' : dir + '/';
    for (const f of all) {
      if (!f.path.startsWith(prefix)) continue;
      const rest = f.path.slice(prefix.length);
      const slash = rest.indexOf('/');
      if (slash === -1) out.set(rest, { name: rest, isDir: false, size: f.content.length, modified: f.modified });
      else if (!out.has(rest.slice(0, slash))) out.set(rest.slice(0, slash), { name: rest.slice(0, slash), isDir: true, size: 0, modified: f.modified });
    }
    for (const d of [...ROOTS, ...session]) {
      if (d !== '/' && dirOf(d) === dir && !out.has(baseOf(d))) out.set(baseOf(d), { name: baseOf(d), isDir: true, size: 0, modified: startedAt });
    }
    return [...out.values()].sort((a, b) => Number(b.isDir) - Number(a.isDir) || a.name.localeCompare(b.name));
  };

  const mkdir = async (p: string) => {
    if (typeof native.mkdir === 'function') await native.mkdir(p);
    else session.add(p);
  };
  return { isDir, list, mkdir, session };
}

/* ---------- command line parsing ---------- */

interface Tok { v: string; quoted: boolean }
function tokenize(line: string): Tok[] {
  const toks: Tok[] = [];
  let cur = '';
  let quoted = false;
  let q: string | null = null;
  let has = false;
  const push = () => {
    if (has) toks.push({ v: cur, quoted });
    cur = '';
    quoted = false;
    has = false;
  };
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (q) {
      if (c === q) q = null;
      else cur += c;
    } else if (c === '"' || c === "'") {
      q = c;
      quoted = has = true;
    } else if (c === ' ' || c === '\t') push();
    else if (c === '>' && !has) {
      const op = line[i + 1] === '>' ? '>>' : '>';
      i += op.length - 1;
      toks.push({ v: op, quoted: false });
    } else {
      cur += c;
      has = true;
    }
  }
  push();
  return toks;
}

/* ---------- app ---------- */

export const terminal: AppManifest = {
  id: 'terminal',
  name: 'Terminal',
  icon: terminalIcon,
  description: 'Command line for your MWX 7 files',
  keywords: ['shell', 'console', 'command', 'cli', 'bash', 'prompt'],
  pinned: true,
  desktop: false,
  window: { width: 700, height: 440, minWidth: 380, minHeight: 220 },

  mount({ win, fs, os }) {
    const dirs = makeDirs(fs);
    let cwd = '/Documents';
    let buf = '';
    let pos = 0;
    let busy = false;
    const history: string[] = [];
    let hIdx = 0;
    let draft = '';

    win.body.classList.add('term');
    win.body.tabIndex = 0;
    win.setTitle('Terminal — MWX 7');
    const scroll = h('div', { class: 'term-scroll' });
    const log = h('div', { class: 'term-log' });
    const inputLine = h('div', { class: 'term-line term-input' });
    scroll.append(log, inputLine);
    win.body.append(scroll);

    const user = () => os.settings.get().userName || 'user';
    const toBottom = () => { scroll.scrollTop = scroll.scrollHeight; };

    const line = (content: (Node | string)[] | string = '', cls = '') => {
      log.append(h('div', { class: `term-line ${cls}`.trim() }, ...(Array.isArray(content) ? content : [content])));
    };
    const err = (msg: string) => line(msg, 'err');
    const span = (cls: string, text: string) => h('span', { class: cls }, text);
    const promptNodes = (): (Node | string)[] => [span('t-user', `${user()}@mwx7`), ' ', span('t-path', cwd), ' ', span('t-sym', '❯'), ' '];

    let cursorEl: HTMLElement | null = null;
    const render = () => {
      inputLine.replaceChildren(...promptNodes(), buf.slice(0, pos));
      cursorEl = h('span', { class: 'term-cursor moving' }, pos < buf.length ? buf[pos] : ' ');
      inputLine.append(cursorEl, buf.slice(pos + 1));
      // keep the cursor solid while typing, resume blinking when idle
      clearTimeout(idle);
      idle = window.setTimeout(() => cursorEl?.classList.remove('moving'), 500);
      toBottom();
    };
    let idle = 0;

    const clearScreen = () => { log.replaceChildren(); };

    /* ----- commands ----- */

    type Cmd = (args: Tok[]) => Promise<void> | void;
    const flagsAndArgs = (args: Tok[]) => {
      const flags = args.filter((a) => !a.quoted && /^-[a-zA-Z]+$/.test(a.v)).map((a) => a.v.slice(1)).join('');
      return { flags, rest: args.filter((a) => a.quoted || !/^-[a-zA-Z]+$/.test(a.v)).map((a) => a.v) };
    };
    const fmtDate = (t: number) => new Date(t).toLocaleDateString(undefined, { month: 'short', day: '2-digit' }) + ' ' +
      new Date(t).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
    const nameNode = (e: Entry): Node | string => (e.isDir ? span('t-dir', e.name + '/') : e.name);

    const writeFile = async (path: string, content: string, append: boolean) => {
      if (await dirs.isDir(path)) throw new Error(`${path}: is a directory`);
      const prev = append ? (await fs.read(path)) ?? '' : '';
      await fs.write(path, prev + content);
    };

    const cmds: Record<string, Cmd> = {
      help() {
        const rows: [string, string][] = [
          ['help', 'show this list'], ['ls [-l] [dir]', 'list files and folders'], ['cd [dir]', 'change directory'],
          ['pwd', 'print working directory'], ['cat <file…>', 'print file contents'],
          ['echo <text> [> file]', 'print text, or write (>) / append (>>) to a file'], ['touch <file…>', 'create empty files'],
          ['mkdir <dir…>', 'create folders'], ['rm [-r] <path…>', 'delete files (or folders with -r)'],
          ['open <file|app>', 'open a .txt in Notepad, or launch an app'], ['clear', 'clear the screen (Ctrl+L)'],
          ['date', 'current date and time'], ['whoami', 'current user'], ['history', 'previous commands'],
          ['mwx7fetch', 'system information'],
        ];
        for (const [c, d] of rows) line([span('t-key', c.padEnd(22)), span('dim', d)]);
        line('Tab completes, ↑/↓ browse history, Ctrl+C cancels, Ctrl+L clears.', 'dim');
      },
      async ls(args) {
        const { flags, rest } = flagsAndArgs(args);
        const target = resolve(cwd, rest[0] ?? '.');
        if (!(await dirs.isDir(target))) {
          if (await fs.exists(target)) return line(baseOf(target));
          return err(`ls: ${rest[0]}: no such file or directory`);
        }
        const entries = await dirs.list(target);
        if (!entries.length) return line('(empty)', 'dim');
        if (flags.includes('l')) {
          for (const e of entries) {
            line([span('dim', `${e.isDir ? 'd' : '-'}rw-  ${String(e.isDir ? '-' : e.size).padStart(7)}  ${fmtDate(e.modified)}  `), nameNode(e)]);
          }
        } else {
          line(entries.flatMap((e, i) => (i ? ['   ', nameNode(e)] : [nameNode(e)])));
        }
      },
      async cd(args) {
        const target = args[0] ? resolve(cwd, args[0].v) : '/Documents';
        if (await dirs.isDir(target)) cwd = target;
        else if (await fs.exists(target)) err(`cd: ${args[0].v}: not a directory`);
        else err(`cd: ${args[0].v}: no such directory`);
      },
      pwd() { line(cwd); },
      async cat(args) {
        if (!args.length) return err('usage: cat <file…>');
        for (const a of args) {
          const p = resolve(cwd, a.v);
          const text = await fs.read(p);
          if (text !== null) line(text.replace(/\n$/, ''));
          else err(`cat: ${a.v}: ${(await dirs.isDir(p)) ? 'is a directory' : 'no such file'}`);
        }
      },
      async echo(args) {
        const i = args.findIndex((a) => !a.quoted && (a.v === '>' || a.v === '>>'));
        const text = (i === -1 ? args : args.slice(0, i)).map((a) => a.v).join(' ');
        if (i === -1) return line(text);
        const target = args[i + 1];
        if (!target) return err('echo: missing file after redirection');
        try { await writeFile(resolve(cwd, target.v), text + '\n', args[i].v === '>>'); } catch (e) { err(`echo: ${(e as Error).message}`); }
      },
      async touch(args) {
        if (!args.length) return err('usage: touch <file…>');
        for (const a of args) {
          const p = resolve(cwd, a.v);
          if (!(await fs.exists(p))) await fs.write(p, '');
        }
      },
      async mkdir(args) {
        if (!args.length) return err('usage: mkdir <dir…>');
        for (const a of args) {
          const p = resolve(cwd, a.v);
          if ((await dirs.isDir(p)) || (await fs.exists(p))) err(`mkdir: ${a.v}: already exists`);
          else await dirs.mkdir(p);
        }
      },
      async rm(args) {
        const { flags, rest } = flagsAndArgs(args);
        if (!rest.length) return err('usage: rm [-r] <path…>');
        for (const r of rest) {
          const p = resolve(cwd, r);
          if (await fs.exists(p)) await fs.remove(p);
          else if (await dirs.isDir(p)) {
            if (!flags.includes('r')) err(`rm: ${r}: is a directory (use -r)`);
            else {
              for (const f of await fs.all()) if (f.path.startsWith(p + '/')) await fs.remove(f.path);
              dirs.session.delete(p);
              if (cwd === p || cwd.startsWith(p + '/')) cwd = dirOf(p);
            }
          } else err(`rm: ${r}: no such file or directory`);
        }
      },
      async open(args) {
        if (!args.length) return err('usage: open <file|app>');
        const name = args[0].v;
        const p = resolve(cwd, name);
        if (await fs.exists(p)) {
          if (/\.txt$/i.test(p)) os.launch('notepad', { path: p });
          else err(`open: no app is associated with ${baseOf(p)}`);
          return;
        }
        const key = name.toLowerCase();
        const app = os.apps().find((a) => a.id === key || a.name.toLowerCase() === key);
        if (app) os.launch(app.id);
        else err(`open: ${name}: no such file or app`);
      },
      clear() { clearScreen(); },
      date() { line(new Date().toString()); },
      whoami() { line(user()); },
      history() { history.forEach((c, i) => line([span('dim', String(i + 1).padStart(4) + '  '), c])); },
      mwx7fetch() {
        const orb = [
          '      .:::::::.      ',
          '    .::ooOOOoo::.    ',
          '  .:ooOOOOOOOOOoo:.  ',
          ' .:oOOOO@@@OOOOOOo:. ',
          ' :ooOOO@@@@@OOOOOoo: ',
          ' :ooOOOO@@@OOOOOOoo: ',
          ' ::oOOOOOOOOOOOOOo:: ',
          '  ::ooOOOOOOOOOoo::  ',
          "    ':::oooooo:::'    ",
        ];
        const paint = (row: string) => {
          const frag: (Node | string)[] = [];
          for (const ch of row) {
            const cls = ch === '@' ? 't-orb-b' : ch === 'O' || ch === 'o' ? 't-orb-a' : ch === ' ' ? '' : 't-orb-c';
            frag.push(cls ? span(cls, ch) : ch);
          }
          return frag;
        };
        const up = Math.floor((Date.now() - startedAt) / 1000);
        const uptime = up >= 3600 ? `${Math.floor(up / 3600)}h ${Math.floor((up % 3600) / 60)}m` : up >= 60 ? `${Math.floor(up / 60)}m ${up % 60}s` : `${up}s`;
        const info: (Node | string)[][] = [
          [span('t-user', user()), '@', span('t-user', 'mwx7')],
          [span('dim', '─'.repeat(user().length + 5))],
          [span('t-key', 'OS'.padEnd(12)), 'MWX 7'],
          [span('t-key', 'Version'.padEnd(12)), VERSION],
          [span('t-key', 'Resolution'.padEnd(12)), `${window.innerWidth}×${window.innerHeight}`],
          [span('t-key', 'Threads'.padEnd(12)), `${navigator.hardwareConcurrency || 1}`],
          [span('t-key', 'Uptime'.padEnd(12)), `${uptime}`],
          [span('t-key', 'Theme'.padEnd(12)), `Aero Glass`],
          [span('t-key', 'Terminal'.padEnd(12)), `mwx7-term`],
        ];
        orb.forEach((row, i) => line([...paint(row), '   ', ...(info[i] ?? [])]));
      },
    };

    const run = async (raw: string) => {
      const toks = tokenize(raw);
      if (!toks.length) return;
      const handler = cmds[toks[0].v];
      if (!handler) return err(`${toks[0].v}: command not found — try "help"`);
      try {
        await handler(toks.slice(1));
      } catch (e) {
        err(`${toks[0].v}: ${(e as Error).message}`);
      }
    };

    /* ----- completion ----- */

    const complete = async () => {
      const head = buf.slice(0, pos);
      const m = /(\S*)$/.exec(head)!;
      const word = m[1];
      const before = head.slice(0, head.length - word.length);
      const first = !before.trim();
      let cands: string[] = [];
      if (first) cands = COMMANDS.filter((c) => c.startsWith(word));
      else {
        const slash = word.lastIndexOf('/');
        const dirPart = slash === -1 ? '' : word.slice(0, slash + 1);
        const stem = word.slice(slash + 1);
        const dirPath = resolve(cwd, dirPart || '.');
        const entries = await dirs.list(dirPath);
        cands = entries.filter((e) => e.name.startsWith(stem)).map((e) => dirPart + e.name + (e.isDir ? '/' : ''));
        if (/^\s*open\s+\S*$/.test(head) && !dirPart) cands.push(...os.apps().map((a) => a.id).filter((id) => id.startsWith(word)));
      }
      if (!cands.length) return;
      let common = cands[0];
      for (const c of cands) while (!c.startsWith(common)) common = common.slice(0, -1);
      const single = cands.length === 1;
      const insert = common + (single && !common.endsWith('/') ? ' ' : '');
      if (insert.length > word.length) {
        buf = before + insert + buf.slice(pos);
        pos = before.length + insert.length;
      } else if (cands.length > 1) {
        line([...promptNodes(), buf]);
        line(cands.map((c) => baseOf(c.replace(/\/$/, '')) + (c.endsWith('/') ? '/' : '')).join('   '), 'dim');
      }
    };

    /* ----- keyboard ----- */

    const submit = async () => {
      const cmd = buf;
      line([...promptNodes(), cmd]);
      buf = '';
      pos = 0;
      if (cmd.trim() && history[history.length - 1] !== cmd) history.push(cmd);
      hIdx = history.length;
      busy = true;
      inputLine.style.display = 'none';
      await run(cmd);
      busy = false;
      inputLine.style.display = '';
      render();
    };

    const onKey = (e: KeyboardEvent) => {
      if (busy) return e.preventDefault();
      const ctrl = e.ctrlKey && !e.metaKey && !e.altKey;
      if (e.metaKey || (e.ctrlKey && e.altKey)) return;
      // Ctrl+C with a text selection stays a normal copy
      if (ctrl && e.key.toLowerCase() === 'c' && String(window.getSelection())) return;
      if (ctrl && e.key.toLowerCase() === 'v') return; // let the paste event handle it
      let handled = true;
      if (e.key === 'Enter') void submit();
      else if (e.key === 'Backspace') {
        if (pos > 0) { buf = buf.slice(0, pos - 1) + buf.slice(pos); pos--; }
      } else if (e.key === 'Delete') buf = buf.slice(0, pos) + buf.slice(pos + 1);
      else if (e.key === 'ArrowLeft') pos = Math.max(0, pos - 1);
      else if (e.key === 'ArrowRight') pos = Math.min(buf.length, pos + 1);
      else if (e.key === 'Home' || (ctrl && e.key === 'a')) pos = 0;
      else if (e.key === 'End' || (ctrl && e.key === 'e')) pos = buf.length;
      else if (ctrl && e.key === 'u') { buf = buf.slice(pos); pos = 0; }
      else if (ctrl && e.key === 'l') clearScreen();
      else if (ctrl && e.key === 'c') {
        line([...promptNodes(), buf + '^C']);
        buf = '';
        pos = 0;
        hIdx = history.length;
      } else if (e.key === 'ArrowUp') {
        if (hIdx > 0) {
          if (hIdx === history.length) draft = buf;
          buf = history[--hIdx];
          pos = buf.length;
        }
      } else if (e.key === 'ArrowDown') {
        if (hIdx < history.length) {
          hIdx++;
          buf = hIdx === history.length ? draft : history[hIdx];
          pos = buf.length;
        }
      } else if (e.key === 'Tab') {
        busy = true;
        void complete().finally(() => { busy = false; render(); });
      } else if (e.key.length === 1 && !ctrl) {
        buf = buf.slice(0, pos) + e.key + buf.slice(pos);
        pos++;
      } else handled = false;
      if (handled) {
        e.preventDefault();
        if (e.key !== 'Enter' && e.key !== 'Tab') render();
      }
    };

    const onPaste = (e: ClipboardEvent) => {
      e.preventDefault();
      if (busy) return;
      const text = (e.clipboardData?.getData('text') ?? '').replace(/\r?\n/g, ' ');
      buf = buf.slice(0, pos) + text + buf.slice(pos);
      pos += text.length;
      render();
    };

    win.body.addEventListener('keydown', onKey);
    win.body.addEventListener('paste', onPaste);
    scroll.addEventListener('mouseup', () => { if (!String(window.getSelection())) win.body.focus(); });
    win.body.addEventListener('focusin', render);
    win.body.addEventListener('focusout', render);

    line([span('t-user', 'MWX 7 Terminal'), span('dim', `  v${VERSION}`)]);
    line('Type "help" for a list of commands.', 'dim');
    line('');
    render();
    setTimeout(() => win.body.focus(), 50);

    return () => {
      clearTimeout(idle);
      win.body.removeEventListener('keydown', onKey);
      win.body.removeEventListener('paste', onPaste);
    };
  },
};
