/** Pinball sound effects (Web Audio). Synthesized and deliberately mechanical: filtered-noise transients plus low thumps. */

export class Sfx {
  muted = false;
  private ac: AudioContext | null = null;
  private master: GainNode | null = null;
  private noise: AudioBuffer | null = null;
  private last = new Map<string, number>();

  /** The shared context and output bus (null until the first user gesture); the music engine plugs into these. */
  get ctx(): AudioContext | null {
    return this.ac;
  }
  get out(): GainNode | null {
    return this.master;
  }

  /** Must be called from a user gesture (key press) to satisfy autoplay rules. */
  unlock(): void {
    try {
      if (!this.ac) {
        const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AC) return;
        const c = (this.ac = new AC());
        this.master = c.createGain();
        this.master.gain.value = this.muted ? 0 : 0.7;
        const comp = c.createDynamicsCompressor();
        comp.threshold.value = -16;
        comp.ratio.value = 4;
        this.master.connect(comp).connect(c.destination);
        const len = c.sampleRate;
        this.noise = c.createBuffer(1, len, c.sampleRate);
        const d = this.noise.getChannelData(0);
        for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
      }
      if (this.ac.state === 'suspended') void this.ac.resume();
    } catch {
      /* audio is optional */
    }
  }

  setMuted(m: boolean): void {
    this.muted = m;
    if (this.master && this.ac) this.master.gain.setTargetAtTime(m ? 0 : 0.7, this.ac.currentTime, 0.03);
  }

  dispose(): void {
    const c = this.ac;
    this.ac = this.master = null;
    if (c && c.state !== 'closed') void c.close().catch(() => undefined);
  }

  private ok(key: string, gap: number): boolean {
    const now = performance.now();
    if (now - (this.last.get(key) ?? -1e9) < gap) return false;
    this.last.set(key, now);
    return !!this.ac && !!this.master && !this.muted;
  }

  // ---- building blocks ----------------------------------------------------------------------------------------

  /** Low "thump": a sine with a fast downward pitch drop, the body of every solenoid / rubber impact. */
  private thump(f0: number, f1: number, dur: number, vol: number, delay = 0): void {
    const c = this.ac!;
    const t = c.currentTime + delay;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(f0, t);
    o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t + dur * 0.8);
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(this.master!);
    o.start(t);
    o.stop(t + dur + 0.02);
  }

  /** Filtered noise burst with an instant attack: the "tick" of metal, plastic and wood. */
  private burst(freq: number, q: number, dur: number, vol: number, type: BiquadFilterType = 'bandpass', delay = 0, freqEnd = freq): void {
    const c = this.ac!;
    const t = c.currentTime + delay;
    const s = c.createBufferSource();
    s.buffer = this.noise;
    const f = c.createBiquadFilter();
    f.type = type;
    f.Q.value = q;
    f.frequency.setValueAtTime(freq, t);
    if (freqEnd !== freq) f.frequency.exponentialRampToValueAtTime(Math.max(30, freqEnd), t + dur);
    const g = c.createGain();
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(f).connect(g).connect(this.master!);
    s.start(t, Math.random() * 0.5);
    s.stop(t + dur + 0.02);
  }

  /** Short inharmonic metal ring (struck steel), very quiet; gives bumpers and targets their material. */
  private ring(f: number, dur: number, vol: number, delay = 0): void {
    const c = this.ac!;
    const t = c.currentTime + delay;
    for (const [m, v] of [[1, 1], [2.76, 0.5], [5.4, 0.25]] as const) {
      const o = c.createOscillator();
      const g = c.createGain();
      o.type = 'sine';
      o.frequency.value = f * m;
      g.gain.setValueAtTime(vol * v, t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur / m ** 0.5);
      o.connect(g).connect(this.master!);
      o.start(t);
      o.stop(t + dur + 0.02);
    }
  }

  // ---- effects -------------------------------------------------------------------------------------------------

  bumper(i: number): void {
    if (!this.ok('bumper', 40)) return;
    this.thump(150 - i * 8, 48, 0.11, 0.7);
    this.burst(2200, 0.9, 0.035, 0.5);
    this.burst(900, 1.4, 0.06, 0.3);
    this.ring(1500 + i * 90, 0.09, 0.05);
  }
  sling(): void {
    if (!this.ok('sling', 50)) return;
    this.thump(110, 55, 0.08, 0.55);
    this.burst(3200, 0.8, 0.022, 0.6, 'highpass');
    this.burst(1400, 1.2, 0.05, 0.25);
  }
  flipper(): void {
    if (!this.ok('flip', 35)) return;
    // Solenoid: a crisp click, a hard low thunk, then the rubber bumper bottoming out a few ms later.
    this.burst(4200, 0.7, 0.012, 0.6, 'highpass');
    this.thump(130, 52, 0.06, 0.6);
    this.burst(700, 1.1, 0.03, 0.22, 'bandpass', 0.014);
  }
  flipperHit(): void {
    if (!this.ok('fhit', 60)) return;
    this.burst(2600, 1.3, 0.02, 0.32);
    this.thump(240, 120, 0.035, 0.25);
  }
  wall(speed: number): void {
    if (!this.ok('wall', 70)) return;
    const v = Math.min(1, speed / 900);
    this.burst(1100 + v * 900, 1.0, 0.03, 0.08 + 0.3 * v);
    this.thump(200, 100, 0.04, 0.05 + 0.2 * v);
  }
  target(): void {
    if (!this.ok('target', 40)) return;
    this.burst(3800, 1.0, 0.014, 0.5, 'highpass');
    this.thump(220, 100, 0.05, 0.3);
    this.ring(1850, 0.12, 0.05);
  }
  rollover(): void {
    if (!this.ok('roll', 40)) return;
    this.burst(2400, 2, 0.018, 0.22);
    this.thump(420, 260, 0.025, 0.1);
  }
  launch(power: number): void {
    if (!this.ok('launch', 100)) return;
    this.thump(95, 32, 0.2, 0.5 + 0.3 * power);
    this.burst(2500, 0.8, 0.015, 0.5, 'highpass');
    // the ball rolling up the shooter lane
    this.burst(900 + 600 * power, 0.7, 0.35 + 0.25 * power, 0.14, 'lowpass', 0.03, 200);
  }
  charge(p: number): void {
    if (!this.ok('charge', 90)) return;
    this.burst(1300 + p * 900, 2.2, 0.012, 0.16);
    this.thump(90 + p * 40, 70, 0.025, 0.08);
  }
  drain(): void {
    if (!this.ok('drain', 300)) return;
    this.burst(1400, 0.6, 0.6, 0.25, 'lowpass', 0, 120);
    this.thump(80, 30, 0.35, 0.55, 0.08);
  }
  save(): void {
    if (!this.ok('save', 300)) return;
    this.ring(660, 0.35, 0.05);
    this.ring(990, 0.4, 0.045, 0.1);
  }
  mission(): void {
    if (!this.ok('mission', 300)) return;
    [523, 659, 784].forEach((f, i) => this.ring(f, 0.45, 0.05, i * 0.09));
    this.thump(100, 45, 0.18, 0.3);
  }
  wormhole(): void {
    if (!this.ok('worm', 200)) return;
    this.burst(300, 2.5, 0.55, 0.28, 'bandpass', 0, 2600);
    this.thump(50, 110, 0.5, 0.3);
  }
  over(): void {
    if (!this.ok('over', 500)) return;
    this.thump(90, 34, 0.5, 0.6);
    this.thump(70, 28, 0.7, 0.5, 0.35);
    this.burst(900, 0.7, 0.9, 0.12, 'lowpass', 0.35, 100);
  }
}
