import { h } from './dom';

export interface ConfirmOptions {
  title: string;
  message: string;
  detail?: string;
  /** Icon markup (an <img>/<svg>) shown on the left, like a Windows message box. */
  icon?: string;
  okLabel?: string;
  cancelLabel?: string;
}

/**
 * Windows 7-style modal message box (glass frame, white body, grey button row).
 * Resolves true for OK / Enter, false for Cancel / Escape / outside click.
 */
export function confirmDialog(opts: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    const ok = h('button', { class: 'btn' }, opts.okLabel ?? 'OK');
    const cancel = h('button', { class: 'btn' }, opts.cancelLabel ?? 'Cancel');
    const box = h(
      'div',
      { class: 'msgbox', role: 'alertdialog', 'aria-label': opts.title },
      h('div', { class: 'msgbox-title' }, opts.title),
      h(
        'div',
        { class: 'msgbox-body' },
        opts.icon ? h('span', { class: 'msgbox-icon', html: opts.icon }) : null,
        h('div', { class: 'msgbox-text' }, h('div', { class: 'msgbox-main' }, opts.message), opts.detail ? h('div', { class: 'msgbox-detail' }, opts.detail) : null),
      ),
      h('div', { class: 'msgbox-buttons' }, ok, cancel),
    );
    const overlay = h('div', { class: 'msgbox-overlay' }, box);

    const done = (value: boolean) => {
      window.removeEventListener('keydown', onKey, true);
      box.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(.97)' }], { duration: 120 }).onfinish = () =>
        overlay.remove();
      resolve(value);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        done(false);
      } else if (e.key === 'Enter') {
        e.stopPropagation();
        e.preventDefault();
        done(true);
      }
    };
    ok.addEventListener('click', () => done(true));
    cancel.addEventListener('click', () => done(false));
    overlay.addEventListener('pointerdown', (e) => {
      // Like Windows: clicking outside a modal box just flashes it.
      if (e.target === overlay) box.animate([{ filter: 'brightness(1.25)' }, { filter: 'none' }], { duration: 300 });
    });
    window.addEventListener('keydown', onKey, true);
    document.body.append(overlay);
    box.animate([{ opacity: 0, transform: 'scale(.97)' }, { opacity: 1, transform: 'none' }], { duration: 160, easing: 'cubic-bezier(.2,.8,.2,1)' });
    ok.focus();
  });
}
