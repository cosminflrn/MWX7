/** Original 64x64 icon: a glossy blue globe with a gold swoosh orbit. Gradient ids are br- prefixed. */
export const browserIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <radialGradient id="br-globe" cx=".38" cy=".28" r=".85"><stop offset="0" stop-color="#9fe0ff"/><stop offset=".45" stop-color="#2f8fe6"/><stop offset="1" stop-color="#0b3f94"/></radialGradient>
    <linearGradient id="br-land" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#b9f08a"/><stop offset="1" stop-color="#3f9b32"/></linearGradient>
    <linearGradient id="br-swoosh" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffd66b" stop-opacity="0"/><stop offset=".35" stop-color="#ffc23d"/><stop offset=".75" stop-color="#f08a0c"/><stop offset="1" stop-color="#ffb43a" stop-opacity=".2"/></linearGradient>
    <linearGradient id="br-shine" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".8"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  </defs>
  <circle cx="32" cy="32" r="26" fill="url(#br-globe)"/>
  <path d="M16 22c4-6 10-7 13-5 2 2-1 5 2 7s1 6-3 7-5 5-8 4-5-8-4-13Z" fill="url(#br-land)" opacity=".92"/>
  <path d="M38 38c4-3 9-2 10 2s-3 9-7 10-6-2-6-5 1-5 3-7Z" fill="url(#br-land)" opacity=".92"/>
  <path d="M40 13c4 1 8 4 9 8-3-2-6-2-8-1s-3-4-1-7Z" fill="url(#br-land)" opacity=".85"/>
  <path d="M9 41C13 29 30 21 48 20c5-.3 8 .4 9 1.7-6-.3-14 1.2-22 5C24 32 15 38 9 41Z" fill="none"/>
  <path d="M5.5 38C8 24 26 13 46 14c7 0 12 2 13 5-5-2.5-13-2-22 2C25 26 12 32 5.5 38Z" fill="url(#br-swoosh)"/>
  <path d="M10 25C13 13 22 7 32 7s19 6 22 18c-7-5-14-7-22-7S17 20 10 25Z" fill="url(#br-shine)" opacity=".6"/>
  <circle cx="32" cy="32" r="25.6" fill="none" stroke="#06316f" stroke-opacity=".55" stroke-width=".7"/>
</svg>`;
