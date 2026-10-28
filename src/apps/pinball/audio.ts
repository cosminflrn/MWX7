/** Fully synthesized sound effects (Web Audio). Nothing here is sampled or copied. */

type Wave = OscillatorType;

export class Sfx {
  muted = false;
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private noise: AudioBuffer | null = null;
  private last = new Map<string, number>();

  /** Must be called from a user gesture (key press) to satisfy autoplay rules. */
  unlock(): void {
    try {
      if (!this.ctx) {
        const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AC) return;
        this.ctx = new AC();
        this.master = this.ctx.createGain();
        this.master.gain.value = this.muted ? 0 : 0.5;
        const comp = this.ctx.createDynamicsCompressor();
        this.master.connect(comp).connect(this.ctx.destination);
        const len = this.ctx.sampleRate;
        this.noise = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
        const d = this.noise.getChannelData(0);
        for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
      }
      if (this.ctx.state === 'suspended') void this.ctx.resume();
    } catch {
      /* audio is optional */
    }
  }

  setMuted(m: boolean): void {
    this.muted = m;
    if (this.master && this.ctx) this.master.gain.setTargetAtTime(m ? 0 : 0.5, this.ctx.currentTime, 0.02);
  }

  suspend(): void {
    if (this.ctx && this.ctx.state === 'running') void this.ctx.suspend();
  }

  private ok(key: string, gap: number): boolean {
    const now = performance.now();
    if (now - (this.last.get(key) ?? -1e9) < gap) return false;
    this.last.set(key, now);
    return !!this.ctx && !!this.master && !this.muted;
  }

  private tone(f0: number, f1: number, dur: number, type: Wave, vol: number, delay = 0): void {
    const c = this.ctx!;
    const t = c.currentTime + delay;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(f0, t);
    o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(this.master!);
    o.start(t);
    o.stop(t + dur + 0.02);
  }

  private hiss(f0: number, f1: number, q: number, dur: number, vol: number, type: BiquadFilterType = 'bandpass', delay = 0): void {
    const c = this.ctx!;
    const t = c.currentTime + delay;
    const s = c.createBufferSource();
    s.buffer = this.noise;
    const f = c.createBiquadFilter();
    f.type = type;
    f.Q.value = q;
    f.frequency.setValueAtTime(f0, t);
    f.frequency.exponentialRampToValueAtTime(Math.max(30, f1), t + dur);
    const g = c.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(f).connect(g).connect(this.master!);
    s.start(t);
    s.stop(t + dur + 0.02);
  }

  bumper(i: number): void {
    if (!this.ok('bumper', 40)) return;
    const base = 300 + i * 70;
    this.tone(base * 2.2, base * 0.8, 0.16, 'triangle', 0.55);
    this.tone(base * 4.4, base * 3, 0.07, 'sine', 0.25);
    this.hiss(2400, 600, 1.2, 0.07, 0.25);
  }
  sling(): void {
    if (!this.ok('sling', 50)) return;
    this.hiss(1800, 500, 2, 0.08, 0.5);
    this.tone(180, 70, 0.09, 'square', 0.18);
  }
  flipper(): void {
    if (!this.ok('flip', 35)) return;
    this.tone(150, 55, 0.07, 'square', 0.22);
    this.hiss(3000, 900, 0.8, 0.04, 0.3);
  }
  flipperHit(): void {
    if (!this.ok('fhit', 60)) return;
    this.tone(520, 260, 0.05, 'triangle', 0.25);
  }
  wall(speed: number): void {
    if (!this.ok('wall', 70)) return;
    const v = Math.min(1, speed / 900);
    this.tone(900 + v * 500, 500, 0.04, 'sine', 0.06 + 0.12 * v);
  }
  target(): void {
    if (!this.ok('target', 40)) return;
    this.tone(1200, 800, 0.1, 'sine', 0.3);
    this.tone(1800, 1200, 0.07, 'triangle', 0.15, 0.02);
  }
  rollover(): void {
    if (!this.ok('roll', 40)) return;
    this.tone(880, 1320, 0.09, 'sine', 0.22);
  }
  launch(power: number): void {
    if (!this.ok('launch', 100)) return;
    this.hiss(300 + 400 * power, 4200, 0.9, 0.45 + 0.3 * power, 0.5);
    this.tone(90, 40, 0.12, 'sawtooth', 0.3);
  }
  charge(p: number): void {
    if (!this.ok('charge', 90)) return;
    this.tone(110 + p * 160, 120 + p * 170, 0.06, 'triangle', 0.08);
  }
  drain(): void {
    if (!this.ok('drain', 300)) return;
    this.tone(420, 60, 0.9, 'sawtooth', 0.28);
    this.tone(210, 45, 1.0, 'square', 0.12);
  }
  save(): void {
    if (!this.ok('save', 300)) return;
    [523, 659, 784].forEach((f, i) => this.tone(f, f, 0.14, 'sine', 0.25, i * 0.08));
  }
  mission(): void {
    if (!this.ok('mission', 300)) return;
    [392, 523, 659, 784, 1046].forEach((f, i) => this.tone(f, f * 1.01, 0.18, 'triangle', 0.25, i * 0.07));
  }
  wormhole(): void {
    if (!this.ok('worm', 200)) return;
    this.tone(180, 1400, 0.5, 'sine', 0.25);
    this.hiss(400, 3000, 3, 0.5, 0.25);
  }
  over(): void {
    if (!this.ok('over', 500)) return;
    [330, 262, 196, 131].forEach((f, i) => this.tone(f, f * 0.97, 0.3, 'triangle', 0.3, i * 0.2));
  }
}
