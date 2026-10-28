/**
 * MWX 7 wallpaper engine: live, looping desktop backgrounds.
 *
 * - Photo wallpapers (Meadow, Sierra) play real time-lapse footage from `public/media/wallpapers/`.
 *   If the clip is missing they degrade to the poster with a slow Ken Burns drift and drifting
 *   cloud shadows; if the poster is missing too, to a hand-tuned gradient. Nothing ever shows broken.
 * - Generated wallpapers (Aero Aurora, Dusk Glass) are drawn live on a canvas at a reduced internal
 *   resolution and upscaled by the compositor, so they stay cheap on integrated GPUs.
 * - Every layer stops all work while the tab is hidden.
 */
import '../styles/wallpaper.css';

export interface Wallpaper {
  id: string;
  name: string;
}

export const wallpapers: Wallpaper[] = [
  { id: 'meadow', name: 'Meadow' },
  { id: 'aurora', name: 'Aero Aurora' },
  { id: 'sierra', name: 'Sierra' },
  { id: 'dusk', name: 'Dusk Glass' },
];

// Ids saved by earlier builds → their successor, so nobody boots into a blank desktop.
const LEGACY: Record<string, string> = { serenity: 'meadow', wave: 'aurora', graphite: 'sierra' };

/** Maps any stored id (including retired ones) to a wallpaper that exists. */
export function resolveWallpaperId(id: string | undefined): string {
  const key = id && LEGACY[id] ? LEGACY[id] : id;
  return wallpapers.some((w) => w.id === key) ? key! : 'meadow';
}

const media = (file: string) => `${import.meta.env.BASE_URL}media/wallpapers/${file}`;

/** Painted behind every photo wallpaper: what you see before the poster arrives, or if it never does. */
const FALLBACK: Record<string, string> = {
  meadow:
    'radial-gradient(120% 60% at 30% 0%, rgba(255,255,255,.35), transparent 60%),' +
    'linear-gradient(180deg, #1e5fc4 0%, #4f96e6 38%, #a9d3f6 58%, #7dbb45 60%, #4b922a 78%, #2d6a17 100%)',
  sierra:
    'radial-gradient(120% 60% at 70% 0%, rgba(255,255,255,.25), transparent 60%),' +
    'linear-gradient(180deg, #27466e 0%, #5f82aa 40%, #a9bccf 56%, #57677a 60%, #36414e 80%, #1f262e 100%)',
  aurora: 'linear-gradient(180deg, #071a52 0%, #1546a8 50%, #0a2468 100%)',
  dusk: 'linear-gradient(180deg, #2a1050 0%, #7a2a6e 52%, #e8704a 100%)',
};

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

/* ------------------------------------------------------------------ visibility */

// One listener for all layers; each layer pauses itself rather than relying on browser throttling,
// which still decodes video in some engines.
const visibilityHooks = new Set<(hidden: boolean) => void>();
document.addEventListener('visibilitychange', () => visibilityHooks.forEach((f) => f(document.hidden)));

/* ------------------------------------------------------------------ shared bits */

const smoothstep = (t: number) => t * t * (3 - 2 * t);
const TAU = Math.PI * 2;

/** Deterministic PRNG so generated wallpapers look the same on every boot. */
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let grainUrl = '';
/** A tile of fine luminance noise: dithers 8-bit gradient banding on big glossy surfaces. */
function grain(): string {
  if (grainUrl) return grainUrl;
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const ctx = c.getContext('2d');
  if (!ctx) return '';
  const img = ctx.createImageData(128, 128);
  const rnd = mulberry32(7);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = Math.round(rnd() * 255);
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
    img.data[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return (grainUrl = c.toDataURL('image/png'));
}

function grainLayer(): HTMLElement {
  const g = document.createElement('div');
  g.className = 'wp-grain';
  const url = grain();
  if (url) g.style.backgroundImage = `url("${url}")`;
  return g;
}

function probeImage(src: string): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img.naturalWidth > 0);
    img.onerror = () => resolve(false);
    img.src = src;
  });
}

interface Layer {
  el: HTMLElement;
  destroy(): void;
}

/* ------------------------------------------------------------------ photo wallpapers */

