import type { Sfx } from './audio';
import { newBall, stepWorld, type Ball, type PhysEvents } from './physics';
import {
  BALL_R,
  H,
  NEON,
  PLUNGER_REST_Y,
  PLUNGER_TRAVEL,
  PLUNGER_X,
  SAUCER,
  createWorld,
  type World,
} from './table';

export type Phase = 'ready' | 'play' | 'over';

export const RANKS = [
  { name: 'Cadet', at: 0 },
  { name: 'Pilot', at: 1 },
  { name: 'Navigator', at: 3 },
  { name: 'Commander', at: 5 },
  { name: 'Admiral', at: 8 },
];

interface Mission {
  id: string;
  text: string;
  goal: (done: number) => number;
}

const MISSIONS: Mission[] = [
  { id: 'lanes', text: 'Light all three nav lanes', goal: () => 1 },
  { id: 'targets', text: 'Break the shield bank', goal: () => 1 },
  { id: 'bumpers', text: 'Overload the reactors', goal: (d) => 15 + 5 * Math.floor(d / 5) },
  { id: 'orbit', text: 'Fly the orbit loop', goal: (d) => 2 + Math.floor(d / 5) },
  { id: 'worm', text: 'Enter the wormhole', goal: () => 1 },
];

export interface Spark {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  max: number;
  color: string;
}

export interface Banner {
  text: string;
  sub: string;
  color: string;
  t: number;
  dur: number;
}

export const BALL_SAVE_SECONDS = 8;

export class Game {
  world: World = createWorld();
  ball: Ball = newBall();
  phase: Phase = 'ready';
  score = 0;
  high = 0;
  ballNo = 1;
  readonly ballsMax = 3;
  bonus = 0;
  mult = 1;
  lanes = [false, false, false];
  inLit = [false, false];
  outLit = [false, false];
  missionsDone = 0;
  missionProg = 0;
  bumperHits = 0;
  saveT = 0;
  pull = 0;
  charging = false;
  plungerKick = 0;
  time = 0;
  flash: Record<string, number> = {};
  sparks: Spark[] = [];
  banner: Banner | null = null;
  ticker = 'Hold UP to charge the plunger';
  trail: { x: number; y: number }[] = [];
  /** Set by index.ts to persist a new high score. */
  onHigh: (high: number) => void = () => undefined;

  private serveDelay = 0;
  private saucerT = 0;
  private targetResetT = 0;
  private lastOrb: { id: string; t: number } | null = null;
  private stillT = 0;
  private chargeTick = 0;
  private highDirty = false;
  private grantSave = true;

  constructor(private sfx: Sfx) {
    this.serve();
  }

  get rankIndex(): number {
    let r = 0;
    RANKS.forEach((k, i) => {
      if (this.missionsDone >= k.at) r = i;
    });
    return r;
  }
  get currentMission(): { text: string; prog: number; goal: number } {
    const m = MISSIONS[this.missionsDone % MISSIONS.length];
    return { text: m.text, prog: this.missionProg, goal: m.goal(this.missionsDone) };
  }

  newGame(): void {
    this.score = 0;
    this.ballNo = 1;
    this.bonus = 0;
    this.mult = 1;
    this.lanes = [false, false, false];
    this.inLit = [false, false];
    this.outLit = [false, false];
    this.missionsDone = 0;
    this.missionProg = 0;
    this.bumperHits = 0;
    this.saveT = 0;
    this.grantSave = true;
    this.sparks.length = 0;
    this.banner = null;
    for (const t of this.world.targets) t.on = true;
    this.phase = 'ready';
    this.serve();
    this.say('NEW GAME', 'Rank: Cadet', NEON.cyan);
  }

