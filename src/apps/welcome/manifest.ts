import type { AppManifest } from '../../core/types';
import { welcomeIcon } from './icon';
import { lazyMount } from '../lazy';

export const welcome: AppManifest = {
  id: 'welcome',
  name: 'Welcome to MWX 7',
  icon: welcomeIcon,
  description: 'A quick tour of what you can do',
  keywords: ['getting started', 'tour', 'intro', 'help'],
  singleInstance: true,
  window: { width: 680, height: 500, resizable: false },

  mount: lazyMount(() => import('./index')),
};
