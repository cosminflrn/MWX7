import { icons } from '../assets/icons';
import { settings } from '../core/settings';
import { h } from '../ui/dom';

/**
 * Account pictures — real photographs in the spirit of the classic XP / 7
 * account pictures (see public/media/CREDITS.md for sources and licenses).
 */
const FILES: string[] = [
  '01-flower.jpg',
  '02-goldfish.jpg',
  '03-guitar.jpg',
  '04-chess.jpg',
  '05-soccer.jpg',
  '06-dog.jpg',
  '07-cat.jpg',
  '08-butterfly.jpg',
  '09-airplane.jpg',
  '10-snowboard.jpg',
  '11-beach.jpg',
  '12-horse.jpg',
];

const BASE = import.meta.env.BASE_URL;

export const AVATARS: string[] = FILES.map((f) => `${BASE}media/avatars/${f}`);

/** Markup for the current user's picture (falls back to the silhouette). */
export function avatarHtml(url = settings.get().avatar): string {
  return url ? `<img class="icon-img avatar-img" alt="" draggable="false" src="${url}">` : icons.avatar;
}

/** A grid of pictures; calls `onPick` with the chosen URL. */
export function avatarPicker(selected: string, onPick: (url: string) => void): HTMLElement {
  const grid = h('div', { class: 'avatar-grid', role: 'listbox' });
  const options = AVATARS.length ? AVATARS : [''];
  for (const url of options) {
    const btn = h('button', {
      class: `avatar-opt${url === selected ? ' sel' : ''}`,
      role: 'option',
      html: avatarHtml(url),
      onclick: () => {
        grid.querySelectorAll('.sel').forEach((n) => n.classList.remove('sel'));
        btn.classList.add('sel');
        onPick(url);
      },
    });
    grid.append(btn);
  }
  return grid;
}
