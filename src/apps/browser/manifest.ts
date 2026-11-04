import type { AppManifest } from '../../core/types';
import { browserIcon } from './icon';
import { lazyMount } from '../lazy';

export const browser: AppManifest = {
  id: 'browser',
  name: 'Internet',
  icon: browserIcon,
  description: 'Browse the web',
  keywords: ['browser', 'web', 'internet', 'www', 'search', 'wikipedia'],
  pinned: true,
  desktop: true,
  window: { width: 1100, height: 720, minWidth: 520, minHeight: 360 },

  mount: lazyMount(() => import('./index')),
};
