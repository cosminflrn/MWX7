import { bus } from './events';
import { settings } from './settings';

/**
 * MWX 7 sound engine.
 * - Musical cues (startup, log off, notifications, errors) are played on real
 *   sampled instruments (FluidR3_GM, MIT — see public/audio/system/LICENSE.txt)
 *   in original arrangements.
 * - Mechanical cues (clicks, swooshes, the POST beep) are synthesized: they are
 *   short transients where synthesis sounds as real as a recording.
 * Browsers only allow audio after a user gesture: unlockAudio() is called from
 * the first click / key press of the boot sequence.
 */

export type SoundName =
  | 'post'
  | 'startup'
  | 'logoff'
  | 'notify'
  | 'error'
  | 'minimize'
  | 'restore'
  | 'close'
  | 'click'
  | 'rclick'
  | 'menuOpen'
  | 'menuClose'
  | 'empty';

let ac: AudioContext | null = null;
let master: GainNode | null = null;
let reverb: ConvolverNode | null = null;
let samplesReady: Promise<void> | null = null;
const buffers = new Map<string, AudioBuffer>();

const BASE = `${import.meta.env.BASE_URL}audio/system/`;
const SAMPLES = [
  ...['D3', 'A3', 'D4', 'Gb4', 'A4', 'Db5', 'D5', 'E5', 'Gb5', 'A5', 'B5', 'D6'].map((n) => `acoustic_grand_piano-${n}`),
  ...['D3', 'A3', 'D4', 'Gb4', 'A4', 'E5'].flatMap((n) => [`string_ensemble_1-${n}`, `pad_2_warm-${n}`]),
  ...['D4', 'Gb4', 'A4', 'D5'].map((n) => `orchestral_harp-${n}`),
  ...['A5', 'B5', 'D6', 'E6'].map((n) => `celesta-${n}`),
  ...['A3', 'Eb4', 'B5', 'E6'].map((n) => `vibraphone-${n}`),
];

function impulse(ctx: AudioContext, seconds: number, decay: number): AudioBuffer {
  const len = Math.floor(ctx.sampleRate * seconds);
  const buf = ctx.createBuffer(2, len, ctx.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay);
  }
  return buf;
}

function engine(): AudioContext | null {
  if (!settings.get().sounds) return null;
  if (!ac) {
    try {
      ac = new AudioContext();
    } catch {
      return null;
    }
    master = ac.createGain();
    master.gain.value = settings.get().volume;
    // A gentle bus compressor keeps chords full without peaking.
    const comp = ac.createDynamicsCompressor();
    comp.threshold.value = -16;
    comp.ratio.value = 3;
    master.connect(comp).connect(ac.destination);
    reverb = ac.createConvolver();
    reverb.buffer = impulse(ac, 2.8, 3);
    const wet = ac.createGain();
    wet.gain.value = 0.22;
    reverb.connect(wet).connect(master);
  }
  if (ac.state === 'suspended') void ac.resume();
  return ac;
}

function loadSamples(ctx: AudioContext): Promise<void> {
  samplesReady ??= Promise.all(
    SAMPLES.map(async (name) => {
      try {
        const res = await fetch(`${BASE}${name}.mp3`);
        buffers.set(name, await ctx.decodeAudioData(await res.arrayBuffer()));
      } catch (err) {
        console.warn('[sound] missing sample', name, err);
      }
    }),
  ).then(() => undefined);
  return samplesReady;
}

/** Call from a user gesture (click / key press) before the first sound. */
export function unlockAudio(): void {
  const ctx = engine();
  if (ctx) void loadSamples(ctx);
}

bus.on('settings:change', (s) => {
  if (master) master.gain.value = s.volume;
});

/* ---------- building blocks ---------- */

/** Plays a sample at `t`, with an optional fade-out so long samples end gracefully. */
function sample(ctx: AudioContext, name: string, t: number, vol: number, wet = 0.5, fadeAt?: number): void {
  const buf = buffers.get(name);
  if (!buf) return;
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const amp = ctx.createGain();
  amp.gain.setValueAtTime(vol, t);
  if (fadeAt !== undefined) {
    amp.gain.setValueAtTime(vol, t + fadeAt);
    amp.gain.linearRampToValueAtTime(0.0001, t + fadeAt + 0.8);
  }
  src.connect(amp);
  amp.connect(master!);
  if (wet > 0) {
    const send = ctx.createGain();
    send.gain.value = wet;
    amp.connect(send).connect(reverb!);
  }
  src.start(t);
}

