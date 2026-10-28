import { h } from '../ui/dom';

/**
 * Rubber-band selection on the desktop: drag on empty space to draw a
 * Win7-style selection rectangle; icons it touches get selected.
 * Ctrl / Shift / Cmd keep the existing selection.
 */
export function mountSelection(desktop: HTMLElement, iconLayer: HTMLElement): void {
  const band = h('div', { class: 'rubber-band' });

  const isBackground = (t: EventTarget | null) => {
    const el = t as HTMLElement | null;
    if (!el || !desktop.contains(el)) return false;
    return !el.closest('.desk-icon, .win, #windows > *:not(.snap-preview)');
  };

  desktop.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !isBackground(e.target)) return;
    const keep = e.ctrlKey || e.shiftKey || e.metaKey;
    const icons = [...iconLayer.querySelectorAll<HTMLElement>('.desk-icon')];
    const before = new Set(keep ? icons.filter((i) => i.classList.contains('selected')) : []);
    if (!keep) icons.forEach((i) => i.classList.remove('selected'));

    const sx = e.clientX;
    const sy = e.clientY;
    let active = false;
    desktop.setPointerCapture(e.pointerId);

    const move = (ev: PointerEvent) => {
      const x = Math.min(sx, ev.clientX);
      const y = Math.min(sy, ev.clientY);
      const w = Math.abs(ev.clientX - sx);
      const hgt = Math.abs(ev.clientY - sy);
      if (!active) {
        if (w < 3 && hgt < 3) return;
        active = true;
        desktop.append(band);
      }
      Object.assign(band.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${hgt}px` });
      for (const icon of icons) {
        const r = icon.getBoundingClientRect();
        const hit = r.left < x + w && r.right > x && r.top < y + hgt && r.bottom > y;
        icon.classList.toggle('selected', hit || before.has(icon));
      }
    };
    const up = () => {
      desktop.removeEventListener('pointermove', move);
      desktop.removeEventListener('pointerup', up);
      desktop.removeEventListener('pointercancel', up);
      band.remove();
    };
    desktop.addEventListener('pointermove', move);
    desktop.addEventListener('pointerup', up);
    desktop.addEventListener('pointercancel', up);
  });
}
