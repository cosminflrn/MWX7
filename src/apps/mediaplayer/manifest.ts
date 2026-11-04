import type { AppManifest } from '../../core/types';
import { mediaPlayerIcon } from './icon';
import { lazyMount } from '../lazy';

export const mediaplayer: AppManifest = {
  id: 'mediaplayer',
  name: 'Media Player',
  icon: mediaPlayerIcon,
  description: 'Play music from your Music folder',
  keywords: ['music', 'audio', 'player', 'mp3', 'ogg', 'wav', 'song'],
  pinned: true,
  desktop: false,
  window: { width: 860, height: 540, minWidth: 560, minHeight: 380 },

  mount: lazyMount(() => import('./index')),
};
