import type { AppManifest } from '../../core/types';
import { stickyIcon } from './icon';
import { lazyMount } from '../lazy';

export const stickynotes: AppManifest = {
  id: 'stickynotes',
  name: 'Sticky Notes',
  icon: stickyIcon,
  description: 'Jot down quick reminders',
  keywords: ['note', 'memo', 'reminder', 'post-it', 'sticky'],
  pinned: false,
  desktop: false,
  window: { width: 240, height: 240, minWidth: 170, minHeight: 130 },

  mount: lazyMount(() => import('./index')),
};
