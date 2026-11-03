/** Original 64x64 "getting started" icon: glossy blue disc with a compass star. Ids are wl- prefixed. */
export const welcomeIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <radialGradient id="wl-bg" cx=".35" cy=".25" r=".9"><stop offset="0" stop-color="#8fd0ff"/><stop offset=".55" stop-color="#1f74d8"/><stop offset="1" stop-color="#0b3a85"/></radialGradient>
    <linearGradient id="wl-st" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fffbe0"/><stop offset="1" stop-color="#ffc83a"/></linearGradient>
    <linearGradient id="wl-gl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  </defs>
  <circle cx="32" cy="32" r="28" fill="url(#wl-bg)" stroke="#0a2f6e" stroke-width="2"/>
  <circle cx="32" cy="32" r="22" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="1.500"/>
  <path d="M32 9l5.500 17.500L55 32l-17.500 5.500L32 55l-5.500-17.500L9 32l17.500-5.500z" fill="url(#wl-st)" stroke="#9a6a00" stroke-width="1.200" stroke-linejoin="round"/>
  <circle cx="32" cy="32" r="3.500" fill="#1f74d8" stroke="#fff" stroke-width="1"/>
  <ellipse cx="32" cy="17" rx="21" ry="12" fill="url(#wl-gl)"/>
</svg>`;
