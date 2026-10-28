/**
 * Pure canvas helpers for Paint: pencil, brush styles, flood fill, shapes and bitmap transforms.
 * Nothing in here knows about the DOM UI, so the tools in index.ts stay thin.
 */

export type BrushKind = 'round' | 'cal1' | 'cal2' | 'air' | 'oil' | 'crayon';

export type ShapeKind =
  | 'line'
  | 'ellipse'
  | 'rect'
  | 'round'
  | 'triangle'
  | 'rtriangle'
  | 'diamond'
  | 'pentagon'
  | 'hexagon'
  | 'star'
  | 'arrow'
  | 'heart';

export const SHAPES: ShapeKind[] = [
  'line',
  'ellipse',
  'rect',
  'round',
  'triangle',
  'rtriangle',
  'diamond',
  'pentagon',
  'hexagon',
  'star',
  'arrow',
  'heart',
];

export const SIZES = [1, 3, 5, 8] as const;

/** Brushes read much heavier than outlines at the same "px" size, as in the original. */
export const brushDia = (size: number): number => (size === 1 ? 2 : size * 2);
/** The eraser is a square block; these sides feel right next to the 1/3/5/8 size steps. */
export const eraserSide = (size: number): number => ({ 1: 4, 3: 8, 5: 12, 8: 18 })[size] ?? size * 2 + 2;

const int = Math.round;

/* ---------------------------------------------------------------- pencil */

/** Bresenham with 1x1 rects keeps the pencil perfectly aliased, like a real pixel pencil. */
export function pencilLine(ctx: CanvasRenderingContext2D, ax: number, ay: number, bx: number, by: number, color: string): void {
  let x0 = Math.floor(ax);
  let y0 = Math.floor(ay);
  const x1 = Math.floor(bx);
  const y1 = Math.floor(by);
  const dx = Math.abs(x1 - x0);
  const dy = -Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  ctx.fillStyle = color;
  for (;;) {
    ctx.fillRect(x0, y0, 1, 1);
    if (x0 === x1 && y0 === y1) break;
    const e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x0 += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y0 += sy;
    }
  }
}

export function eraseLine(ctx: CanvasRenderingContext2D, ax: number, ay: number, bx: number, by: number, side: number, color: string): void {
  ctx.fillStyle = color;
  const steps = Math.max(Math.abs(bx - ax), Math.abs(by - ay), 1);
  const half = side / 2;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    ctx.fillRect(int(ax + (bx - ax) * t - half), int(ay + (by - ay) * t - half), side, side);
  }
}

/* ---------------------------------------------------------------- brushes */

/** Spray a burst of dots; held still, the caller keeps calling this on a timer. */
export function airPuff(ctx: CanvasRenderingContext2D, size: number, color: string, x: number, y: number): void {
  const r = size * 3 + 2;
  const n = Math.ceil(r * 1.4);
  ctx.fillStyle = color;
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2;
    // r * random² clusters the dots in the middle like a real spray nozzle
    const d = r * Math.random() ** 1.6;
    ctx.fillRect(Math.round(x + Math.cos(a) * d), Math.round(y + Math.sin(a) * d), 1, 1);
  }
}

function crayonStamp(ctx: CanvasRenderingContext2D, size: number, color: string, x: number, y: number): void {
  const r = brushDia(size) / 2 + 1;
  const n = Math.ceil(r * r * 1.1);
  ctx.fillStyle = color;
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2;
    const d = r * Math.sqrt(Math.random());
    ctx.globalAlpha = 0.45 + Math.random() * 0.5;
    ctx.fillRect(Math.round(x + Math.cos(a) * d), Math.round(y + Math.sin(a) * d), 1, 1);
  }
  ctx.globalAlpha = 1;
}

export function brushDot(ctx: CanvasRenderingContext2D, kind: BrushKind, size: number, color: string, x: number, y: number): void {
  if (kind === 'air') return airPuff(ctx, size, color, x, y);
  if (kind === 'crayon') return crayonStamp(ctx, size, color, x, y);
  brushSegment(ctx, kind, size, color, x, y, x + 0.01, y);
}