function photoLayer(id: string): Layer {
  const el = document.createElement('div');
  el.className = `wp-layer wp-photo wp-${id}`;
  el.style.background = FALLBACK[id];

  const still = document.createElement('div');
  still.className = 'wp-still';
  const shadows = document.createElement('div');
  shadows.className = 'wp-cloud-shadows';
  const video = document.createElement('video');
  video.className = 'wp-video';
  video.muted = true;
  video.defaultMuted = true;
  video.loop = true;
  video.playsInline = true;
  video.autoplay = !reducedMotion();
  video.preload = 'auto';
  video.setAttribute('muted', '');
  video.setAttribute('playsinline', '');
  video.setAttribute('aria-hidden', 'true');
  video.disablePictureInPicture = true;
  video.poster = media(`${id}.jpg`);
  el.append(still, shadows, video);

  let dead = false;
  let videoOk = true;

  void probeImage(media(`${id}.jpg`)).then((ok) => {
    if (dead || !ok) return;
    still.style.backgroundImage = `url("${media(`${id}.jpg`)}")`;
    still.classList.add('on');
  });

  // Without footage the still alone would look frozen; a slow drift plus cloud shadows keeps it alive.
  const animateStill = () => {
    el.classList.add('wp-kenburns');
    video.remove();
  };

  video.addEventListener('playing', () => video.classList.add('on'));
  // `autoplay` ignores page visibility; a layer created in a background tab must stay paused.
  video.addEventListener('play', () => {
    if (document.hidden) video.pause();
  });
  video.addEventListener('error', () => {
    videoOk = false;
    animateStill();
  });

  const tryPlay = () => {
    if (dead || !videoOk || document.hidden || reducedMotion()) return;
    video.play().catch(() => {
      // Autoplay refused (rare for muted video): drift the still and retry on the first gesture.
      if (!videoOk) return;
      el.classList.add('wp-kenburns');
      const retry = () => {
        el.classList.remove('wp-kenburns');
        tryPlay();
      };
      window.addEventListener('pointerdown', retry, { once: true, capture: true });
    });
  };

  video.src = media(`${id}.mp4`);
  tryPlay();

  const onVis = (hidden: boolean) => {
    el.classList.toggle('wp-paused', hidden);
    if (hidden) video.pause();
    else tryPlay();
  };
  visibilityHooks.add(onVis);

  return {
    el,
    destroy() {
      dead = true;
      visibilityHooks.delete(onVis);
      video.pause();
      video.removeAttribute('src');
      video.load(); // releases the decoder immediately instead of on GC
      el.remove();
    },
  };
}

/* ------------------------------------------------------------------ canvas wallpapers */

interface Renderer {
  /** Resize internal buffers to a CSS size; the renderer picks its own internal resolution. */
  resize(cssW: number, cssH: number): void;
  draw(t: number): void;
  readonly canvas: HTMLCanvasElement;
  /** Minimum milliseconds between frames. */
  frameMs: number;
}

function canvas2d(w = 1, h = 1): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return [c, c.getContext('2d', { alpha: false })!];
}

/**
 * Aero Aurora — a luminous ribbon of hairlines folding over deep blue, after the console-menu wave.
 * Each line is a sum of slow travelling sines; lines in a sheet share the carrier and differ in a
 * "twist" term, so the sheet pinches and folds and additive blending brightens the folds on its own.
 */
