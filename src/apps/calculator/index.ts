import { icons } from '../../assets/icons';
import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import './calculator.css';

type Op = '+' | '−' | '×' | '÷';

export const calculator: AppManifest = {
  id: 'calculator',
  name: 'Calculator',
  icon: icons.calculator,
  description: 'Quick math',
  keywords: ['calc', 'math', 'numbers'],
  pinned: true,
  desktop: true,
  singleInstance: true,
  window: { width: 264, height: 400, resizable: false },

  mount({ win }) {
    let display = '0';
    let acc: number | null = null;
    let op: Op | null = null;
    let fresh = true;
    let expr = '';

    const screen = h('div', { class: 'calc-value' }, display);
    const history = h('div', { class: 'calc-expr' });
    win.body.classList.add('calc');
    win.body.append(h('div', { class: 'calc-screen' }, history, screen));

    const fmt = (n: number) => {
      if (!Number.isFinite(n)) return 'Error';
      const s = String(Number.parseFloat(n.toPrecision(12)));
      return s.length > 14 ? n.toExponential(6) : s;
    };
    const apply = (a: number, b: number, o: Op) => (o === '+' ? a + b : o === '−' ? a - b : o === '×' ? a * b : a / b);
    const render = () => {
      screen.textContent = display;
      screen.style.fontSize = display.length > 10 ? '24px' : '36px';
      history.textContent = expr;
    };

    const press = (k: string) => {
      if (/^[0-9]$/.test(k)) {
        display = fresh || display === '0' ? k : display + k;
        fresh = false;
      } else if (k === '.') {
        if (fresh) display = '0.';
        else if (!display.includes('.')) display += '.';
        fresh = false;
      } else if (k === 'C') {
        display = '0';
        acc = null;
        op = null;
        expr = '';
        fresh = true;
      } else if (k === '±') {
        display = display.startsWith('-') ? display.slice(1) : display === '0' ? '0' : '-' + display;
      } else if (k === '%') {
        display = fmt(Number(display) / 100);
      } else if (k === '⌫') {
        display = fresh || display.length <= 1 ? '0' : display.slice(0, -1);
      } else if (k === '=') {
        if (op && acc !== null) {
          expr = `${fmt(acc)} ${op} ${display} =`;
          display = fmt(apply(acc, Number(display), op));
          acc = null;
          op = null;
          fresh = true;
        }
      } else {
        const next = k as Op;
        if (op && acc !== null && !fresh) display = fmt(apply(acc, Number(display), op));
        acc = Number(display);
        op = next;
        expr = `${display} ${op}`;
        fresh = true;
      }
      render();
    };

    const keys = ['C', '±', '%', '÷', '7', '8', '9', '×', '4', '5', '6', '−', '1', '2', '3', '+', '0', '.', '='];
    const pad = h('div', { class: 'calc-pad' });
    for (const k of keys) {
      const kind = '÷×−+='.includes(k) ? 'op' : 'C±%'.includes(k) ? 'fn' : 'num';
      pad.append(h('button', { class: `calc-key ${kind}${k === '0' ? ' wide' : ''}`, onclick: () => press(k) }, k));
    }
    win.body.append(pad);

    const keyMap: Record<string, string> = { '/': '÷', '*': '×', '-': '−', '+': '+', Enter: '=', '=': '=', Escape: 'C', Backspace: '⌫', ',': '.' };
    win.body.tabIndex = 0;
    win.body.addEventListener('keydown', (e) => {
      const k = /^[0-9.]$/.test(e.key) ? e.key : keyMap[e.key];
      if (k) {
        e.preventDefault();
        press(k);
      }
    });
    setTimeout(() => win.body.focus(), 50);
  },
};
