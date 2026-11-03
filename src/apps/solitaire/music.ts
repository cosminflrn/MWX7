/**
 * Background music: a calm, looping ambient piece synthesized live with Web Audio (no audio files, original harmony).
 * Chords are voiced as a soft pad plus a gentle arpeggio; everything is scheduled a little ahead on one timeline so the loop is seamless.
 */
const BAR = 4; // seconds per chord
const CHORDS: number[][] = [[48, 55, 60, 64, 67], [45, 52, 57, 60, 64], [41, 48, 53, 57, 64], [43, 50, 55, 59, 62]]; // MIDI notes, bass first
const ARP = [0, 2, 1, 3, 2, 1, 3, -1]; // indices into the chord (above the bass), 8 eighth-note steps per bar
const LOOKAHEAD = 2;
const hz = (m: number) => 440 * Math.pow(2, (m - 69) / 12);

export class GameMusic {
  enabled = true;
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private bus: GainNode | null = null;
  private timer = 0;
  private next = 0;
  private bar = 0;
  private disposed = false;

  /** Safe to call repeatedly; resumes a suspended context (autoplay policy) and starts the scheduler once. */
  start(): void {
    if (this.disposed) return;
    try {
      if (!this.ctx) {
        const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        const ctx = new Ctor();
        const master = ctx.createGain();
        master.gain.value = this.enabled ? 0.5 : 0;
        // A soft feedback echo stands in for reverb.
        const bus = ctx.createGain();
        const delay = ctx.createDelay(1);
        delay.delayTime.value = 0.42;
        const fb = ctx.createGain();
        fb.gain.value = 0.38;
        const lp = ctx.createBiquadFilter();
        lp.type = 'lowpass';
        lp.frequency.value = 2400;
        bus.connect(master);
        bus.connect(delay);
        delay.connect(lp);
        lp.connect(fb);
        fb.connect(delay);
        lp.connect(master);
        master.connect(ctx.destination);
        this.ctx = ctx;
        this.master = master;
        this.bus = bus;
        this.next = ctx.currentTime + 0.1;
        this.timer = window.setInterval(() => this.pump(), 400);
        this.pump();
      }
      if (this.ctx.state === 'suspended') void this.ctx.resume();
    } catch {
      /* audio unavailable: the game works fine without it */
    }
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    if (this.master && this.ctx) this.master.gain.setTargetAtTime(on ? 0.5 : 0, this.ctx.currentTime, 0.08);
    if (on) this.start();
  }

  dispose(): void {
    this.disposed = true;
    clearInterval(this.timer);
    void this.ctx?.close().catch(() => undefined);
    this.ctx = null;
  }

  private pump(): void {
    const ctx = this.ctx;
    if (!ctx) return;
    while (this.next < ctx.currentTime + LOOKAHEAD) {
      this.playBar(CHORDS[this.bar % CHORDS.length], this.next);
      this.next += BAR;
      this.bar++;
    }
  }

  private tone(freq: number, t: number, dur: number, peak: number, type: OscillatorType, attack: number): void {
    const ctx = this.ctx;
    if (!ctx || !this.bus) return;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = type;
    o.frequency.value = freq;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(peak, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g);
    g.connect(this.bus);
    o.start(t);
    o.stop(t + dur + 0.05);
  }

  private playBar(chord: number[], t: number): void {
    const [bass, ...rest] = chord;
    this.tone(hz(bass - 12), t, BAR * 1.1, 0.16, 'sine', 0.3);
    for (const m of rest) {
      this.tone(hz(m) * 1.003, t, BAR * 1.15, 0.045, 'triangle', 0.9);
      this.tone(hz(m) / 1.003, t, BAR * 1.15, 0.045, 'sine', 0.9);
    }
    const step = BAR / 8;
    ARP.forEach((idx, i) => {
      if (idx < 0) return;
      const m = rest[idx % rest.length] + 12;
      this.tone(hz(m), t + i * step, 1.6, 0.075, 'sine', 0.012);
    });
  }
}