function auroraRenderer(scale = 0.6, maxW = 1280): Renderer {
  const [canvas, ctx] = canvas2d();
  const [bg, bgx] = canvas2d();
  const glow = document.createElement('canvas');
  const gx = glow.getContext('2d')!;
  const sprite = document.createElement('canvas');
  let W = 1;
  let H = 1;

  const rnd = mulberry32(31);
  const sparkles = Array.from({ length: 90 }, () => ({
    x: rnd(),
    off: (rnd() + rnd() + rnd() - 1.5) * 0.55,
    speed: 0.004 + rnd() * 0.01,
    size: 0.5 + rnd() * rnd() * 1.6,
    tw: 0.4 + rnd() * 1.4,
    ph: rnd() * TAU,
    a: 0.25 + rnd() * 0.6,
  }));

  // Two sheets, deliberately incommensurate speeds so the shape never visibly repeats.
  const sheets = [
    { lines: 36, a1: 0.075, f1: 0.95, s1: 0.055, p1: 0.6, a2: 0.032, f2: 2.1, s2: -0.083, p2: 1.9, thick: 0.07, tf: 0.75, ts: 0.041, tp: 0.3, alpha: 0.085 },
    { lines: 28, a1: 0.062, f1: 1.25, s1: -0.047, p1: 2.4, a2: 0.028, f2: 0.62, s2: 0.067, p2: 0.4, thick: 0.05, tf: 1.1, ts: -0.036, tp: 2.0, alpha: 0.07 },
  ];

  const centre = (s: (typeof sheets)[number], u: number, t: number) =>
    s.a1 * Math.sin(u * s.f1 + t * s.s1 * TAU + s.p1) + s.a2 * Math.sin(u * s.f2 + t * s.s2 * TAU + s.p2);

  const paintBackground = () => {
    const g = bgx.createLinearGradient(0, 0, W * 0.25, H);
    g.addColorStop(0, '#06184d');
    g.addColorStop(0.42, '#1446a6');
    g.addColorStop(0.58, '#1850b6');
    g.addColorStop(1, '#071d5c');
    bgx.fillStyle = g;
    bgx.fillRect(0, 0, W, H);
    // Broad haze along the ribbon's path keeps the centre of the screen luminous.
    const haze = bgx.createRadialGradient(W * 0.5, H * 0.5, 0, W * 0.5, H * 0.5, W * 0.62);
    haze.addColorStop(0, 'rgba(90,160,255,0.26)');
    haze.addColorStop(0.55, 'rgba(60,120,230,0.08)');
    haze.addColorStop(1, 'rgba(40,90,200,0)');
    bgx.save();
    bgx.translate(0, H * 0.5);
    bgx.scale(1, 0.55);
    bgx.translate(0, -H * 0.5);
    bgx.fillStyle = haze;
    bgx.fillRect(0, -H, W, H * 3);
    bgx.restore();
    const v = bgx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35, W / 2, H / 2, Math.hypot(W, H) * 0.55);
    v.addColorStop(0, 'rgba(0,4,24,0)');
    v.addColorStop(1, 'rgba(0,4,24,0.5)');
    bgx.fillStyle = v;
    bgx.fillRect(0, 0, W, H);
  };

  const paintSprite = () => {
    const r = Math.max(4, Math.round(H / 90));
    sprite.width = sprite.height = r * 2;
    const c = sprite.getContext('2d')!;
    const g = c.createRadialGradient(r, r, 0, r, r, r);
    g.addColorStop(0, 'rgba(235,246,255,1)');
    g.addColorStop(0.18, 'rgba(190,225,255,0.55)');
    g.addColorStop(1, 'rgba(150,200,255,0)');
    c.fillStyle = g;
    c.fillRect(0, 0, r * 2, r * 2);
  };

  return {
    canvas,
    frameMs: 1000 / 60,
    resize(cssW, cssH) {
      const k = Math.min(scale, maxW / Math.max(1, cssW));
      W = Math.max(2, Math.round(cssW * k));
      H = Math.max(2, Math.round(cssH * k));
      canvas.width = bg.width = W;
      canvas.height = bg.height = H;
      // The glow is rendered tiny and upscaled: bilinear filtering does the blur for free (canvas `filter` costs ~4 ms).
      glow.width = Math.max(2, Math.round(W / 12));
      glow.height = Math.max(2, Math.round(H / 12));
      paintBackground();
      paintSprite();
    },
    draw(t) {
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
      ctx.drawImage(bg, 0, 0);
      const cy = H * 0.5;
      const step = Math.max(4, Math.round(W / 150));

      // Glow pass.
      const gw = glow.width;
      const gh = glow.height;
      gx.clearRect(0, 0, gw, gh);
      gx.globalCompositeOperation = 'lighter';
      for (const s of sheets) {
        for (const [width, alpha] of [
          [gh * 0.22, 0.09],
          [gh * 0.08, 0.15],
        ]) {
          gx.beginPath();
          for (let x = -2; x <= gw + 2; x += 1) {
            const u = (x / gw) * TAU;
            const y = gh * 0.5 + gh * centre(s, u, t);
            if (x === -2) gx.moveTo(x, y);
            else gx.lineTo(x, y);
          }
          gx.lineWidth = width;
          gx.strokeStyle = `rgba(120,185,255,${alpha})`;
          gx.stroke();
        }
      }
      ctx.globalCompositeOperation = 'lighter';
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(glow, 0, 0, W, H);

      // Hairline sheets.
      ctx.lineWidth = Math.max(0.7, H / 900);
      for (const s of sheets) {
        for (let i = 0; i < s.lines; i++) {
          const k = i / (s.lines - 1) - 0.5;
          // Edge lines a touch brighter, like light catching the rim of a sheet of silk.
          const rim = Math.pow(Math.abs(k) * 2, 4);
          ctx.strokeStyle = `rgba(185,222,255,${s.alpha * (0.75 + rim * 1.1)})`;
          ctx.beginPath();
          for (let x = -step; x <= W + step; x += step) {
            const u = (x / W) * TAU;
            const twist = Math.sin(u * s.tf + t * s.ts * TAU + s.tp + k * 0.9);
            const y = cy + H * (centre(s, u, t) + k * s.thick * twist + k * 0.006);
            if (x === -step) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
      }

      // Sparkles ride the ribbon and drift slowly leftwards.
      const sw = sprite.width;
      const s0 = sheets[0];
      for (const p of sparkles) {
        const x = (((p.x - t * p.speed) % 1) + 1) % 1;
        const u = x * TAU;
        const y = cy + H * (centre(s0, u, t) + p.off * 0.16);
        const tw = 0.5 + 0.5 * Math.sin(t * p.tw * TAU * 0.25 + p.ph);
        // Fade in/out near the screen edges so wrap-around is invisible.
        const edge = smoothstep(Math.min(1, Math.min(x, 1 - x) * 8));
        ctx.globalAlpha = p.a * tw * tw * edge;
        const d = sw * p.size;
        ctx.drawImage(sprite, x * W - d / 2, y - d / 2, d, d);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';
    },
  };
}

/**
 * Dusk Glass — an aubergine-to-ember sky whose light breathes over a 80 s cycle.
 * Drawn on a tiny canvas (colour fields need no resolution) and stretched by the compositor;
 * every motion term is a whole harmonic of the cycle, so the loop is exact.
 */
function duskRenderer(): Renderer {
  const [canvas, ctx] = canvas2d(192, 108);
  const PERIOD = 80;
  const mix = (a: number[], b: number[], k: number) => a.map((v, i) => Math.round(v + (b[i] - v) * k));
  const rgb = (c: number[], a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  const top = [
    [34, 10, 66],
    [48, 14, 78],
  ];
  const mid = [
    [122, 38, 112],
    [146, 44, 104],
  ];
  const low = [
    [232, 108, 70],
    [240, 132, 74],
  ];

  return {
    canvas,
    frameMs: 1000 / 20,
    resize() {
      /* fixed internal size by design */
    },
    draw(t) {
      const W = canvas.width;
      const H = canvas.height;
      const ph = ((t % PERIOD) / PERIOD) * TAU;
      const k = 0.5 - 0.5 * Math.cos(ph);
      const g = ctx.createLinearGradient(0, 0, W * 0.18, H);
      g.addColorStop(0, rgb(mix(top[0], top[1], k)));
      g.addColorStop(0.5 + 0.04 * Math.sin(ph), rgb(mix(mid[0], mid[1], 1 - k)));
      g.addColorStop(1, rgb(mix(low[0], low[1], k)));
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);

      const blob = (x: number, y: number, r: number, c: number[], a: number) => {
        const rg = ctx.createRadialGradient(x * W, y * H, 0, x * W, y * H, r * W);
        rg.addColorStop(0, rgb(c, a));
        rg.addColorStop(1, rgb(c, 0));
        ctx.fillStyle = rg;
        ctx.fillRect(0, 0, W, H);
      };
      ctx.globalCompositeOperation = 'screen';
      // Low sun glow wandering along the horizon.
      blob(0.66 + 0.1 * Math.sin(ph), 1.02 + 0.03 * Math.sin(ph * 2), 0.55, [255, 170, 96], 0.55 + 0.1 * Math.sin(ph * 2 + 1));
      // Rose band under the clouds.
      blob(0.3 + 0.08 * Math.cos(ph), 0.66 + 0.04 * Math.sin(ph), 0.5, [236, 90, 120], 0.28);
      ctx.globalCompositeOperation = 'source-over';
      // Cool violet from the upper left, the night arriving.
      blob(0.12 + 0.06 * Math.sin(ph + 2), 0.06, 0.62, [70, 36, 150], 0.5 + 0.12 * Math.cos(ph));
      blob(0.92, 0.1 + 0.05 * Math.cos(ph * 2), 0.4, [40, 12, 70], 0.45);
    },
  };
}

function canvasLayer(id: string, make: () => Renderer): Layer {
  const el = document.createElement('div');
  el.className = `wp-layer wp-canvas wp-${id}`;
  el.style.background = FALLBACK[id];
  const r = make();
  r.canvas.className = 'wp-canvas-el';
  el.append(r.canvas, grainLayer());
  if (id === 'dusk') {
    for (const n of ['wp-glass a', 'wp-glass b', 'wp-glass c']) {
      const pane = document.createElement('div');
      pane.className = n;
      el.append(pane);
    }
  }

  // Start each boot at a random point so the wallpaper never "restarts" visibly.
  const t0 = performance.now() - Math.random() * 60_000;
  let raf = 0;
  let last = 0;
  let cost = 0;
  let frameMs = r.frameMs;
  let w = 0;
  let h = 0;

  const size = () => {
    const nw = el.clientWidth || window.innerWidth;
    const nh = el.clientHeight || window.innerHeight;
    if (nw === w && nh === h) return;
    w = nw;
    h = nh;
    r.resize(w, h);
    r.draw((performance.now() - t0) / 1000);
  };

  const frame = (now: number) => {
    raf = requestAnimationFrame(frame);
    if (now - last < frameMs - 1) return;
    last = now;
    const a = performance.now();
    r.draw((now - t0) / 1000);
    // If a frame costs more than ~6 ms the machine is struggling: halve the rate rather than jank the UI.
    cost = cost * 0.95 + (performance.now() - a) * 0.05;
    if (cost > 6 && frameMs < 1000 / 30) frameMs = 1000 / 30;
  };

  const start = () => {
    if (raf || document.hidden || reducedMotion()) return;
    last = 0;
    raf = requestAnimationFrame(frame);
  };
  const stop = () => {
    cancelAnimationFrame(raf);
    raf = 0;
  };

  const ro = new ResizeObserver(size);
  ro.observe(el);
  requestAnimationFrame(size);
  size();
  start();

  const onVis = (hidden: boolean) => (hidden ? stop() : start());
  visibilityHooks.add(onVis);

  return {
    el,
    destroy() {
      stop();
      ro.disconnect();
      visibilityHooks.delete(onVis);
      el.remove();
    },
  };
}

const RENDERERS: Record<string, () => Renderer> = {
  aurora: () => auroraRenderer(),
  dusk: () => duskRenderer(),
};

/* ------------------------------------------------------------------ public API */

/** Mounts a live, animated wallpaper into `host` (absolutely positioned, fills it). */
export function createWallpaperLayer(id: string): Layer {
  const key = resolveWallpaperId(id);
  return RENDERERS[key] ? canvasLayer(key, RENDERERS[key]) : photoLayer(key);
}

const stills = new Map<string, string>();

/** A single frame of a generated wallpaper as a data URL (for thumbnails and the logon screen). */
function snapshot(id: string, w: number, h: number, scale: number): string {
  const key = `${id}:${w}x${h}`;
  let url = stills.get(key);
  if (!url) {
    const r = id === 'aurora' ? auroraRenderer(scale, 4096) : duskRenderer();
    r.resize(w, h);
    r.draw(id === 'aurora' ? 12 : 30);
    url = r.canvas.toDataURL('image/jpeg', 0.88);
    stills.set(key, url);
  }
  return url;
}

/** CSS background value for small previews in Settings (synchronous). */
export function wallpaperThumb(id: string): string {
  const key = resolveWallpaperId(id);
  if (RENDERERS[key]) return `url("${snapshot(key, 240, 150, 1)}") center / cover, ${FALLBACK[key]}`;
  return `url("${media(`${key}-thumb.jpg`)}") center / cover, ${FALLBACK[key]}`;
}

/**
 * Static CSS background for full-screen surfaces that can't host a live layer yet (the logon screen).
 * @deprecated mount `createWallpaperLayer` instead.
 */
export async function wallpaperBackground(id: string): Promise<string> {
  const key = resolveWallpaperId(id);
  if (RENDERERS[key]) {
    const w = Math.min(window.innerWidth, 1920);
    const h = Math.round((w * window.innerHeight) / Math.max(1, window.innerWidth));
    return `url("${snapshot(key, w, h, 1)}") center / cover no-repeat, ${FALLBACK[key]}`;
  }
  return `url("${media(`${key}.jpg`)}") center / cover no-repeat, ${FALLBACK[key]}`;
}