export function brushSegment(
  ctx: CanvasRenderingContext2D,
  kind: BrushKind,
  size: number,
  color: string,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
): void {
  const d = brushDia(size);
  const dist = Math.hypot(x1 - x0, y1 - y0);
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  switch (kind) {
    case 'round': {
      ctx.lineWidth = d;
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      ctx.stroke();
      // zero-length strokes draw nothing in some engines; the dot guarantees a click leaves a mark
      ctx.beginPath();
      ctx.arc(x1, y1, d / 2, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
    case 'cal1':
    case 'cal2': {
      // A flat nib held at 45°: the stroke is the parallelogram swept by the nib between two samples.
      const half = (d * 1.1 + 2) / 2;
      const k = half * Math.SQRT1_2;
      const nx = k;
      const ny = kind === 'cal1' ? -k : k;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x0 - nx, y0 - ny);
      ctx.lineTo(x0 + nx, y0 + ny);
      ctx.lineTo(x1 + nx, y1 + ny);
      ctx.lineTo(x1 - nx, y1 - ny);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      break;
    }
    case 'air': {
      const step = Math.max(2, size);
      const n = Math.max(1, Math.floor(dist / step));
      for (let i = 1; i <= n; i++) airPuff(ctx, size, color, x0 + ((x1 - x0) * i) / n, y0 + ((y1 - y0) * i) / n);
      break;
    }
    case 'crayon': {
      const n = Math.max(1, Math.floor(dist / 2));
      for (let i = 1; i <= n; i++) crayonStamp(ctx, size, color, x0 + ((x1 - x0) * i) / n, y0 + ((y1 - y0) * i) / n);
      break;
    }
    case 'oil': {
      // A fan of bristles along a 45° axis, each a little different in weight and opacity so the
      // stroke has streaks. Values are index-derived (not random) so consecutive segments join up.
      const n = Math.max(3, Math.round(d / 1.8));
      for (let i = 0; i < n; i++) {
        const t = i / (n - 1) - 0.5;
        const ox = t * d * 0.72;
        const oy = -t * d * 0.72;
        ctx.globalAlpha = 0.55 + 0.4 * (((i * 7) % 5) / 4);
        ctx.lineWidth = 1.3 + (i % 3) * 0.55;
        ctx.beginPath();
        ctx.moveTo(x0 + ox, y0 + oy);
        ctx.lineTo(x1 + ox, y1 + oy);
        ctx.stroke();
      }
      break;
    }
  }
  ctx.restore();
}

/* ---------------------------------------------------------------- colours */

export function parseHex(hex: string): [number, number, number] {
  const v = hex.replace('#', '');
  const n = parseInt(v.length === 3 ? v.replace(/./g, '$&$&') : v, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function toHex(r: number, g: number, b: number): string {
  return '#' + [r, g, b].map((c) => c.toString(16).padStart(2, '0')).join('');
}

/* ---------------------------------------------------------------- flood fill */

/**
 * Scanline flood fill. `tol` is the largest per-channel difference (0-255) from the clicked pixel that still
 * counts as "the same area"; a little tolerance swallows the anti-aliased fringe around brush strokes.
 */
export function floodFill(ctx: CanvasRenderingContext2D, sx: number, sy: number, color: string, tol: number): boolean {
  const { width: w, height: h } = ctx.canvas;
  sx = Math.floor(sx);
  sy = Math.floor(sy);
  if (sx < 0 || sy < 0 || sx >= w || sy >= h) return false;
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  const [fr, fg, fb] = parseHex(color);
  const s = (sy * w + sx) * 4;
  const tr = d[s]!;
  const tg = d[s + 1]!;
  const tb = d[s + 2]!;
  const ta = d[s + 3]!;
  if (tol === 0 && tr === fr && tg === fg && tb === fb && ta === 255) return false;

  const seen = new Uint8Array(w * h);
  const ok = (p: number): boolean => {
    if (seen[p]) return false;
    const i = p * 4;
    return (
      Math.abs(d[i]! - tr) <= tol &&
      Math.abs(d[i + 1]! - tg) <= tol &&
      Math.abs(d[i + 2]! - tb) <= tol &&
      Math.abs(d[i + 3]! - ta) <= tol
    );
  };
  const put = (p: number) => {
    seen[p] = 1;
    const i = p * 4;
    d[i] = fr;
    d[i + 1] = fg;
    d[i + 2] = fb;
    d[i + 3] = 255;
  };

  const stack: number[] = [sx, sy];
  while (stack.length) {
    const y = stack.pop()!;
    let x = stack.pop()!;
    while (x >= 0 && ok(y * w + x)) x--;
    x++;
    let up = false;
    let down = false;
    while (x < w && ok(y * w + x)) {
      put(y * w + x);
      if (y > 0) {
        const o = ok((y - 1) * w + x);
        if (o && !up) stack.push(x, y - 1);
        up = o;
      }
      if (y < h - 1) {
        const o = ok((y + 1) * w + x);
        if (o && !down) stack.push(x, y + 1);
        down = o;
      }
      x++;
    }
  }
  ctx.putImageData(img, 0, 0);
  return true;
}

/* ---------------------------------------------------------------- shapes */

/** Unit-square outlines for the polygon shapes (also used to draw the gallery icons). */
export const POLY: Partial<Record<ShapeKind, [number, number][]>> = {
  triangle: [
    [0.5, 0],
    [1, 1],
    [0, 1],
  ],
  rtriangle: [
    [0, 0],
    [1, 1],
    [0, 1],
  ],
  diamond: [
    [0.5, 0],
    [1, 0.5],
    [0.5, 1],
    [0, 0.5],
  ],
  pentagon: [
    [0.5, 0],
    [1, 0.38],
    [0.81, 1],
    [0.19, 1],
    [0, 0.38],
  ],
  hexagon: [
    [0.25, 0],
    [0.75, 0],
    [1, 0.5],
    [0.75, 1],
    [0.25, 1],
    [0, 0.5],
  ],
  arrow: [
    [0, 0.3],
    [0.58, 0.3],
    [0.58, 0],
    [1, 0.5],
    [0.58, 1],
    [0.58, 0.7],
    [0, 0.7],
  ],
  star: Array.from({ length: 10 }, (_, i) => {
    const a = -Math.PI / 2 + (i * Math.PI) / 5;
    const r = i % 2 ? 0.2 : 0.5;
    // a five-point star is 0.951 wide and 0.905 tall inside its circumscribed circle
    return [0.5 + (r * Math.cos(a)) / 0.951, (r * Math.sin(a) + 0.5) / 0.905] as [number, number];
  }),
};

export const HEART_PATH =
  'M.5 1C.05.62 0 .32 0 .25 0 .1.12 0 .27 0c.11 0 .19.06.23.16C.54.06.62 0 .73 0 .88 0 1 .1 1 .25 1 .32.95.62.5 1Z';

export interface ShapeStyle {
  stroke: string | null;
  fill: string | null;
  width: number;
}

/** Applies Shift: lines snap to 45° steps, everything else becomes a square / circle. */
export function constrainPoint(kind: ShapeKind, x0: number, y0: number, x1: number, y1: number): [number, number] {
  const dx = x1 - x0;
  const dy = y1 - y0;
  if (kind === 'line') {
    const step = Math.PI / 4;
    const a = Math.round(Math.atan2(dy, dx) / step) * step;
    const len = Math.hypot(dx, dy);
    return [x0 + Math.cos(a) * len, y0 + Math.sin(a) * len];
  }
  const s = Math.max(Math.abs(dx), Math.abs(dy));
  return [x0 + Math.sign(dx || 1) * s, y0 + Math.sign(dy || 1) * s];
}

export function drawShape(
  ctx: CanvasRenderingContext2D,
  kind: ShapeKind,
  ax: number,
  ay: number,
  bx: number,
  by: number,
  st: ShapeStyle,
): void {
  const x0 = int(ax);
  const y0 = int(ay);
  const x1 = int(bx);
  const y1 = int(by);
  ctx.save();
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.lineWidth = st.width;
  ctx.strokeStyle = st.stroke ?? '#000';

  if (kind === 'line') {
    if (st.stroke) {
      ctx.beginPath();
      ctx.moveTo(x0 + 0.5, y0 + 0.5);
      ctx.lineTo(x1 + 0.5, y1 + 0.5);
      ctx.stroke();
    }
    ctx.restore();
    return;
  }

  // The stroke is centred on the path, so inset by half its width to keep the shape inside the drag box.
  const ins = st.stroke ? st.width / 2 : 0;
  let l = Math.min(x0, x1) + ins;
  let t = Math.min(y0, y1) + ins;
  let r = Math.max(x0, x1) + 1 - ins;
  let b = Math.max(y0, y1) + 1 - ins;
  if (r < l) l = r = (l + r) / 2;
  if (b < t) t = b = (t + b) / 2;
  const w = r - l;
  const h = b - t;

  ctx.beginPath();
  if (kind === 'rect') ctx.rect(l, t, w, h);
  else if (kind === 'ellipse') ctx.ellipse(l + w / 2, t + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
  else if (kind === 'round') {
    const rad = Math.min(w, h, 80) * 0.25;
    ctx.moveTo(l + rad, t);
    ctx.arcTo(r, t, r, b, rad);
    ctx.arcTo(r, b, l, b, rad);
    ctx.arcTo(l, b, l, t, rad);
    ctx.arcTo(l, t, r, t, rad);
    ctx.closePath();
  } else if (kind === 'heart') {
    heartPath(ctx, l, t, w, h);
  } else {
    const pts = POLY[kind]!;
    pts.forEach(([px, py], i) => (i ? ctx.lineTo(l + px * w, t + py * h) : ctx.moveTo(l + px * w, t + py * h)));
    ctx.closePath();
  }
  if (st.fill) {
    ctx.fillStyle = st.fill;
    ctx.fill();
  }
  if (st.stroke) ctx.stroke();
  ctx.restore();
}

function heartPath(ctx: CanvasRenderingContext2D, l: number, t: number, w: number, h: number): void {
  const X = (v: number) => l + v * w;
  const Y = (v: number) => t + v * h;
  ctx.moveTo(X(0.5), Y(1));
  ctx.bezierCurveTo(X(0.05), Y(0.62), X(0), Y(0.32), X(0), Y(0.25));
  ctx.bezierCurveTo(X(0), Y(0.1), X(0.12), Y(0), X(0.27), Y(0));
  ctx.bezierCurveTo(X(0.38), Y(0), X(0.46), Y(0.06), X(0.5), Y(0.16));
  ctx.bezierCurveTo(X(0.54), Y(0.06), X(0.62), Y(0), X(0.73), Y(0));
  ctx.bezierCurveTo(X(0.88), Y(0), X(1), Y(0.1), X(1), Y(0.25));
  ctx.bezierCurveTo(X(1), Y(0.32), X(0.95), Y(0.62), X(0.5), Y(1));
  ctx.closePath();
}

/* ---------------------------------------------------------------- bitmap transforms */

export type Transform = 'rotR' | 'rotL' | 'rot180' | 'flipH' | 'flipV';

export function makeCanvas(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = Math.max(1, w);
  c.height = Math.max(1, h);
  return c;
}

export function transformed(src: HTMLCanvasElement, how: Transform): HTMLCanvasElement {
  const { width: w, height: h } = src;
  const swap = how === 'rotR' || how === 'rotL';
  const out = makeCanvas(swap ? h : w, swap ? w : h);
  const c = out.getContext('2d')!;
  switch (how) {
    case 'rotR':
      c.setTransform(0, 1, -1, 0, h, 0);
      break;
    case 'rotL':
      c.setTransform(0, -1, 1, 0, 0, w);
      break;
    case 'rot180':
      c.setTransform(-1, 0, 0, -1, w, h);
      break;
    case 'flipH':
      c.setTransform(-1, 0, 0, 1, w, 0);
      break;
    case 'flipV':
      c.setTransform(1, 0, 0, -1, 0, h);
      break;
  }
  c.drawImage(src, 0, 0);
  return out;
}

export function scaled(src: HTMLCanvasElement, w: number, h: number): HTMLCanvasElement {
  const out = makeCanvas(w, h);
  const c = out.getContext('2d')!;
  c.imageSmoothingEnabled = true;
  c.imageSmoothingQuality = 'high';
  c.drawImage(src, 0, 0, out.width, out.height);
  return out;
}

export function invertColors(ctx: CanvasRenderingContext2D): void {
  const { width: w, height: h } = ctx.canvas;
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    d[i] = 255 - d[i]!;
    d[i + 1] = 255 - d[i + 1]!;
    d[i + 2] = 255 - d[i + 2]!;
  }
  ctx.putImageData(img, 0, 0);
}