  private serve(): void {
    const b = this.ball;
    b.x = PLUNGER_X;
    b.y = PLUNGER_REST_Y - 2 - BALL_R;
    b.vx = 0;
    b.vy = 0;
    b.active = true;
    b.held = false;
    b.inPlay = false;
    this.pull = 0;
    this.charging = false;
    this.phase = this.phase === 'over' ? 'over' : 'ready';
    this.trail.length = 0;
    this.world.plunger.ay = this.world.plunger.by = PLUNGER_REST_Y;
    this.ticker = 'Hold UP to charge the plunger';
  }

  say(text: string, sub = '', color: string = NEON.cyan, dur = 1.8): void {
    this.banner = { text, sub, color, t: 0, dur };
    this.ticker = sub ? `${text} - ${sub}` : text;
  }

  private add(n: number): void {
    if (this.phase === 'over') return;
    this.score += n;
    if (this.score > this.high) {
      this.high = this.score;
      this.highDirty = true;
    }
  }

  private burst(x: number, y: number, color: string, n = 10, speed = 160): void {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const v = speed * (0.35 + Math.random() * 0.8);
      this.sparks.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 0.45 + Math.random() * 0.3, max: 0.75, color });
    }
    if (this.sparks.length > 160) this.sparks.splice(0, this.sparks.length - 160);
  }

  // ---- input -------------------------------------------------------------------------------------------------

  setFlipper(i: 0 | 1, down: boolean): void {
    const f = this.world.flippers[i];
    if (down && !f.pressed) {
      this.sfx.flipper();
      // Lane change: flipper buttons rotate the top rollover lights, like a real table.
      const l = this.lanes;
      if (i === 0) this.lanes = [l[1], l[2], l[0]];
      else this.lanes = [l[2], l[0], l[1]];
    }
    f.pressed = down;
  }

  setPlunger(down: boolean): void {
    if (this.phase === 'over') return;
    const atPlunger = this.ballAtPlunger();
    if (down) {
      if (atPlunger) this.charging = true;
    } else if (this.charging) {
      this.charging = false;
      if (atPlunger) this.launch();
      else this.pull = 0;
    }
  }

  private ballAtPlunger(): boolean {
    const b = this.ball;
    return b.active && !b.held && b.x > 380 && b.y > 600 && Math.abs(b.vy) < 120;
  }

  private launch(): void {
    const b = this.ball;
    const p = this.pull;
    b.vy = -(430 + 1170 * p);
    b.vx = 0;
    this.plungerKick = 1;
    this.sfx.launch(p);
    this.pull = 0;
    if (this.phase === 'ready') {
      this.phase = 'play';
      this.saveT = this.grantSave ? BALL_SAVE_SECONDS : 0;
      this.grantSave = false;
    }
    this.ticker = 'Ball in play';
  }

  // ---- simulation --------------------------------------------------------------------------------------------

  private ev: PhysEvents = {
    bumper: (i, speed) => {
      this.add(100);
      this.bonus += 100;
      this.bumperHits++;
      this.flash[`b${i}`] = 1;
      this.flash.shake = Math.min(1, speed / 700);
      const b = this.world.circs[i];
      this.burst(b.x, b.y, NEON.amber, 12, 220);
      this.sfx.bumper(i);
      this.mission('bumpers');
    },
    sling: (i) => {
      this.add(10);
      this.flash[`s${i}`] = 1;
      const s = this.world.segs.find((q) => q.kind === 'sling' && q.idx === i)!;
      this.burst((s.ax + s.bx) / 2, (s.ay + s.by) / 2, NEON.cyan, 7, 200);
      this.sfx.sling();
    },
    target: (i) => {
      const t = this.world.targets[i];
      if (!t.on) return;
      t.on = false;
      this.add(500);
      this.bonus += 500;
      this.flash[`t${i}`] = 1;
      this.burst(19, (t.ay + t.by) / 2, NEON.magenta, 10, 180);
      this.sfx.target();
      if (this.world.targets.every((q) => !q.on)) {
        this.add(5000);
        this.bonus += 2000;
        this.say('SHIELDS DOWN', '+5,000', NEON.magenta);
        this.targetResetT = 1.1;
        this.sfx.mission();
        this.mission('targets');
      }
    },
    wall: (v) => this.sfx.wall(v),
    flipper: () => this.sfx.flipperHit(),
    sensor: (id) => this.onSensor(id),
  };

  private onSensor(id: string): void {
    const b = this.ball;
    if (id.startsWith('lane')) {
      const i = Number(id.slice(4));
      this.sfx.rollover();
      this.flash[id] = 1;
      if (this.lanes[i]) {
        this.add(50);
        return;
      }
      this.lanes[i] = true;
      this.add(250);
      this.bonus += 250;
      if (this.lanes.every(Boolean)) {
        this.lanes = [false, false, false];
        this.mult = Math.min(5, this.mult + 1);
        this.add(3000);
        this.say('NAV LANES LIT', `Bonus x${this.mult}`, NEON.cyan);
        this.sfx.mission();
        this.mission('lanes');
      }
    } else if (id === 'inL' || id === 'inR') {
      const i = id === 'inL' ? 0 : 1;
      this.sfx.rollover();
      this.flash[id] = 1;
      this.add(500);
      this.inLit[i] = true;
      if (this.inLit[0] && this.inLit[1]) {
        this.inLit = [false, false];
        this.bonus += 3000;
        this.say('DOCKING BONUS', '+3,000 end-of-ball', NEON.lime);
      }
    } else if (id === 'outL' || id === 'outR') {
      this.flash[id] = 1;
      this.add(1000);
      this.sfx.rollover();
    } else if (id === 'orbA' || id === 'orbB') {
      this.flash[id] = 1;
      if (!b.inPlay) return;
      const prev = this.lastOrb;
      if (prev && prev.id !== id && this.time - prev.t < 2.6) {
        this.lastOrb = null;
        this.add(2500);
        this.bonus += 1500;
        this.say('ORBIT COMPLETE', '+2,500', NEON.magenta);
        this.sfx.wormhole();
        this.mission('orbit');
      } else this.lastOrb = { id, t: this.time };
    } else if (id === 'saucer') {
      if (b.held || Math.hypot(b.vx, b.vy) > 950) return;
      b.held = true;
      b.x = SAUCER.x;
      b.y = SAUCER.y;
      b.vx = b.vy = 0;
      this.saucerT = 0.9;
      this.add(1500);
      this.bonus += 1000;
      this.flash.saucer = 1;
      this.say('WORMHOLE', '+1,500', NEON.violet);
      this.sfx.wormhole();
      this.mission('worm');
    }
  }

  private mission(id: string): void {
    const cur = MISSIONS[this.missionsDone % MISSIONS.length];
    if (cur.id !== id) return;
    this.missionProg++;
    this.flash.mission = 1;
    if (this.missionProg < cur.goal(this.missionsDone)) return;
    const before = this.rankIndex;
    this.missionsDone++;
    this.missionProg = 0;
    this.add(5000 * this.missionsDone);
    this.bonus += 2500;
    this.sfx.mission();
    const after = this.rankIndex;
    if (after > before) this.say(`PROMOTED: ${RANKS[after].name.toUpperCase()}`, `Missions flown: ${this.missionsDone}`, NEON.amber, 2.6);
    else this.say('MISSION COMPLETE', `+${(5000 * this.missionsDone).toLocaleString('en-US')}`, NEON.amber, 2.2);
    this.flash.rank = 1;
  }

  /** One fixed physics step. */
  step(dt: number): void {
    this.time += dt;
    const b = this.ball;

    if (this.charging && this.ballAtPlunger()) {
      this.pull = Math.min(1, this.pull + dt / 1.1);
      this.world.plunger.ay = this.world.plunger.by = PLUNGER_REST_Y + PLUNGER_TRAVEL * this.pull;
      this.chargeTick += dt;
      if (this.chargeTick > 0.09) {
        this.chargeTick = 0;
        this.sfx.charge(this.pull);
      }
    }

    // The plunger snaps back up after release (the ball already has its launch velocity).
    if (!this.charging && this.world.plunger.ay > PLUNGER_REST_Y) {
      this.world.plunger.ay = this.world.plunger.by = Math.max(PLUNGER_REST_Y, this.world.plunger.ay - 2600 * dt);
    }

    stepWorld(this.world, b, dt, this.ev);

    if (this.phase === 'play' && this.saveT > 0) this.saveT = Math.max(0, this.saveT - dt);

    if (b.active && !b.inPlay && b.y > 300 && b.x < 370) b.inPlay = true;

    if (b.held) {
      this.saucerT -= dt;
      if (this.saucerT <= 0) {
        b.held = false;
        b.vx = -300 - Math.random() * 120;
        b.vy = -520 - Math.random() * 120;
        this.sfx.sling();
        this.burst(SAUCER.x, SAUCER.y, NEON.violet, 14, 240);
      }
    }

    if (this.targetResetT > 0) {
      this.targetResetT -= dt;
      if (this.targetResetT <= 0) for (const t of this.world.targets) t.on = true;
    }

    // Ball stuck on a flipper tip or similar: give it a nudge.
    if (b.active && !b.held && b.inPlay) {
      this.stillT = Math.hypot(b.vx, b.vy) < 8 ? this.stillT + dt : 0;
      if (this.stillT > 2.5) {
        this.stillT = 0;
        b.vx += (Math.random() - 0.5) * 240;
        b.vy -= 160;
      }
    }

    if (b.active && b.y > H + 16) this.drain();

    if (!b.active && this.phase !== 'over') {
      this.serveDelay -= dt;
      if (this.serveDelay <= 0) this.serve();
    }

    this.updateFx(dt);
  }

  private drain(): void {
    const b = this.ball;
    b.active = false;
    this.sfx.drain();
    if (this.saveT > 0 || this.phase === 'ready') {
      this.saveT = 0;
      this.say('BALL SAVED', 'Shoot again', NEON.ice);
      this.sfx.save();
      this.serveDelay = 0.8;
      return;
    }
    const total = this.bonus * this.mult;
    this.add(total);
    this.say('END OF BALL', `Bonus ${this.bonus.toLocaleString('en-US')} x${this.mult}`, NEON.amber, 2.4);
    this.bonus = 0;
    this.mult = 1;
    this.inLit = [false, false];
    this.outLit = [false, false];
    this.lastOrb = null;
    if (this.ballNo >= this.ballsMax) {
      this.phase = 'over';
      this.ticker = 'Game over - press F2 for a new game';
      this.sfx.over();
      this.persistHigh();
    } else {
      this.ballNo++;
      this.grantSave = true;
      this.phase = 'ready';
      this.serveDelay = 2.2;
    }
  }

  persistHigh(): void {
    if (!this.highDirty) return;
    this.highDirty = false;
    this.onHigh(this.high);
  }

  private updateFx(dt: number): void {
    for (const k of Object.keys(this.flash)) {
      this.flash[k] = Math.max(0, this.flash[k] - dt * (k === 'shake' ? 6 : 2.6));
    }
    if (this.banner) {
      this.banner.t += dt;
      if (this.banner.t > this.banner.dur) this.banner = null;
    }
    for (let i = this.sparks.length - 1; i >= 0; i--) {
      const s = this.sparks[i];
      s.life -= dt;
      if (s.life <= 0) {
        this.sparks.splice(i, 1);
        continue;
      }
      s.vy += 380 * dt;
      s.x += s.vx * dt;
      s.y += s.vy * dt;
    }
    this.plungerKick = Math.max(0, this.plungerKick - dt * 4);
    const b = this.ball;
    if (b.active) {
      const last = this.trail[this.trail.length - 1];
      if (!last || Math.hypot(last.x - b.x, last.y - b.y) > 3) this.trail.push({ x: b.x, y: b.y });
      if (this.trail.length > 10) this.trail.shift();
    } else this.trail.length = 0;
  }
}
