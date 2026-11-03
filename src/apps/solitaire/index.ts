import type { AppManifest } from '../../core/types';
import { GameMusic } from './music';
import { showTutorial } from './tutorial';
import { h } from '../../ui/dom';
import { solitaireIcon } from './icon';
import './solitaire.css';

/** Klondike, draw-1. Cards are DOM nodes moved with transforms only; the stage scales uniformly on small screens. */

const CW = 70;
const CH = 98;
const GAP = 14;
const M = 14;
const SW = 602;
const SH = 560;
const TAB_Y = 132;
const FRAME_X = 18;
const FRAME_Y = 40;
const STATUS_H = 24;
const colX = (i: number) => M + i * (CW + GAP);

function fit(): number {
  const availH = (typeof window === 'undefined' ? 900 : window.innerHeight) - 30 - 70 - 24;
  const availW = (typeof window === 'undefined' ? 1600 : window.innerWidth) - 40;
  return Math.min(1, (availH - FRAME_Y - STATUS_H) / SH, (availW - FRAME_X) / SW);
}
const SCALE = fit();
const VW = Math.floor(SW * SCALE);
const VH = Math.floor(SH * SCALE);

const SUITS = ['spade', 'heart', 'diamond', 'club'] as const;
const RANK = ['', 'A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'];
const isRed = (s: number) => s === 1 || s === 2;

const SYMBOLS = `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <symbol id="sl-spade" viewBox="0 0 20 20"><path d="M10 1.2C14 5.5 18.5 8 18.5 12C18.5 14.6 16.6 16 14.6 16C13.2 16 12 15.4 11.2 14.4C11.4 16.4 12 17.6 13.4 18.8L6.6 18.8C8 17.6 8.6 16.4 8.8 14.4C8 15.4 6.8 16 5.4 16C3.4 16 1.5 14.6 1.5 12C1.5 8 6 5.5 10 1.2Z"/></symbol>
  <symbol id="sl-heart" viewBox="0 0 20 20"><path d="M10 18.4C2.4 12.6 1 8.6 1 6.2C1 3.2 3.2 1.6 5.4 1.6C7.4 1.6 9 2.8 10 4.6C11 2.8 12.6 1.6 14.6 1.6C16.8 1.6 19 3.2 19 6.2C19 8.6 17.6 12.6 10 18.4Z"/></symbol>
  <symbol id="sl-diamond" viewBox="0 0 20 20"><path d="M10 .8C12.6 5 15.6 8 19.2 10C15.6 12 12.6 15 10 19.2C7.4 15 4.4 12 .8 10C4.4 8 7.4 5 10 .8Z"/></symbol>
  <symbol id="sl-club" viewBox="0 0 20 20"><circle cx="10" cy="5.6" r="3.9"/><circle cx="5" cy="11.6" r="3.9"/><circle cx="15" cy="11.6" r="3.9"/><path d="M8.8 11L11.2 11C11 15 11.6 17 13.8 19L6.2 19C8.4 17 9 15 8.8 11Z"/></symbol>
</defs></svg>`;
const suitSvg = (s: number, cls = '') => `<svg class="${cls}"><use href="#sl-${SUITS[s]}"/></svg>`;

/** Pip layouts on a 3 x 7 grid: [x 0..2, y 0..6 in sixths]. */
const PIPS: Record<number, Array<[number, number]>> = {
  1: [[1, 3]],
  2: [[1, 0], [1, 6]],
  3: [[1, 0], [1, 3], [1, 6]],
  4: [[0, 0], [2, 0], [0, 6], [2, 6]],
  5: [[0, 0], [2, 0], [1, 3], [0, 6], [2, 6]],
  6: [[0, 0], [2, 0], [0, 3], [2, 3], [0, 6], [2, 6]],
  7: [[0, 0], [2, 0], [1, 1.5], [0, 3], [2, 3], [0, 6], [2, 6]],
  8: [[0, 0], [2, 0], [1, 1.5], [0, 3], [2, 3], [1, 4.5], [0, 6], [2, 6]],
  9: [[0, 0], [2, 0], [0, 2], [2, 2], [1, 3], [0, 4], [2, 4], [0, 6], [2, 6]],
  10: [[0, 0], [2, 0], [1, 1], [0, 2], [2, 2], [0, 4], [2, 4], [1, 5], [0, 6], [2, 6]],
};

