import type { MenuItem } from '../core/types';
import { h } from './dom';

/** Floating glass menu used by the menu bar, context menus and dock. */

/** URL of a small menu icon from public/media/icons/16/ (32px artwork shown at 16px). */
export function menuIcon(name: string): string {
  return `${import.meta.env.BASE_URL}media/icons/16/${name}.png`;
}

let current: { el: HTMLElement; close: () => void } | null = null;

export interface OpenMenuOptions {
  /** Clicks inside the anchor don't count as "outside" (the anchor toggles itself). */
  anchor?: HTMLElement;
  onClose?: () => void;
  /** Open upwards from y (used by the dock). */
  above?: boolean;
}

export function closeMenu(): void {
  current?.close();
}

export function isMenuOpen(): boolean {
  return current !== null;
}

export function openMenu(items: MenuItem[], pos: { x: number; y: number }, opts: OpenMenuOptions = {}): () => void {
  closeMenu();

  const el = h('div', { class: 'menu-pop', role: 'menu' });
  for (const item of items) {
    if (item.separator) {
      el.append(h('div', { class: 'menu-sep' }));
      continue;
    }
    el.append(
      h(
        'button',
        {
          class: `menu-item${item.checked ? ' checked' : ''}`,
          role: 'menuitem',
          disabled: item.disabled,
          onclick: () => {
            close();
            item.action?.();
          },
        },
        h(
          'span',
          { class: 'menu-check' },
          item.checked
            ? '✓'
            : item.icon
              ? item.icon.startsWith('<')
                ? h('span', { class: 'menu-icon', html: item.icon })
                : h('img', { class: 'menu-icon', src: item.icon, alt: '', draggable: false })
              : '',
        ),
        h('span', { class: 'menu-label' }, item.label ?? ''),
      ),
    );
  }
  document.body.append(el);

  const r = el.getBoundingClientRect();
  const x = Math.min(pos.x, window.innerWidth - r.width - 6);
  const y = opts.above ? pos.y - r.height : Math.min(pos.y, window.innerHeight - r.height - 6);
  el.style.left = `${Math.max(6, x)}px`;
  el.style.top = `${Math.max(6, y)}px`;

  const onDown = (e: PointerEvent) => {
    const t = e.target as Node;
    if (el.contains(t) || opts.anchor?.contains(t)) return;
    close();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') close();
  };
  document.addEventListener('pointerdown', onDown, true);
  document.addEventListener('keydown', onKey, true);

  function close() {
    if (current?.el !== el) return;
    current = null;
    document.removeEventListener('pointerdown', onDown, true);
    document.removeEventListener('keydown', onKey, true);
    el.remove();
    opts.onClose?.();
  }

  current = { el, close };
  return close;
}
