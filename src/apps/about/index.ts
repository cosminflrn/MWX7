import { icons } from '../../assets/icons';
import { getApp } from '../../core/registry';
import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import './about.css';

export const VERSION = '0.4.0';

export const about: AppManifest = {
  id: 'about',
  name: 'About MWX 7',
  icon: icons.about,
  description: 'Version and credits',
  keywords: ['version', 'info', 'credits', 'system'],
  desktop: true,
  singleInstance: true,
  window: { width: 420, height: 430, resizable: false },

  mount({ win, args }) {
    const app = typeof args.app === 'string' ? getApp(args.app) : undefined;
    win.body.classList.add('about');
    if (app) {
      win.setTitle(`About ${app.name}`);
      win.body.append(
        h('div', { class: 'about-logo', html: app.icon }),
        h('h1', {}, app.name),
        h('p', { class: 'about-tag' }, app.description ?? ''),
        h('p', { class: 'about-small' }, `Part of MWX 7 ${VERSION}`),
      );
      return;
    }
    win.body.append(
      h('div', { class: 'about-logo', html: icons.orb }),
      h('h1', {}, 'MWX ', h('span', { class: 'about-seven' }, '7')),
      h('p', { class: 'about-tag' }, 'The dream desktop.'),
      h(
        'dl',
        { class: 'about-specs' },
        h('dt', {}, 'Version'),
        h('dd', {}, `${VERSION} “Explorer”`),
        h('dt', {}, 'Processor'),
        h('dd', {}, navigator.hardwareConcurrency ? `${navigator.hardwareConcurrency} browser threads` : 'Your browser'),
        h('dt', {}, 'Storage'),
        h('dd', {}, 'Memory — this session only'),
        h('dt', {}, 'Built by'),
        h('dd', {}, 'Cosmin & Claude'),
      ),
      h('a', { class: 'about-link', href: 'https://github.com/cosminflrn/MWX7', target: '_blank', rel: 'noopener' }, 'github.com/cosminflrn/MWX7'),
      h(
        'p',
        { class: 'about-small' },
        'Icons: KDE Oxygen (LGPL) · Font: Selawik (OFL) · Footage & photos: Pexels · Sounds: FluidR3 (MIT). Details in media/CREDITS.md.',
      ),
    );
  },
};
