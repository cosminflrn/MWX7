import type { AppManifest } from '../../core/types';
import { icons } from '../../assets/icons';
import { lazyMount } from '../lazy';

export const notepad: AppManifest = {
  id: 'notepad',
  name: 'Notepad',
  icon: icons.notepad,
  description: 'Write and save plain text',
  keywords: ['text', 'editor', 'write', 'note', 'txt'],
  pinned: true,
  desktop: true,
  window: { width: 620, height: 440, minWidth: 320, minHeight: 200 },

  mount: lazyMount(() => import('./index')),
};
