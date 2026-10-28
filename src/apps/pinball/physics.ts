import { BALL_R, FLIP_REST, FLIP_UP, updateTip, type Flipper, type World } from './table';

export interface Ball {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  active: boolean;
  held: boolean;
  inPlay: boolean;
}

export const newBall = (): Ball => ({ x: 0, y: 0, vx: 0, vy: 0, r: BALL_R, active: false, held: false, inPlay: false });

export interface PhysEvents {
  bumper(i: number, speed: number): void;
  sling(i: number): void;
  target(i: number): void;
  wall(speed: number): void;
  flipper(speed: number): void;
  sensor(id: string): void;
}

const G = 980;
const MAX_V = 1700;
const FLIP_UP_W = 26;
const FLIP_DOWN_W = 12;

let nx = 0;
let ny = 0;

/**
 * Resolve overlap between the ball and a circle of radius `rad` at (cx, cy) whose surface moves at (svx, svy).
 * Returns the approach speed along the normal (>0 on impact), 0 for resting/separating contact, -1 for no contact.
 * The normal is left in module-level nx/ny.
 */
function resolve(b: Ball, cx: number, cy: number, rad: number, e: number, svx: number, svy: number): number {
  let dx = b.x - cx;
  let dy = b.y - cy;
  const min = b.r + rad;
  const d2 = dx * dx + dy * dy;
  if (d2 >= min * min) return -1;
  const d = Math.sqrt(d2);
  if (d < 1e-6) {
    dx = 0;
    dy = -1;
  } else {
    dx /= d;
    dy /= d;
  }
  nx = dx;
  ny = dy;
  b.x = cx + dx * min;
  b.y = cy + dy * min;
  const vn = (b.vx - svx) * dx + (b.vy - svy) * dy;
  if (vn >= 0) return 0;
  // Below a small approach speed treat it as resting contact so the ball rolls instead of buzzing.
  const ee = -vn < 45 ? 0 : e;
  const j = -(1 + ee) * vn;
  b.vx += j * dx;
  b.vy += j * dy;
  return -vn;
}

function closestOnSeg(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const abx = bx - ax;
  const aby = by - ay;
  const l2 = abx * abx + aby * aby;
  if (l2 === 0) return 0;
  const t = ((px - ax) * abx + (py - ay) * aby) / l2;
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

function stepFlipper(f: Flipper, dt: number): void {
  f.prevTipX = f.tipX;
  f.prevTipY = f.tipY;
  const target = f.pressed ? FLIP_UP : FLIP_REST;
  const w = f.pressed ? FLIP_UP_W : FLIP_DOWN_W;
  const d = target - f.theta;
  const step = w * dt;
  f.theta = Math.abs(d) <= step ? target : f.theta + Math.sign(d) * step;
  updateTip(f);
}

function collide(w: World, b: Ball, ev: PhysEvents): void {
  for (let pass = 0; pass < 2; pass++) {
    for (const s of w.segs) {
      if (!s.on) continue;
      if (s.oneWay) {
        const dx = s.bx - s.ax;
        const dy = s.by - s.ay;
        const l = Math.hypot(dx, dy);
        if (((b.x - s.ax) * -dy + (b.y - s.ay) * dx) / l < 0) continue;
      }
      const t = closestOnSeg(b.x, b.y, s.ax, s.ay, s.bx, s.by);
      const hit = resolve(b, s.ax + (s.bx - s.ax) * t, s.ay + (s.by - s.ay) * t, s.r, s.e, 0, 0);
      if (hit < 0) continue;
      if (s.kind === 'sling') {
        if (hit > 90) {
          // Kicker: ensure a hard outward snap.
          const out = b.vx * nx + b.vy * ny;
          if (out < 560) {
            b.vx += (560 - out) * nx;
            b.vy += (560 - out) * ny;
          }
          ev.sling(s.idx);
        }
      } else if (s.kind === 'target') {
        if (hit > 20) ev.target(s.idx);
      } else if (hit > 140) ev.wall(hit);
    }
    for (const c of w.circs) {
      const hit = resolve(b, c.x, c.y, c.r, c.e, 0, 0);
      if (hit > 60 && c.kind === 'bumper') {
        const out = b.vx * nx + b.vy * ny;
        if (out < 470) {
          b.vx += (470 - out) * nx;
          b.vy += (470 - out) * ny;
        }
        ev.bumper(c.idx, hit);
      }
    }
    for (const f of w.flippers) {
      const dt = 1 / 240;
      const t = closestOnSeg(b.x, b.y, f.px, f.py, f.tipX, f.tipY);
      const cx = f.px + (f.tipX - f.px) * t;
      const cy = f.py + (f.tipY - f.py) * t;
      // Surface velocity at the contact point, from the tip displacement of this step.
      const svx = ((f.tipX - f.prevTipX) * t) / dt;
      const svy = ((f.tipY - f.prevTipY) * t) / dt;
      const hit = resolve(b, cx, cy, f.r0 + (f.r1 - f.r0) * t, 0.32, svx, svy);
      if (hit > 80) ev.flipper(hit);
    }
  }
}

/** Advance the world by one fixed step (dt = 1/240 s). */
export function stepWorld(w: World, b: Ball, dt: number, ev: PhysEvents): void {
  for (const f of w.flippers) stepFlipper(f, dt);
  if (!b.active || b.held) return;

  // Sub-divide so the ball never moves more than ~2.5 px between collision tests (no tunnelling).
  const speed = Math.hypot(b.vx, b.vy);
  const n = Math.min(8, Math.max(1, Math.ceil((speed * dt) / 2.5)));
  const h = dt / n;
  for (let i = 0; i < n; i++) {
    b.vy += G * h;
    // Light rolling drag keeps long runs believable.
    const drag = 1 - 0.05 * h;
    b.vx *= drag;
    b.vy *= drag;
    const v = Math.hypot(b.vx, b.vy);
    if (v > MAX_V) {
      b.vx *= MAX_V / v;
      b.vy *= MAX_V / v;
    }
    b.x += b.vx * h;
    b.y += b.vy * h;
    collide(w, b, ev);
  }

  for (const s of w.sensors) {
    const inside = Math.hypot(b.x - s.x, b.y - s.y) < s.r + 2;
    if (inside && !s.inside) ev.sensor(s.id);
    s.inside = inside;
  }
}
