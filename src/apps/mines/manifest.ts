import type { AppManifest } from '../../core/types';
import { lazyMount } from '../lazy';
import { minesIcon } from './icon';
import { cellSize, FRAME_X, FRAME_Y, GAPY, HEAD, LEVELS, PAD, type Level } from './layout';

function make(level: Level): AppManifest {
  const l = LEVELS[level];
  const c = cellSize(level);
  return {
  id: level === 'beginner' ? 'mines' : `mines-${level}`,
  name: 'Mines',
  icon: minesIcon,
  description: 'Clear the field without hitting a mine',
  keywords: ['game', 'minesweeper', 'bombs', 'puzzle'],
  pinned: false,
  hidden: level !== 'beginner',
  singleInstance: false,
  window: { width: l.cols * c + PAD * 2 + FRAME_X, height: l.rows * c + PAD * 2 + HEAD + GAPY + FRAME_Y, resizable: false },

    mount: lazyMount(() => import('./index').then((m) => ({ impl: m.impl(level) }))),
  };
}

export const mines = make('beginner');
export const minesIntermediate = make('intermediate');
export const minesExpert = make('expert');
