import { h } from '../ui/dom';
import '../styles/gadgets.css';

/**
 * Win7-style desktop gadgets: glossy glass cards, draggable with the mouse, session-only positions.
 * They sit between the desktop icons and the windows. Only one rAF loop exists (clock hand + frame timing),
 * and it stops while the gadgets are hidden or the tab is in the background.
 */

const W = 148;
const GAP = 10;
// Below the notification toasts (top-right), so the two never overlap.
const TOP = 132;
const RIGHT = 16;

let layer: HTMLElement | null = null;
let shown = true;
let wake: () => void = () => {};


export function toggleGadgets(): void {
  if (!layer) return;
  shown = !shown;
  layer.classList.toggle('off', !shown);
  wake();
}

const svg = (viewBox: string, html: string, cls = '') =>
  h('div', { class: `gdg-art ${cls}`, html: `<svg viewBox="${viewBox}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${html}</svg>` });

/** Shared gradient defs, once, in a hidden svg (ids are gdg- prefixed). */
const DEFS = `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <radialGradient id="gdg-face" cx=".5" cy=".4" r=".7"><stop offset="0" stop-color="#ffffff"/><stop offset=".7" stop-color="#e4edf8"/><stop offset="1" stop-color="#b7c8dd"/></radialGradient>
  <linearGradient id="gdg-bezel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f6f9fd"/><stop offset=".45" stop-color="#8fa2b8"/><stop offset=".55" stop-color="#d3dde9"/><stop offset="1" stop-color="#53647a"/></linearGradient>
  <linearGradient id="gdg-shine" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  <radialGradient id="gdg-dial" cx=".5" cy=".35" r=".8"><stop offset="0" stop-color="#2b3f5c"/><stop offset="1" stop-color="#0a1424"/></radialGradient>
  <radialGradient id="gdg-sun" cx=".4" cy=".35" r=".75"><stop offset="0" stop-color="#fff3a6"/><stop offset=".6" stop-color="#ffc233"/><stop offset="1" stop-color="#e58a0c"/></radialGradient>
  <linearGradient id="gdg-cloud" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#c9d6e6"/></linearGradient>
</defs></svg>`;

function card(title: string, cls: string, body: Node[]): HTMLElement {
  return h('section', { class: `gdg ${cls}`, 'aria-label': title }, h('div', { class: 'gdg-shine' }), ...body);
}

/* ---------- Clock ---------- */
function buildClock() {
  let ticks = '';
  for (let i = 0; i < 60; i++) {
    const big = i % 5 === 0;
    ticks += `<line x1="50" y1="${big ? 8 : 9.5}" x2="50" y2="${big ? 13.5 : 11.5}" stroke="#2b3a4f" stroke-width="${big ? 1.6 : 0.6}" stroke-linecap="round" transform="rotate(${i * 6} 50 50)"/>`;
  }
  const art = svg(
    '0 0 100 100',
    `<circle cx="50" cy="50" r="47" fill="url(#gdg-bezel)"/>
     <circle cx="50" cy="50" r="43.5" fill="url(#gdg-face)" stroke="#52667f" stroke-opacity=".6" stroke-width=".6"/>
     ${ticks}
     <text x="50" y="33" text-anchor="middle" font-size="5.4" letter-spacing="1.2" fill="#5b6c82" font-family="Selawik,Segoe UI,sans-serif">MWX 7</text>
     <g class="gdg-h" data-h><path d="M48.2 56 L49 29 Q50 26 51 29 L51.8 56Z" fill="#1d2a3c"/></g>
     <g class="gdg-h" data-m><path d="M48.6 58 L49.3 17 Q50 14 50.7 17 L51.4 58Z" fill="#1d2a3c"/></g>
     <g class="gdg-h" data-s><line x1="50" y1="60" x2="50" y2="13" stroke="#d6341f" stroke-width="1"/><circle cx="50" cy="50" r="2.6" fill="#d6341f"/></g>
     <circle cx="50" cy="50" r="1.1" fill="#f6d2cb"/>
     <path d="M12 38C16 18 32 8 50 8S84 18 88 38C74 29 64 27 50 27S26 29 12 38Z" fill="url(#gdg-shine)" opacity=".55"/>`,
    'gdg-clock-art',
  );
  const el = card('Clock', 'gdg-clock', [art]);
  const hand = (k: string) => el.querySelector<SVGGElement>(`[data-${k}]`)!;
  const hH = hand('h'), hM = hand('m'), hS = hand('s');
  return {
    el,
    /** Hour + minute hands (cheap; called once a second). */
    slow(d: Date) {
      const m = d.getMinutes() + d.getSeconds() / 60;
      hM.style.transform = `rotate(${m * 6}deg)`;
      hH.style.transform = `rotate(${((d.getHours() % 12) + m / 60) * 30}deg)`;
    },
    /** Sweeping second hand: one transform write per frame. */
    sweep(now: number) {
      const d = new Date(now);
      hS.style.transform = `rotate(${(d.getSeconds() + d.getMilliseconds() / 1000) * 6}deg)`;
    },
  };
}

