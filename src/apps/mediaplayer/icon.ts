/** Original 64x64 icon: a dark glossy disc with an orange play triangle and a blue rim. Gradient ids are mp- prefixed. */
export const mediaPlayerIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="mp-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fd2ff"/><stop offset=".5" stop-color="#2b7fe0"/><stop offset="1" stop-color="#0c3b8e"/></linearGradient>
    <radialGradient id="mp-disc" cx=".4" cy=".3" r=".9"><stop offset="0" stop-color="#4a5566"/><stop offset=".6" stop-color="#1a202b"/><stop offset="1" stop-color="#090c12"/></radialGradient>
    <linearGradient id="mp-play" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffc86a"/><stop offset=".5" stop-color="#ff8f1f"/><stop offset="1" stop-color="#d4580a"/></linearGradient>
    <linearGradient id="mp-shine" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  </defs>
  <circle cx="32" cy="32" r="27.5" fill="url(#mp-rim)"/>
  <circle cx="32" cy="32" r="23.5" fill="url(#mp-disc)"/>
  <circle cx="32" cy="32" r="17" fill="none" stroke="#fff" stroke-opacity=".08" stroke-width="1"/>
  <circle cx="32" cy="32" r="20.5" fill="none" stroke="#fff" stroke-opacity=".06" stroke-width="1"/>
  <path d="M26 21.5v21c0 1.3 1.4 2 2.5 1.3l17-10.5c1-.6 1-2 0-2.6l-17-10.5c-1.1-.7-2.5 0-2.5 1.3Z" fill="url(#mp-play)" stroke="#8a3600" stroke-opacity=".5" stroke-width=".6"/>
  <path d="M10 27C12 15 21 8.500 32 8.500S52 15 54 27C47 22.500 40 21 32 21S17 22.500 10 27Z" fill="url(#mp-shine)" opacity=".55"/>
  <circle cx="32" cy="32" r="27.200" fill="none" stroke="#06265c" stroke-opacity=".55" stroke-width=".7"/>
</svg>`;
