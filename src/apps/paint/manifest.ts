import type { AppManifest } from '../../core/types';
import { icons } from '../../assets/icons';
import { lazyMount } from '../lazy';

export const paint: AppManifest = {
  id: 'paint',
  name: 'Paint',
  icon: icons.paint,
  description: 'Draw, paint and edit pictures',
  keywords: ['draw', 'image', 'picture', 'bitmap', 'brush', 'png', 'canvas', 'edit'],
  pinned: false,
  desktop: false,
  window: { width: 1120, height: 700, minWidth: 420, minHeight: 360 },

  mount: lazyMount(() => import('./index')),
};