/** Sustained layer (strings / pad) with a slow swell and release. */
function swell(ctx: AudioContext, name: string, t: number, dur: number, vol: number): void {
  const buf = buffers.get(name);
  if (!buf) return;
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const amp = ctx.createGain();
  amp.gain.setValueAtTime(0.0001, t);
  amp.gain.linearRampToValueAtTime(vol, t + Math.min(0.9, dur * 0.35));
  amp.gain.setValueAtTime(vol, t + dur * 0.65);
  amp.gain.linearRampToValueAtTime(0.0001, t + dur);
  const lp = ctx.createBiquadFilter();
  lp.type = 'lowpass';
  lp.frequency.value = 3800;
  src.connect(lp).connect(amp);
  amp.connect(master!);
  const send = ctx.createGain();
  send.gain.value = 0.7;
  amp.connect(send).connect(reverb!);
  src.start(t);
  src.stop(t + dur + 0.1);
}

function noise(ctx: AudioContext, seconds: number): AudioBufferSourceNode {
  const len = Math.max(1, Math.floor(ctx.sampleRate * seconds));
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  const src = ctx.createBufferSource();
  src.buffer = buf;
  return src;
}

/** Air movement: band-passed noise sweeping between two frequencies. */
function swoosh(ctx: AudioContext, t: number, from: number, to: number, dur: number, vol: number): void {
  const src = noise(ctx, dur);
  const bp = ctx.createBiquadFilter();
  bp.type = 'bandpass';
  bp.Q.value = 0.9;
  bp.frequency.setValueAtTime(from, t);
  bp.frequency.exponentialRampToValueAtTime(to, t + dur);
  const amp = ctx.createGain();
  amp.gain.setValueAtTime(0.0001, t);
  amp.gain.linearRampToValueAtTime(vol, t + dur * 0.35);
  amp.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  src.connect(bp).connect(amp).connect(master!);
  src.start(t);
}

/**
 * A soft, satisfying click: a tiny felt-damped "tock" — a very short band of
 * noise for the contact plus a quickly decaying low body tone.
 */
function tock(ctx: AudioContext, t: number, body: number, vol: number): void {
  const src = noise(ctx, 0.02);
  const hp = ctx.createBiquadFilter();
  hp.type = 'bandpass';
  hp.frequency.value = 3200;
  hp.Q.value = 1.4;
  const a = ctx.createGain();
  a.gain.setValueAtTime(vol, t);
  a.gain.exponentialRampToValueAtTime(0.0001, t + 0.018);
  src.connect(hp).connect(a).connect(master!);
  src.start(t);

  const osc = ctx.createOscillator();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(body, t);
  osc.frequency.exponentialRampToValueAtTime(body * 0.6, t + 0.04);
  const b = ctx.createGain();
  b.gain.setValueAtTime(vol * 0.9, t);
  b.gain.exponentialRampToValueAtTime(0.0001, t + 0.05);
  osc.connect(b).connect(master!);
  osc.start(t);
  osc.stop(t + 0.06);
}

/* ---------- the sounds ---------- */

const MUSICAL: SoundName[] = ['startup', 'logoff', 'notify', 'error'];

