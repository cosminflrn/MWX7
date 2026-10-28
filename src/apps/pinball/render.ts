import type { Game } from './game';
import { BUMPER_R, BUMPERS, H, INSERTS, NEON, PLUNGER_X, SAUCER, W, type Flipper, type Insert, type Seg } from './table';

type Ctx = CanvasRenderingContext2D;

/** Top of the table is drawn narrower than the bottom: a cheap, convincing slanted-playfield perspective. */
const TOP_SCALE = 0.86;

function rng(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function line(c: Ctx, ax: number, ay: number, bx: number, by: number, w: number, style: string | CanvasGradient): void {
  c.strokeStyle = style;
  c.lineWidth = w;
  c.lineCap = 'round';
  c.beginPath();
  c.moveTo(ax, ay);
  c.lineTo(bx, by);
  c.stroke();
}

function rgba(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
}

function halo(c: Ctx, x: number, y: number, r: number, color: string, a: number): void {
  if (a <= 0.01) return;
  const g = c.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, rgba(color, 0.85 * a));
  g.addColorStop(0.4, rgba(color, 0.3 * a));
  g.addColorStop(1, rgba(color, 0));
  c.globalCompositeOperation = 'lighter';
  c.fillStyle = g;
  c.fillRect(x - r, y - r, r * 2, r * 2);
  c.globalCompositeOperation = 'source-over';
}

function shapePath(c: Ctx, shape: Insert['shape'], x: number, y: number, r: number, rot = 0): void {
  c.beginPath();
  if (shape === 'dot') c.arc(x, y, r, 0, Math.PI * 2);
  else if (shape === 'diamond') {
    c.moveTo(x, y - r * 1.25);
    c.lineTo(x + r, y);
    c.lineTo(x, y + r * 1.25);
    c.lineTo(x - r, y);
    c.closePath();
  } else if (shape === 'arrow') {
    c.moveTo(x - r, y - r * 0.9);
    c.lineTo(x + r, y - r * 0.9);
    c.lineTo(x, y + r * 1.1);
    c.closePath();
  } else if (shape === 'star') {
    for (let i = 0; i < 10; i++) {
      const a = -Math.PI / 2 + (i * Math.PI) / 5;
      const rr = i % 2 ? r * 0.45 : r;
      c[i ? 'lineTo' : 'moveTo'](x + Math.cos(a) * rr, y + Math.sin(a) * rr);
    }
    c.closePath();
  } else {
    // chevron
    const ca = Math.cos(rot);
    const sa = Math.sin(rot);
    const p = (px: number, py: number): [number, number] => [x + px * ca - py * sa, y + px * sa + py * ca];
    const pts = [p(-r, -r), p(r * 0.2, 0), p(-r, r), p(-r * 0.35, r), p(r, 0), p(-r * 0.35, -r)];
    c.moveTo(...pts[0]);
    for (const q of [pts[1], pts[2], pts[3], pts[4], pts[5]]) c.lineTo(...q);
    c.closePath();
  }
}

function drawInsert(c: Ctx, ins: Insert, lit: number): void {
  const { x, y, r, color, shape, rot } = ins;
  // Lens body: dark bezel then tinted translucent plastic.
  shapePath(c, shape, x, y, r + 1.6, rot);
  c.fillStyle = '#04060f';
  c.fill();
  shapePath(c, shape, x, y, r, rot);
  c.fillStyle = rgba(color, 0.14 + 0.78 * lit);
  c.fill();
  c.lineWidth = 0.9;
  c.strokeStyle = rgba(color, 0.35 + 0.65 * lit);
  c.stroke();
  if (lit > 0.05) {
    shapePath(c, shape, x, y, r * 0.55, rot);
    c.fillStyle = `rgba(255,255,255,${0.75 * lit})`;
    c.fill();
    halo(c, x, y, r * 3.6, color, lit);
  }
}

export class Renderer {
  private scene = document.createElement('canvas');
  private bg = document.createElement('canvas');
  private k = 1;
  private stars: { x: number; y: number; r: number; p: number; c: string }[] = [];

  constructor(private canvas: HTMLCanvasElement, private worldSegs: Seg[]) {}

  resize(cssW: number, dpr: number): void {
    const cw = Math.max(32, Math.round(cssW * dpr));
    const ch = Math.round((cw * H) / W);
    for (const c of [this.canvas, this.scene, this.bg]) {
      c.width = cw;
      c.height = ch;
    }
    this.canvas.style.width = `${cw / dpr}px`;
    this.canvas.style.height = `${ch / dpr}px`;
    this.k = cw / W;
    this.buildBackground();
  }

  // ---- static layer ------------------------------------------------------------------------------------------

