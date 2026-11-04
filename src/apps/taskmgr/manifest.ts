import type { AppManifest } from '../../core/types';
import { taskmgrIcon } from './icon';
import { lazyMount } from '../lazy';

export const taskmgr: AppManifest = {
  id: 'taskmgr',
  name: 'Task Manager',
  icon: taskmgrIcon,
  description: 'See what is running and how the system is doing',
  keywords: ['processes', 'performance', 'cpu', 'memory', 'end task', 'monitor'],
  pinned: false,
  desktop: false,
  singleInstance: true,
  window: { width: 480, height: 520, minWidth: 400, minHeight: 420 },

  mount: lazyMount(() => import('./index')),
};
