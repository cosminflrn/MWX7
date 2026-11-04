import type { AppManifest } from '../../core/types';
import { photosIcon } from './icon';
import { lazyMount } from '../lazy';

export const photos: AppManifest = {
  id: 'photos',
  name: 'Photo Viewer',
  icon: photosIcon,
  description: 'View pictures and play slideshows',
  keywords: ['pictures', 'images', 'photo', 'jpg', 'png', 'slideshow', 'gallery'],
  pinned: false,
  desktop: false,
  window: { width: 860, height: 600, minWidth: 520, minHeight: 360 },

  mount: lazyMount(() => import('./index')),
};
