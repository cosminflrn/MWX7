export const W = 580;
export const H = 740;
export const PANEL_W = 232;
/** Chrome around the window body: title bar (30) on top, 8px glass frame on the other three sides, plus a 1px border all round. */
const FRAME_X = 18;
const FRAME_Y = 40;
const MENUBAR_H = 30;
const DOCK_RESERVE = 70;

/**
 * Fixed-size window that hugs the content: table + score panel at 1:1, scaled down uniformly when the screen
 * cannot hold it (the OS would otherwise clamp one axis and leave gaps).
 */
function fitWindow(): { width: number; height: number; resizable: false } {
  const cw = W + PANEL_W;
  const availH = (typeof window === 'undefined' ? 900 : window.innerHeight) - MENUBAR_H - DOCK_RESERVE - 24;
  const availW = (typeof window === 'undefined' ? 1600 : window.innerWidth) - 40;
  const s = Math.min(1, (availH - FRAME_Y) / H, (availW - FRAME_X) / cw);
  return { width: Math.floor(cw * s) + FRAME_X, height: Math.floor(H * s) + FRAME_Y, resizable: false };
}
export const WINDOW = fitWindow();
