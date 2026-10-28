/**
 * Original artwork for Explorer: a hard-disk drive glyph and the abstract "Aero" sample pictures.
 * Everything here is drawn from scratch (SVG gradients, blur, translucent shapes) — no third-party assets.
 */

export const driveIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="xd-top" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6f8fb"/><stop offset=".5" stop-color="#d3dae4"/><stop offset="1" stop-color="#aab5c4"/></linearGradient>
    <linearGradient id="xd-face" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c7d0dc"/><stop offset=".55" stop-color="#8e9bad"/><stop offset="1" stop-color="#6d7a8d"/></linearGradient>
    <linearGradient id="xd-sheen" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity=".25"/></linearGradient>
  </defs>
  <ellipse cx="32" cy="55" rx="25" ry="3.2" fill="#000" opacity=".22"/>
  <path d="M7 24 14 12h36l7 12z" fill="url(#xd-top)" stroke="#000" stroke-opacity=".28" stroke-width=".75" stroke-linejoin="round"/>
  <rect x="7" y="24" width="50" height="27" rx="3" fill="url(#xd-face)" stroke="#000" stroke-opacity=".32" stroke-width=".75"/>
  <rect x="7" y="24" width="50" height="27" rx="3" fill="url(#xd-sheen)"/>
  <path d="M8 25.5h48" stroke="#fff" stroke-opacity=".7" stroke-width="1"/>
  <rect x="12" y="40" width="26" height="5" rx="1.5" fill="#000" opacity=".18"/>
  <rect x="12.5" y="40.5" width="25" height="4" rx="1" fill="#566377" opacity=".55"/>
  <circle cx="47" cy="42.5" r="2" fill="#6fe27a" stroke="#1d7a2d" stroke-opacity=".7" stroke-width=".6"/>
  <circle cx="46.4" cy="41.9" r=".7" fill="#fff" opacity=".85"/>
  <circle cx="51.5" cy="42.5" r="1.1" fill="#4f5b6c"/>
</svg>`;

export interface SampleImage {
  name: string;
  svg: string;
}

/** Tiny deterministic PRNG so the bokeh looks organic but is identical on every load. */
function rng(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

const open = (defs: string, body: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" width="800" height="500"><defs>${defs}</defs>${body}</svg>`;

function aurora(): string {
  const r = rng(7);
  const stars = Array.from({ length: 46 }, () => {
    const x = Math.round(r() * 800);
    const y = Math.round(r() * 230);
    return `<circle cx="${x}" cy="${y}" r="${(0.5 + r() * 1.1).toFixed(1)}" fill="#fff" opacity="${(0.25 + r() * 0.6).toFixed(2)}"/>`;
  }).join('');
  return open(
    `<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#050f30"/><stop offset=".55" stop-color="#0c4687"/><stop offset="1" stop-color="#34b4c8"/></linearGradient>
     <linearGradient id="a" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#6cf2cf" stop-opacity="0"/><stop offset=".4" stop-color="#6cf2cf" stop-opacity=".8"/><stop offset="1" stop-color="#5a9bff" stop-opacity="0"/></linearGradient>
     <linearGradient id="b" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#9a7bff" stop-opacity="0"/><stop offset=".5" stop-color="#7cc4ff" stop-opacity=".6"/><stop offset="1" stop-color="#6cf2cf" stop-opacity="0"/></linearGradient>
     <filter id="f1" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="16"/></filter>
     <filter id="f2" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="7"/></filter>
     <linearGradient id="hz" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#021226" stop-opacity="0"/><stop offset="1" stop-color="#021226" stop-opacity=".75"/></linearGradient>`,
    `<rect width="800" height="500" fill="url(#bg)"/>${stars}
     <g filter="url(#f1)"><path d="M-40 250C120 110 300 330 470 190S740 110 860 230V320C700 230 540 390 380 310S120 250-40 340Z" fill="url(#a)"/></g>
     <g filter="url(#f2)" opacity=".9"><path d="M-40 300C140 190 310 370 480 250S730 190 860 280V300C720 250 560 390 390 330S140 280-40 330Z" fill="url(#b)"/></g>
     <path d="M0 400C120 372 230 410 360 388S620 360 800 396V500H0Z" fill="#031a33" opacity=".9"/>
     <path d="M0 430C150 408 280 446 430 424S660 410 800 432V500H0Z" fill="#021226"/>
     <rect y="340" width="800" height="160" fill="url(#hz)"/>`,
  );
}

