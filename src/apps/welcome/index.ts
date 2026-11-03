import { icons } from '../../assets/icons';
import { getApp } from '../../core/registry';
import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import './welcome.css';

// Duplicated from apps/about (apps may not import each other); keep in sync on release.
const VERSION = '0.8.0';

interface Tile {
  icon: string;
  title: string;
  text: string;
  app?: string;
}

export const welcome: AppManifest = {
  id: 'welcome',
  name: 'Welcome to MWX 7',
  icon: icons.orb,
  description: 'A quick tour of what you can do',
  keywords: ['getting started', 'tour', 'intro', 'help'],
  singleInstance: true,
  window: { width: 620, height: 440, resizable: false },

  mount({ win, os }) {
    win.body.classList.add('welcome');
    const appIcon = (id: string) => getApp(id)?.icon ?? icons.orb;
    const tiles: Tile[] = [
      { icon: icons.explorer, title: 'Explore your files', text: 'Browse folders and drives in My Computer.', app: 'explorer' },
      { icon: appIcon('browser'), title: 'Browse the web', text: 'Surf with Internet, right inside the desktop.', app: 'browser' },
      { icon: appIcon('mediaplayer'), title: 'Play music', text: 'Listen to Bach in Media Player.', app: 'mediaplayer' },
      { icon: appIcon('pinball'), title: 'Play Space Pinball', text: 'Take a quick break with a classic table.', app: 'pinball' },
      { icon: icons.settings, title: 'Make it yours', text: 'Pick a wallpaper and Window Color in Settings.', app: 'settings' },
      {
        icon: icons.desktop,
        title: 'Try the desktop magic',
        text: 'Aero Peek, Overview and the genie minimize.',
      },
    ];

    win.body.append(
      h(
        'div',
        { class: 'wl-hero' },
        h('div', { class: 'wl-orb', html: icons.orb }),
        h(
          'div',
          { class: 'wl-hero-text' },
          h('h1', {}, 'Welcome to MWX ', h('span', {}, '7')),
          h(
            'p',
            {},
            'A dream desktop blending Windows XP, Windows 7 and macOS, running in your browser. Nothing is saved: every reload is a fresh machine.',
          ),
        ),
      ),
      h('div', { class: 'wl-head' }, 'Get started'),
      h(
        'div',
        { class: 'wl-grid' },
        ...tiles.map((t) =>
          h(
            t.app ? 'button' : 'div',
            {
              class: t.app ? 'wl-tile' : 'wl-tile wl-info',
              onclick: t.app ? () => os.launch(t.app!) : undefined,
            },
            h('span', { class: 'wl-ico', html: t.icon }),
            h('span', { class: 'wl-txt' }, h('b', {}, t.title), h('small', {}, t.text)),
          ),
        ),
      ),
      h(
        'div',
        { class: 'wl-foot' },
        h('button', { class: 'wl-begin', onclick: () => win.close() }, 'Begin'),
        h('span', { class: 'wl-ver' }, `MWX 7 · Version ${VERSION}`),
      ),
    );
  },
};
