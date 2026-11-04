
export type Level = 'beginner' | 'intermediate' | 'expert';
export const LEVELS: Record<Level, { cols: number; rows: number; mines: number; name: string }> = {
  beginner: { cols: 9, rows: 9, mines: 10, name: 'Beginner' },
  intermediate: { cols: 16, rows: 16, mines: 40, name: 'Intermediate' },
  expert: { cols: 30, rows: 16, mines: 99, name: 'Expert' },
};
export const PAD = 10;
export const HEAD = 40;
export const GAPY = 8;
export const FRAME_X = 18;
export const FRAME_Y = 40;

export function cellSize(l: Level): number {
  const { cols, rows } = LEVELS[l];
  const w = typeof window === 'undefined' ? 1600 : window.innerWidth;
  const hh = typeof window === 'undefined' ? 900 : window.innerHeight;
  return Math.max(16, Math.min(26, Math.floor((w - 80 - FRAME_X - PAD * 2) / cols), Math.floor((hh - 200 - FRAME_Y - PAD * 2 - HEAD - GAPY) / rows)));
}