function bokeh(): string {
  const r = rng(21);
  const hues = ['#7fd6ff', '#9fe8ff', '#b7a6ff', '#ffffff', '#6fb4ff', '#8ff0d4'];
  const discs = Array.from({ length: 34 }, () => {
    const rad = 18 + r() * 62;
    const c = hues[Math.floor(r() * hues.length)];
    return `<circle cx="${Math.round(r() * 800)}" cy="${Math.round(r() * 500)}" r="${rad.toFixed(0)}" fill="${c}" fill-opacity="${(0.07 + r() * 0.16).toFixed(2)}" stroke="${c}" stroke-opacity=".28" stroke-width="1.2"/>`;
  }).join('');
  return open(
    `<radialGradient id="bg" cx=".3" cy=".25" r="1.05"><stop offset="0" stop-color="#2d8fe0"/><stop offset=".5" stop-color="#14498f"/><stop offset="1" stop-color="#091c47"/></radialGradient>
     <radialGradient id="gl" cx=".7" cy=".8" r=".6"><stop offset="0" stop-color="#7fe9ff" stop-opacity=".55"/><stop offset="1" stop-color="#7fe9ff" stop-opacity="0"/></radialGradient>
     <filter id="s"><feGaussianBlur stdDeviation="1.6"/></filter>`,
    `<rect width="800" height="500" fill="url(#bg)"/><rect width="800" height="500" fill="url(#gl)"/><g filter="url(#s)">${discs}</g>`,
  );
}

function glassWaves(): string {
  const wave = (y: number, amp: number, op: number, fill: string) =>
    `<path d="M0 ${y}C120 ${y - amp} 240 ${y + amp} 400 ${y}S680 ${y - amp} 800 ${y + 10}V500H0Z" fill="${fill}" fill-opacity="${op}"/>
     <path d="M0 ${y}C120 ${y - amp} 240 ${y + amp} 400 ${y}S680 ${y - amp} 800 ${y + 10}" fill="none" stroke="#fff" stroke-opacity="${(op + 0.25).toFixed(2)}" stroke-width="1.4"/>`;
  return open(
    `<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e9f6ff"/><stop offset=".5" stop-color="#8fd0f2"/><stop offset="1" stop-color="#2b86c9"/></linearGradient>
     <radialGradient id="sun" cx=".78" cy=".18" r=".42"><stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>`,
    `<rect width="800" height="500" fill="url(#bg)"/><rect width="800" height="500" fill="url(#sun)"/>
     ${wave(250, 46, 0.22, '#ffffff')}${wave(300, 40, 0.26, '#bfe8fb')}${wave(352, 36, 0.32, '#5fb6e6')}${wave(404, 30, 0.42, '#2b7fc1')}${wave(448, 22, 0.62, '#16568f')}`,
  );
}

function horizon(): string {
  return open(
    `<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1c2a66"/><stop offset=".45" stop-color="#7a4f9a"/><stop offset=".75" stop-color="#f08a6a"/><stop offset="1" stop-color="#ffd08a"/></linearGradient>
     <radialGradient id="sun" cx=".5" cy=".7" r=".4"><stop offset="0" stop-color="#fff4cf"/><stop offset=".35" stop-color="#ffd48a" stop-opacity=".85"/><stop offset="1" stop-color="#ffb06a" stop-opacity="0"/></radialGradient>
     <linearGradient id="h1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6a4a8c"/><stop offset="1" stop-color="#3d2f6b"/></linearGradient>
     <linearGradient id="h2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3f3777"/><stop offset="1" stop-color="#241f52"/></linearGradient>
     <linearGradient id="h3" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#241f52"/><stop offset="1" stop-color="#121238"/></linearGradient>`,
    `<rect width="800" height="500" fill="url(#sky)"/><rect width="800" height="500" fill="url(#sun)"/>
     <circle cx="400" cy="350" r="34" fill="#fff6dc" opacity=".92"/>
     <path d="M0 360C110 330 210 346 320 336S560 306 800 350V500H0Z" fill="url(#h1)"/>
     <path d="M0 400C140 372 260 398 400 384S650 358 800 394V500H0Z" fill="url(#h2)"/>
     <path d="M0 448C160 424 300 452 450 436S690 418 800 446V500H0Z" fill="url(#h3)"/>`,
  );
}

export const sampleImages = (): SampleImage[] => [
  { name: 'Aurora.svg', svg: aurora() },
  { name: 'Bokeh.svg', svg: bokeh() },
  { name: 'Glass Waves.svg', svg: glassWaves() },
  { name: 'Horizon.svg', svg: horizon() },
];
