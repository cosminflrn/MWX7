/**
 * Background soundtrack: a calm, cinematic space-ambient loop (80 s, 20 bars at 60 bpm, D minor / Dorian colour).
 * The instruments are real recorded notes (FluidR3_GM, MIT, see public/audio/pinball/LICENSE.txt); the sequence,
 * voicings and arrangement are original. Notes are pitch-shifted by at most a few semitones from the nearest sample.
 * Everything is scheduled on one absolute timeline, so the loop point is seamless and reverb tails run through it.
 */
import type { Sfx } from './audio';

type Inst = 'ep' | 'str' | 'pad' | 'bass';

const BASE = `${import.meta.env.BASE_URL}audio/pinball/`;
const SAMPLES: Record<Inst, [string, number][]> = {
  ep: [['A3', 57], ['C4', 60], ['Eb4', 63], ['Gb4', 66], ['A4', 69], ['C5', 72]],
  str: [['D3', 50], ['F3', 53], ['A3', 57], ['D4', 62]],
  pad: [['F3', 53], ['A3', 57], ['D4', 62], ['F4', 65]],
  bass: [['C2', 36], ['F2', 41], ['A2', 45]],
};

const BAR = 4; // seconds
const LOOP_BARS = 20;
const LOOKAHEAD = 2;

interface Chord {
  bass: number;
  pad: number[];
  str: number[];
  ep: number[];
}
const C: Record<string, Chord> = {
  Dm9: { bass: 38, pad: [50, 57, 60, 64], str: [57, 62, 65, 69], ep: [57, 62, 65, 69, 72] },
  Bbmaj7: { bass: 34, pad: [53, 57, 58, 62], str: [58, 62, 65, 69], ep: [58, 62, 65, 69, 74] },
  Gm9: { bass: 43, pad: [50, 55, 58, 62], str: [58, 62, 65, 69], ep: [55, 58, 62, 65, 69] },
  Asus: { bass: 45, pad: [52, 57, 62, 67], str: [57, 62, 64, 67], ep: [57, 62, 64, 67, 69] },
  Fadd9: { bass: 41, pad: [53, 57, 60, 65], str: [55, 60, 65, 69], ep: [57, 60, 65, 67, 72] },
  Cadd9: { bass: 36, pad: [52, 55, 60, 62], str: [55, 60, 64, 67], ep: [55, 60, 64, 67, 72] },
  DmF: { bass: 41, pad: [50, 57, 62, 65], str: [57, 62, 65, 69], ep: [57, 62, 65, 69, 72] },
  Ebmaj7: { bass: 39, pad: [51, 55, 58, 62], str: [55, 58, 62, 67], ep: [55, 58, 62, 65, 70] },
  FA: { bass: 45, pad: [53, 57, 60, 65], str: [57, 60, 65, 69], ep: [57, 60, 65, 69, 72] },
};
const PROG: string[] = [
  'Dm9', 'Bbmaj7', 'Gm9', 'Asus',
  'Dm9', 'Bbmaj7', 'Fadd9', 'Cadd9',
  'Gm9', 'DmF', 'Ebmaj7', 'Asus',
  'Bbmaj7', 'FA', 'Gm9', 'Asus',
  'Dm9', 'Bbmaj7', 'Gm9', 'Dm9',
];

/** [beat, chord-tone index, velocity] per bar, by section (4 bars each): sparse, flowing, flowing, flowing, sparse. */
type Pat = [number, number, number][];
const SPARSE: Pat = [[0, 1, 0.7], [1.5, 3, 0.45], [3, 2, 0.45]];
const FLOW: Pat = [[0, 0, 0.7], [0.5, 2, 0.42], [1, 3, 0.5], [2, 4, 0.55], [2.5, 3, 0.38], [3.5, 2, 0.4]];
const PATS: Pat[] = [SPARSE, FLOW, FLOW, FLOW, SPARSE];

export class Music {
  enabled = true;
  private bufs: Record<Inst, { buf: AudioBuffer; midi: number }[]> | null = null;
  private loading: Promise<void> | null = null;
  private bus: GainNode | null = null;
  private input: AudioNode | null = null;
  private timer = 0;
  private t0 = 0;
  private bar = 0;
  private seed = 7;
  private dead = false;
  private failed = false;

