/**
 * MWX 7 wallpapers. All original — painted procedurally on a canvas at the
 * screen's resolution (no image files, no third-party photos).
 */

type Painter = (ctx: CanvasRenderingContext2D, w: number, h: number) => void;

export interface Wallpaper {
  id: string;
  name: string;
  paint?: Painter;
  css?: string;
}

/** Deterministic PRNG so a wallpaper looks identical on every boot. */
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const gauss = (rnd: () => number) => (rnd() + rnd() + rnd() + rnd() - 2) / 2;

/* ---------------- Serenity Hill ---------------- */

function cumulus(ctx: CanvasRenderingContext2D, rnd: () => number, cx: number, cy: number, cw: number, ch: number, puffs: number): void {
  // Paint the cloud on its own layer so shading only touches the cloud.
  const pad = ch * 1.2;
  const layer = document.createElement('canvas');
  layer.width = Math.ceil(cw + pad * 2);
  layer.height = Math.ceil(ch * 2 + pad * 2);
  const c = layer.getContext('2d')!;
  const ox = cx - cw / 2 - pad;
  const oy = cy - ch * 1.5 - pad;
  const base = cy - oy; // flat-ish bottom of the cloud in layer coords

  for (let i = 0; i < puffs; i++) {
    const t = gauss(rnd);
    const x = cw / 2 + pad + t * cw * 0.42;
    const edge = 1 - Math.min(1, Math.abs(t) * 1.3);
    const r = ch * (0.14 + rnd() * 0.26) * (0.45 + edge * 0.75);
    const y = base - r * 0.55 - Math.abs(gauss(rnd)) * ch * 0.75 * edge;
    const g = c.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(0.6, 'rgba(255,255,255,0.85)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    c.fillStyle = g;
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.fill();
  }

  // Shading: bright sunlit tops, cool blue-grey bellies.
  c.globalCompositeOperation = 'source-atop';
  const shade = c.createLinearGradient(0, base - ch * 1.4, 0, base + ch * 0.1);
  shade.addColorStop(0, 'rgba(255,255,255,0)');
  shade.addColorStop(0.6, 'rgba(232,240,250,0.12)');
  shade.addColorStop(1, 'rgba(176,198,226,0.6)');
  c.fillStyle = shade;
  c.fillRect(0, 0, layer.width, layer.height);
  const sun = c.createRadialGradient(layer.width * 0.3, base - ch * 1.2, 0, layer.width * 0.3, base - ch * 1.2, cw * 0.6);
  sun.addColorStop(0, 'rgba(255,255,250,0.5)');
  sun.addColorStop(1, 'rgba(255,255,250,0)');
  c.fillStyle = sun;
  c.fillRect(0, 0, layer.width, layer.height);

  ctx.save();
  ctx.filter = `blur(${Math.max(0.4, ch * 0.005)}px)`;
  ctx.drawImage(layer, ox, oy);
  ctx.restore();
}

function wisp(ctx: CanvasRenderingContext2D, rnd: () => number, x: number, y: number, len: number, alpha: number): void {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(-0.08 + rnd() * 0.06);
  for (let i = 0; i < 26; i++) {
    const px = gauss(rnd) * len * 0.5;
    const py = gauss(rnd) * len * 0.025;
    const rx = len * (0.12 + rnd() * 0.16);
    const ry = rx * 0.09;
    const g = ctx.createRadialGradient(px, py, 0, px, py, rx);
    g.addColorStop(0, `rgba(255,255,255,${alpha})`);
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.ellipse(px, py, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

const serenity: Painter = (ctx, W, H) => {
  const rnd = mulberry32(2001);

  // Sky: deep zenith blue fading to a pale, hazy horizon.
  const sky = ctx.createLinearGradient(0, 0, 0, H * 0.78);
  sky.addColorStop(0, '#0a3c98');
  sky.addColorStop(0.3, '#1758c0');
  sky.addColorStop(0.62, '#3f88e0');
  sky.addColorStop(0.88, '#8fc1f2');
  sky.addColorStop(1, '#c4e0fa');
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, W, H);

  // High, thin cirrus first, then the big fair-weather cumulus.
  wisp(ctx, rnd, W * 0.62, H * 0.1, W * 0.35, 0.22);
  wisp(ctx, rnd, W * 0.22, H * 0.07, W * 0.22, 0.18);
  wisp(ctx, rnd, W * 0.88, H * 0.3, W * 0.2, 0.2);
  cumulus(ctx, rnd, W * 0.24, H * 0.25, W * 0.3, H * 0.11, 340);
  cumulus(ctx, rnd, W * 0.76, H * 0.19, W * 0.26, H * 0.085, 280);
  cumulus(ctx, rnd, W * 0.52, H * 0.33, W * 0.12, H * 0.04, 110);
  cumulus(ctx, rnd, W * 0.93, H * 0.42, W * 0.12, H * 0.035, 90);
  cumulus(ctx, rnd, W * 0.06, H * 0.44, W * 0.1, H * 0.03, 80);

  // Distant ridge on the right, softened by haze.
  ctx.beginPath();
  ctx.moveTo(W * 0.4, H);
  ctx.bezierCurveTo(W * 0.55, H * 0.6, W * 0.75, H * 0.57, W * 1.02, H * 0.6);
  ctx.lineTo(W, H);
  ctx.closePath();
  const far = ctx.createLinearGradient(0, H * 0.57, 0, H * 0.8);
  far.addColorStop(0, '#79b452');
  far.addColorStop(1, '#4d8c2e');
  ctx.fillStyle = far;
  ctx.fill();
  ctx.fillStyle = 'rgba(190,220,245,0.14)';
  ctx.fill();

  // The hill.
  const hill = new Path2D();
  hill.moveTo(-10, H * 0.8);
  hill.bezierCurveTo(W * 0.14, H * 0.66, W * 0.32, H * 0.56, W * 0.52, H * 0.585);
  hill.bezierCurveTo(W * 0.7, H * 0.61, W * 0.86, H * 0.72, W + 10, H * 0.7);
  hill.lineTo(W + 10, H + 10);
  hill.lineTo(-10, H + 10);
  hill.closePath();

  const grass = ctx.createLinearGradient(0, H * 0.56, 0, H);
  grass.addColorStop(0, '#8fd146');
  grass.addColorStop(0.18, '#62b02a');
  grass.addColorStop(0.55, '#3f8d1b');
  grass.addColorStop(1, '#2b6812');
  ctx.fillStyle = grass;
  ctx.fill(hill);

  ctx.save();
  ctx.clip(hill);

  // Sunlight from the upper left, shade falling off to the right.
  const light = ctx.createRadialGradient(W * 0.36, H * 0.6, 0, W * 0.36, H * 0.6, W * 0.55);
  light.addColorStop(0, 'rgba(225,255,130,0.32)');
  light.addColorStop(1, 'rgba(225,255,130,0)');
  ctx.fillStyle = light;
  ctx.fillRect(0, 0, W, H);
  const shade = ctx.createLinearGradient(W * 0.45, 0, W, 0);
  shade.addColorStop(0, 'rgba(0,40,0,0)');
  shade.addColorStop(1, 'rgba(0,40,0,0.18)');
  ctx.fillStyle = shade;
  ctx.fillRect(0, 0, W, H);

  // Wind patches.
  for (let i = 0; i < 46; i++) {
    const x = rnd() * W;
    const y = H * (0.62 + rnd() * 0.4);
    const r = W * (0.04 + rnd() * 0.1);
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    const dark = rnd() > 0.45;
    g.addColorStop(0, dark ? 'rgba(20,70,10,0.11)' : 'rgba(200,240,120,0.08)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(1.8, 0.45);
    ctx.translate(-x, -y);
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
    ctx.restore();
  }

  // Grass texture: denser and larger towards the viewer.
  const blades = Math.round((W * H) / 70);
  for (let i = 0; i < blades; i++) {
    const y = H * 0.55 + Math.pow(rnd(), 0.8) * H * 0.46;
    const x = rnd() * W;
    const depth = Math.min(1, Math.max(0, (y - H * 0.56) / (H * 0.44)));
    const len = 1 + depth * depth * 7 + rnd() * 2;
    const tone = rnd();
    ctx.fillStyle =
      tone < 0.45 ? `rgba(25,75,12,${0.1 + depth * 0.12})` : tone < 0.85 ? `rgba(120,190,50,${0.08 + depth * 0.1})` : `rgba(210,240,140,${0.07 + depth * 0.08})`;
    ctx.fillRect(x, y - len, 0.6 + depth * 1.1, len);
  }
  ctx.restore();

  // Rim light on the crest.
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(-10, H * 0.8);
  ctx.bezierCurveTo(W * 0.14, H * 0.66, W * 0.32, H * 0.56, W * 0.52, H * 0.585);
  ctx.bezierCurveTo(W * 0.7, H * 0.61, W * 0.86, H * 0.72, W + 10, H * 0.7);
  ctx.strokeStyle = 'rgba(225,250,170,0.45)';
  ctx.lineWidth = Math.max(1.5, H * 0.002);
  ctx.filter = 'blur(1.5px)';
  ctx.stroke();
  ctx.restore();

  // A whisper of vignette for depth.
  const v = ctx.createRadialGradient(W / 2, H * 0.45, Math.min(W, H) * 0.4, W / 2, H * 0.45, Math.max(W, H) * 0.8);
  v.addColorStop(0, 'rgba(0,0,0,0)');
  v.addColorStop(1, 'rgba(0,10,40,0.22)');
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, W, H);
};

/* ---------------- Blue Wave (XMB-style) ---------------- */

const wave: Painter = (ctx, W, H) => {
  const rnd = mulberry32(3);
  const bg = ctx.createLinearGradient(0, 0, W * 0.3, H);
  bg.addColorStop(0, '#0d2f86');
  bg.addColorStop(0.5, '#1a52bf');
  bg.addColorStop(1, '#0a2265');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);
  const glow = ctx.createRadialGradient(W * 0.3, H * 0.35, 0, W * 0.3, H * 0.35, W * 0.7);
  glow.addColorStop(0, 'rgba(110,180,255,0.35)');
  glow.addColorStop(1, 'rgba(110,180,255,0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);

  ctx.globalCompositeOperation = 'lighter';
  const sheet = (base: number, a1: number, f1: number, p1: number, a2: number, f2: number, p2: number, lines: number, twist: number) => {
    for (let k = 0; k < lines; k++) {
      const mid = 1 - Math.abs(k - lines / 2) / (lines / 2);
      ctx.beginPath();
      for (let x = -20; x <= W + 20; x += 6) {
        const u = (x / W) * Math.PI * 2;
        const y =
          H * base + a1 * H * Math.sin(u * f1 + p1 + k * twist) + a2 * H * Math.sin(u * f2 + p2 - k * twist * 1.6) + k * H * 0.0022;
        if (x === -20) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = `rgba(175,218,255,${0.035 + mid * mid * 0.13})`;
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }
  };
  // Wide soft glow under the ribbon.
  ctx.save();
  ctx.filter = `blur(${Math.round(H * 0.03)}px)`;
  sheet(0.57, 0.07, 0.9, 0.4, 0.035, 1.9, 1.2, 18, 0.05);
  ctx.restore();
  sheet(0.56, 0.07, 0.9, 0.4, 0.035, 1.9, 1.2, 90, 0.018);
  sheet(0.6, 0.05, 1.2, 2.2, 0.03, 0.6, 0.3, 60, 0.026);

  // Bright leading edge with a soft glow.
  ctx.save();
  ctx.shadowColor = 'rgba(160,220,255,0.9)';
  ctx.shadowBlur = 18;
  ctx.beginPath();
  for (let x = -20; x <= W + 20; x += 6) {
    const u = (x / W) * Math.PI * 2;
    const y = H * 0.56 + 0.07 * H * Math.sin(u * 0.9 + 0.4) + 0.035 * H * Math.sin(u * 1.9 + 1.2);
    if (x === -20) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = 'rgba(220,240,255,0.35)';
  ctx.lineWidth = 1.4;
  ctx.stroke();
  ctx.restore();

  // Drifting sparkles.
  for (let i = 0; i < 90; i++) {
    const x = rnd() * W;
    const u = (x / W) * Math.PI * 2;
    const y = H * 0.56 + 0.07 * H * Math.sin(u * 0.9 + 0.4) + gauss(rnd) * H * 0.12;
    const r = (0.4 + rnd() * 0.9) * (H / 900);
    const g = ctx.createRadialGradient(x, y, 0, x, y, r * 4);
    g.addColorStop(0, `rgba(220,240,255,${0.15 + rnd() * 0.3})`);
    g.addColorStop(1, 'rgba(220,240,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x - r * 4, y - r * 4, r * 8, r * 8);
  }
  ctx.globalCompositeOperation = 'source-over';

  const v = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.3, W / 2, H / 2, Math.max(W, H) * 0.75);
  v.addColorStop(0, 'rgba(0,0,0,0)');
  v.addColorStop(1, 'rgba(0,5,30,0.45)');
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, W, H);
};

export const wallpapers: Wallpaper[] = [
  { id: 'serenity', name: 'Serenity Hill', paint: serenity },
  { id: 'wave', name: 'Blue Wave', paint: wave },
  {
    id: 'graphite',
    name: 'Graphite',
    css: 'repeating-linear-gradient(0deg, rgba(255,255,255,.035) 0 1px, transparent 1px 3px), radial-gradient(ellipse at 50% 28%, #6f8fb2, #2c4561 62%, #141f2b)',
  },
  {
    id: 'dusk',
    name: 'Dusk',
    css: 'radial-gradient(ellipse at 75% 18%, rgba(255,214,150,.55), transparent 55%), radial-gradient(ellipse at 15% 85%, rgba(110,60,210,.55), transparent 60%), linear-gradient(160deg, #f0845a, #b9407a 45%, #33195f)',
  },
];

const byId = (id: string) => wallpapers.find((w) => w.id === id) ?? wallpapers[0];

const cache = new Map<string, string>();

/** Returns a CSS `background` value for the wallpaper at the given pixel size. */
export async function wallpaperBackground(id: string, width = window.innerWidth, height = window.innerHeight): Promise<string> {
  const wp = byId(id);
  if (!wp.paint) return wp.css!;
  const scale = Math.min(window.devicePixelRatio || 1, 2, 2880 / width);
  const W = Math.round(width * scale);
  const H = Math.round(height * scale);
  const key = `${wp.id}:${W}x${H}`;
  let url = cache.get(key);
  if (!url) {
    const canvas = document.createElement('canvas');
    canvas.width = W;
    canvas.height = H;
    wp.paint(canvas.getContext('2d')!, W, H);
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/jpeg', 0.92));
    url = blob ? URL.createObjectURL(blob) : canvas.toDataURL('image/jpeg', 0.92);
    cache.set(key, url);
  }
  return `url("${url}") center / cover no-repeat, #1a52bf`;
}

/** Small preview for the Settings picker (synchronous). */
export function wallpaperThumb(id: string, w = 240, h = 150): string {
  const wp = byId(id);
  if (!wp.paint) return wp.css!;
  const key = `thumb:${wp.id}`;
  let url = cache.get(key);
  if (!url) {
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    wp.paint(canvas.getContext('2d')!, w, h);
    url = canvas.toDataURL('image/jpeg', 0.85);
    cache.set(key, url);
  }
  return `url("${url}") center / cover`;
}
