import type { AppManifest } from '../../core/types';
import { icons } from '../../assets/icons';
import { lazyMount } from '../lazy';

export const explorer: AppManifest = {
  id: 'explorer',
  name: 'My Computer',
  icon: icons.explorer,
  description: 'Browse files and folders',
  keywords: ['files', 'folders', 'file manager', 'documents', 'finder', 'computer', 'explorer'],
  pinned: true,
  desktop: true,
  window: { width: 920, height: 600, minWidth: 520, minHeight: 360 },

  mount: lazyMount(() => import('./index')),
};
