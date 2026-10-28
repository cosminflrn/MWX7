import { play } from '../core/sound';
import { allWindows, focusWindow, workArea, type Win } from '../core/wm';
import { closeMenu } from '../ui/menu';
import { h } from '../ui/dom';

/**
 * Mission Control: every open window glides into a non-overlapping grid so you
 * can pick one. Minimized windows line up in a smaller row at the bottom.
 * Triggers: F3, Ctrl+↑ (outside text fields) and the top-left hot corner.
 * Only transforms are animated (no layout), so it stays smooth.
 */

interface Placed {
  w: Win;
  wasHidden: boolean;
  label: HTMLElement;
}

let active: { dim: HTMLElement; placed: Placed[]; onKey: (e: KeyboardEvent) => void; onClick: (e: MouseEvent) => void } | null = null;
const ANIM = 'transform 0.38s cubic-bezier(.2,.8,.2,1), opacity 0.3s';

function layout(items: Win[], area: { x: number; y: number; w: number; h: number }): Map<Win, { x: number; y: number; s: number }> {
  const out = new Map<Win, { x: number; y: number; s: number }>();
  if (!items.length) return out;
  // Pick the column count that gives the largest average scale.
  let best = { cols: 1, scale: 0 };
  for (let cols = 1; cols <= items.length; cols++) {
    const rows = Math.ceil(items.length / cols);
    const cw = area.w / cols;
    const ch = area.h / rows;
    const scale = items.reduce((acc, w) => acc + Math.min(1, (cw * 0.84) / w.rect.w, (ch * 0.78) / w.rect.h), 0) / items.length;
    if (scale > best.scale) best = { cols, scale };
  }
  const cols = best.cols;
  const rows = Math.ceil(items.length / cols);
  const cw = area.w / cols;
  const ch = area.h / rows;
  items.forEach((w, i) => {
    const r = Math.floor(i / cols);
    const inRow = r === rows - 1 ? items.length - r * cols : cols;
    const c = i % cols;
    // Center a short last row, like macOS.
    const rowOffset = ((cols - inRow) * cw) / 2;
    const s = Math.min(1, (cw * 0.84) / w.rect.w, (ch * 0.78) / w.rect.h);
    const x = area.x + rowOffset + c * cw + (cw - w.rect.w * s) / 2;
    const y = area.y + r * ch + (ch * 0.92 - w.rect.h * s) / 2;
    out.set(w, { x, y, s });
  });
  return out;
}

export function isMissionControlOpen(): boolean {
  return !!active;
}

export function openMissionControl(): void {
  if (active) return closeMissionControl();
  const wins = allWindows();
  if (!wins.length) return;
  closeMenu();

  const wa = workArea();
  const shown = wins.filter((w) => !w.minimized);
  const hidden = wins.filter((w) => w.minimized);
  const stripH = hidden.length ? Math.min(150, wa.h * 0.2) : 0;
  const main = layout(shown, { x: 40, y: wa.y + 30, w: wa.w - 80, h: wa.h - 50 - stripH });
  const strip = layout(hidden, { x: wa.w * 0.15, y: wa.y + wa.h - stripH, w: wa.w * 0.7, h: stripH });

  const layer = document.getElementById('windows')!;
  const dim = h('div', { class: 'mc-dim' });
  layer.prepend(dim);
  document.body.classList.add('mission');
  play('menuOpen');

  const placed: Placed[] = [];
  for (const [w, t] of [...main, ...strip]) {
    const wasHidden = w.el.style.display === 'none';
    if (wasHidden) {
      w.el.style.display = '';
      w.el.style.opacity = '0';
    }
    w.el.style.transformOrigin = '0 0';
    w.el.style.transition = ANIM;
    const label = h('div', { class: 'mc-label' }, w.title);
    label.style.left = `${t.x + (w.rect.w * t.s) / 2}px`;
    label.style.top = `${t.y + w.rect.h * t.s + 10}px`;
    dim.append(label);
    requestAnimationFrame(() => {
      w.el.style.transform = `translate(${t.x - w.rect.x}px, ${t.y - w.rect.y}px) scale(${t.s})`;
      w.el.style.opacity = wasHidden ? '0.85' : '';
    });
    placed.push({ w, wasHidden, label });
  }

  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape' || e.key === 'F3') {
      e.preventDefault();
      closeMissionControl();
    }
  };
  // Capture phase: a click anywhere picks a window (or dismisses) and never reaches the app inside.
  const onClick = (e: MouseEvent) => {
    const el = (e.target as HTMLElement).closest('.win') as HTMLElement | null;
    e.preventDefault();
    e.stopPropagation();
    const pick = el ? placed.find((p) => p.w.el === el)?.w : undefined;
    closeMissionControl(pick);
  };
  window.addEventListener('keydown', onKey, true);
  document.addEventListener('click', onClick, true);
  active = { dim, placed, onKey, onClick };
}

export function closeMissionControl(pick?: Win): void {
  const a = active;
  if (!a) return;
  active = null;
  window.removeEventListener('keydown', a.onKey, true);
  document.removeEventListener('click', a.onClick, true);
  document.body.classList.remove('mission');
  play('menuClose');
  for (const p of a.placed) {
    p.w.el.style.transform = '';
    if (p.wasHidden && p.w !== pick) p.w.el.style.opacity = '0';
  }
  a.dim.classList.add('leaving');
  window.setTimeout(() => {
    a.dim.remove();
    for (const p of a.placed) {
      p.w.el.style.transition = '';
      p.w.el.style.transformOrigin = '';
      p.w.el.style.opacity = '';
      if (p.wasHidden && p.w.minimized) p.w.el.style.display = 'none';
    }
    if (pick) focusWindow(pick.id);
  }, 390);
}

/** Keyboard + hot-corner triggers. */
export function mountMissionControl(): void {
  window.addEventListener('keydown', (e) => {
    if (active) return;
    const t = e.target as HTMLElement;
    const typing = t.closest?.('input, textarea, [contenteditable]');
    if (e.key === 'F3' || (e.ctrlKey && !e.altKey && e.key === 'ArrowUp' && !typing)) {
      e.preventDefault();
      openMissionControl();
    }
  });
  let cornerTimer = 0;
  window.addEventListener('pointermove', (e) => {
    const inCorner = e.clientX <= 1 && e.clientY <= 1;
    if (inCorner && !cornerTimer && !document.querySelector('.screen')) {
      cornerTimer = window.setTimeout(() => {
        cornerTimer = 0;
        openMissionControl();
      }, 280);
    } else if (!inCorner && cornerTimer) {
      clearTimeout(cornerTimer);
      cornerTimer = 0;
    }
  });
}
