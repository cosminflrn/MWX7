import { bus } from './events';
import { settings } from './settings';

/**
 * MWX 7 sound engine. Every sound is synthesized at runtime with Web Audio:
 * no audio files, nothing sampled from other operating systems.
 * Browsers only allow audio after a user gesture, so the boot sequence calls
 * unlockAudio() from its first click/keypress.
 */

export type SoundName = 'post' | 'startup' | 'logoff' | 'notify' | 'error' | 'minimize' | 'restore' | 'click';

let ac: AudioContext | null = null;
let master: GainNode | null = null;
let reverb: ConvolverNode | null = null;

const midi = (n: number) => 440 * Math.pow(2, (n - 69) / 12);
// Note names → MIDI numbers for the few octaves we use.
const N: Record<string, number> = {};
['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'].forEach((name, i) => {
  for (let o = 1; o <= 7; o++) N[`${name}${o}`] = 12 * (o + 1) + i;
});
const hz = (note: string) => midi(N[note]);

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
    master.connect(ac.destination);
    reverb = ac.createConvolver();
    reverb.buffer = impulse(ac, 3.2, 2.6);
    const wet = ac.createGain();
    wet.gain.value = 0.32;
    reverb.connect(wet).connect(master);
  }
  master!.gain.value = settings.get().volume;
  if (ac.state === 'suspended') void ac.resume();
  return ac;
}

/** Call from a user gesture (click / keydown) before the first sound. */
export function unlockAudio(): void {
  engine();
}

bus.on('settings:change', (s) => {
  if (master) master.gain.value = s.volume;
});

/* ---------- instruments ---------- */

interface Out {
  dry: AudioNode;
  wet: AudioNode;
}

function outs(ctx: AudioContext, wetAmount = 1): Out {
  const dry = ctx.createGain();
  dry.connect(master!);
  const wet = ctx.createGain();
  wet.gain.value = wetAmount;
  wet.connect(reverb!);
  return { dry, wet };
}

/** Soft FM bell: sine carrier with a decaying inharmonic modulator. */
function bell(ctx: AudioContext, o: Out, freq: number, t: number, dur = 2.4, vol = 0.16): void {
  const car = ctx.createOscillator();
  const mod = ctx.createOscillator();
  const modGain = ctx.createGain();
  const amp = ctx.createGain();
  car.frequency.value = freq;
  mod.frequency.value = freq * 3.5;
  modGain.gain.setValueAtTime(freq * 1.6, t);
  modGain.gain.exponentialRampToValueAtTime(freq * 0.05, t + dur * 0.6);
  amp.gain.setValueAtTime(0.0001, t);
  amp.gain.exponentialRampToValueAtTime(vol, t + 0.012);
  amp.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  mod.connect(modGain).connect(car.frequency);
  car.connect(amp);
  amp.connect(o.dry);
  amp.connect(o.wet);
  car.start(t);
  mod.start(t);
  car.stop(t + dur + 0.05);
  mod.stop(t + dur + 0.05);
}

/** Warm analog-style pad: detuned saws through a slowly opening low-pass. */
function pad(ctx: AudioContext, o: Out, notes: string[], t: number, dur: number, vol = 0.05): void {
  const filter = ctx.createBiquadFilter();
  filter.type = 'lowpass';
  filter.Q.value = 0.7;
  filter.frequency.setValueAtTime(400, t);
  filter.frequency.linearRampToValueAtTime(2400, t + dur * 0.45);
  filter.frequency.linearRampToValueAtTime(900, t + dur);
  const amp = ctx.createGain();
  amp.gain.setValueAtTime(0.0001, t);
  amp.gain.linearRampToValueAtTime(vol, t + Math.min(1.1, dur * 0.35));
  amp.gain.setValueAtTime(vol, t + dur * 0.6);
  amp.gain.linearRampToValueAtTime(0.0001, t + dur);
  filter.connect(amp);
  amp.connect(o.dry);
  amp.connect(o.wet);
  for (const n of notes) {
    for (const detune of [-7, 7]) {
      const osc = ctx.createOscillator();
      osc.type = 'sawtooth';
      osc.frequency.value = hz(n);
      osc.detune.value = detune;
      osc.connect(filter);
      osc.start(t);
      osc.stop(t + dur + 0.05);
    }
  }
}

