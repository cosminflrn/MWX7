import { h } from './dom';

/**
 * macOS-style sheet that slides down from the top of a window's body.
 * Usage: showSheet(ctx.win.body, (close) => h('div', {}, ...))
 */
export function showSheet(host: HTMLElement, build: (close: () => void) => HTMLElement): () => void {
  const backdrop = h('div', { class: 'sheet-backdrop' });
  const sheet = h('div', { class: 'sheet' });
  backdrop.append(sheet);

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    sheet.animate([{ transform: 'none' }, { transform: 'translateY(-110%)' }], { duration: 160, easing: 'ease-in' }).onfinish =
      () => backdrop.remove();
  };

  sheet.append(build(close));
  sheet.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
    }
  });
  host.append(backdrop);
  sheet.animate([{ transform: 'translateY(-110%)' }, { transform: 'none' }], { duration: 200, easing: 'cubic-bezier(.2,.8,.2,1)' });
  sheet.querySelector<HTMLElement>('input, button, [tabindex]')?.focus();
  return close;
}
