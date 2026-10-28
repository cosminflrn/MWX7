/** Original MWX7 wallpapers — pure SVG/CSS, no third-party images. */

const uri = (svg: string) => `url("data:image/svg+xml,${encodeURIComponent(svg.replace(/\s+/g, ' ').trim())}")`;

const aurora = uri(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#05244f"/><stop offset=".55" stop-color="#0a56a3"/><stop offset="1" stop-color="#082a63"/></linearGradient>
    <radialGradient id="glow" cx=".72" cy=".32" r=".6"><stop offset="0" stop-color="#5ff2ff" stop-opacity=".5"/><stop offset="1" stop-color="#5ff2ff" stop-opacity="0"/></radialGradient>
    <radialGradient id="glow2" cx=".15" cy=".9" r=".5"><stop offset="0" stop-color="#7d5cff" stop-opacity=".35"/><stop offset="1" stop-color="#7d5cff" stop-opacity="0"/></radialGradient>
    <linearGradient id="s1" x1="0" x2="1"><stop offset="0" stop-color="#9ef7ff" stop-opacity="0"/><stop offset=".55" stop-color="#d4fcff" stop-opacity=".6"/><stop offset="1" stop-color="#9ef7ff" stop-opacity="0"/></linearGradient>
    <filter id="b" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="22"/></filter>
    <filter id="b2" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="3"/></filter>
  </defs>
  <rect width="1600" height="1000" fill="url(#bg)"/>
  <rect width="1600" height="1000" fill="url(#glow)"/>
  <rect width="1600" height="1000" fill="url(#glow2)"/>
  <path d="M-100 760 C 300 560, 700 900, 1100 600 S 1600 420, 1800 460" stroke="url(#s1)" stroke-width="140" fill="none" filter="url(#b)"/>
  <path d="M-100 700 C 320 520, 720 860, 1120 560 S 1600 380, 1800 420" stroke="url(#s1)" stroke-width="8" fill="none" filter="url(#b2)"/>
  <path d="M-100 830 C 340 650, 760 950, 1150 690 S 1600 530, 1800 570" stroke="#7fe9ff" stroke-opacity=".3" stroke-width="2.5" fill="none"/>
  <path d="M-100 640 C 360 470, 740 800, 1140 520 S 1600 340, 1800 380" stroke="#ffffff" stroke-opacity=".18" stroke-width="1.5" fill="none"/>
  <circle cx="1150" cy="320" r="230" fill="#7ff0ff" opacity=".1" filter="url(#b)"/>
</svg>`);

const meadow = uri(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2f7fd8"/><stop offset=".7" stop-color="#9fd0ff"/><stop offset="1" stop-color="#d8efff"/></linearGradient>
    <linearGradient id="h1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7cc443"/><stop offset="1" stop-color="#2f7a19"/></linearGradient>
    <linearGradient id="h2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a3dc5a"/><stop offset="1" stop-color="#3d8f1f"/></linearGradient>
    <filter id="c" x="-30%" y="-80%" width="160%" height="260%"><feGaussianBlur stdDeviation="14"/></filter>
  </defs>
  <rect width="1600" height="1000" fill="url(#sky)"/>
  <g fill="#fff" opacity=".85" filter="url(#c)">
    <ellipse cx="300" cy="230" rx="190" ry="45"/><ellipse cx="420" cy="200" rx="120" ry="50"/>
    <ellipse cx="1180" cy="160" rx="230" ry="50"/><ellipse cx="1300" cy="135" rx="120" ry="45"/>
    <ellipse cx="820" cy="330" rx="150" ry="30"/>
  </g>
  <path d="M0 690 C 280 600, 520 640, 760 700 S 1260 600, 1600 640 V1000 H0Z" fill="url(#h1)"/>
  <path d="M-50 1000 C 150 760, 520 700, 900 760 S 1450 860, 1650 800 V1000Z" fill="url(#h2)"/>
  <path d="M-50 1000 C 150 760, 520 700, 900 760 S 1450 860, 1650 800" fill="none" stroke="#d8f5a6" stroke-opacity=".5" stroke-width="3"/>
</svg>`);

export interface Wallpaper {
  id: string;
  name: string;
  css: string;
}

export const wallpapers: Wallpaper[] = [
  { id: 'aurora', name: 'Aero Aurora', css: `${aurora} center / cover no-repeat, #0a56a3` },
  { id: 'meadow', name: 'Meadow', css: `${meadow} center / cover no-repeat, #2f7fd8` },
  {
    id: 'graphite',
    name: 'Graphite Pinstripe',
    css: 'repeating-linear-gradient(0deg, rgba(255,255,255,.045) 0 1px, transparent 1px 4px), radial-gradient(ellipse at 50% 28%, #7395bb, #2f4763 62%, #17232f)',
  },
  {
    id: 'sunset',
    name: 'Dusk Glass',
    css: 'radial-gradient(ellipse at 75% 20%, rgba(255,214,140,.55), transparent 55%), radial-gradient(ellipse at 15% 85%, rgba(120,70,220,.55), transparent 60%), linear-gradient(160deg, #ff8a5c, #c4407a 45%, #3b1f6e)',
  },
];

export function wallpaperCss(id: string): string {
  return (wallpapers.find((w) => w.id === id) ?? wallpapers[0]).css;
}
