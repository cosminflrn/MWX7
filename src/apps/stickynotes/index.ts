import type { AppManifest, MenuItem } from '../../core/types';
import { h } from '../../ui/dom';
import { openMenu } from '../../ui/menu';
import { showSheet } from '../../ui/sheet';
import { stickyIcon } from './icon';
import './stickynotes.css';

const COLORS: Array<[string, string]> = [
  ['yellow', 'Yellow'],
  ['blue', 'Blue'],
  ['green', 'Green'],
  ['pink', 'Pink'],
  ['purple', 'Purple'],
  ['white', 'White'],
];
const SWATCH: Record<string, string> = { yellow: '#f1d95b', blue: '#9ccbf0', green: '#a4dc8b', pink: '#f1a2c0', purple: '#c1a4e8', white: '#f4f5f7' };
const swatch = (c: string) => `<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="2" width="12" height="12" rx="2.500" fill="${SWATCH[c]}" stroke="#000" stroke-opacity=".35"/></svg>`;
const ICON_PLUS = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.500v11M2.500 8h11" stroke="currentColor" stroke-width="1.800" stroke-linecap="round" fill="none"/></svg>';
const ICON_X = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3.500 3.500 9 9m0-9-9 9" stroke="currentColor" stroke-width="1.800" stroke-linecap="round" fill="none"/></svg>';

/** One window per note; notes are session-only by design, so nothing is persisted. */
export const stickynotes: AppManifest = {
  id: 'stickynotes',
  name: 'Sticky Notes',
  icon: stickyIcon,
  description: 'Jot down quick reminders',
  keywords: ['note', 'memo', 'reminder', 'post-it', 'sticky'],
  pinned: false,
  desktop: false,
  window: { width: 240, height: 240, minWidth: 170, minHeight: 130 },

  mount({ win, args, os }) {
    win.body.classList.add('sn');
    let color = typeof args.color === 'string' && SWATCH[args.color] ? args.color : 'yellow';
    win.body.dataset.c = color;

    const text = h('textarea', { class: 'sn-text', spellcheck: false, placeholder: 'Type your note here…', 'aria-label': 'Note' });
    const add = h('button', { class: 'sn-hb', 'aria-label': 'New note', title: 'New note', html: ICON_PLUS, onclick: () => os.launch('stickynotes', { color }) });
    const close = h('button', { class: 'sn-hb', 'aria-label': 'Delete note', title: 'Delete note', html: ICON_X, onclick: () => win.close() });
    win.body.append(h('div', { class: 'sn-head' }, add, close), text);

    const setColor = (c: string) => {
      color = c;
      win.body.dataset.c = c;
    };
    const menu = (e: MouseEvent) => {
      e.preventDefault();
      const items: MenuItem[] = COLORS.map(([id, label]) => ({ label, icon: swatch(id), checked: id === color, action: () => setColor(id) }));
      openMenu(items, { x: e.clientX, y: e.clientY });
    };
    win.body.addEventListener('contextmenu', menu);

    const title = () => {
      const first = text.value.trim().split('\n')[0].slice(0, 28);
      win.setTitle(first ? `${first} — Sticky Notes` : 'Sticky Notes');
    };
    text.addEventListener('input', title);
    title();

    // Closing a note that has text asks first, like Win7; empty notes just go away.
    let confirmed = false;
    win.onBeforeClose(() => {
      if (confirmed || !text.value.trim()) return true;
      showSheet(win.body, (done) =>
        h('div', { class: 'sheet-form' },
          h('div', { class: 'sn-dlg' }, h('b', {}, 'Delete this note?'), 'It will be permanently deleted.'),
          h('div', { class: 'sheet-actions' },
            h('button', { class: 'btn primary', onclick: () => { confirmed = true; done(); win.close(); } }, 'Delete'),
            h('button', { class: 'btn', onclick: done }, 'Cancel'))),
      );
      return false;
    });
    setTimeout(() => text.focus(), 60);
  },
};
