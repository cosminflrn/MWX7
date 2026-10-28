import { icons } from '../../assets/icons';
import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import './calculator.css';

type Op = '+' | '−' | '×' | '÷';

const MAX_DIGITS = 16;

/** Key layout: Windows 7 Calculator, Standard view (5 columns). `kind` drives styling only. */
interface Key {
  id: string;
  label: string;
  kind: 'mem' | 'fn' | 'num' | 'op' | 'eq';
  title?: string;
}
const LAYOUT: Key[] = [
  { id: 'MC', label: 'MC', kind: 'mem', title: 'Clear memory' },
  { id: 'MR', label: 'MR', kind: 'mem', title: 'Recall memory' },
  { id: 'MS', label: 'MS', kind: 'mem', title: 'Store in memory' },
  { id: 'M+', label: 'M+', kind: 'mem', title: 'Add to memory' },
  { id: 'M-', label: 'M-', kind: 'mem', title: 'Subtract from memory' },
  { id: '⌫', label: '←', kind: 'fn', title: 'Backspace' },
  { id: 'CE', label: 'CE', kind: 'fn', title: 'Clear entry' },
  { id: 'C', label: 'C', kind: 'fn', title: 'Clear' },
  { id: '±', label: '±', kind: 'fn', title: 'Negate' },
  { id: '√', label: '√', kind: 'fn', title: 'Square root' },
  { id: '7', label: '7', kind: 'num' },
  { id: '8', label: '8', kind: 'num' },
  { id: '9', label: '9', kind: 'num' },
  { id: '÷', label: '/', kind: 'op', title: 'Divide' },
  { id: '%', label: '%', kind: 'fn', title: 'Percent' },
  { id: '4', label: '4', kind: 'num' },
  { id: '5', label: '5', kind: 'num' },
  { id: '6', label: '6', kind: 'num' },
  { id: '×', label: '*', kind: 'op', title: 'Multiply' },
  { id: '1/x', label: '1/x', kind: 'fn', title: 'Reciprocal' },
  { id: '1', label: '1', kind: 'num' },
  { id: '2', label: '2', kind: 'num' },
  { id: '3', label: '3', kind: 'num' },
  { id: '−', label: '-', kind: 'op', title: 'Subtract' },
  { id: '=', label: '=', kind: 'eq', title: 'Equals' },
  { id: '0', label: '0', kind: 'num' },
  { id: '.', label: '.', kind: 'num' },
  { id: '+', label: '+', kind: 'op', title: 'Add' },
];

