import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import { minesIcon } from './icon';
import './mines.css';

/**
 * Mines. The window hugs the board and window sizes are fixed per manifest, so each level is its own manifest
 * (Intermediate / Expert are hidden from Start). Changing level opens the right-sized window and closes the old one.
 */

type Level = 'beginner' | 'intermediate' | 'expert';
const LEVELS: Record<Level, { cols: number; rows: number; mines: number; name: string }> = {
  beginner: { cols: 9, rows: 9, mines: 10, name: 'Beginner' },
  intermediate: { cols: 16, rows: 16, mines: 40, name: 'Intermediate' },
  expert: { cols: 30, rows: 16, mines: 99, name: 'Expert' },
};
const PAD = 10;
const HEAD = 40;
const GAPY = 8;
const FRAME_X = 18;
const FRAME_Y = 40;

function cellSize(l: Level): number {
  const { cols, rows } = LEVELS[l];
  const w = typeof window === 'undefined' ? 1600 : window.innerWidth;
  const hh = typeof window === 'undefined' ? 900 : window.innerHeight;
  return Math.max(16, Math.min(26, Math.floor((w - 80 - FRAME_X - PAD * 2) / cols), Math.floor((hh - 200 - FRAME_Y - PAD * 2 - HEAD - GAPY) / rows)));
}

const MINE = `<svg viewBox="0 0 20 20"><g stroke="#10151f" stroke-width="1.7" stroke-linecap="round"><path d="M10 2.5V17.5M2.5 10H17.5M4.7 4.7L15.3 15.3M15.3 4.7L4.7 15.3"/></g><circle cx="10" cy="10" r="5.6" fill="#232b3a" stroke="#05070c" stroke-width=".5"/><ellipse cx="8.1" cy="7.7" rx="1.8" ry="1.1" fill="#fff" opacity=".85" transform="rotate(-30 8.1 7.7)"/></svg>`;
const FLAG = `<svg viewBox="0 0 20 20"><path d="M6 17.5H14" stroke="#2c3440" stroke-width="1.8" stroke-linecap="round"/><path d="M10 4V17" stroke="#2c3440" stroke-width="1.5" stroke-linecap="round"/><path d="M10.4 3.6L16.6 6.6L10.4 9.8Z" fill="#e0402a" stroke="#8c1d0e" stroke-width=".6" stroke-linejoin="round"/></svg>`;
const faces = {
  play: `<svg viewBox="0 0 32 32"><circle cx="11.5" cy="13" r="1.8" fill="#10223f"/><circle cx="20.5" cy="13" r="1.8" fill="#10223f"/><path d="M10 19.5Q16 25 22 19.5" fill="none" stroke="#10223f" stroke-width="1.8" stroke-linecap="round"/><path d="M5 12C6 6 11 3.5 16 3.5S26 6 27 12C22 9 20 8.5 16 8.5S10 9 5 12Z" fill="#fff" opacity=".4"/></svg>`,
  lost: `<svg viewBox="0 0 32 32"><path d="M9.5 11.5L13.5 15.5M13.5 11.5L9.5 15.5M18.5 11.5L22.5 15.5M22.5 11.5L18.5 15.5" stroke="#10223f" stroke-width="1.7" stroke-linecap="round"/><path d="M10.5 23Q16 18.5 21.5 23" fill="none" stroke="#10223f" stroke-width="1.8" stroke-linecap="round"/></svg>`,
  won: `<svg viewBox="0 0 32 32"><rect x="6.5" y="10.5" width="8" height="5" rx="2" fill="#10223f"/><rect x="17.5" y="10.5" width="8" height="5" rx="2" fill="#10223f"/><path d="M14.5 12H17.5" stroke="#10223f" stroke-width="1.4"/><path d="M10 19.5Q16 25 22 19.5" fill="none" stroke="#10223f" stroke-width="1.8" stroke-linecap="round"/></svg>`,
};

