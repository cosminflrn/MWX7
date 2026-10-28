import { icons } from '../assets/icons';
import { bus } from '../core/events';
import { h } from '../ui/dom';

/** macOS-style banners, top-right, in Aero glass. */
export function mountNotifications(host: HTMLElement): void {
  bus.on('notify', ({ title, body, icon }) => {
    const toast = h(
      'div',
      { class: 'toast', role: 'status' },
      h('span', { class: 'toast-icon', html: icon ?? icons.orb }),
      h('div', { class: 'toast-text' }, h('b', {}, title), body ? h('span', {}, body) : null),
    );
    const dismiss = () => {
      toast.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateX(40px)' }], {
        duration: 200,
        easing: 'ease-in',
      }).onfinish = () => toast.remove();
    };
    toast.addEventListener('click', dismiss);
    host.append(toast);
    toast.animate([{ opacity: 0, transform: 'translateX(60px)' }, { opacity: 1, transform: 'none' }], {
      duration: 260,
      easing: 'cubic-bezier(.2,.8,.2,1)',
    });
    window.setTimeout(dismiss, 5000);
  });
}