/* ---------- Calendar ---------- */
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function buildCalendar() {
  const month = h('div', { class: 'gdg-cal-month' });
  const day = h('div', { class: 'gdg-cal-day' });
  const wk = h('div', { class: 'gdg-cal-wk' });
  const el = card('Calendar', 'gdg-cal', [
    h('div', { class: 'gdg-cal-page' }, month, day, wk),
  ]);
  let key = '';
  return {
    el,
    update(d: Date) {
      const k = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      if (k === key) return;
      key = k;
      month.textContent = `${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
      day.textContent = String(d.getDate());
      wk.textContent = DAYS[d.getDay()];
    },
  };
}

/* ---------- CPU meter ---------- */
const A0 = -125;
const A1 = 125;

function dial(label: string) {
  let ticks = '';
  for (let i = 0; i <= 10; i++) {
    const a = A0 + ((A1 - A0) * i) / 10;
    ticks += `<line x1="30" y1="${i % 5 === 0 ? 7 : 8.5}" x2="30" y2="11.5" stroke="#9fc8f5" stroke-opacity="${i % 5 === 0 ? 0.95 : 0.55}" stroke-width="${i % 5 === 0 ? 1.1 : 0.6}" transform="rotate(${a} 30 32)"/>`;
  }
  const arc = (a: number, r: number) => `${30 + r * Math.sin((a * Math.PI) / 180)} ${32 - r * Math.cos((a * Math.PI) / 180)}`;
  const s = svg(
    '0 0 60 60',
    `<circle cx="30" cy="32" r="28" fill="url(#gdg-bezel)"/>
     <circle cx="30" cy="32" r="26" fill="url(#gdg-dial)"/>
     <path d="M${arc(A1 - 50, 19)} A19 19 0 0 1 ${arc(A1, 19)}" fill="none" stroke="#ff6a4d" stroke-opacity=".75" stroke-width="2"/>
     ${ticks}
     <text x="30" y="46" text-anchor="middle" font-size="6.5" fill="#bcd6f2" font-family="Selawik,Segoe UI,sans-serif">${label}</text>
     <g class="gdg-needle"><line x1="30" y1="36" x2="30" y2="10.5" stroke="#ff7a52" stroke-width="1.1" stroke-linecap="round"/><circle cx="30" cy="32" r="2.4" fill="#e8eef6"/></g>
     <path d="M7 24C10 12 19 6 30 6S50 12 53 24C44 19 38 18 30 18S16 19 7 24Z" fill="url(#gdg-shine)" opacity=".35"/>`,
  );
  const needle = s.querySelector<SVGGElement>('.gdg-needle')!;
  const val = h('div', { class: 'gdg-dial-val' }, '0%');
  const wrap = h('div', { class: 'gdg-dial' }, s, val);
  return {
    wrap,
    set(pct: number) {
      const p = Math.max(0, Math.min(100, pct));
      needle.style.transform = `rotate(${A0 + ((A1 - A0) * p) / 100}deg)`;
      val.textContent = `${Math.round(p)}%`;
    },
  };
}

function buildMeter() {
  const cpu = dial('CPU');
  const ram = dial('RAM');
  const el = card('CPU Meter', 'gdg-cpu', [h('div', { class: 'gdg-dials' }, cpu.wrap, ram.wrap)]);
  let c = 6;
  let r = 42;
  return {
    el,
    /** jank = ms of dropped-frame time over the last second. */
    update(jank: number) {
      const target = 4 + Math.min(70, jank / 14) + Math.random() * 5;
      c += (target - c) * 0.6;
      const mem = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
      const mb = mem ? mem.usedJSHeapSize / 1048576 : 60;
      const goal = 36 + Math.min(34, mb / 5) + Math.sin(Date.now() / 23000) * 2.5;
      r += (goal - r) * 0.2;
      cpu.set(c);
      ram.set(r);
    },
  };
}

/* ---------- Weather (offline demo) ---------- */
function buildWeather() {
  const glyph = svg(
    '0 0 64 48',
    `<g stroke="#ffb629" stroke-width="2" stroke-linecap="round" opacity=".95">${[0, 45, 90, 135, 180, 225, 270, 315].map((a) => `<line x1="22" y1="6" x2="22" y2="9.5" transform="rotate(${a} 22 19)"/>`).join('')}</g>
     <circle cx="22" cy="19" r="9" fill="url(#gdg-sun)" stroke="#b9650a" stroke-opacity=".45" stroke-width=".6"/>
     <path d="M20 40.5C14.5 40.5 12 36.7 13 33.2C14 30 17.4 29 19.8 30C21 25.5 25.6 23 30 24.2C33.6 25 35.6 27.6 36 30C41.4 29.3 45.6 32.6 45 36.4C44.6 39.2 42.2 40.5 39.6 40.5Z" fill="url(#gdg-cloud)" stroke="#6f87a6" stroke-opacity=".55" stroke-width=".7"/>
     <path d="M17 33C19 31 22 31 24 32.4" stroke="#fff" stroke-width="1.2" fill="none" stroke-linecap="round" opacity=".9"/>`,
    'gdg-wx-art',
  );
  return card('Weather', 'gdg-wx', [
    h('div', { class: 'gdg-wx-row' }, glyph, h('div', { class: 'gdg-wx-temp' }, '14°')),
    h('div', { class: 'gdg-wx-city' }, 'Bucharest'),
    h('div', { class: 'gdg-wx-desc' }, 'Partly cloudy'),
    h('div', { class: 'gdg-wx-note' }, 'Offline demo'),
  ]);
}

export function mountGadgets(desktop: HTMLElement): void {
  const host = h('div', { id: 'gadgets', html: DEFS });
  layer = host;
  // Between the desktop icons and the windows so windows always cover the gadgets.
  const windows = desktop.querySelector('#windows');
  if (windows) desktop.insertBefore(host, windows);
  else desktop.append(host);

  const clock = buildClock();
  const cal = buildCalendar();
  const meter = buildMeter();
  const wx = buildWeather();
  const cards = [clock.el, cal.el, meter.el, wx];
  const pos = new Map<HTMLElement, { x: number; y: number }>();

  const place = (el: HTMLElement) => {
    const p = pos.get(el)!;
    el.style.transform = `translate3d(${Math.round(p.x)}px,${Math.round(p.y)}px,0)`;
  };
  const layout = () => {
    let y = TOP;
    for (const el of cards) {
      pos.set(el, { x: window.innerWidth - RIGHT - W, y });
      y += el.offsetHeight + GAP;
      place(el);
    }
  };
  host.append(...cards);
  requestAnimationFrame(layout);

  // Keep dragged gadgets reachable after the browser window shrinks.
  window.addEventListener('resize', () => {
    for (const el of cards) {
      const p = pos.get(el);
      if (!p) continue;
      p.x = Math.max(0, Math.min(window.innerWidth - W, p.x));
      p.y = Math.max(30, Math.min(window.innerHeight - el.offsetHeight - 70, p.y));
      place(el);
    }
  });

  let top = 1;
  for (const el of cards) {
    el.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      const p = pos.get(el)!;
      const ox = e.clientX - p.x;
      const oy = e.clientY - p.y;
      el.setPointerCapture(e.pointerId);
      el.style.zIndex = String(++top);
      el.classList.add('drag');
      const move = (ev: PointerEvent) => {
        p.x = Math.max(0, Math.min(window.innerWidth - W, ev.clientX - ox));
        p.y = Math.max(30, Math.min(window.innerHeight - el.offsetHeight - 60, ev.clientY - oy));
        place(el);
      };
      const up = () => {
        el.classList.remove('drag');
        el.removeEventListener('pointermove', move);
        el.removeEventListener('pointerup', up);
        el.removeEventListener('pointercancel', up);
      };
      el.addEventListener('pointermove', move);
      el.addEventListener('pointerup', up);
      el.addEventListener('pointercancel', up);
      e.preventDefault();
    });
  }

  // One loop: sweeping second hand + frame-timing sampling. Idle (no frames) when hidden.
  let raf = 0;
  let last = 0;
  let jank = 0;
  const frame = (t: number) => {
    if (last) jank += Math.max(0, t - last - 17);
    last = t;
    clock.sweep(Date.now());
    raf = requestAnimationFrame(frame);
  };
  const tick = () => {
    const d = new Date();
    clock.slow(d);
    cal.update(d);
    meter.update(jank);
    jank = 0;
  };
  let timer = 0;
  wake = () => {
    const run = shown && !document.hidden;
    if (run && !raf) {
      last = 0;
      raf = requestAnimationFrame(frame);
      tick();
      timer = window.setInterval(tick, 1000);
    } else if (!run && raf) {
      cancelAnimationFrame(raf);
      raf = 0;
      clearInterval(timer);
    }
  };
  document.addEventListener('visibilitychange', wake);
  wake();
}
