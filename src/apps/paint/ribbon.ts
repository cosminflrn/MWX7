/** Small UI kit for the Ribbon: command buttons, split buttons, group frames and dropdown popups. */
import { h } from '../../ui/dom';
import { glyph, type GlyphName } from './glyphs';

export interface BtnOpts {
  icon?: GlyphName;
  label?: string;
  title?: string;
  big?: boolean;
  caret?: boolean;
  cls?: string;
  onclick?: (e: MouseEvent) => void;
}

export function rbtn(o: BtnOpts): HTMLButtonElement {
  const b = h(
    'button',
    {
      class: `pt-rb${o.big ? ' big' : ''}${o.cls ? ' ' + o.cls : ''}`,
      type: 'button',
      title: o.title ?? o.label ?? '',
      'aria-label': o.title ?? o.label ?? '',
      onclick: o.onclick,
    },
    o.icon ? glyph(o.icon, o.big ? 32 : 16) : null,
    o.label ? h('span', { class: 'pt-rb-l' }, o.label, o.caret && o.big ? h('span', { class: 'pt-caret' }) : null) : null,
    o.caret && !o.big ? h('span', { class: 'pt-caret' }) : null,
  );
  return b;
}

/** A large command with an action on its icon and a dropdown on its label, like the original Ribbon. */
export function splitBig(o: { icon: GlyphName; label: string; title?: string; onMain: () => void; onMenu: (anchor: HTMLElement) => void }): HTMLElement {
  const main = rbtn({ icon: o.icon, big: true, title: o.title ?? o.label, cls: 'pt-split-top', onclick: o.onMain });
  const menu = h(
    'button',
    { class: 'pt-rb pt-split-bot', type: 'button', 'aria-label': `${o.label} options`, onclick: (e: MouseEvent) => o.onMenu(e.currentTarget as HTMLElement) },
    h('span', { class: 'pt-rb-l' }, o.label),
    h('span', { class: 'pt-caret' }),
  );
  return h('div', { class: 'pt-split' }, main, menu);
}

export function group(label: string, ...children: (Node | null)[]): HTMLElement {
  return h('div', { class: 'pt-group' }, h('div', { class: 'pt-group-body' }, ...children), h('div', { class: 'pt-group-label' }, label));
}

export const col = (...c: Node[]): HTMLElement => h('div', { class: 'pt-col' }, ...c);
export const row = (...c: Node[]): HTMLElement => h('div', { class: 'pt-row' }, ...c);

/* ------------------------------------------------------------------ popups */

let closeCurrent: (() => void) | null = null;
let currentAnchor: HTMLElement | null = null;

export function closePopup(): void {
  closeCurrent?.();
}

export function popupOpenFor(anchor: HTMLElement): boolean {
  return currentAnchor === anchor;
}

/** Opens `content` under `anchor` inside `host` (the window body, so it is clipped and themed with the app). */
export function openPopup(host: HTMLElement, anchor: HTMLElement, content: HTMLElement): void {
  const toggleOff = popupOpenFor(anchor);
  closePopup();
  if (toggleOff) return;
  const pop = h('div', { class: 'pt-pop' }, content);
  host.append(pop);
  currentAnchor = anchor;
  anchor.classList.add('open');

  const hr = host.getBoundingClientRect();
  const ar = anchor.getBoundingClientRect();
  const left = Math.max(2, Math.min(ar.left - hr.left, hr.width - pop.offsetWidth - 4));
  const top = Math.min(ar.bottom - hr.top - 1, Math.max(2, hr.height - pop.offsetHeight - 4));
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;

  const onDown = (e: PointerEvent) => {
    const t = e.target as Node;
    // the anchor handles its own toggle via popupOpenFor()
    if (!pop.contains(t) && !anchor.contains(t)) close();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
    }
  };
  const close = () => {
    pop.remove();
    anchor.classList.remove('open');
    // the clicked menu item just left the DOM; without this, shortcuts would stop reaching the window
    if (!document.activeElement || document.activeElement === document.body) host.focus({ preventScroll: true });
    document.removeEventListener('pointerdown', onDown, true);
    document.removeEventListener('keydown', onKey, true);
    if (closeCurrent === close) {
      closeCurrent = null;
      currentAnchor = null;
    }
  };
  document.addEventListener('pointerdown', onDown, true);
  document.addEventListener('keydown', onKey, true);
  closeCurrent = close;
}

export interface PopItem {
  label: string;
  icon?: GlyphName;
  checked?: boolean;
  disabled?: boolean;
  shortcut?: string;
  action: () => void;
}

export function popMenu(items: (PopItem | 'sep')[]): HTMLElement {
  const el = h('div', { class: 'pt-menu', role: 'menu' });
  for (const it of items) {
    if (it === 'sep') {
      el.append(h('div', { class: 'pt-menu-sep' }));
      continue;
    }
    el.append(
      h(
        'button',
        {
          class: `pt-mi${it.checked ? ' on' : ''}`,
          type: 'button',
          role: 'menuitem',
          disabled: it.disabled,
          onclick: () => {
            closePopup();
            it.action();
          },
        },
        h('span', { class: 'pt-mi-ic' }, it.icon ? glyph(it.icon, 16) : null),
        h('span', { class: 'pt-mi-l' }, it.label),
        h('span', { class: 'pt-mi-sc' }, it.shortcut ?? ''),
      ),
    );
  }
  return el;
}
