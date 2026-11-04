import type { AppManifest } from '../../core/types';
import { icons } from '../../assets/icons';
import { lazyMount } from '../lazy';

export const settingsApp: AppManifest = {
  id: 'settings',
  name: 'Settings',
  icon: icons.settings,
  description: 'Personalize MWX 7',
  keywords: ['preferences', 'control panel', 'wallpaper', 'personalize', 'system', 'sound', 'account'],
  pinned: true,
  singleInstance: true,
  window: { width: 700, height: 500, minWidth: 520, minHeight: 380 },

  mount: lazyMount(() => import('./index')),
};
