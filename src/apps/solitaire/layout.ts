export const SW = 602;
export const SH = 560;
export const FRAME_X = 18;
export const FRAME_Y = 40;
export const STATUS_H = 24;

function fit(): number {
  const availH = (typeof window === 'undefined' ? 900 : window.innerHeight) - 30 - 70 - 24;
  const availW = (typeof window === 'undefined' ? 1600 : window.innerWidth) - 40;
  return Math.min(1, (availH - FRAME_Y - STATUS_H) / SH, (availW - FRAME_X) / SW);
}
export const SCALE = fit();
export const VW = Math.floor(SW * SCALE);
export const VH = Math.floor(SH * SCALE);
