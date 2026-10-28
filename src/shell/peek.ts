import { closeWindow, focusWindow, windowsOf, type Win } from '../core/wm';
import { h } from '../ui/dom';

/**
 * Aero Peek: hovering a running app in the dock shows live thumbnails of its
 * windows. Hovering a thumbnail "peeks" — every other window turns to glass
 * so you can see just that one. Click to switch, × to close.
 */

let pop: HTMLElement | null = null;
let closeTimer = 0;
let peekTimer = 0;

const THUMB_W = 186;
const THUMB_H = 118;

/**
 * A live-looking thumbnail: a scaled copy of the window's DOM (typed text and
 * canvas pixels included), like Windows 7's DWM thumbnails. Works for
 * minimized windows too, since the copy is laid out independently.
 */
function thumbnail(w: Win): HTMLElement {
  const clone = w.el.cloneNode(true) as HTMLElement;
  clone.querySelectorAll('.rz').forEach((n) => n.remove());
  const srcFields = w.el.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea');
  clone.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea').forEach((f, i) => {
    if (srcFields[i]) f.value = srcFields[i].value;
  });
  const srcCanvases = w.el.querySelectorAll('canvas');
  clone.querySelectorAll('canvas').forEach((c, i) => {
    try {
      c.getContext('2d')?.drawImage(srcCanvases[i], 0, 0);
    } catch {
      /* empty canvas */
    }
  });
  const scale = Math.min(THUMB_W / w.rect.w, THUMB_H / w.rect.h);
  clone.removeAttribute('id');
  clone.classList.add('peek-clone');
  clone.classList.remove('peek-target');
  Object.assign(clone.style, {
    position: 'absolute',
    left: '0',
    top: '0',
    width: `${w.rect.w}px`,
    height: `${w.rect.h}px`,
    display: '',
    visibility: 'visible',
    opacity: '1',
    zIndex: '0',
    transform: `scale(${scale})`,
    transformOrigin: '0 0',
  });
  return h('div', { class: 'peek-thumb', style: `width:${Math.round(w.rect.w * scale)}px;height:${Math.round(w.rect.h * scale)}px` }, clone);
}

function unpeek(): void {
  window.clearTimeout(peekTimer);
  document.body.classList.remove('peeking');
  document.querySelectorAll('.win.peek-target').forEach((n) => n.classList.remove('peek-target'));
}

export function closePeek(): void {
  window.clearTimeout(closeTimer);
  unpeek();
  const node = pop;
  pop = null;
  if (node) node.animate([{ opacity: 1 }, { opacity: 0, transform: 'translateY(6px)' }], { duration: 120 }).onfinish = () => node.remove();
}

function scheduleClose(): void {
  window.clearTimeout(closeTimer);
  closeTimer = window.setTimeout(closePeek, 280);
}

function openPeek(appId: string, anchor: HTMLElement): void {
  const wins = windowsOf(appId);
  if (!wins.length) return;
  closePeek();
  const panel = h('div', { class: 'peek-pop' });
  pop = panel;
  panel.addEventListener('pointerenter', () => window.clearTimeout(closeTimer));
  panel.addEventListener('pointerleave', scheduleClose);

  for (const w of wins) {
    const shot = h('div', { class: 'peek-shot' }, thumbnail(w));
    const close = h('button', { class: 'peek-close', 'aria-label': 'Close', title: 'Close' }, '×');
    const tile = h(
      'div',
      { class: `peek-tile${w.minimized ? ' minimized' : ''}` },
      h('div', { class: 'peek-head' }, h('span', { class: 'peek-icon', html: w.manifest.icon }), h('span', { class: 'peek-title' }, w.title), close),
      shot,
    );
    tile.addEventListener('click', (e) => {
      if ((e.target as HTMLElement).closest('.peek-close')) return;
      closePeek();
      focusWindow(w.id);
    });
    close.addEventListener('click', () => {
      closeWindow(w.id);
      tile.remove();
      if (!panel.querySelector('.peek-tile')) closePeek();
    });
    tile.addEventListener('pointerenter', () => {
      window.clearTimeout(peekTimer);
      if (w.minimized) return;
      peekTimer = window.setTimeout(() => {
        document.querySelectorAll('.win.peek-target').forEach((n) => n.classList.remove('peek-target'));
        w.el.classList.add('peek-target');
        document.body.classList.add('peeking');
      }, 380);
    });
    tile.addEventListener('pointerleave', unpeek);
    panel.append(tile);
  }

  document.body.append(panel);
  const r = anchor.getBoundingClientRect();
  const left = Math.min(Math.max(8, r.left + r.width / 2 - panel.offsetWidth / 2), window.innerWidth - panel.offsetWidth - 8);
  panel.style.left = `${Math.round(left)}px`;
  panel.style.bottom = `${Math.round(window.innerHeight - r.top + 14)}px`;
  panel.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 160, easing: 'cubic-bezier(.2,.8,.2,1)' });
}

/** Wire Aero Peek onto a dock item. */
export function attachPeek(btn: HTMLElement, appId: string): void {
  let hoverTimer = 0;
  btn.addEventListener('pointerenter', () => {
    window.clearTimeout(closeTimer);
    hoverTimer = window.setTimeout(() => openPeek(appId, btn), 480);
  });
  btn.addEventListener('pointerleave', () => {
    window.clearTimeout(hoverTimer);
    scheduleClose();
  });
  btn.addEventListener('pointerdown', () => {
    window.clearTimeout(hoverTimer);
    closePeek();
  });
}