  private buildBackground(): void {
    const c = this.bg.getContext('2d')!;
    c.setTransform(this.k, 0, 0, this.k, 0, 0);
    const R = rng(7);

    // Deep space base
    const base = c.createLinearGradient(0, 0, 0, H);
    base.addColorStop(0, '#02030c');
    base.addColorStop(0.45, '#080b22');
    base.addColorStop(1, '#0d0824');
    c.fillStyle = base;
    c.fillRect(0, 0, W, H);

    // Nebula clouds
    c.globalCompositeOperation = 'lighter';
    const neb: [number, number, number, string, number][] = [
      [90, 120, 230, '#6a2cc8', 0.5],
      [330, 250, 210, '#1f56d6', 0.42],
      [150, 430, 190, '#b0267f', 0.3],
      [320, 560, 200, '#12908e', 0.26],
      [210, 40, 160, '#3c1c8f', 0.4],
    ];
    for (const [x, y, r, col, a] of neb) {
      const g = c.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, rgba(col, a));
      g.addColorStop(0.55, rgba(col, a * 0.35));
      g.addColorStop(1, rgba(col, 0));
      c.fillStyle = g;
      c.fillRect(x - r, y - r, r * 2, r * 2);
    }
    // Dust grain: lots of tiny soft blobs give the clouds texture
    for (let i = 0; i < 380; i++) {
      const x = R() * W;
      const y = R() * H;
      const r = 2 + R() * 9;
      const col = ['#8f5cff', '#3d8bff', '#ff59c8', '#35e0d0'][Math.floor(R() * 4)];
      const g = c.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, rgba(col, 0.06 + R() * 0.05));
      g.addColorStop(1, rgba(col, 0));
      c.fillStyle = g;
      c.fillRect(x - r, y - r, r * 2, r * 2);
    }
    c.globalCompositeOperation = 'source-over';

    // Stars
    this.stars = [];
    for (let i = 0; i < 260; i++) {
      const s = { x: R() * W, y: R() * H, r: 0.3 + R() * R() * 1.3, p: R() * 6.28, c: ['#ffffff', '#cfe6ff', '#ffe9c4', '#d9c9ff'][Math.floor(R() * 4)] };
      this.stars.push(s);
      c.globalAlpha = 0.35 + R() * 0.65;
      c.fillStyle = s.c;
      c.beginPath();
      c.arc(s.x, s.y, s.r, 0, 6.3);
      c.fill();
      if (s.r > 1.1) {
        c.globalAlpha *= 0.5;
        line(c, s.x - 4, s.y, s.x + 4, s.y, 0.4, s.c);
        line(c, s.x, s.y - 4, s.x, s.y + 4, 0.4, s.c);
      }
    }
    c.globalAlpha = 1;

    this.drawPlanet(c);
    this.drawInlay(c);

    // Launch lane trough
    const lane = c.createLinearGradient(380, 0, 410, 0);
    lane.addColorStop(0, 'rgba(0,0,0,.55)');
    lane.addColorStop(0.5, 'rgba(8,12,34,.35)');
    lane.addColorStop(1, 'rgba(0,0,0,.6)');
    c.fillStyle = lane;
    c.fillRect(379, 100, 31, 626);
    for (let y = 560; y > 220; y -= 46) {
      c.strokeStyle = rgba(NEON.cyan, 0.2);
      c.lineWidth = 1.5;
      c.beginPath();
      c.moveTo(386, y + 8);
      c.lineTo(394, y);
      c.lineTo(402, y + 8);
      c.stroke();
    }

    // Distance haze (far end of the slanted table is dimmer and bluer)
    const haze = c.createLinearGradient(0, 0, 0, H * 0.5);
    haze.addColorStop(0, 'rgba(4,6,28,.62)');
    haze.addColorStop(1, 'rgba(4,6,28,0)');
    c.fillStyle = haze;
    c.fillRect(0, 0, W, H * 0.5);

    // Drain void
    const drain = c.createLinearGradient(0, 690, 0, H);
    drain.addColorStop(0, 'rgba(0,0,0,0)');
    drain.addColorStop(0.6, 'rgba(0,0,0,.85)');
    drain.addColorStop(1, '#000');
    c.fillStyle = drain;
    c.fillRect(0, 690, W, H - 690);

    this.drawHardware(c);
  }

  private drawPlanet(c: Ctx): void {
    const x = 200;
    const y = 430;
    const r = 58;
    c.save();
    c.globalAlpha = 0.55;
    // back ring
    c.strokeStyle = 'rgba(200,170,255,.28)';
    c.lineWidth = 6;
    c.beginPath();
    c.ellipse(x, y, r * 1.75, r * 0.5, -0.28, Math.PI, Math.PI * 2);
    c.stroke();
    const g = c.createRadialGradient(x - r * 0.4, y - r * 0.45, r * 0.1, x, y, r);
    g.addColorStop(0, '#9c7bff');
    g.addColorStop(0.5, '#4a3a9c');
    g.addColorStop(1, '#0c0b2a');
    c.fillStyle = g;
    c.beginPath();
    c.arc(x, y, r, 0, 6.3);
    c.fill();
    // bands
    c.save();
    c.clip();
    for (let i = -3; i <= 3; i++) {
      c.fillStyle = i % 2 ? 'rgba(255,170,230,.10)' : 'rgba(80,200,255,.08)';
      c.fillRect(x - r, y + i * 14 - 4, r * 2, 9);
    }
    c.restore();
    // front ring
    c.strokeStyle = 'rgba(210,190,255,.4)';
    c.lineWidth = 6;
    c.beginPath();
    c.ellipse(x, y, r * 1.75, r * 0.5, -0.28, 0, Math.PI);
    c.stroke();
    c.strokeStyle = 'rgba(120,230,255,.25)';
    c.lineWidth = 1.2;
    c.beginPath();
    c.ellipse(x, y, r * 2.05, r * 0.6, -0.28, 0, Math.PI * 2);
    c.stroke();
    c.restore();
  }

  /** Printed playfield art: dim neon guide lines. Lit state is drawn per frame by insert glows. */
  private drawInlay(c: Ctx): void {
    c.save();
    c.lineCap = 'round';
    // concentric arch echoing the orbit rail
    for (const [rad, a, col] of [[184, 0.42, NEON.cyan], [170, 0.2, NEON.violet]] as const) {
      c.strokeStyle = rgba(col, a);
      c.lineWidth = 2;
      c.beginPath();
      c.arc(210, 210, rad, Math.PI * 1.02, Math.PI * 1.98);
      c.stroke();
    }
    // lane guide lines to the flippers
    c.strokeStyle = rgba(NEON.cyan, 0.3);
    c.lineWidth = 1.6;
    for (const m of [0, 1]) {
      const X = (x: number) => (m ? 388 - x : x);
      c.beginPath();
      c.moveTo(X(46), 520);
      c.lineTo(X(46), 590);
      c.lineTo(X(112), 628);
      c.stroke();
      c.strokeStyle = rgba(NEON.amber, 0.28);
      c.beginPath();
      c.moveTo(X(23), 530);
      c.lineTo(X(23), 700);
      c.stroke();
      c.strokeStyle = rgba(NEON.cyan, 0.3);
    }
    // wormhole rings
    for (const [rr, a] of [[SAUCER.r + 10, 0.35], [SAUCER.r + 18, 0.18]] as const) {
      c.strokeStyle = rgba(NEON.violet, a);
      c.lineWidth = 1.5;
      c.setLineDash([3, 4]);
      c.beginPath();
      c.arc(SAUCER.x, SAUCER.y, rr, 0, 6.3);
      c.stroke();
    }
    c.setLineDash([]);
    // shield bank frame
    c.strokeStyle = rgba(NEON.magenta, 0.35);
    c.lineWidth = 1.4;
    c.beginPath();
    c.moveTo(34, 312);
    c.lineTo(34, 444);
    c.stroke();
    // lettering
    c.fillStyle = rgba(NEON.ice, 0.34);
    c.font = '700 9px system-ui, sans-serif';
    c.textAlign = 'center';
    (c as Ctx & { letterSpacing: string }).letterSpacing = '3px';
    c.fillText('NAV LANES', 194, 60);
    c.fillText('REACTORS', 210, 172);
    c.fillText('WORMHOLE', 312, 380);
    c.fillText('ORBIT RANK', 194, 500);
    c.fillText('SAVE', 194, 626);
    (c as Ctx & { letterSpacing: string }).letterSpacing = '0px';
    c.restore();
  }

  private metalRail(c: Ctx, s: Seg): void {
    const { ax, ay, bx, by, r } = s;
    // cast shadow on the playfield
    c.save();
    c.shadowColor = 'rgba(0,0,0,.75)';
    c.shadowBlur = 7;
    c.shadowOffsetX = 3;
    c.shadowOffsetY = 5;
    line(c, ax, ay, bx, by, r * 2 + 1, '#0a0d18');
    c.restore();
    line(c, ax, ay + 2.2, bx, by + 2.2, r * 2 + 1, '#0b0f1c'); // wall face under the rail
    line(c, ax, ay, bx, by, r * 2 + 0.6, '#4b566c');
    line(c, ax + r * 0.5, ay + r * 0.55, bx + r * 0.5, by + r * 0.55, r * 0.9, '#1d2434');
    line(c, ax - r * 0.28, ay - r * 0.38, bx - r * 0.28, by - r * 0.38, r * 1.25, '#c8d2e4');
    line(c, ax - r * 0.42, ay - r * 0.5, bx - r * 0.42, by - r * 0.5, r * 0.45, 'rgba(255,255,255,.95)');
  }

  private drawHardware(c: Ctx): void {
    const g = this.worldSegs;
    // rails first (so rubber and inserts sit on top)
    for (const s of g) if (s.kind === 'arch' || s.kind === 'wall' || s.kind === 'guide' || s.kind === 'divider') this.metalRail(c, s);
    // lane floor cap
    line(c, 380, 710, 408, 710, 3, '#273046');

    // bumper bases
    for (const b of BUMPERS) {
      c.save();
      c.shadowColor = 'rgba(0,0,0,.8)';
      c.shadowBlur = 9;
      c.shadowOffsetX = 4;
      c.shadowOffsetY = 7;
      c.fillStyle = '#05070f';
      c.beginPath();
      c.arc(b.x, b.y, BUMPER_R + 3, 0, 6.3);
      c.fill();
      c.restore();
    }
    // wormhole well
    const w = c.createRadialGradient(SAUCER.x, SAUCER.y, 1, SAUCER.x, SAUCER.y, SAUCER.r + 4);
    w.addColorStop(0, '#000');
    w.addColorStop(0.7, '#150a33');
    w.addColorStop(1, '#6c4cc8');
    c.fillStyle = w;
    c.beginPath();
    c.arc(SAUCER.x, SAUCER.y, SAUCER.r + 3, 0, 6.3);
    c.fill();
    c.strokeStyle = '#cdd6e8';
    c.lineWidth = 1.6;
    c.stroke();

    for (const ins of INSERTS) drawInsert(c, ins, 0);

    // Slingshot rubber bodies and shadows
    for (const m of [0, 1]) {
      const X = (x: number) => (m ? 388 - x : x);
      c.save();
      c.shadowColor = 'rgba(0,0,0,.7)';
      c.shadowBlur = 6;
      c.shadowOffsetX = 3;
      c.shadowOffsetY = 5;
      c.beginPath();
      c.moveTo(X(64), 492);
      c.lineTo(X(112), 592);
      c.lineTo(X(64), 572);
      c.closePath();
      c.fillStyle = '#0d1020';
      c.fill();
      c.restore();
    }
  }

  // ---- per-frame --------------------------------------------------------------------------------------------

  draw(g: Game, now: number): void {
    const sc = this.scene.getContext('2d')!;
    const cw = this.scene.width;
    const ch = this.scene.height;
    sc.setTransform(1, 0, 0, 1, 0, 0);
    sc.globalCompositeOperation = 'source-over';
    sc.drawImage(this.bg, 0, 0);
    sc.setTransform(this.k, 0, 0, this.k, 0, 0);

    const t = now / 1000;
    // twinkle
    sc.globalCompositeOperation = 'lighter';
    for (let i = 0; i < this.stars.length; i += 3) {
      const s = this.stars[i];
      const a = 0.25 + 0.35 * Math.sin(t * 1.7 + s.p);
      if (a > 0.1) {
        sc.fillStyle = rgba('#cfe6ff', a * 0.6);
        sc.beginPath();
        sc.arc(s.x, s.y, s.r * 0.9, 0, 6.3);
        sc.fill();
      }
    }
    sc.globalCompositeOperation = 'source-over';

    this.drawLights(sc, g, t);
    this.drawTargets(sc, g);
    this.drawSlings(sc, g);
    this.drawBumpers(sc, g, t);
    this.drawPlunger(sc, g);
    for (const f of g.world.flippers) this.drawFlipper(sc, f);
    if (g.ball.active) this.drawBall(sc, g);
    this.drawSparks(sc, g);
    this.drawBanner(sc, g);

    // ---- compose to screen with perspective ----
    const out = this.canvas.getContext('2d')!;
    out.setTransform(1, 0, 0, 1, 0, 0);
    out.globalCompositeOperation = 'source-over';
    const cab = out.createLinearGradient(0, 0, 0, ch);
    cab.addColorStop(0, '#05060d');
    cab.addColorStop(1, '#0c0f1c');
    out.fillStyle = cab;
    out.fillRect(0, 0, cw, ch);

    const shake = g.flash.shake ?? 0;
    const sx = shake > 0.02 ? (Math.random() - 0.5) * 3 * shake * this.k : 0;
    const sy = shake > 0.02 ? (Math.random() - 0.5) * 3 * shake * this.k : 0;
    // cabinet side rails following the trapezoid
    const edge = (y: number) => (cw * (1 - (TOP_SCALE + (1 - TOP_SCALE) * (y / ch)))) / 2;
    for (const side of [0, 1]) {
      const rail = Math.max(8, cw * 0.045);
      const grad = out.createLinearGradient(side ? cw - edge(0) : 0, 0, side ? cw - edge(0) + rail : edge(0), 0);
      grad.addColorStop(0, '#2a3144');
      grad.addColorStop(1, '#0a0d18');
      out.beginPath();
      if (!side) {
        out.moveTo(edge(0) - rail, 0);
        out.lineTo(edge(0), 0);
        out.lineTo(edge(ch), ch);
        out.lineTo(edge(ch) - rail, ch);
      } else {
        out.moveTo(cw - edge(0), 0);
        out.lineTo(cw - edge(0) + rail, 0);
        out.lineTo(cw - edge(ch) + rail, ch);
        out.lineTo(cw - edge(ch), ch);
      }
      out.closePath();
      out.fillStyle = grad;
      out.fill();
    }
    out.imageSmoothingEnabled = true;
    const STRIP = 2;
    for (let y = 0; y < ch; y += STRIP) {
      const s = TOP_SCALE + (1 - TOP_SCALE) * ((y + STRIP / 2) / ch);
      const dw = cw * s;
      out.drawImage(this.scene, 0, y, cw, STRIP, (cw - dw) / 2 + sx, y + sy, dw, STRIP);
    }

    // glass: soft diagonal sheen + edge vignette
    const sheen = out.createLinearGradient(0, 0, cw, ch * 0.7);
    sheen.addColorStop(0, 'rgba(255,255,255,.10)');
    sheen.addColorStop(0.28, 'rgba(255,255,255,.03)');
    sheen.addColorStop(0.34, 'rgba(255,255,255,.07)');
    sheen.addColorStop(0.5, 'rgba(255,255,255,0)');
    out.fillStyle = sheen;
    out.fillRect(0, 0, cw, ch);
    const vig = out.createRadialGradient(cw / 2, ch * 0.55, ch * 0.3, cw / 2, ch * 0.55, ch * 0.85);
    vig.addColorStop(0, 'rgba(0,0,0,0)');
    vig.addColorStop(1, 'rgba(0,0,0,.5)');
    out.fillStyle = vig;
    out.fillRect(0, 0, cw, ch);
  }

  private litValue(g: Game, key: string, t: number): number {
    const f = g.flash[key] ?? 0;
    if (key.startsWith('lane')) {
      const i = Number(key.slice(4));
      const chase = g.phase === 'ready' ? Math.max(0, Math.sin(t * 4 - i * 1.2)) * 0.5 : 0;
      return Math.max(g.lanes[i] ? 1 : 0, f, chase);
    }
    if (key === 'inL') return Math.max(g.inLit[0] ? 0.9 : 0, f);
    if (key === 'inR') return Math.max(g.inLit[1] ? 0.9 : 0, f);
    if (key === 'save') return g.saveT > 0 ? (g.saveT < 2.5 ? (Math.sin(t * 14) > 0 ? 1 : 0.15) : 0.85) : 0;
    if (key === 'mission') return Math.max(0.35 + 0.3 * Math.sin(t * 3), f);
    if (key.startsWith('rank')) {
      const i = Number(key.slice(4));
      return i <= g.rankIndex ? Math.max(0.9, g.flash.rank ?? 0) : 0;
    }
    return f;
  }

  private drawLights(c: Ctx, g: Game, t: number): void {
    for (const ins of INSERTS) {
      const v = this.litValue(g, ins.key, t);
      if (v > 0.02) drawInsert(c, ins, v);
    }
    // wormhole glow
    const wf = Math.max(g.flash.saucer ?? 0, 0.25 + 0.15 * Math.sin(t * 2.4));
    halo(c, SAUCER.x, SAUCER.y, 34, NEON.violet, wf);
    const swirl = t * 2.2;
    c.strokeStyle = rgba(NEON.ice, 0.35);
    c.lineWidth = 1.2;
    for (let i = 0; i < 3; i++) {
      c.beginPath();
      c.arc(SAUCER.x, SAUCER.y, 3 + i * 3, swirl + i * 2, swirl + i * 2 + 2.4);
      c.stroke();
    }
  }

  private drawTargets(c: Ctx, g: Game): void {
    g.world.targets.forEach((s, i) => {
      const cy = (s.ay + s.by) / 2;
      const f = g.flash[`t${i}`] ?? 0;
      c.save();
      c.shadowColor = 'rgba(0,0,0,.6)';
      c.shadowBlur = 4;
      c.shadowOffsetX = 2;
      c.shadowOffsetY = 3;
      c.fillStyle = '#05070f';
      c.fillRect(13, cy - 12.5, 12, 25);
      c.restore();
      if (s.on) {
        const gr = c.createLinearGradient(14, 0, 24, 0);
        gr.addColorStop(0, '#ff9af2');
        gr.addColorStop(0.45, NEON.magenta);
        gr.addColorStop(1, '#7a1070');
        c.fillStyle = gr;
        c.fillRect(14, cy - 11.5, 10, 23);
        c.fillStyle = 'rgba(255,255,255,.75)';
        c.fillRect(15, cy - 10.5, 2.2, 21);
        c.strokeStyle = 'rgba(255,255,255,.45)';
        c.lineWidth = 0.8;
        c.strokeRect(14, cy - 11.5, 10, 23);
        halo(c, 18, cy, 24, NEON.magenta, 0.45 + f);
      } else {
        c.fillStyle = '#10131f';
        c.fillRect(14, cy - 11.5, 10, 23);
        c.fillStyle = rgba(NEON.magenta, 0.15 + 0.6 * f);
        c.fillRect(14, cy - 11.5, 3, 23);
        halo(c, 16, cy, 20, NEON.magenta, f);
      }
    });
  }

  private drawSlings(c: Ctx, g: Game): void {
    for (const m of [0, 1]) {
      const X = (x: number) => (m ? 388 - x : x);
      const f = g.flash[`s${m}`] ?? 0;
      const gr = c.createLinearGradient(X(64), 492, X(112), 592);
      gr.addColorStop(0, '#2a2f66');
      gr.addColorStop(1, '#0b0d22');
      c.beginPath();
      c.moveTo(X(64), 492);
      c.lineTo(X(112), 592);
      c.lineTo(X(64), 572);
      c.closePath();
      c.fillStyle = gr;
      c.fill();
      c.strokeStyle = 'rgba(160,190,255,.35)';
      c.lineWidth = 1;
      c.stroke();
      // kicker rubber with a neon strip
      line(c, X(64), 492, X(112), 592, 5.5, '#141a30');
      line(c, X(64.5), 493, X(111.5), 591, 2.2, rgba(NEON.cyan, 0.45 + 0.55 * f));
      line(c, X(64.5), 493, X(111.5), 591, 0.8, `rgba(255,255,255,${0.35 + 0.65 * f})`);
      halo(c, X((64 + 112) / 2), 542, 50, NEON.cyan, 0.18 + 0.7 * f);
    }
  }

  private drawBumpers(c: Ctx, g: Game, t: number): void {
    BUMPERS.forEach((b, i) => {
      const f = g.flash[`b${i}`] ?? 0;
      const R = BUMPER_R;
      halo(c, b.x, b.y, R * 2.6, NEON.amber, 0.22 + 0.9 * f);
      // chrome skirt
      const sk = c.createLinearGradient(b.x - R, b.y - R, b.x + R, b.y + R);
      sk.addColorStop(0, '#ffffff');
      sk.addColorStop(0.35, '#93a0b8');
      sk.addColorStop(0.6, '#3a4458');
      sk.addColorStop(1, '#bcc7da');
      c.fillStyle = sk;
      c.beginPath();
      c.arc(b.x, b.y, R, 0, 6.3);
      c.fill();
      c.fillStyle = '#05070f';
      c.beginPath();
      c.arc(b.x, b.y, R * 0.82, 0, 6.3);
      c.fill();
      // neon ring
      c.strokeStyle = rgba(NEON.cyan, 0.5 + 0.5 * f);
      c.lineWidth = 1.6;
      c.beginPath();
      c.arc(b.x, b.y, R * 0.74, 0, 6.3);
      c.stroke();
      // cap (slightly dome-shaped, pushed in when hit)
      const cr = R * (0.62 - 0.04 * f);
      const cap = c.createRadialGradient(b.x - cr * 0.35, b.y - cr * 0.4, cr * 0.1, b.x, b.y, cr);
      cap.addColorStop(0, f > 0.2 ? '#fffbe0' : '#ffe0a0');
      cap.addColorStop(0.45, f > 0.2 ? '#ffc04a' : '#ff8a28');
      cap.addColorStop(1, '#7a1d00');
      c.fillStyle = cap;
      c.beginPath();
      c.arc(b.x, b.y, cr, 0, 6.3);
      c.fill();
      c.fillStyle = 'rgba(255,255,255,.55)';
      c.beginPath();
      c.ellipse(b.x - cr * 0.3, b.y - cr * 0.42, cr * 0.4, cr * 0.2, -0.5, 0, 6.3);
      c.fill();
      // little pulsing core light
      halo(c, b.x, b.y, R * 1.2, NEON.amber, 0.15 + 0.15 * Math.sin(t * 5 + i));
    });
  }

  private drawPlunger(c: Ctx, g: Game): void {
    const top = g.world.plunger.ay + g.plungerKick * 5;
    const bottom = 724;
    // spring
    c.strokeStyle = '#9aa6bb';
    c.lineWidth = 1.5;
    c.beginPath();
    const n = 9;
    for (let i = 0; i <= n; i++) {
      const y = top + 5 + ((bottom - top - 8) * i) / n;
      c.lineTo(PLUNGER_X + (i % 2 ? 7 : -7), y);
    }
    c.stroke();
    // rod + tip
    const rod = c.createLinearGradient(PLUNGER_X - 4, 0, PLUNGER_X + 4, 0);
    rod.addColorStop(0, '#6b7690');
    rod.addColorStop(0.35, '#ffffff');
    rod.addColorStop(1, '#4a5368');
    c.fillStyle = rod;
    c.fillRect(PLUNGER_X - 4, top + 2, 8, 12);
    const cap = c.createLinearGradient(0, top - 1, 0, top + 4);
    cap.addColorStop(0, '#f6f9ff');
    cap.addColorStop(1, '#7c879d');
    c.fillStyle = cap;
    c.fillRect(PLUNGER_X - 13, top - 1, 26, 4);
    if (g.pull > 0.02) halo(c, PLUNGER_X, top - 6, 26, NEON.amber, g.pull * 0.8);
  }

  private drawFlipper(c: Ctx, f: Flipper): void {
    const dx = f.tipX - f.px;
    const dy = f.tipY - f.py;
    const L = Math.hypot(dx, dy);
    const ux = dx / L;
    const uy = dy / L;
    const nx = -uy;
    const ny = ux;
    const poly = (ox: number, oy: number) => {
      c.beginPath();
      c.moveTo(f.px + nx * f.r0 + ox, f.py + ny * f.r0 + oy);
      c.lineTo(f.tipX + nx * f.r1 + ox, f.tipY + ny * f.r1 + oy);
      c.arc(f.tipX + ox, f.tipY + oy, f.r1, Math.atan2(ny, nx), Math.atan2(ny, nx) + Math.PI);
      c.lineTo(f.px - nx * f.r0 + ox, f.py - ny * f.r0 + oy);
      c.arc(f.px + ox, f.py + oy, f.r0, Math.atan2(-ny, -nx), Math.atan2(-ny, -nx) + Math.PI);
      c.closePath();
    };
    c.save();
    c.shadowColor = 'rgba(0,0,0,.8)';
    c.shadowBlur = 6;
    c.shadowOffsetX = 3;
    c.shadowOffsetY = 6;
    poly(0, 0);
    c.fillStyle = '#000';
    c.fill();
    c.restore();
    // side face
    poly(0, 3);
    c.fillStyle = '#1b2232';
    c.fill();
    // brushed-chrome top: gradient across the flipper width
    const mx = (f.px + f.tipX) / 2;
    const my = (f.py + f.tipY) / 2;
    const gr = c.createLinearGradient(mx + nx * f.r0, my + ny * f.r0, mx - nx * f.r0, my - ny * f.r0);
    gr.addColorStop(0, '#2b3345');
    gr.addColorStop(0.25, '#dfe6f4');
    gr.addColorStop(0.42, '#ffffff');
    gr.addColorStop(0.6, '#8a96ac');
    gr.addColorStop(1, '#1e2535');
    poly(0, 0);
    c.fillStyle = gr;
    c.fill();
    c.lineWidth = 0.8;
    c.strokeStyle = 'rgba(8,12,24,.9)';
    c.stroke();
    // neon inlay stripe + specular line
    const col = f.pressed ? NEON.cyan : '#5a7090';
    line(c, f.px + ux * 12, f.py + uy * 12, f.tipX - ux * 7, f.tipY - uy * 7, 1.6, col);
    line(c, f.px + ux * 8 + nx * f.r0 * 0.5, f.py + uy * 8 + ny * f.r0 * 0.5, f.tipX - ux * 6 + nx * f.r1 * 0.5, f.tipY - uy * 6 + ny * f.r1 * 0.5, 0.9, 'rgba(255,255,255,.85)');
    if (f.pressed) halo(c, mx, my, 40, NEON.cyan, 0.25);
    // pivot bolt
    const bolt = c.createRadialGradient(f.px - 1.5, f.py - 1.5, 0.5, f.px, f.py, 4);
    bolt.addColorStop(0, '#fff');
    bolt.addColorStop(1, '#5a6478');
    c.fillStyle = bolt;
    c.beginPath();
    c.arc(f.px, f.py, 3.4, 0, 6.3);
    c.fill();
  }

  private drawBall(c: Ctx, g: Game): void {
    const b = g.ball;
    const r = b.r;
    // motion trail
    c.globalCompositeOperation = 'lighter';
    const sp = Math.hypot(b.vx, b.vy);
    const fast = Math.min(1, sp / 1200);
    g.trail.forEach((p, i) => {
      const a = (i / g.trail.length) * 0.22 * fast;
      if (a < 0.01) return;
      c.fillStyle = rgba(NEON.cyan, a);
      c.beginPath();
      c.arc(p.x, p.y, r * (0.5 + 0.5 * (i / g.trail.length)), 0, 6.3);
      c.fill();
    });
    c.globalCompositeOperation = 'source-over';
    // contact shadow
    c.fillStyle = 'rgba(0,0,0,.5)';
    c.beginPath();
    c.ellipse(b.x + 3.5, b.y + 5.5, r * 1.0, r * 0.75, 0, 0, 6.3);
    c.fill();
    // chrome sphere: dark base, environment (sky / horizon / floor), specular, rim light
    c.save();
    c.beginPath();
    c.arc(b.x, b.y, r, 0, 6.3);
    c.clip();
    const base = c.createRadialGradient(b.x - r * 0.35, b.y - r * 0.4, r * 0.1, b.x, b.y, r * 1.05);
    base.addColorStop(0, '#ffffff');
    base.addColorStop(0.35, '#cdd5e5');
    base.addColorStop(0.75, '#5b667c');
    base.addColorStop(1, '#10151f');
    c.fillStyle = base;
    c.fillRect(b.x - r, b.y - r, r * 2, r * 2);
    // reflected nebula band; it slides with the ball so the metal feels like it reflects the table
    const hy = b.y + r * 0.12 + Math.sin(b.x * 0.05) * r * 0.1;
    const env = c.createLinearGradient(0, hy - r * 0.6, 0, hy + r);
    env.addColorStop(0, 'rgba(120,170,255,0)');
    env.addColorStop(0.5, 'rgba(70,90,200,.5)');
    env.addColorStop(0.52, 'rgba(255,170,230,.45)');
    env.addColorStop(1, 'rgba(10,10,30,.7)');
    c.fillStyle = env;
    c.fillRect(b.x - r, hy - r * 0.6, r * 2, r * 1.8);
    c.restore();
    c.fillStyle = 'rgba(255,255,255,.95)';
    c.beginPath();
    c.ellipse(b.x - r * 0.38, b.y - r * 0.42, r * 0.3, r * 0.2, -0.7, 0, 6.3);
    c.fill();
    c.strokeStyle = 'rgba(150,230,255,.45)';
    c.lineWidth = 0.8;
    c.beginPath();
    c.arc(b.x, b.y, r - 0.5, 0.3, 1.5);
    c.stroke();
    c.strokeStyle = 'rgba(5,8,16,.9)';
    c.lineWidth = 0.7;
    c.beginPath();
    c.arc(b.x, b.y, r, 0, 6.3);
    c.stroke();
  }

  private drawSparks(c: Ctx, g: Game): void {
    c.globalCompositeOperation = 'lighter';
    for (const s of g.sparks) {
      const a = Math.max(0, s.life / s.max);
      c.fillStyle = rgba(s.color, a);
      c.beginPath();
      c.arc(s.x, s.y, 1 + 1.6 * a, 0, 6.3);
      c.fill();
    }
    c.globalCompositeOperation = 'source-over';
  }

  private drawBanner(c: Ctx, g: Game): void {
    const b = g.banner;
    if (!b) return;
    const p = b.t / b.dur;
    const a = p < 0.1 ? p / 0.1 : p > 0.75 ? Math.max(0, (1 - p) / 0.25) : 1;
    const y = 330 - 10 * p;
    c.save();
    c.globalAlpha = a;
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    (c as Ctx & { letterSpacing: string }).letterSpacing = '3px';
    c.font = '800 25px system-ui, "Segoe UI", sans-serif';
    c.shadowColor = b.color;
    c.shadowBlur = 16;
    c.fillStyle = '#fff';
    c.fillText(b.text, 194, y);
    c.shadowBlur = 0;
    c.font = '600 12px system-ui, "Segoe UI", sans-serif';
    c.fillStyle = b.color;
    (c as Ctx & { letterSpacing: string }).letterSpacing = '2px';
    if (b.sub) c.fillText(b.sub.toUpperCase(), 194, y + 24);
    c.restore();
  }
}