export const calculator: AppManifest = {
  id: 'calculator',
  name: 'Calculator',
  icon: icons.calculator,
  description: 'Quick math',
  keywords: ['calc', 'math', 'numbers'],
  pinned: true,
  desktop: true,
  singleInstance: true,
  window: { width: 248, height: 352, resizable: false },

  mount({ win, os }) {
    let display = '0'; // raw entry / result, always parseable by Number()
    let acc: number | null = null;
    let op: Op | null = null;
    let fresh = true; // next digit starts a new entry
    let expr = '';
    let memory = 0;
    let hasMemory = false;
    let error = false;
    let repeat: { op: Op; operand: number } | null = null; // "=" pressed again repeats the last operation

    const screen = h('div', { class: 'calc-value' }, display);
    const history = h('div', { class: 'calc-expr' });
    const mem = h('div', { class: 'calc-mem' }, 'M');
    win.body.classList.add('calc');
    win.body.append(h('div', { class: 'calc-screen' }, history, h('div', { class: 'calc-line' }, mem, screen)));

    const fmt = (n: number) => {
      if (!Number.isFinite(n)) return 'Error';
      const s = String(Number.parseFloat(n.toPrecision(MAX_DIGITS)));
      return s.length > MAX_DIGITS ? n.toExponential(8).replace(/\.?0+e/, 'e') : s;
    };
    // Win7 groups thousands in the display; the raw string stays untouched
    const group = (s: string) => {
      if (error || !/^-?\d+(\.\d*)?$/.test(s)) return s;
      const [int, frac] = s.split('.');
      const g = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      return frac === undefined ? g : `${g}.${frac}`;
    };
    const apply = (a: number, b: number, o: Op) => (o === '+' ? a + b : o === '−' ? a - b : o === '×' ? a * b : a / b);

    const keyEls = new Map<string, HTMLButtonElement>();
    const render = () => {
      const text = group(display);
      screen.textContent = text;
      screen.style.fontSize = text.length > 18 ? '17px' : text.length > 13 ? '21px' : text.length > 10 ? '24px' : '28px';
      history.textContent = expr;
      mem.style.visibility = hasMemory ? 'visible' : 'hidden';
      keyEls.get('MC')!.disabled = !hasMemory;
      keyEls.get('MR')!.disabled = !hasMemory;
    };

    const fail = (msg: string) => {
      display = msg;
      error = true;
      acc = null;
      op = null;
      expr = '';
      repeat = null;
      fresh = true;
    };
    const prefix = () => (op && acc !== null ? `${fmt(acc)} ${op} ` : '');

    const unary = (name: string, fn: (v: number) => number, domainError?: (v: number) => string | null) => {
      const v = Number(display);
      const bad = domainError?.(v);
      if (bad) return fail(bad);
      expr = `${prefix()}${name}(${fmt(v)})`;
      display = fmt(fn(v));
      fresh = true;
    };

    const press = (k: string) => {
      if (error && !/^(C|CE|[0-9.])$/.test(k)) return;
      if (/^[0-9]$/.test(k)) {
        if (error) {
          error = false;
          display = '0';
        }
        if (fresh) {
          if (!op) expr = ''; // a finished calculation scrolls away when you start a new one
          display = k;
        } else if (display.replace(/[-.]/g, '').length < MAX_DIGITS) display = display === '0' ? k : display + k;
        fresh = false;
      } else if (k === '.') {
        if (error) {
          error = false;
          display = '0';
        }
        if (fresh) {
          if (!op) expr = '';
          display = '0.';
        } else if (!display.includes('.')) display += '.';
        fresh = false;
      } else if (k === 'C') {
        display = '0';
        acc = null;
        op = null;
        expr = '';
        repeat = null;
        error = false;
        fresh = true;
      } else if (k === 'CE') {
        display = '0';
        error = false;
        fresh = true;
        if (!op) expr = '';
      } else if (k === '±') {
        display = display.startsWith('-') ? display.slice(1) : display === '0' ? '0' : '-' + display;
      } else if (k === '%') {
        // Win7: with a pending operation it is a percentage *of the first operand*; alone it yields 0
        const v = Number(display);
        const r = op && acc !== null ? (acc * v) / 100 : 0;
        display = fmt(r);
        expr = `${prefix()}${display}`;
        fresh = true;
      } else if (k === '√') {
        unary('√', Math.sqrt, (v) => (v < 0 ? 'Invalid input' : null));
      } else if (k === '1/x') {
        unary('1/', (v) => 1 / v, (v) => (v === 0 ? 'Cannot divide by zero' : null));
      } else if (k === '⌫') {
        if (!fresh) display = display.length <= 1 || (display.length === 2 && display.startsWith('-')) ? '0' : display.slice(0, -1);
      } else if (k === 'MC') {
        memory = 0;
        hasMemory = false;
      } else if (k === 'MR') {
        display = fmt(memory);
        fresh = true;
      } else if (k === 'MS') {
        memory = Number(display);
        hasMemory = true;
        fresh = true;
      } else if (k === 'M+' || k === 'M-') {
        memory += k === 'M+' ? Number(display) : -Number(display);
        hasMemory = true;
        fresh = true;
      } else if (k === '=') {
        const b = Number(display);
        if (op && acc !== null) {
          if (op === '÷' && b === 0) {
            fail('Cannot divide by zero');
            return render();
          }
          expr = `${fmt(acc)} ${op} ${fmt(b)} =`;
          repeat = { op, operand: b };
          display = fmt(apply(acc, b, op));
          acc = null;
          op = null;
        } else if (repeat) {
          if (repeat.op === '÷' && repeat.operand === 0) return;
          expr = `${fmt(b)} ${repeat.op} ${fmt(repeat.operand)} =`;
          display = fmt(apply(b, repeat.operand, repeat.op));
        }
        fresh = true;
      } else {
        const next = k as Op;
        if (op && acc !== null && !fresh) {
          if (op === '÷' && Number(display) === 0) {
            fail('Cannot divide by zero');
            return render();
          }
          display = fmt(apply(acc, Number(display), op));
        }
        acc = Number(display);
        op = next;
        repeat = null;
        expr = `${fmt(acc)} ${op}`;
        fresh = true;
      }
      render();
    };

    const pad = h('div', { class: 'calc-pad' });
    for (const k of LAYOUT) {
      const el = h('button', { class: `calc-key ${k.kind}${k.id === '0' ? ' zero' : ''}`, title: k.title, type: 'button', onclick: () => press(k.id) }, k.label);
      keyEls.set(k.id, el);
      pad.append(el);
    }
    // keys never take focus, so Space/Enter can't re-trigger the last clicked key; the body keeps the keyboard
    pad.addEventListener('mousedown', (e) => {
      e.preventDefault();
      win.body.focus();
    });
    win.body.append(pad);

    const copy = () => void navigator.clipboard?.writeText(display).catch(() => undefined);
    const paste = async () => {
      try {
        const t = ((await navigator.clipboard.readText()) ?? '').trim().replace(/,/g, '');
        if (/^-?\d*\.?\d+$/.test(t)) {
          error = false;
          display = fmt(Number(t));
          fresh = false;
          render();
        }
      } catch {
        os.notify('Calculator', 'Clipboard access was not allowed.', icons.calculator);
      }
    };
    win.setMenus([
      { label: 'View', items: [{ label: 'Standard', checked: true, action: () => undefined }] },
      {
        label: 'Edit',
        items: [
          { label: 'Copy', shortcut: 'Ctrl+C', action: copy },
          { label: 'Paste', shortcut: 'Ctrl+V', action: () => void paste() },
        ],
      },
      { label: 'Help', items: [{ label: 'About Calculator', action: () => os.launch('about', { app: 'calculator' }) }] },
    ]);

    const keyMap: Record<string, string> = { '/': '÷', '*': '×', '-': '−', '+': '+', Enter: '=', '=': '=', Escape: 'C', Delete: 'CE', Backspace: '⌫', ',': '.', '%': '%', '@': '√', r: '1/x', F9: '±' };
    win.body.tabIndex = 0;
    win.body.addEventListener('keydown', (e) => {
      if (e.ctrlKey || e.metaKey) {
        const c = e.key.toLowerCase();
        const mk: Record<string, string> = { l: 'MC', r: 'MR', m: 'MS', p: 'M+', q: 'M-' };
        if (c === 'c') copy();
        else if (c === 'v') void paste();
        else if (mk[c]) press(mk[c]);
        else return;
        e.preventDefault();
        return;
      }
      const k = /^[0-9.]$/.test(e.key) ? e.key : keyMap[e.key];
      if (k) {
        e.preventDefault();
        press(k);
      }
    });
    render();
    setTimeout(() => win.body.focus(), 50);
  },
};
