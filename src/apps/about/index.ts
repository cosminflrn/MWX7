import { icons } from '../../assets/icons';
import { getApp } from '../../core/registry';
import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import './about.css';

export const VERSION = '1.8.0';

/** Latest changes shown in About; keep to a few short lines and mirror CHANGELOG.md. */
const WHATS_NEW = [
  'MWX 7 OS: Keep settings — remembers everything without installing',
  'MWX 7 OS: installer with disk encryption, MWX 7 logon screen',
  'MWX 7 OS: genie minimize into the dock, running apps in the dock',
  'MWX 7 OS: boot splash, Aero glass window frames with traffic lights, Settings app',
  'MWX 7 OS: Start menu with search, volume and network in the status bar',
  'Notifications at the top right; Files and other apps in the MWX 7 look',
];

export const impl: Pick<AppManifest, 'mount'> = {
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
        h('dd', {}, `${VERSION} “Luna”`),
        h('dt', {}, 'Processor'),
        h('dd', {}, navigator.hardwareConcurrency ? `${navigator.hardwareConcurrency} browser threads` : 'Your browser'),
        h('dt', {}, 'Storage'),
        h('dd', {}, 'Memory — this session only'),
        h('dt', {}, 'Built by'),
        h('dd', {}, 'Cosmin & Claude'),
      ),
      h('a', { class: 'about-link', href: 'https://github.com/cosminflrn/MWX7', target: '_blank', rel: 'noopener' }, 'github.com/cosminflrn/MWX7'),
      h(
        'details',
        { class: 'about-new' },
        h('summary', {}, `What\u2019s new in ${VERSION}`),
        h('ul', {}, ...WHATS_NEW.map((t) => h('li', {}, t))),
      ),
      h(
        'p',
        { class: 'about-small' },
        'Icons: Crystal Clear (LGPL, Everaldo Coelho) · Font: Selawik (OFL) · Footage & photos: Pexels · Sounds: FluidR3 (MIT). Details in media/CREDITS.md.',
      ),
    );
  },
};