interface Card {
  id: number;
  suit: number;
  rank: number;
  up: boolean;
  el: HTMLElement;
  x: number;
  y: number;
  z: number;
}

function faceHtml(suit: number, rank: number): string {
  const corner = (c: string) => `<div class="sol-corner ${c}"><b>${RANK[rank]}</b>${suitSvg(suit)}</div>`;
  let mid = '';
  if (rank > 10) {
    mid = `<div class="sol-court">${suitSvg(suit)}<b>${RANK[rank]}</b>${suitSvg(suit).replace('<svg', '<svg style="transform:rotate(180deg)"')}</div>`;
  } else {
    for (const [cx, cy] of PIPS[rank]) {
      const left = 24 + cx * 11;
      const top = 15 + (cy / 6) * 68;
      mid += `<svg class="sol-pip${cy > 3 ? ' inv' : ''}" style="left:${left}px;top:${top}px"><use href="#sl-${SUITS[suit]}"/></svg>`;
    }
  }
  return `<div class="sol-front">${corner('tl')}${corner('br')}${mid}</div><div class="sol-back"></div>`;
}

export const solitaire: AppManifest = {
  id: 'solitaire',
  name: 'Solitaire',
  icon: solitaireIcon,
  description: 'Klondike card game',
  keywords: ['game', 'cards', 'klondike', 'patience'],
  pinned: false,
  singleInstance: true,
  window: { width: VW + FRAME_X, height: VH + STATUS_H + FRAME_Y, resizable: false },

  mount({ win }) {
    win.setTitle('Solitaire');
    win.body.classList.add('sol');

    const stage = h('div', { class: 'sol-stage', style: `transform:scale(${SCALE})`, html: SYMBOLS });
    const view = h('div', { class: 'sol-view', style: `width:${VW}px;height:${VH}px` }, stage);
    const stScore = h('span');
    const stTime = h('span');
    const stMoves = h('span');
    const winEl = h('div', { class: 'sol-win' }, h('h2', {}, 'You win!'));
    const winBtn = h('button', { onclick: () => newGame() }, 'New Game');
    winEl.append(winBtn);
    view.append(winEl);
    win.body.append(view, h('div', { class: 'sol-status' }, stScore, stTime, stMoves));

    // Slots (static)
    const slot = (x: number, y: number, cls = '', inner = '') => stage.append(h('div', { class: `sol-slot ${cls}`, style: `left:${x}px;top:${y}px`, html: inner }));
    const recycle = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 3.5V8h-4.5"/></svg>`;
    const stockSlot = h('div', { class: 'sol-slot stock', style: `left:${colX(0)}px;top:${M}px`, html: recycle });
    stage.append(stockSlot);
    slot(colX(1), M);
    for (let i = 0; i < 4; i++) slot(colX(3 + i), M, '', `<span class="sol-a">A</span>`);
    for (let i = 0; i < 7; i++) slot(colX(i), TAB_Y);

    // Cards
    const all: Card[] = [];
    for (let s = 0; s < 4; s++)
      for (let r = 1; r <= 13; r++) {
        const el = h('div', { class: `sol-card ${isRed(s) ? 'red' : 'blk'}`, html: faceHtml(s, r) });
        const c: Card = { id: all.length, suit: s, rank: r, up: false, el, x: colX(0), y: M, z: 0 };
        el.dataset.id = String(c.id);
        all.push(c);
        stage.append(el);
      }

    let stock: Card[] = [];
    let waste: Card[] = [];
    let found: Card[][] = [[], [], [], []];
    let tab: Card[][] = [[], [], [], [], [], [], []];
    let score = 0;
    let moves = 0;
    let secs = 0;
    let timer = 0;
    let won = false;
    let raf = 0;
    const timeouts = new Set<number>();
    const later = (fn: () => void, ms: number) => {
      const t = window.setTimeout(() => { timeouts.delete(t); fn(); }, ms);
      timeouts.add(t);
    };

    const fmtTime = () => `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`;
    const stats = () => {
      stScore.textContent = `Score: ${score}`;
      stTime.textContent = `Time: ${fmtTime()}`;
      stMoves.textContent = `Moves: ${moves}`;
    };
    const startTimer = () => {
      if (timer || won) return;
      timer = window.setInterval(() => { secs++; stTime.textContent = `Time: ${fmtTime()}`; }, 1000);
    };
    const stopTimer = () => { clearInterval(timer); timer = 0; };

    const layoutCard = (c: Card, x: number, y: number, z: number) => {
      c.x = x; c.y = y; c.z = z;
      c.el.style.transform = `translate3d(${x}px,${y}px,0)`;
      c.el.style.zIndex = String(z);
      c.el.classList.toggle('up', c.up);
    };
    /** Place every card where its pile says it belongs. */
    const render = () => {
      stock.forEach((c, i) => layoutCard(c, colX(0), M, 10 + i));
      waste.forEach((c, i) => layoutCard(c, colX(1), M, 100 + i));
      found.forEach((p, f) => p.forEach((c, i) => layoutCard(c, colX(3 + f), M, 200 + i)));
      tab.forEach((p, col) => {
        const downD = 12, upD = 24;
        const need = p.reduce((a, c) => a + (c.up ? upD : downD), 0) - (p.length ? (p[p.length - 1].up ? upD : downD) : 0);
        const avail = SH - TAB_Y - CH - 6;
        const k = need > avail ? avail / need : 1;
        let y = TAB_Y;
        p.forEach((c, i) => {
          layoutCard(c, colX(col), Math.round(y), 300 + i);
          y += (c.up ? upD : downD) * k;
        });
      });
      stockSlot.style.opacity = stock.length ? '0' : '1';
    };

    function newGame(): void {
      cancelAnimationFrame(raf);
      raf = 0;
      timeouts.forEach(clearTimeout);
      timeouts.clear();
      stopTimer();
      won = false;
      winEl.classList.remove('show');
      score = 0; moves = 0; secs = 0;
      const deck = all.slice();
      for (let i = deck.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [deck[i], deck[j]] = [deck[j], deck[i]];
      }
      stage.classList.remove('sol-anim');
      all.forEach((c) => { c.up = false; c.el.classList.remove('fly'); c.el.style.transitionDelay = ''; });
      stock = []; waste = []; found = [[], [], [], []]; tab = [[], [], [], [], [], [], []];
      stock = deck.slice();
      render();
      void stage.offsetWidth; // commit the stacked state before the deal glides out
      stage.classList.add('sol-anim');
      let d = 0;
      for (let row = 0; row < 7; row++)
        for (let col = row; col < 7; col++) {
          const c = stock.pop()!;
          c.up = col === row;
          tab[col].push(c);
          c.el.style.transitionDelay = `${d++ * 22}ms`;
        }
      render();
      stats();
      later(() => all.forEach((c) => (c.el.style.transitionDelay = '')), 28 * 22 + 300);
    }

    const canTab = (c: Card, col: number) => {
      const top = tab[col][tab[col].length - 1];
      return top ? top.up && isRed(top.suit) !== isRed(c.suit) && top.rank === c.rank + 1 : c.rank === 13;
    };
    const canFound = (c: Card, f: number) => {
      const top = found[f][found[f].length - 1];
      return top ? top.suit === c.suit && top.rank + 1 === c.rank : c.rank === 1;
    };

    type Loc = { kind: 'stock' | 'waste' | 'found' | 'tab'; i: number; idx: number };
    const locate = (c: Card): Loc => {
      let i = stock.indexOf(c);
      if (i >= 0) return { kind: 'stock', i: 0, idx: i };
      i = waste.indexOf(c);
      if (i >= 0) return { kind: 'waste', i: 0, idx: i };
      for (let f = 0; f < 4; f++) { i = found[f].indexOf(c); if (i >= 0) return { kind: 'found', i: f, idx: i }; }
      for (let t = 0; t < 7; t++) { i = tab[t].indexOf(c); if (i >= 0) return { kind: 'tab', i: t, idx: i }; }
      return { kind: 'stock', i: 0, idx: 0 };
    };
    const pileOf = (l: Loc): Card[] => (l.kind === 'stock' ? stock : l.kind === 'waste' ? waste : l.kind === 'found' ? found[l.i] : tab[l.i]);

    /** Moves cards (tail of their pile) onto a destination, applies scoring and the auto-flip. */
    const moveTo = (cards: Card[], dest: { kind: 'found' | 'tab'; i: number }) => {
      const from = locate(cards[0]);
      const src = pileOf(from);
      src.splice(from.idx, cards.length);
      (dest.kind === 'found' ? found[dest.i] : tab[dest.i]).push(...cards);
      if (from.kind === 'waste') score += dest.kind === 'found' ? 10 : 5;
      else if (from.kind === 'tab' && dest.kind === 'found') score += 10;
      else if (from.kind === 'found' && dest.kind === 'tab') score = Math.max(0, score - 15);
      if (from.kind === 'tab' && src.length && !src[src.length - 1].up) { src[src.length - 1].up = true; score += 5; }
      moves++;
      startTimer();
      render();
      stats();
      if (found.every((p) => p.length === 13)) celebrate();
    };

    const draw = () => {
      if (won) return;
      if (stock.length) {
        const c = stock.pop()!;
        c.up = true;
        waste.push(c);
      } else if (waste.length) {
        stock = waste.reverse();
        stock.forEach((c) => (c.up = false));
        waste = [];
        score = Math.max(0, score - 100);
      } else return;
      moves++;
      startTimer();
      render();
      stats();
    };
    stage.addEventListener('click', (e) => {
      const el = (e.target as HTMLElement).closest<HTMLElement>('.sol-card, .sol-slot.stock');
      if (!el) return;
      if (el === stockSlot) return draw();
      const c = all[Number(el.dataset.id)];
      if (locate(c).kind === 'stock') draw();
    });

    stage.addEventListener('dblclick', (e) => {
      const el = (e.target as HTMLElement).closest<HTMLElement>('.sol-card');
      if (!el || won) return;
      const c = all[Number(el.dataset.id)];
      const l = locate(c);
      if (!c.up || (l.kind !== 'waste' && l.kind !== 'tab') || pileOf(l)[pileOf(l).length - 1] !== c) return;
      const f = found.findIndex((_, i) => canFound(c, i));
      if (f >= 0) moveTo([c], { kind: 'found', i: f });
    });

    // Drag and drop
    stage.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || won) return;
      const el = (e.target as HTMLElement).closest<HTMLElement>('.sol-card');
      if (!el) return;
      const c = all[Number(el.dataset.id)];
      const l = locate(c);
      if (!c.up || l.kind === 'stock') return;
      const pile = pileOf(l);
      if (l.kind !== 'tab' && pile[pile.length - 1] !== c) return;
      const group = pile.slice(l.idx);
      const sx = e.clientX, sy = e.clientY;
      let dragging = false;
      const move = (ev: PointerEvent) => {
        const dx = (ev.clientX - sx) / SCALE, dy = (ev.clientY - sy) / SCALE;
        if (!dragging && Math.hypot(dx, dy) < 4) return;
        if (!dragging) {
          dragging = true;
          group.forEach((g, i) => { g.el.classList.add('drag'); g.el.style.zIndex = String(2000 + i); });
        }
        group.forEach((g) => (g.el.style.transform = `translate3d(${g.x + dx}px,${g.y + dy}px,0)`));
      };
      const up = (ev: PointerEvent) => {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
        if (!dragging) return;
        const dx = (ev.clientX - sx) / SCALE, dy = (ev.clientY - sy) / SCALE;
        const bx = c.x + dx, by = c.y + dy;
        let best: { kind: 'found' | 'tab'; i: number } | null = null;
        let bestA = CW * CH * 0.2;
        const test = (kind: 'found' | 'tab', i: number, rx: number, ry: number, rh: number) => {
          const a = Math.max(0, Math.min(bx + CW, rx + CW) - Math.max(bx, rx)) * Math.max(0, Math.min(by + CH, ry + rh) - Math.max(by, ry));
          if (a > bestA && (kind === 'found' ? group.length === 1 && canFound(c, i) : canTab(c, i) && !(l.kind === 'tab' && l.i === i))) {
            bestA = a;
            best = { kind, i };
          }
        };
        for (let f = 0; f < 4; f++) test('found', f, colX(3 + f), M, CH);
        for (let t = 0; t < 7; t++) test('tab', t, colX(t), TAB_Y, SH - TAB_Y);
        group.forEach((g) => g.el.classList.remove('drag'));
        if (best) moveTo(group, best);
        else render();
      };
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up);
    });

    // Win: cards leave the foundations one by one and bounce off the floor.
    function celebrate(): void {
      won = true;
      stopTimer();
      const queue: Card[] = [];
      for (let r = 13; r >= 1; r--) for (let f = 0; f < 4; f++) queue.push(found[f][r - 1]);
      const live: Array<{ c: Card; x: number; y: number; vx: number; vy: number }> = [];
      let next = 0;
      let lastLaunch = 0;
      let zi = 3000;
      const step = (t: number) => {
        if (next < queue.length && t - lastLaunch > 170) {
          const c = queue[next++];
          lastLaunch = t;
          c.el.classList.add('fly');
          c.el.style.zIndex = String(zi++);
          live.push({ c, x: c.x, y: c.y, vx: (Math.random() < 0.5 ? -1 : 1) * (2 + Math.random() * 4), vy: -4 - Math.random() * 4 });
        }
        for (let i = live.length - 1; i >= 0; i--) {
          const p = live[i];
          p.vy += 0.45;
          p.x += p.vx;
          p.y += p.vy;
          if (p.y > SH - CH) { p.y = SH - CH; p.vy *= -0.82; }
          p.c.el.style.transform = `translate3d(${p.x}px,${p.y}px,0)`;
          if (p.x < -CW - 4 || p.x > SW + 4) live.splice(i, 1);
        }
        if (next >= queue.length && !live.length) {
          winEl.classList.add('show');
          raf = 0;
          return;
        }
        if (next >= queue.length - 4) winEl.classList.add('show');
        raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    }

    const music = new GameMusic();
    const buildMenus = () =>
      win.setMenus([{ label: 'Game', items: [
        { label: 'New Game', action: () => newGame() },
        { separator: true },
        { label: 'Music', checked: music.enabled, action: () => { music.setEnabled(!music.enabled); buildMenus(); } },
        { separator: true },
        { label: 'Exit', action: () => win.close() },
      ] }]);
    buildMenus();
    // Music starts on open; if the browser still blocks audio, the first click in the window starts it.
    music.start();
    win.body.addEventListener('pointerdown', () => music.start(), true);
    showTutorial(win.body, 'sol', 'How to play Solitaire', [
      'Build four suit piles from Ace up to King.',
      'On the table, stack cards in descending order, alternating red and black.',
      'Click the stock to deal; drag cards between piles, or double-click to send one to a pile.',
      'Only a King can fill an empty column.',
    ]);

    newGame();
    return () => {
      cancelAnimationFrame(raf);
      stopTimer();
      timeouts.forEach(clearTimeout);
      music.dispose();
    };
  },
};
