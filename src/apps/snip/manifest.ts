import type { AppManifest } from '../../core/types';
import { png } from '../../assets/icons';
import { lazyMount } from '../lazy';

export const snip: AppManifest = {
  id: 'snip',
  name: 'Snipping Tool',
  icon: png('snip'),
  description: 'Capture a part of the screen',
  keywords: ['screenshot', 'capture', 'screen', 'crop', 'snip'],
  singleInstance: true,
  window: { width: 560, height: 420, minWidth: 380, minHeight: 280 },

  mount: lazyMount(() => import('./index')),
};
