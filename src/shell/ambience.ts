/**
 * Desktop ambience: a quiet, wallpaper-matched soundscape that plays only while the desktop itself
 * has focus (no active window), fades in and out, and goes silent when system sounds are off or
 * the tab is hidden. Everything is synthesized with Web Audio — no recordings.
 *
 * Owns its own AudioContext (created on the first user gesture) so it never competes with the
 * system-sound engine's master volume or reverb.
 */
import { bus } from '../core/events';
import { settings } from '../core/settings';
import { resolveWallpaperId } from './wallpapers';

/** Ambience sits far under UI sounds: this is the master level at volume 1.0. */
const LEVEL = 0.6;
const FADE = 1.5;

type Scene = { out: GainNode; stop(): void };
type SceneFactory = (ac: AudioContext, dest: AudioNode, space: AudioNode) => Scene;

const rand = (a: number, b: number) => a + Math.random() * (b - a);

/* ------------------------------------------------------------------ building blocks */

const buffers = new WeakMap<BaseAudioContext, Record<string, AudioBuffer>>();

/** Long, decorrelated stereo noise beds. Long enough that the loop point is inaudible. */
function noise(ac: BaseAudioContext, kind: 'pink' | 'brown' | 'white'): AudioBuffer {
  let cache = buffers.get(ac);
  if (!cache) buffers.set(ac, (cache = {}));
  if (cache[kind]) return cache[kind];
  const len = Math.floor(ac.sampleRate * 11.3);
  const buf = ac.createBuffer(2, len, ac.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0, last = 0;
    for (let i = 0; i < len; i++) {
      const w = Math.random() * 2 - 1;
      if (kind === 'white') d[i] = w * 0.5;
      else if (kind === 'brown') {
        last = (last + 0.02 * w) / 1.02;
        d[i] = last * 3.5;
      } else {
        // Paul Kellet's pink filter: natural 1/f spectrum, the basis of believable wind.
        b0 = 0.99886 * b0 + w * 0.0555179;
        b1 = 0.99332 * b1 + w * 0.0750759;
        b2 = 0.969 * b2 + w * 0.153852;
        b3 = 0.8665 * b3 + w * 0.3104856;
        b4 = 0.55 * b4 + w * 0.5329522;
        b5 = -0.7616 * b5 - w * 0.016898;
        d[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11;
        b6 = w * 0.115926;
      }
    }
    // Cross-fade the tail into the head so the loop has no click.
    const x = Math.floor(ac.sampleRate * 0.25);
    for (let i = 0; i < x; i++) {
      const k = i / x;
      d[i] = d[i] * k + d[len - x + i] * (1 - k);
    }
  }
  return (cache[kind] = buf);
}

function source(ac: BaseAudioContext, kind: 'pink' | 'brown' | 'white'): AudioBufferSourceNode {
  const s = ac.createBufferSource();
  s.buffer = noise(ac, kind);
  s.loop = true;
  s.loopEnd = s.buffer.duration - 0.25;
  // Random start offset so two layers using the same buffer never phase together.
  s.start(ac.currentTime, rand(0, s.buffer.duration - 1));
  return s;
}

function filter(ac: BaseAudioContext, type: BiquadFilterType, freq: number, q = 0.7): BiquadFilterNode {
  const f = ac.createBiquadFilter();
  f.type = type;
  f.frequency.value = freq;
  f.Q.value = q;
  return f;
}

function gain(ac: BaseAudioContext, v: number): GainNode {
  const g = ac.createGain();
  g.gain.value = v;
  return g;
}

/**
 * Smooth random control signal in [-1, 1]: random targets every 1/rate s, cosine-interpolated.
 * Used for flutter and gusting where an LFO would sound mechanical.
 */
function flutter(ac: BaseAudioContext, param: AudioParam, depth: number, rate: number): AudioNode[] {
  // Control-rate buffer: 3 kHz is the lowest rate every engine accepts, keeping 37 s tiny.
  const seconds = 37;
  let buf: AudioBuffer;
  try {
    buf = ac.createBuffer(1, 3000 * seconds, 3000);
  } catch {
    buf = ac.createBuffer(1, Math.round(ac.sampleRate * seconds), ac.sampleRate);
  }
  const len = buf.length;
  const d = buf.getChannelData(0);
  const pts = Math.max(2, Math.round(seconds * rate));
  const v = Array.from({ length: pts }, () => Math.random() * 2 - 1);
  for (let i = 0; i < len; i++) {
    const x = (i / len) * pts;
    const a = Math.floor(x);
    const k = 0.5 - 0.5 * Math.cos((x - a) * Math.PI);
    d[i] = v[a % pts] * (1 - k) + v[(a + 1) % pts] * k; // wraps to v[0]: seamless loop
  }
  const s = ac.createBufferSource();
  s.buffer = buf;
  s.loop = true;
  s.start(ac.currentTime, Math.random() * seconds);
  const g = gain(ac, depth);
  s.connect(g).connect(param);
  return [s, g];
}

function impulse(ac: BaseAudioContext, seconds: number, decay: number): AudioBuffer {
  const len = Math.floor(ac.sampleRate * seconds);
  const buf = ac.createBuffer(2, len, ac.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    // Darker tail: a one-pole lowpass whose cutoff falls as the reverb decays, like real air absorption.
    let y = 0;
    for (let i = 0; i < len; i++) {
      const k = i / len;
      const a = 0.15 + 0.8 * k;
      y = y * a + (Math.random() * 2 - 1) * (1 - a);
      d[i] = y * Math.pow(1 - k, decay) * (i < 60 ? i / 60 : 1);
    }
  }
  return buf;
}

/**
 * Wind: pink noise through a resonant band whose level and centre frequency follow random gusts.
 * Gusts are scheduled as exponential approaches to random targets, so the swell never repeats.
 */
interface WindOpts {
  base: number; // centre frequency at calm
  spread: number; // how far the band opens in a gust (Hz)
  q: number;
  calm: number; // level between gusts
  gust: [number, number]; // range of gust peak level
  every: [number, number]; // seconds between gust targets
  strongChance?: number; // chance a gust is a strong one
  rustle?: number; // level of the high grass/leaf layer
  whistle?: number; // narrow high-altitude whistle
  pan?: number;
}

function wind(ac: AudioContext, dest: AudioNode, space: AudioNode, o: WindOpts): { nodes: AudioNode[]; tick(): void } {
  const nodes: AudioNode[] = [];
  const src = source(ac, 'pink');
  const hp = filter(ac, 'highpass', 70, 0.5);
  const band = filter(ac, 'bandpass', o.base, o.q);
  const body = filter(ac, 'lowpass', o.base * 3, 0.5);
  const amp = gain(ac, o.calm);
  const pan = ac.createStereoPanner();
  pan.pan.value = o.pan ?? 0;
  src.connect(hp).connect(band).connect(body).connect(amp).connect(pan);
  pan.connect(dest);
  const send = gain(ac, 0.35);
  pan.connect(send).connect(space);
  nodes.push(src, hp, band, body, amp, pan, send);
  nodes.push(...flutter(ac, band.frequency, o.base * 0.3, 0.7));

  let rustleAmp: GainNode | null = null;
  if (o.rustle) {
    // Grass and leaves: bright, dense, flickering detail that only really appears inside a gust.
    const r = source(ac, 'white');
    const rhp = filter(ac, 'highpass', 2400, 0.6);
    const rlp = filter(ac, 'lowpass', 7500, 0.5);
    const flick = gain(ac, 0.55);
    rustleAmp = gain(ac, 0);
    r.connect(rhp).connect(rlp).connect(flick).connect(rustleAmp).connect(dest);
    rustleAmp.connect(send);
    nodes.push(r, rhp, rlp, flick, rustleAmp);
    // Fast, irregular flicker (~6-18 Hz) — the "many blades" texture.
    nodes.push(...flutter(ac, flick.gain, 0.45, 9));
  }

  let whistle: { f: BiquadFilterNode; g: GainNode } | null = null;
  if (o.whistle) {
    const w = source(ac, 'pink');
    const f = filter(ac, 'bandpass', 900, 18);
    const g = gain(ac, 0);
    const p = ac.createStereoPanner();
    p.pan.value = -(o.pan ?? 0) * 1.5;
    w.connect(f).connect(g).connect(p).connect(dest);
    p.connect(send);
    nodes.push(w, f, g, p);
    whistle = { f, g };
  }

  let next = 0;
  return {
    nodes,
    tick() {
      const now = ac.currentTime;
      if (now < next) return;
      const strong = Math.random() < (o.strongChance ?? 0.12);
      const calm = Math.random() < 0.35;
      const lvl = calm ? o.calm * rand(0.7, 1.1) : rand(o.gust[0], o.gust[1]) * (strong ? 1.6 : 1);
      const rise = calm ? rand(1.2, 2.5) : strong ? rand(0.5, 0.9) : rand(0.8, 1.8);
      const k = Math.min(1, (lvl - o.calm) / Math.max(1e-4, o.gust[1] * 1.6 - o.calm));
      amp.gain.setTargetAtTime(lvl, now, rise);
      band.frequency.setTargetAtTime(o.base + o.spread * Math.max(0, k), now, rise * 1.2);
      body.frequency.setTargetAtTime(o.base * (2.4 + 3 * Math.max(0, k)), now, rise);
      rustleAmp?.gain.setTargetAtTime(o.rustle! * Math.max(0, k) * Math.max(0, k), now, rise * 0.8);
      if (whistle) {
        whistle.g.gain.setTargetAtTime(o.whistle! * Math.max(0, k - 0.25), now, rise * 1.4);
        whistle.f.frequency.setTargetAtTime(rand(700, 1300) * (1 + k * 0.3), now, rise * 2);
      }
      next = now + rand(o.every[0], o.every[1]) * (strong ? 0.7 : 1);
    },
  };
}

function scene(ac: AudioContext, build: (dest: AudioNode, nodes: AudioNode[]) => (() => void) | void): Scene {
  const out = gain(ac, 0);
  const nodes: AudioNode[] = [];
  const tick = build(out, nodes);
  const timer = tick ? window.setInterval(tick, 200) : 0;
  tick?.();
  return {
    out,
    stop() {
      clearInterval(timer);
      for (const n of nodes) {
        if (n instanceof AudioScheduledSourceNode) {
          try {
            n.stop();
          } catch {
            /* already stopped */
          }
        }
        n.disconnect();
      }
      out.disconnect();
    },
  };
}

/* ------------------------------------------------------------------ scenes */

const meadow: SceneFactory = (ac, dest, space) => {
  const s = scene(ac, (out, nodes) => {
    const main = wind(ac, out, space, { base: 380, spread: 520, q: 0.8, calm: 0.05, gust: [0.12, 0.26], every: [2.5, 6], rustle: 0.05, pan: -0.15 });
    // A second, distant layer on the other side gives width without obvious stereo tricks.
    const far = wind(ac, out, space, { base: 260, spread: 260, q: 0.6, calm: 0.04, gust: [0.06, 0.12], every: [4, 9], pan: 0.35 });
    nodes.push(...main.nodes, ...far.nodes);
    return () => {
      main.tick();
      far.tick();
    };
  });
  s.out.connect(dest);
  return s;
};

const sierra: SceneFactory = (ac, dest, space) => {
  const s = scene(ac, (out, nodes) => {
    const ridge = wind(ac, out, space, {
      base: 520,
      spread: 900,
      q: 0.9,
      calm: 0.04,
      gust: [0.1, 0.24],
      every: [2, 5.5],
      strongChance: 0.22,
      whistle: 0.05,
      rustle: 0.015,
      pan: 0.2,
    });
    // Low, distant roar of air over the valley.
    const src = source(ac, 'brown');
    const lp = filter(ac, 'lowpass', 220, 0.5);
    const g = gain(ac, 0.07);
    src.connect(lp).connect(g).connect(out);
    nodes.push(...ridge.nodes, src, lp, g, ...flutter(ac, g.gain, 0.04, 0.12));
    return ridge.tick;
  });
  s.out.connect(dest);
  return s;
};

const aurora: SceneFactory = (ac, dest, space) => {
  const s = scene(ac, (out, nodes) => {
    // Resonant "breath" voices: noise rung through narrow bands on an open, unresolved voicing.
    const pitches = [146.83, 220, 293.66, 329.63, 440, 554.37, 659.25];
    const bus = gain(ac, 1);
    const hp = filter(ac, 'highpass', 110, 0.5);
    bus.connect(hp);
    hp.connect(gain(ac, 0.5)).connect(out);
    const send = gain(ac, 1.1);
    hp.connect(send).connect(space);
    nodes.push(bus, hp, send);
    pitches.forEach((hz, i) => {
      const src = source(ac, 'pink');
      const f = filter(ac, 'bandpass', hz, 60 + i * 12);
      const g = gain(ac, 0);
      const p = ac.createStereoPanner();
      p.pan.value = ((i % 2 ? 1 : -1) * (0.2 + i * 0.08));
      src.connect(f).connect(g).connect(p).connect(bus);
      // Each voice swells on its own slow cycle so the chord keeps re-voicing itself.
      const lfo = ac.createOscillator();
      lfo.frequency.value = 1 / rand(14, 31);
      const depth = gain(ac, 0.9 / (1 + i * 0.25));
      lfo.connect(depth).connect(g.gain);
      g.gain.value = 0.9 / (1 + i * 0.25);
      lfo.start();
      nodes.push(src, f, g, p, lfo, depth);
    });
    // A soft whoosh that rises and falls like the wave rolling past (~24 s, the ribbon's tempo).
    const air = source(ac, 'pink');
    const sweep = filter(ac, 'bandpass', 900, 1.4);
    const ag = gain(ac, 0.022);
    air.connect(sweep).connect(ag);
    ag.connect(out);
    ag.connect(send);
    const sl = ac.createOscillator();
    sl.frequency.value = 1 / 24;
    const sd = gain(ac, 600);
    sl.connect(sd).connect(sweep.frequency);
    const al = ac.createOscillator();
    al.frequency.value = 1 / 24;
    const ad = gain(ac, 0.016);
    al.connect(ad).connect(ag.gain);
    sl.start();
    al.start();
    nodes.push(air, sweep, ag, sl, sd, al, ad);
    // High glints: very quiet sine partials that bloom in and out, the sparkles of the wave.
    let next = 0;
    return () => {
      const now = ac.currentTime;
      if (now < next) return;
      next = now + rand(2.5, 6);
      const o = ac.createOscillator();
      o.type = 'sine';
      o.frequency.value = [1174.66, 1318.51, 1760, 2217.46, 2637.02][Math.floor(rand(0, 5))];
      const g = gain(ac, 0);
      const p = ac.createStereoPanner();
      p.pan.value = rand(-0.7, 0.7);
      o.connect(g).connect(p).connect(send);
      g.gain.setTargetAtTime(0.004, now, 0.6);
      g.gain.setTargetAtTime(0, now + 1.6, 1.4);
      o.start(now);
      o.stop(now + 9);
      o.onended = () => p.disconnect();
    };
  });
  s.out.connect(dest);
  return s;
};

const dusk: SceneFactory = (ac, dest, space) => {
  const s = scene(ac, (out, nodes) => {
    const breeze = wind(ac, out, space, { base: 300, spread: 260, q: 0.6, calm: 0.07, gust: [0.12, 0.2], every: [4, 9], rustle: 0.012 });
    nodes.push(...breeze.nodes);
    // Crickets: a 4.6 kHz-ish carrier gated into short pulses, in phrases, far away (lowpassed, mostly reverb).
    const far = filter(ac, 'lowpass', 5200, 0.5);
    const dry = gain(ac, 0.25);
    const wet = gain(ac, 1);
    far.connect(dry).connect(out);
    far.connect(wet).connect(space);
    nodes.push(far, dry, wet);
    const crickets = [
      { hz: 4520, pan: -0.55, rate: 0.032, pulses: 3, level: 0.022, next: 0 },
      { hz: 4870, pan: 0.6, rate: 0.028, pulses: 2, level: 0.016, next: 0 },
      { hz: 4280, pan: 0.1, rate: 0.036, pulses: 4, level: 0.011, next: 0 },
    ];
    const pans = crickets.map((c) => {
      const p = ac.createStereoPanner();
      p.pan.value = c.pan;
      p.connect(far);
      nodes.push(p);
      return p;
    });
    return () => {
      breeze.tick();
      const now = ac.currentTime;
      crickets.forEach((c, i) => {
        if (now + 0.4 < c.next) return;
        const t0 = Math.max(now + 0.05, c.next);
        // A phrase of chirps, then a rest, like real field crickets.
        const chirps = Math.floor(rand(3, 9));
        const gap = rand(0.42, 0.62);
        const o = ac.createOscillator();
        o.frequency.value = c.hz * rand(0.99, 1.01);
        const g = gain(ac, 0);
        o.connect(g).connect(pans[i]);
        for (let k = 0; k < chirps; k++) {
          for (let p = 0; p < c.pulses; p++) {
            const t = t0 + k * gap + p * c.rate;
            g.gain.setValueAtTime(0, t);
            g.gain.linearRampToValueAtTime(c.level, t + 0.004);
            g.gain.exponentialRampToValueAtTime(c.level * 0.3, t + c.rate * 0.6);
            g.gain.linearRampToValueAtTime(0, t + c.rate * 0.8);
          }
        }
        const end = t0 + chirps * gap;
        o.start(t0);
        o.stop(end + 0.1);
        o.onended = () => g.disconnect();
        c.next = end + rand(2, 9);
      });
    };
  });
  s.out.connect(dest);
  return s;
};

const SCENES: Record<string, SceneFactory> = { meadow, sierra, aurora, dusk };

/* ------------------------------------------------------------------ controller */

let mounted = false;

export function mountAmbience(): void {
  if (mounted) return;
  mounted = true;

  let ac: AudioContext | null = null;
  let master: GainNode | null = null;
  let space: ConvolverNode | null = null;
  let current: { id: string; scene: Scene } | null = null;
  let desktopFocused = true;
  let overlay = !!document.querySelector('.screen');
  let stopTimer = 0;

  const wanted = () => {
    const s = settings.get();
    return !!ac && s.sounds && s.volume > 0 && desktopFocused && !overlay && !document.hidden;
  };

  const ensure = (): boolean => {
    if (ac) return true;
    try {
      ac = new AudioContext({ latencyHint: 'playback' });
    } catch {
      return false;
    }
    master = gain(ac, 0);
    // Gentle bus compression keeps gust peaks from ever poking out over the UI.
    const comp = ac.createDynamicsCompressor();
    comp.threshold.value = -30;
    comp.ratio.value = 3;
    comp.attack.value = 0.2;
    comp.release.value = 1;
    master.connect(comp).connect(ac.destination);
    space = ac.createConvolver();
    space.buffer = impulse(ac, 3.6, 2.2);
    space.connect(gain(ac, 0.5)).connect(master);
    return true;
  };

  const swapScene = (id: string) => {
    if (!ac || !master || !space) return;
    if (current?.id === id) return;
    const old = current;
    const next = SCENES[id] ?? meadow;
    const sc = next(ac, master, space);
    const now = ac.currentTime;
    sc.out.gain.setValueAtTime(0, now);
    sc.out.gain.linearRampToValueAtTime(1, now + FADE);
    current = { id, scene: sc };
    if (old) {
      old.scene.out.gain.cancelScheduledValues(now);
      old.scene.out.gain.setValueAtTime(old.scene.out.gain.value, now);
      old.scene.out.gain.linearRampToValueAtTime(0, now + FADE);
      window.setTimeout(() => old.scene.stop(), FADE * 1000 + 200);
    }
  };

  const update = () => {
    if (!ac || !master) return;
    const now = ac.currentTime;
    const g = master.gain;
    g.cancelScheduledValues(now);
    g.setValueAtTime(g.value, now);
    if (wanted()) {
      clearTimeout(stopTimer);
      stopTimer = 0;
      if (ac.state === 'suspended') void ac.resume();
      swapScene(resolveWallpaperId(settings.get().wallpaper));
      g.linearRampToValueAtTime(LEVEL * settings.get().volume, now + FADE);
    } else {
      g.linearRampToValueAtTime(0, now + FADE);
      // After the fade, tear the graph down and suspend the context: zero CPU while silent.
      if (!stopTimer) {
        stopTimer = window.setTimeout(() => {
          stopTimer = 0;
          if (wanted() || !ac) return;
          current?.scene.stop();
          current = null;
          void ac.suspend();
        }, FADE * 1000 + 250);
      }
    }
  };

  const unlock = () => {
    window.removeEventListener('pointerdown', unlock, true);
    window.removeEventListener('keydown', unlock, true);
    if (ensure()) update();
  };
  window.addEventListener('pointerdown', unlock, true);
  window.addEventListener('keydown', unlock, true);

  bus.on('window:focus', (w) => {
    desktopFocused = w === null;
    update();
  });
  bus.on('settings:change', () => update());
  document.addEventListener('visibilitychange', update);

  // Boot, logon and log-off screens cover the desktop: stay quiet while any is up.
  new MutationObserver(() => {
    const o = !!document.querySelector('body > .screen');
    if (o !== overlay) {
      overlay = o;
      update();
    }
  }).observe(document.body, { childList: true });
}
