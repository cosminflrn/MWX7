import type { AppManifest } from '../../core/types';
import { pinballIcon } from './icon';
import { lazyMount } from '../lazy';
import { WINDOW } from './layout';

export const pinball: AppManifest = {
  id: 'pinball',
  name: 'Space Pinball',
  icon: pinballIcon,
  description: 'Deep-space pinball with ranks and missions',
  keywords: ['game', 'pinball', 'arcade', 'ball', 'space', 'flipper'],
  pinned: false,
  desktop: true,
  singleInstance: true,
  window: WINDOW,

  mount: lazyMount(() => import('./index')),
};
