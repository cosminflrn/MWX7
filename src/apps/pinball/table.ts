/** Table layout: all geometry is in table units (a 580 x 740 playfield, y grows downwards). */

import { H, W } from './layout';
export { H, W };
/** Left wall x, right edge of the playfield (the launch-lane divider) and the outer right wall. */
export const WALL_L = 10;
export const LANE_DIV = 538;
export const WALL_R = 570;
/** Horizontal centre of the playfield proper (left wall .. lane divider). Mirror x about it with `MIRROR - x`. */
export const CX = (WALL_L + LANE_DIV) / 2;
export const MIRROR = WALL_L + LANE_DIV;
/** The top arch is an ellipse spanning the whole width (playfield + launch lane). */
export const ARCH = { cx: (WALL_L + WALL_R) / 2, cy: 210, rx: (WALL_R - WALL_L) / 2, ry: 200 };
export const BALL_R = 7.5;

export type SegKind = 'wall' | 'arch' | 'guide' | 'sling' | 'slingBody' | 'target' | 'plunger' | 'divider' | 'gate';

export interface Seg {
  ax: number;
  ay: number;
  bx: number;
  by: number;
  /** half thickness (capsule radius) */
  r: number;
  e: number;
  kind: SegKind;
  idx: number;
  /** one-way: only collides when the ball is on the left-hand normal side */
  oneWay: boolean;
  on: boolean;
}

export interface Circ {
  x: number;
  y: number;
  r: number;
  e: number;
  kind: 'bumper' | 'post';
  idx: number;
}

export interface Sensor {
  id: string;
  x: number;
  y: number;
  r: number;
  inside: boolean;
}

export interface Flipper {
  side: 'L' | 'R';
  px: number;
  py: number;
  len: number;
  r0: number;
  r1: number;
  theta: number;
  pressed: boolean;
  tipX: number;
  tipY: number;
  prevTipX: number;
  prevTipY: number;
}

export const FLIP_LEN = 82;
export const FLIP_PX = 187; // pivot distance from the left wall side; right pivot mirrors it
export const FLIP_REST = 0.5236; // +30deg (tip down)
export const FLIP_UP = -0.46; // about -26deg (tip raised)

export interface Insert {
  key: string;
  x: number;
  y: number;
  r: number;
  color: string;
  shape: 'dot' | 'arrow' | 'diamond' | 'star' | 'chevron';
  rot?: number;
}

export const NEON = {
  cyan: '#3ff3ff',
  magenta: '#ff3df0',
  amber: '#ffb03a',
  lime: '#8aff6b',
  violet: '#9a6cff',
  red: '#ff4a5e',
  ice: '#bfe4ff',
};

export const LANE_X = [CX - 66, CX, CX + 66];
export const BUMPERS = [
  { x: CX - 80, y: 246 },
  { x: CX, y: 186 },
  { x: CX + 80, y: 246 },
  { x: CX, y: 304 },
];
export const BUMPER_R = 21;
export const SAUCER = { x: 462, y: 402, r: 12 };
export const PLUNGER_X = (LANE_DIV + WALL_R) / 2;
export const PLUNGER_REST_Y = 668;
export const PLUNGER_TRAVEL = 34;
export const TARGET_Y = [330, 362, 394, 426];

export const INSERTS: Insert[] = [
  ...LANE_X.map((x, i): Insert => ({ key: `lane${i}`, x, y: 90, r: 7, color: NEON.cyan, shape: 'dot' })),
  { key: 'inL', x: 66, y: 540, r: 8, color: NEON.lime, shape: 'arrow', rot: 0 },
  { key: 'inR', x: MIRROR - 66, y: 540, r: 8, color: NEON.lime, shape: 'arrow', rot: 0 },
  { key: 'outL', x: 27, y: 552, r: 6, color: NEON.amber, shape: 'diamond' },
  { key: 'outR', x: MIRROR - 27, y: 552, r: 6, color: NEON.amber, shape: 'diamond' },
  { key: 'orbA', x: MIRROR - 84, y: 92, r: 8, color: NEON.magenta, shape: 'chevron', rot: 2.5 },
  { key: 'orbB', x: 84, y: 92, r: 8, color: NEON.magenta, shape: 'chevron', rot: 0.6 },
  { key: 'save', x: CX, y: 604, r: 8, color: NEON.ice, shape: 'dot' },
  { key: 'mission', x: CX, y: 392, r: 15, color: NEON.amber, shape: 'star' },
  ...[0, 1, 2, 3, 4].map((i): Insert => ({
    key: `rank${i}`,
    x: CX - 72 + i * 36,
    y: 476 + Math.abs(i - 2) * 9,
    r: 6,
    color: NEON.violet,
    shape: 'diamond',
  })),
];

