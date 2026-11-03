/**
 * Background music: a real piano recording (J.S. Bach, Goldberg Variations, Variatio 3, Kimiko Ishizaka, CC0; see public/media/CREDITS.md).
 * The file is pre-built as a seamless loop (its tail is cross-faded into its head), so a plain looping <audio> is gapless.
 */
const SRC = `${import.meta.env.BASE_URL}media/music/solitaire-goldberg-variatio-3.ogg`;
const VOLUME = 0.4;

export class GameMusic {
  enabled = true;
  private audio: HTMLAudioElement | null = null;
  private fade = 0;
  private disposed = false;

  /** Safe to call repeatedly; retries play() so the first click can lift the autoplay block. */
  start(): void {
    if (this.disposed || !this.enabled) return;
    try {
      if (!this.audio) {
        const a = new Audio(SRC);
        a.loop = true;
        a.preload = 'auto';
        a.volume = VOLUME;
        this.audio = a;
      }
      if (this.audio.paused) void this.audio.play().catch(() => undefined);
    } catch {
      /* audio unavailable: the game works fine without it */
    }
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    const a = this.audio;
    if (on) {
      if (a) a.volume = VOLUME;
      this.start();
      return;
    }
    if (!a) return;
    // short fade-out so the toggle never clicks
    clearInterval(this.fade);
    this.fade = window.setInterval(() => {
      a.volume = Math.max(0, a.volume - 0.08);
      if (a.volume <= 0) {
        clearInterval(this.fade);
        a.pause();
      }
    }, 30);
  }

  dispose(): void {
    this.disposed = true;
    clearInterval(this.fade);
    this.audio?.pause();
    this.audio = null;
  }
}