function make(level: Level): AppManifest {
  const l = LEVELS[level];
  const c = cellSize(level);
  return {
  id: level === 'beginner' ? 'mines' : `mines-${level}`,
  name: 'Mines',
  icon: minesIcon,
  description: 'Clear the field without hitting a mine',
  keywords: ['game', 'minesweeper', 'bombs', 'puzzle'],
  pinned: false,
  hidden: level !== 'beginner',
  singleInstance: false,
  window: { width: l.cols * c + PAD * 2 + FRAME_X, height: l.rows * c + PAD * 2 + HEAD + GAPY + FRAME_Y, resizable: false },

  mount({ win, os }) {
    const { cols, rows, mines: total, name } = LEVELS[level];
    const size = cellSize(level);
    win.setTitle('Mines');
    win.body.classList.add('mn');
    win.body.style.setProperty('--c', `${size}px`);

    const mineLcd = h('div', { class: 'mn-lcd' });
    const timeLcd = h('div', { class: 'mn-lcd' });
    const face = h('button', { class: 'mn-face', 'aria-label': 'New game', onclick: () => reset() });
    const board = h('div', { class: 'mn-board', style: `grid-template-columns:repeat(${cols},${size}px)` });
    win.body.append(h('div', { class: 'mn-head' }, mineLcd, face, timeLcd), board);

    interface Cell { el: HTMLElement; mine: boolean; open: boolean; flag: boolean; n: number }
    const cells: Cell[] = [];
    for (let i = 0; i < cols * rows; i++) {
      const el = h('div', { class: 'mn-cell', 'data-i': i }, h('div', { class: 'mn-tile' }));
      cells.push({ el, mine: false, open: false, flag: false, n: 0 });
      board.append(el);
    }

    let state: 'ready' | 'play' | 'won' | 'lost' = 'ready';
    let flags = 0;
    let opened = 0;
    let secs = 0;
    let timer = 0;

    const lcd = (n: number) => String(Math.max(-99, Math.min(999, n))).padStart(3, '0');
    const showMines = () => (mineLcd.textContent = lcd(total - flags));
    const stop = () => { clearInterval(timer); timer = 0; };
    const neighbours = (i: number): number[] => {
      const x = i % cols, y = (i / cols) | 0;
      const out: number[] = [];
      for (let dy = -1; dy <= 1; dy++)
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx, ny = y + dy;
          if ((dx || dy) && nx >= 0 && ny >= 0 && nx < cols && ny < rows) out.push(ny * cols + nx);
        }
      return out;
    };

    function reset(): void {
      stop();
      state = 'ready'; flags = 0; opened = 0; secs = 0;
      cells.forEach((c) => {
        c.mine = c.open = c.flag = false; c.n = 0;
        c.el.className = 'mn-cell';
        c.el.style.removeProperty('--d');
        c.el.replaceChildren(h('div', { class: 'mn-tile' }));
        c.el.style.color = '';
      });
      timeLcd.textContent = '000';
      face.innerHTML = faces.play;
      showMines();
    }

    function plant(safe: number): void {
      const avoid = new Set([safe, ...neighbours(safe)]);
      const pool = cells.map((_, i) => i).filter((i) => !avoid.has(i));
      for (let k = 0; k < total; k++) {
        const j = k + Math.floor(Math.random() * (pool.length - k));
        [pool[k], pool[j]] = [pool[j], pool[k]];
        cells[pool[k]].mine = true;
      }
      cells.forEach((c, i) => (c.n = neighbours(i).filter((j) => cells[j].mine).length));
    }

    /** Opens `start` and floods outward; each ring gets a growing delay so the reveal ripples. */
    function reveal(start: number): void {
      const first = cells[start];
      if (first.open || first.flag) return;
      if (state === 'ready') {
        plant(start);
        state = 'play';
        timer = window.setInterval(() => { secs++; timeLcd.textContent = lcd(secs); }, 1000);
      }
      if (first.mine) return lose(start);
      let ring = [start];
      let d = 0;
      first.open = true;
      while (ring.length) {
        const nextRing: number[] = [];
        for (const i of ring) {
          const c = cells[i];
          opened++;
          c.el.style.setProperty('--d', String(d));
          c.el.classList.add('open');
          if (c.n) {
            c.el.append(h('span', { class: `mn-n${c.n}` }, String(c.n)));
          } else {
            for (const j of neighbours(i)) {
              const nb = cells[j];
              if (!nb.open && !nb.mine) {
                if (nb.flag) { nb.flag = false; flags--; nb.el.querySelector('.mn-tile')!.innerHTML = ''; }
                nb.open = true;
                nextRing.push(j);
              }
            }
          }
        }
        ring = nextRing;
        d++;
      }
      showMines();
      if (opened === cols * rows - total) win_();
    }

    function lose(hit: number): void {
      state = 'lost';
      stop();
      face.innerHTML = faces.lost;
      cells.forEach((c, i) => {
        if (c.mine && !c.flag) {
          c.el.classList.add('open');
          c.el.style.setProperty('--d', String(Math.floor(Math.hypot((i % cols) - (hit % cols), ((i / cols) | 0) - ((hit / cols) | 0)))));
          c.el.insertAdjacentHTML('afterbegin', MINE);
          if (i === hit) c.el.classList.add('hit');
        } else if (!c.mine && c.flag) {
          c.el.classList.add('wrong');
        }
      });
    }

    function win_(): void {
      state = 'won';
      stop();
      face.innerHTML = faces.won;
      cells.forEach((c) => {
        if (c.mine && !c.flag) { c.flag = true; c.el.querySelector('.mn-tile')!.innerHTML = FLAG; }
      });
      flags = total;
      showMines();
      os.notify('Mines cleared', `${name} in ${secs} second${secs === 1 ? '' : 's'}.`);
    }

    const live = () => state === 'ready' || state === 'play';
    const cellOf = (e: Event) => {
      const el = (e.target as HTMLElement).closest<HTMLElement>('.mn-cell');
      return el ? Number(el.dataset.i) : -1;
    };

    board.addEventListener('click', (e) => {
      const i = cellOf(e);
      if (i >= 0 && live()) reveal(i);
    });
    board.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      const i = cellOf(e);
      if (i < 0 || !live() || state === 'ready') return;
      const c = cells[i];
      if (c.open) return;
      c.flag = !c.flag;
      flags += c.flag ? 1 : -1;
      c.el.querySelector('.mn-tile')!.innerHTML = c.flag ? FLAG : '';
      showMines();
    });
    // Chord: double-click a number whose flags match it to open the remaining neighbours.
    board.addEventListener('dblclick', (e) => {
      const i = cellOf(e);
      if (i < 0 || state !== 'play') return;
      const c = cells[i];
      const around = neighbours(i);
      if (!c.open || !c.n || around.filter((j) => cells[j].flag).length !== c.n) return;
      for (const j of around) if (state === 'play') reveal(j);
    });

    win.setMenus([
      {
        label: 'Game',
        items: [
          { label: 'New Game', action: () => reset() },
          { separator: true },
          ...(Object.keys(LEVELS) as Level[]).map((l) => ({
            label: LEVELS[l].name,
            checked: l === level,
            action: () => {
              if (l === level) return reset();
              os.launch(l === 'beginner' ? 'mines' : `mines-${l}`);
              win.close();
            },
          })),
          { separator: true },
          { label: 'Exit', action: () => win.close() },
        ],
      },
    ]);

    reset();
    return stop;
  },
};
}

export const mines = make('beginner');
export const minesIntermediate = make('intermediate');
export const minesExpert = make('expert');