export interface World {
  segs: Seg[];
  circs: Circ[];
  sensors: Sensor[];
  flippers: [Flipper, Flipper];
  plunger: Seg;
  targets: Seg[];
}

function seg(ax: number, ay: number, bx: number, by: number, kind: SegKind, r = 2.5, e = 0.45, idx = 0, oneWay = false): Seg {
  return { ax, ay, bx, by, r, e, kind, idx, oneWay, on: true };
}

export function createWorld(): World {
  const segs: Seg[] = [];

  // Top arch (the orbit rail): low restitution so the ball slides around it instead of pinging back.
  const N = 44;
  for (let i = 0; i < N; i++) {
    const a0 = Math.PI + (Math.PI * i) / N;
    const a1 = Math.PI + (Math.PI * (i + 1)) / N;
    segs.push(
      seg(
        ARCH.cx + ARCH.rx * Math.cos(a0),
        ARCH.cy + ARCH.ry * Math.sin(a0),
        ARCH.cx + ARCH.rx * Math.cos(a1),
        ARCH.cy + ARCH.ry * Math.sin(a1),
        'arch',
        3,
        0.12
      )
    );
  }
  segs.push(seg(WALL_L, 210, WALL_L, 728, 'wall', 3));
  segs.push(seg(WALL_R, 210, WALL_R, 728, 'wall', 3));
  segs.push(seg(LANE_DIV, 200, LANE_DIV, 706, 'wall', 3)); // launch lane divider
  // One-way gate: lets the plunged ball out of the lane, never back in.
  segs.push(seg(LANE_DIV, 110, LANE_DIV, 200, 'gate', 1.5, 0.3, 0, true));

  // Rollover lane dividers
  for (const x of [CX - 99, CX - 33, CX + 33, CX + 99]) segs.push(seg(x, 70, x, 114, 'divider', 2.5, 0.4));

  // Inlane / outlane guides (mirrored about the playfield centre)
  for (const m of [0, 1]) {
    const X = (x: number) => (m ? MIRROR - x : x);
    segs.push(seg(X(44), 520, X(44), 728, 'guide', 3));
    segs.push(seg(X(44), 566, X(FLIP_PX), 640, 'guide', 3, 0.3));
    // slingshot: kicker face + body
    segs.push(seg(X(88), 490, X(142), 578, 'sling', 3, 0.5, m));
    segs.push(seg(X(88), 490, X(88), 562, 'slingBody', 2.5, 0.3));
    segs.push(seg(X(88), 562, X(142), 578, 'slingBody', 2.5, 0.3));
  }

  const targets = TARGET_Y.map((y, i) => seg(19, y - 12, 19, y + 12, 'target', 3.5, 0.3, i));
  segs.push(...targets);

  const plunger = seg(LANE_DIV + 2, PLUNGER_REST_Y, WALL_R - 2, PLUNGER_REST_Y, 'plunger', 2, 0.1);
  segs.push(plunger);

  const circs: Circ[] = BUMPERS.map((b, i) => ({ x: b.x, y: b.y, r: BUMPER_R, e: 0.9, kind: 'bumper' as const, idx: i }));

  const s = (id: string, x: number, y: number, r: number): Sensor => ({ id, x, y, r, inside: false });
  const sensors: Sensor[] = [
    ...LANE_X.map((x, i) => s(`lane${i}`, x, 98, 12)),
    s('inL', 66, 550, 11),
    s('inR', MIRROR - 66, 550, 11),
    s('outL', 27, 562, 9),
    s('outR', MIRROR - 27, 562, 9),
    s('orbA', MIRROR - 84, 96, 12),
    s('orbB', 84, 96, 12),
    s('saucer', SAUCER.x, SAUCER.y, 9),
  ];

  const mk = (side: 'L' | 'R', px: number): Flipper => ({
    side,
    px,
    py: 640,
    len: FLIP_LEN,
    r0: 6.5,
    r1: 3.8,
    theta: FLIP_REST,
    pressed: false,
    tipX: 0,
    tipY: 0,
    prevTipX: 0,
    prevTipY: 0,
  });
  const flippers: [Flipper, Flipper] = [mk('L', FLIP_PX), mk('R', MIRROR - FLIP_PX)];
  for (const f of flippers) {
    updateTip(f);
    f.prevTipX = f.tipX;
    f.prevTipY = f.tipY;
  }
  return { segs, circs, sensors, flippers, plunger, targets };
}

export function updateTip(f: Flipper): void {
  const dir = f.side === 'L' ? 1 : -1;
  f.tipX = f.px + dir * f.len * Math.cos(f.theta);
  f.tipY = f.py + f.len * Math.sin(f.theta);
}
