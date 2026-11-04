import type { AppManifest } from '../../core/types';
import { solitaireIcon } from './icon';
import { lazyMount } from '../lazy';
import { FRAME_X, FRAME_Y, STATUS_H, VH, VW } from './layout';

export const solitaire: AppManifest = {
  id: 'solitaire',
  name: 'Solitaire',
  icon: solitaireIcon,
  description: 'Klondike card game',
  keywords: ['game', 'cards', 'klondike', 'patience'],
  pinned: false,
  singleInstance: true,
  window: { width: VW + FRAME_X, height: VH + STATUS_H + FRAME_Y, resizable: false },

  mount: lazyMount(() => import('./index')),
};
