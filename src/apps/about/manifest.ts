import type { AppManifest } from '../../core/types';
import { icons } from '../../assets/icons';
import { lazyMount } from '../lazy';

export const about: AppManifest = {
  id: 'about',
  name: 'About MWX 7',
  icon: icons.about,
  description: 'Version and credits',
  keywords: ['version', 'info', 'credits', 'system'],
  desktop: true,
  singleInstance: true,
  window: { width: 420, height: 470, resizable: false },

  mount: lazyMount(() => import('./index')),
};
