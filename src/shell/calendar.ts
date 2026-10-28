import { launch } from '../core/os';
import { play } from '../core/sound';
import '../styles/calendar.css';
import { h } from '../ui/dom';

/**
 * Win7-style clock flyout: big time, long date, and a month grid that zooms out to months and years.
 * The menu bar owns the clock button; it only calls toggleCalendar() and we mark it pressed while open.
 */

type View = 'days' | 'months' | 'years';

let current: { el: HTMLElement; anchor: HTMLElement; close: () => void } | null = null;

export const isCalendarOpen = (): boolean => current !== null;
export const closeCalendar = (): void => current?.close();

export function toggleCalendar(anchor: HTMLElement): void {
  if (current) current.close();
  else openCalendar(anchor);
}

/* ---------- locale helpers ---------- */

/** 0 = Sunday … 6 = Saturday. Intl knows the locale's week start; the fallback is Monday (en-GB, ro, most of Europe). */
function firstWeekday(): number {
  try {
    const loc = new Intl.Locale(navigator.language) as Intl.Locale & {
      getWeekInfo?: () => { firstDay: number };
      weekInfo?: { firstDay: number };
    };
    const info = loc.getWeekInfo?.() ?? loc.weekInfo;
    if (info) return info.firstDay % 7;
  } catch {
    /* fall through */
  }
  return /-(US|CA|MX|BR|JP|IL|IN|PH|ZA|KR|TW|AU)\b/.test(navigator.language) ? 0 : 1;
}

const cap = (s: string) => s.charAt(0).toLocaleUpperCase() + s.slice(1);
const fmt = (o: Intl.DateTimeFormatOptions, d: Date) => cap(new Intl.DateTimeFormat(undefined, o).format(d));
const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
/** Date arithmetic via components so DST changes can never skip or repeat a day. */
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const addMonths = (d: Date, n: number) => {
  const t = new Date(d.getFullYear(), d.getMonth() + n, 1);
  t.setDate(Math.min(d.getDate(), new Date(t.getFullYear(), t.getMonth() + 1, 0).getDate()));
  return t;
};

/* ---------- flyout ---------- */