  constructor(private sfx: Sfx) {}

  get playing(): boolean {
    return this.bus !== null;
  }

  /** Call from user input; starts (once) if enabled. Safe to call repeatedly. */
  start(): void {
    if (!this.enabled || this.bus || this.dead || this.failed) return;
    const ctx = this.sfx.ctx;
    if (!ctx || !this.sfx.out) return;
    void this.load(ctx).then(() => {
      if (this.enabled && !this.bus && !this.dead && !this.failed) this.begin();
    });
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    if (on) this.start();
    else this.halt(0.6);
  }

  dispose(): void {
    this.dead = true;
    this.halt(0.05);
  }

  private load(ctx: AudioContext): Promise<void> {
    if (this.loading) return this.loading;
    const out: Record<string, { buf: AudioBuffer; midi: number }[]> = { ep: [], str: [], pad: [], bass: [] };
    const jobs: Promise<void>[] = [];
    for (const inst of Object.keys(SAMPLES) as Inst[]) {
      for (const [name, midi] of SAMPLES[inst]) {
        jobs.push(
          fetch(`${BASE}${inst}_${name}.mp3`)
            .then((r) => {
              if (!r.ok) throw new Error(`HTTP ${r.status}`);
              return r.arrayBuffer();
            })
            .then((ab) => ctx.decodeAudioData(ab))
            .then((buf) => void out[inst].push({ buf, midi }))
        );
      }
    }
    this.loading = Promise.all(jobs)
      .then(() => {
        this.bufs = out as Record<Inst, { buf: AudioBuffer; midi: number }[]>;
      })
      .catch((err) => {
        this.failed = true; // music is optional: stay silent, effects keep working
        console.warn('Space Pinball: music samples unavailable', err);
      });
    return this.loading;
  }

  private begin(): void {
    const ctx = this.sfx.ctx;
    const out = this.sfx.out;
    if (!ctx || !out || !this.bufs) return;
    const bus = ctx.createGain();
    bus.gain.setValueAtTime(0.0001, ctx.currentTime);
    bus.gain.linearRampToValueAtTime(0.42, ctx.currentTime + 4); // music sits well under the effects
    bus.connect(out);

    // Light hall reverb from a generated impulse: two decorrelated, progressively darker noise tails.
    const conv = ctx.createConvolver();
    conv.buffer = this.impulse(ctx, 3.6);
    const wet = ctx.createGain();
    wet.gain.value = 0.55;
    const dry = ctx.createGain();
    dry.gain.value = 0.8;
    const tone = ctx.createBiquadFilter(); // takes the edge off the samples so they sit back
    tone.type = 'lowpass';
    tone.frequency.value = 5200;
    tone.connect(dry).connect(bus);
    tone.connect(wet).connect(conv).connect(bus);
    this.input = tone;

    this.bus = bus;
    this.t0 = ctx.currentTime + 0.25;
    this.bar = 0;
    this.seed = 7;
    this.pump();
    this.timer = window.setInterval(() => this.pump(), 250);
  }

  private halt(fade: number): void {
    window.clearInterval(this.timer);
    const bus = this.bus;
    const ctx = this.sfx.ctx;
    this.bus = this.input = null;
    if (!bus || !ctx) return;
    try {
      bus.gain.cancelScheduledValues(ctx.currentTime);
      bus.gain.setTargetAtTime(0.0001, ctx.currentTime, fade / 3);
    } catch {
      /* context closed */
    }
    window.setTimeout(() => {
      try {
        bus.disconnect();
      } catch {
        /* already gone */
      }
    }, (fade + 4) * 1000); // let scheduled sample tails finish, silently
  }

