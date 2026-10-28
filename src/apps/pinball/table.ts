/** Table layout: all geometry is in table units (a 420 x 740 playfield, y grows downwards). */

export const W = 420;
export const H = 740;
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

export const LANE_X = [140, 194, 248];
export const BUMPERS = [
  { x: 138, y: 252 },
  { x: 232, y: 212 },
  { x: 296, y: 282 },
];
export const BUMPER_R = 21;
export const SAUCER = { x: 312, y: 402, r: 12 };
export const PLUNGER_X = 394;
export const PLUNGER_REST_Y = 668;
export const PLUNGER_TRAVEL = 34;
export const TARGET_Y = [330, 362, 394, 426];

export const INSERTS: Insert[] = [
  ...LANE_X.map((x, i): Insert => ({ key: `lane${i}`, x, y: 90, r: 7, color: NEON.cyan, shape: 'dot' })),
  { key: 'inL', x: 50, y: 536, r: 8, color: NEON.lime, shape: 'arrow', rot: 0 },
  { key: 'inR', x: 338, y: 536, r: 8, color: NEON.lime, shape: 'arrow', rot: 0 },
  { key: 'outL', x: 23, y: 552, r: 6, color: NEON.amber, shape: 'diamond' },
  { key: 'outR', x: 365, y: 552, r: 6, color: NEON.amber, shape: 'diamond' },
  { key: 'orbA', x: 342, y: 90, r: 8, color: NEON.magenta, shape: 'chevron', rot: 2.5 },
  { key: 'orbB', x: 78, y: 88, r: 8, color: NEON.magenta, shape: 'chevron', rot: 0.6 },
  { key: 'save', x: 194, y: 604, r: 8, color: NEON.ice, shape: 'dot' },
  { key: 'mission', x: 194, y: 372, r: 15, color: NEON.amber, shape: 'star' },
  ...[0, 1, 2, 3, 4].map((i): Insert => ({
    key: `rank${i}`,
    x: 122 + i * 36,
    y: 470 + Math.abs(i - 2) * 9,
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
  const N = 30;
  for (let i = 0; i < N; i++) {
    const a0 = Math.PI + (Math.PI * i) / N;
    const a1 = Math.PI + (Math.PI * (i + 1)) / N;
    segs.push(seg(210 + 200 * Math.cos(a0), 210 + 200 * Math.sin(a0), 210 + 200 * Math.cos(a1), 210 + 200 * Math.sin(a1), 'arch', 3, 0.12));
  }
  segs.push(seg(10, 210, 10, 728, 'wall', 3));
  segs.push(seg(410, 210, 410, 728, 'wall', 3));
  segs.push(seg(378, 200, 378, 706, 'wall', 3)); // launch lane divider
  // One-way gate: lets the plunged ball out of the lane, never back in.
  segs.push(seg(378, 92, 378, 200, 'gate', 1.5, 0.3, 0, true));

  // Rollover lane dividers
  for (const x of [113, 167, 221, 275]) segs.push(seg(x, 70, x, 114, 'divider', 2.5, 0.4));

  // Inlane / outlane guides (mirrored about x = 194)
  for (const m of [0, 1]) {
    const X = (x: number) => (m ? 388 - x : x);
    segs.push(seg(X(36), 520, X(36), 728, 'guide', 3));
    segs.push(seg(X(36), 590, X(122), 640, 'guide', 3, 0.3));
    // slingshot: kicker face + body
    segs.push(seg(X(64), 492, X(112), 592, 'sling', 3, 0.5, m));
    segs.push(seg(X(64), 492, X(64), 572, 'slingBody', 2.5, 0.3));
    segs.push(seg(X(64), 572, X(112), 592, 'slingBody', 2.5, 0.3));
  }

  const targets = TARGET_Y.map((y, i) => seg(19, y - 12, 19, y + 12, 'target', 3.5, 0.3, i));
  segs.push(...targets);

  const plunger = seg(380, PLUNGER_REST_Y, 408, PLUNGER_REST_Y, 'plunger', 2, 0.1);
  segs.push(plunger);

  const circs: Circ[] = BUMPERS.map((b, i) => ({ x: b.x, y: b.y, r: BUMPER_R, e: 0.9, kind: 'bumper' as const, idx: i }));

  const s = (id: string, x: number, y: number, r: number): Sensor => ({ id, x, y, r, inside: false });
  const sensors: Sensor[] = [
    ...LANE_X.map((x, i) => s(`lane${i}`, x, 98, 12)),
    s('inL', 50, 546, 11),
    s('inR', 338, 546, 11),
    s('outL', 23, 562, 9),
    s('outR', 365, 562, 9),
    s('orbA', 342, 96, 12),
    s('orbB', 78, 94, 12),
    s('saucer', SAUCER.x, SAUCER.y, 9),
  ];

  const mk = (side: 'L' | 'R', px: number): Flipper => ({
    side,
    px,
    py: 640,
    len: 64,
    r0: 6.5,
    r1: 3.8,
    theta: FLIP_REST,
    pressed: false,
    tipX: 0,
    tipY: 0,
    prevTipX: 0,
    prevTipY: 0,
  });
  const flippers: [Flipper, Flipper] = [mk('L', 122), mk('R', 266)];
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