function openCalendar(anchor: HTMLElement): void {
  let view: View = 'days';
  let today = new Date();
  let selected = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  /** The month (days view), year (months view) or decade (years view) on display. */
  let cursor = new Date(selected.getFullYear(), selected.getMonth(), 1);

  const hour12 = !!new Intl.DateTimeFormat(undefined, { hour: 'numeric' }).resolvedOptions().hour12;
  const timeEl = h('div', { class: 'cal-time' });
  const dateEl = h('button', { class: 'cal-link cal-date', type: 'button', title: 'Go to today', onclick: () => goToday() });
  const titleEl = h('button', { class: 'cal-title', type: 'button', onclick: () => zoomOut() });
  const prevEl = h('button', { class: 'cal-arrow', type: 'button', 'aria-label': 'Previous', html: '&#9666;', onclick: () => step(-1) });
  const nextEl = h('button', { class: 'cal-arrow', type: 'button', 'aria-label': 'Next', html: '&#9656;', onclick: () => step(1) });
  const gridEl = h('div', { class: 'cal-grid' });
  const todayEl = h('button', { class: 'cal-link', type: 'button', onclick: () => goToday() }, 'Today');
  const settingsEl = h(
    'button',
    {
      class: 'cal-link',
      type: 'button',
      onclick: () => {
        close();
        launch('settings');
      },
    },
    'Change date and time settings…',
  );

  const el = h(
    'div',
    { class: 'cal-fly', role: 'dialog', 'aria-label': 'Calendar and clock' },
    h(
      'div',
      { class: 'cal-body' },
      h('div', { class: 'cal-top' }, timeEl, dateEl),
      h('div', { class: 'cal-cal' }, h('div', { class: 'cal-nav' }, titleEl, prevEl, nextEl), gridEl),
      h('div', { class: 'cal-foot' }, todayEl, settingsEl),
    ),
  );

  /* -- rendering -- */

  const updateClock = () => {
    const now = new Date();
    // 24-hour locales read "17:42:08"; 12-hour ones "5:42:08 PM" (Win7 drops the leading zero there).
    timeEl.textContent = now.toLocaleTimeString(undefined, { hour: hour12 ? 'numeric' : '2-digit', minute: '2-digit', second: '2-digit' });
    dateEl.textContent = cap(now.toLocaleDateString(undefined, { dateStyle: 'full' }));
    if (!sameDay(now, today)) {
      today = now;
      renderGrid();
    }
  };

  const cell = (label: string, onClick: () => void, cls = '', aria?: string) =>
    h('button', { class: `cal-cell ${cls}`.trim(), type: 'button', 'aria-label': aria ?? label, onclick: onClick }, label);

  function renderGrid(): void {
    const next: HTMLElement[] = [];
    gridEl.classList.toggle('wide', view !== 'days');
    if (view === 'days') {
      titleEl.textContent = fmt({ month: 'long', year: 'numeric' }, cursor);
      const fw = firstWeekday();
      for (let i = 0; i < 7; i++) {
        const ref = new Date(2023, 0, 1 + ((fw + i) % 7)); // 2023-01-01 was a Sunday
        const name = cap(new Intl.DateTimeFormat(undefined, { weekday: 'short' }).format(ref)).replace(/\.$/, '');
        next.push(h('div', { class: 'cal-dow', 'aria-hidden': 'true' }, name.slice(0, 2)));
      }
      const offset = (cursor.getDay() - fw + 7) % 7;
      const start = addDays(cursor, -offset);
      for (let i = 0; i < 42; i++) {
        const d = addDays(start, i);
        const cls = [d.getMonth() !== cursor.getMonth() ? 'dim' : '', sameDay(d, today) ? 'today' : '', sameDay(d, selected) ? 'sel' : '']
          .filter(Boolean)
          .join(' ');
        next.push(
          cell(String(d.getDate()), () => pick(d), cls, d.toLocaleDateString(undefined, { dateStyle: 'full' })),
        );
      }
    } else if (view === 'months') {
      titleEl.textContent = String(cursor.getFullYear());
      for (let m = 0; m < 12; m++) {
        const d = new Date(cursor.getFullYear(), m, 1);
        const isNow = d.getFullYear() === today.getFullYear() && m === today.getMonth();
        next.push(cell(fmt({ month: 'short' }, d).replace(/\.$/, ''), () => zoomIn(d), isNow ? 'today' : '', fmt({ month: 'long', year: 'numeric' }, d)));
      }
    } else {
      const decade = Math.floor(cursor.getFullYear() / 10) * 10;
      titleEl.textContent = `${decade} – ${decade + 9}`;
      for (let y = decade - 1; y <= decade + 10; y++) {
        const isNow = y === today.getFullYear();
        next.push(cell(String(y), () => zoomIn(new Date(y, cursor.getMonth(), 1)), `${isNow ? 'today' : ''} ${y < decade || y > decade + 9 ? 'dim' : ''}`));
      }
    }
    gridEl.replaceChildren(...next);
  }

  /** Re-render with the little zoom Win7 plays when you change level. */
  const renderAnimated = () => {
    renderGrid();
    gridEl.style.animation = 'none';
    void gridEl.offsetWidth;
    gridEl.style.animation = '';
  };

  /* -- navigation -- */

  function step(dir: 1 | -1): void {
    if (view === 'days') cursor = addMonths(cursor, dir);
    else if (view === 'months') cursor = new Date(cursor.getFullYear() + dir, cursor.getMonth(), 1);
    else cursor = new Date(cursor.getFullYear() + dir * 10, cursor.getMonth(), 1);
    renderGrid();
  }
  function zoomOut(): void {
    if (view === 'days') view = 'months';
    else if (view === 'months') view = 'years';
    else return;
    renderAnimated();
  }
  function zoomIn(d: Date): void {
    cursor = new Date(d.getFullYear(), d.getMonth(), 1);
    view = view === 'years' ? 'months' : 'days';
    renderAnimated();
  }
  function pick(d: Date): void {
    selected = d;
    cursor = new Date(d.getFullYear(), d.getMonth(), 1);
    renderGrid();
  }
  function goToday(): void {
    today = new Date();
    view = 'days';
    pick(new Date(today.getFullYear(), today.getMonth(), today.getDate()));
  }

  /* -- lifecycle -- */

  const onDown = (e: PointerEvent) => {
    const t = e.target as Node;
    if (el.contains(t) || anchor.contains(t)) return; // the clock button toggles itself
    close();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      close();
      return;
    }
    // Arrow keys move the selected day, like the Win7 calendar; leave typing in apps alone.
    const ae = document.activeElement as HTMLElement | null;
    if (view !== 'days' || e.ctrlKey || e.altKey || e.metaKey) return;
    if (ae && ae !== document.body && !el.contains(ae)) return;
    const move: Record<string, () => Date> = {
      ArrowLeft: () => addDays(selected, -1),
      ArrowRight: () => addDays(selected, 1),
      ArrowUp: () => addDays(selected, -7),
      ArrowDown: () => addDays(selected, 7),
      PageUp: () => addMonths(selected, -1),
      PageDown: () => addMonths(selected, 1),
    };
    const fn = move[e.key];
    if (fn) {
      e.preventDefault();
      pick(fn());
    }
  };
  const tick = window.setInterval(updateClock, 1000);

  function close(): void {
    if (current?.el !== el) return;
    current = null;
    window.clearInterval(tick);
    document.removeEventListener('pointerdown', onDown, true);
    document.removeEventListener('keydown', onKey, true);
    anchor.classList.remove('open');
    anchor.setAttribute('aria-expanded', 'false');
    el.classList.add('closing');
    window.setTimeout(() => el.remove(), 100);
    play('menuClose');
  }

  updateClock();
  renderGrid();
  el.style.top = `${Math.round(anchor.getBoundingClientRect().bottom) + 3}px`;
  document.body.append(el);
  document.addEventListener('pointerdown', onDown, true);
  document.addEventListener('keydown', onKey, true);
  anchor.classList.add('open');
  anchor.setAttribute('aria-expanded', 'true');
  current = { el, anchor, close };
  play('menuOpen');
}
