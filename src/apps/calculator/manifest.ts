import type { AppManifest } from '../../core/types';
import { icons } from '../../assets/icons';
import { lazyMount } from '../lazy';

export const calculator: AppManifest = {
  id: 'calculator',
  name: 'Calculator',
  icon: icons.calculator,
  description: 'Quick math',
  keywords: ['calc', 'math', 'numbers'],
  pinned: true,
  desktop: true,
  singleInstance: true,
  window: { width: 248, height: 352, resizable: false },

  mount: lazyMount(() => import('./index')),
};
