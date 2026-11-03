/** Original 64x64 icon: a glossy blue tile holding a spiked mine, with a red flag. Ids are mn- prefixed. */
export const minesIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="mn-tile" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fcaff"/><stop offset=".5" stop-color="#3c8cec"/><stop offset=".51" stop-color="#2468d0"/><stop offset="1" stop-color="#4d9ff5"/></linearGradient>
    <linearGradient id="mn-rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f1f6fc"/><stop offset=".5" stop-color="#8c9db2"/><stop offset="1" stop-color="#46556a"/></linearGradient>
    <radialGradient id="mn-bomb" cx=".36" cy=".3" r=".8"><stop offset="0" stop-color="#8d98ad"/><stop offset=".4" stop-color="#2d3646"/><stop offset="1" stop-color="#05070c"/></radialGradient>
  </defs>
  <rect x="4" y="4" width="56" height="56" rx="9" fill="url(#mn-rim)"/>
  <rect x="6.5" y="6.5" width="51" height="51" rx="7" fill="url(#mn-tile)"/>
  <path d="M8 24C9 13 17 8 32 8S55 13 56 24C46 18 40 17 32 17S18 18 8 24Z" fill="#fff" opacity=".35"/>
  <ellipse cx="29" cy="46" rx="14" ry="3" fill="#06204a" opacity=".4"/>
  <g stroke="#10151f" stroke-width="3" stroke-linecap="round">
    <path d="M29 24V44M19 34H39M22 27L36 41M36 27L22 41"/>
  </g>
  <circle cx="29" cy="34" r="10" fill="url(#mn-bomb)" stroke="#05070c" stroke-width=".7"/>
  <ellipse cx="25.6" cy="30" rx="3.2" ry="2" fill="#fff" opacity=".8" transform="rotate(-30 25.6 30)"/>
  <path d="M44 25V13" stroke="#3a4350" stroke-width="1.6" stroke-linecap="round"/>
  <path d="M44.6 13.4L53 16.6L44.6 20.4Z" fill="#e0402a" stroke="#8c1d0e" stroke-width=".6" stroke-linejoin="round"/>
</svg>`;