  private impulse(ctx: AudioContext, secs: number): AudioBuffer {
    const len = Math.floor(ctx.sampleRate * secs);
    const buf = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const d = buf.getChannelData(ch);
      let lp = 0;
      for (let i = 0; i < len; i++) {
        const t = i / len;
        const a = 0.18 + 0.78 * (1 - t); // one-pole lowpass that darkens as the tail decays
        lp += a * (Math.random() * 2 - 1 - lp);
        const env = Math.pow(1 - t, 2.6) * Math.min(1, i / (ctx.sampleRate * 0.02));
        d[i] = lp * env;
      }
    }
    return buf;
  }

  private rnd(): number {
    this.seed = (this.seed * 1664525 + 1013904223) >>> 0;
    return this.seed / 4294967296;
  }

  private pump(): void {
    const ctx = this.sfx.ctx;
    if (!ctx || !this.bus) return;
    if (ctx.state !== 'running') {
      // Suspended / not yet resumed: don't queue a backlog; slide the timeline forward.
      this.t0 = Math.max(this.t0, ctx.currentTime + 0.25 - this.bar * BAR);
      return;
    }
    while (this.t0 + this.bar * BAR < ctx.currentTime + LOOKAHEAD) {
      this.scheduleBar(this.bar % LOOP_BARS, this.t0 + this.bar * BAR);
      this.bar++;
    }
  }

  private scheduleBar(n: number, t: number): void {
    const chord = C[PROG[n]];
    const sec = Math.floor(n / 4);
    const beat = BAR / 4;

    // Warm pad: overlapping retriggers (the notes are only ~3 s long) form a continuous, slowly breathing sustain.
    for (const m of chord.pad) for (let k = 0; k < 3; k++) this.note('pad', m, t + (k * BAR) / 3 + this.rnd() * 0.05, 2.7, 0.2, 1.2, 1.4);
    // Strings join from the second section for lift, and drop out for the final chord.
    if (sec >= 1 && n !== 19) {
      for (const m of chord.str) for (let k = 0; k < 2; k++) this.note('str', m, t + k * 2 + this.rnd() * 0.08, 3, 0.11, 1.3, 1.5);
    }
    // Bass: one long note per bar, a soft echo on beat 3 in the busier sections.
    this.note('bass', chord.bass, t, 3.1, 0.7, 0.03, 1.4);
    if (sec >= 2 && n % 2 === 0) this.note('bass', chord.bass, t + beat * 2.5, 1.6, 0.3, 0.02, 1.0);
    // Electric piano figure with human timing and velocity.
    for (const [b, idx, vel] of PATS[sec]) {
      const m = chord.ep[idx % chord.ep.length];
      this.note('ep', m, t + b * beat + (this.rnd() - 0.5) * 0.04, 3, vel * (0.3 + this.rnd() * 0.06), 0.006, 1.6);
    }
    // A sustained high chord tone as a distant "bell" at the start of each phrase.
    if (n % 4 === 0 && sec > 0 && sec < 4) this.note('ep', chord.ep[4], t + beat * 1.9, 3, 0.1, 0.01, 2.2);
  }

  /** Play the sample closest to `midi`, pitch-shifted to it, with a linear attack and release envelope. */
  private note(inst: Inst, midi: number, when: number, len: number, gain: number, attack: number, release: number): void {
    const ctx = this.sfx.ctx;
    const dest = this.input;
    if (!ctx || !dest || !this.bufs) return;
    let best = this.bufs[inst][0];
    for (const s of this.bufs[inst]) if (Math.abs(s.midi - midi) < Math.abs(best.midi - midi)) best = s;
    const src = ctx.createBufferSource();
    src.buffer = best.buf;
    src.playbackRate.value = 2 ** ((midi - best.midi) / 12);
    const g = ctx.createGain();
    const end = when + Math.min(len, best.buf.duration / src.playbackRate.value - 0.05);
    g.gain.setValueAtTime(0.0001, when);
    g.gain.linearRampToValueAtTime(gain, when + attack);
    g.gain.setValueAtTime(gain, Math.max(when + attack, end - release));
    g.gain.linearRampToValueAtTime(0.0001, end);
    if (inst === 'bass') {
      const lp = ctx.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = 520;
      src.connect(lp).connect(g);
    } else src.connect(g);
    g.connect(dest);
    src.start(when);
    src.stop(end + 0.05);
  }
}