export function play(name: SoundName): void {
  const ctx = engine();
  if (!ctx) return;
  if (MUSICAL.includes(name)) {
    // Sampled cues wait for their instruments (they're fetched at power-on).
    void loadSamples(ctx).then(() => playMusical(ctx, name));
    return;
  }
  const t = ctx.currentTime + 0.005;
  switch (name) {
    case 'post': {
      // PC-speaker POST beep: a raw square wave, no reverb.
      const osc = ctx.createOscillator();
      osc.type = 'square';
      osc.frequency.value = 1000;
      const lp = ctx.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = 5000;
      const amp = ctx.createGain();
      amp.gain.setValueAtTime(0.0001, t);
      amp.gain.linearRampToValueAtTime(0.08, t + 0.004);
      amp.gain.setValueAtTime(0.08, t + 0.17);
      amp.gain.linearRampToValueAtTime(0.0001, t + 0.18);
      osc.connect(lp).connect(amp).connect(master!);
      osc.start(t);
      osc.stop(t + 0.2);
      break;
    }
    case 'click':
      tock(ctx, t, 520, 0.05);
      break;
    case 'rclick':
      tock(ctx, t, 400, 0.05);
      break;
    case 'menuOpen':
      swoosh(ctx, t, 600, 2600, 0.2, 0.03);
      break;
    case 'menuClose':
      swoosh(ctx, t, 2200, 700, 0.16, 0.022);
      break;
    case 'minimize':
      swoosh(ctx, t, 2600, 420, 0.42, 0.03);
      break;
    case 'restore':
      swoosh(ctx, t, 420, 2600, 0.36, 0.026);
      break;
    case 'close':
      swoosh(ctx, t, 1800, 600, 0.18, 0.018);
      break;
    case 'empty':
      // Paper crumpling: a quick cluster of tiny filtered crackles.
      for (let i = 0; i < 18; i++) {
        const at = t + Math.random() * 0.42;
        const src = noise(ctx, 0.03);
        const bp = ctx.createBiquadFilter();
        bp.type = 'bandpass';
        bp.frequency.value = 1200 + Math.random() * 4200;
        bp.Q.value = 2;
        const a = ctx.createGain();
        a.gain.setValueAtTime(0.05 + Math.random() * 0.05, at);
        a.gain.exponentialRampToValueAtTime(0.0001, at + 0.025 + Math.random() * 0.03);
        src.connect(bp).connect(a).connect(master!);
        src.start(at);
      }
      break;
  }
}

function playMusical(ctx: AudioContext, name: SoundName): void {
  const t = ctx.currentTime + 0.03;
  const piano = (n: string, at: number, v: number, fade?: number) => sample(ctx, `acoustic_grand_piano-${n}`, t + at, v, 0.45, fade);
  switch (name) {
    case 'startup': {
      // Original MWX 7 startup: a warm string/pad bed, a harp sweep and a short
      // rising piano phrase that resolves with a celesta sparkle.
      swell(ctx, 'pad_2_warm-D3', t, 4.6, 0.32);
      swell(ctx, 'pad_2_warm-A3', t, 4.6, 0.26);
      swell(ctx, 'string_ensemble_1-D4', t + 0.1, 4.4, 0.24);
      swell(ctx, 'string_ensemble_1-Gb4', t + 0.2, 4.3, 0.2);
      swell(ctx, 'string_ensemble_1-A4', t + 1.9, 2.8, 0.18);
      swell(ctx, 'pad_2_warm-E5', t + 1.9, 2.8, 0.14);
      ['D4', 'Gb4', 'A4', 'D5'].forEach((n, i) => sample(ctx, `orchestral_harp-${n}`, t + i * 0.09, 0.42, 0.6));
      piano('A4', 0.55, 0.42);
      piano('D5', 0.86, 0.44);
      piano('Gb5', 1.17, 0.46);
      piano('E5', 1.55, 0.4);
      piano('D3', 1.95, 0.36, 2.2);
      piano('A5', 1.95, 0.5, 2.2);
      piano('D5', 1.95, 0.3, 2.2);
      sample(ctx, 'celesta-D6', t + 2.0, 0.22, 0.8);
      sample(ctx, 'celesta-A5', t + 2.12, 0.16, 0.8);
      break;
    }
    case 'logoff': {
      swell(ctx, 'pad_2_warm-D3', t, 2.8, 0.26);
      swell(ctx, 'string_ensemble_1-A3', t, 2.6, 0.18);
      piano('A5', 0, 0.36);
      piano('Gb5', 0.28, 0.34);
      piano('D5', 0.56, 0.34);
      piano('A4', 0.9, 0.36, 1.4);
      piano('D4', 0.9, 0.26, 1.4);
      break;
    }
    case 'notify':
      sample(ctx, 'vibraphone-B5', t, 0.22, 0.5, 0.6);
      sample(ctx, 'vibraphone-E6', t + 0.11, 0.2, 0.5, 0.7);
      break;
    case 'error':
      sample(ctx, 'vibraphone-Eb4', t, 0.3, 0.4, 0.5);
      sample(ctx, 'vibraphone-A3', t + 0.01, 0.24, 0.4, 0.5);
      break;
    default:
      break;
  }
}