function noiseSweep(ctx: AudioContext, o: Out, t: number, from: number, to: number, dur: number, vol: number): void {
  const len = Math.floor(ctx.sampleRate * dur);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const bp = ctx.createBiquadFilter();
  bp.type = 'bandpass';
  bp.Q.value = 1.2;
  bp.frequency.setValueAtTime(from, t);
  bp.frequency.exponentialRampToValueAtTime(to, t + dur);
  const amp = ctx.createGain();
  amp.gain.setValueAtTime(0.0001, t);
  amp.gain.linearRampToValueAtTime(vol, t + dur * 0.3);
  amp.gain.linearRampToValueAtTime(0.0001, t + dur);
  src.connect(bp).connect(amp);
  amp.connect(o.dry);
  src.start(t);
}

/* ---------- the sounds ---------- */

export function play(name: SoundName): void {
  const ctx = engine();
  if (!ctx) return;
  const t = ctx.currentTime + 0.03;

  switch (name) {
    case 'post': {
      // PC-speaker style single POST beep: raw square wave, no reverb.
      const osc = ctx.createOscillator();
      osc.type = 'square';
      osc.frequency.value = 1000;
      const lp = ctx.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = 5000;
      const amp = ctx.createGain();
      amp.gain.setValueAtTime(0.0001, t);
      amp.gain.linearRampToValueAtTime(0.09, t + 0.005);
      amp.gain.setValueAtTime(0.09, t + 0.17);
      amp.gain.linearRampToValueAtTime(0.0001, t + 0.18);
      osc.connect(lp).connect(amp).connect(master!);
      osc.start(t);
      osc.stop(t + 0.2);
      break;
    }
    case 'startup': {
      // Original MWX 7 chime: warm swelling pad, a rising five-note bell line, a bright resolve.
      const o = outs(ctx);
      pad(ctx, o, ['D3', 'A3', 'E4', 'F#4'], t, 2.2, 0.035);
      pad(ctx, o, ['B2', 'F#3', 'D4', 'A4'], t + 1.6, 1.6, 0.03);
      pad(ctx, o, ['D3', 'A3', 'C#4', 'F#4', 'E5'], t + 2.6, 3.4, 0.035);
      const line: Array<[string, number, number]> = [
        ['A4', 0.15, 0.14],
        ['D5', 0.48, 0.14],
        ['F#5', 0.8, 0.13],
        ['E5', 1.25, 0.12],
        ['B5', 1.7, 0.12],
        ['A5', 2.6, 0.16],
        ['D6', 2.62, 0.07],
      ];
      for (const [n, at, v] of line) bell(ctx, o, hz(n), t + at, 3, v);
      break;
    }
    case 'logoff': {
      const o = outs(ctx);
      pad(ctx, o, ['D3', 'A3', 'F#4'], t, 2.4, 0.03);
      [['A5', 0], ['F#5', 0.3], ['D5', 0.6], ['A4', 0.95]].forEach(([n, at]) => bell(ctx, o, hz(n as string), t + (at as number), 2.4, 0.12));
      break;
    }
    case 'notify': {
      const o = outs(ctx, 0.6);
      bell(ctx, o, hz('E6'), t, 1.2, 0.07);
      bell(ctx, o, hz('B5'), t + 0.12, 1.4, 0.07);
      break;
    }
    case 'error': {
      const o = outs(ctx, 0.5);
      bell(ctx, o, hz('D#4'), t, 1.0, 0.12);
      bell(ctx, o, hz('A3'), t + 0.02, 1.1, 0.08);
      break;
    }
    case 'minimize':
      noiseSweep(ctx, outs(ctx), t, 2400, 500, 0.28, 0.035);
      break;
    case 'restore':
      noiseSweep(ctx, outs(ctx), t, 500, 2400, 0.26, 0.03);
      break;
    case 'click': {
      const o = outs(ctx, 0.2);
      bell(ctx, o, hz('A6'), t, 0.15, 0.03);
      break;
    }
  }
}
