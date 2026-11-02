import { bus } from '../core/events';
import { settings } from '../core/settings';
import type { Settings } from '../core/types';

/** Win7 "Window Color": recolours every glass surface from Settings, live. */
function apply(s: Settings): void {
  const m = /^#?([0-9a-f]{6})$/i.exec(s.glassColor);
  const n = m ? parseInt(m[1], 16) : 0x1e64dc;
  const root = document.documentElement.style;
  root.setProperty('--glass-rgb', `${n >> 16}, ${(n >> 8) & 255}, ${n & 255}`);
  // 0 → nearly clear glass, 100 → deeply tinted (still see-through).
  const i = Math.min(100, Math.max(0, s.glassIntensity)) / 100;
  root.setProperty('--glass-a', (0.08 + i * 0.7).toFixed(3));
}

export function mountGlass(): void {
  apply(settings.get());
  bus.on('settings:change', apply);
}
