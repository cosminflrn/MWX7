/** Original 64x64 icon: two fanned playing cards (ace of hearts over a spade) on a green felt tile. Ids are sl- prefixed. */
export const solitaireIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <radialGradient id="sl-felt" cx=".5" cy=".3" r=".9"><stop offset="0" stop-color="#4fb56a"/><stop offset="1" stop-color="#14502b"/></radialGradient>
    <linearGradient id="sl-card" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e3eaf3"/></linearGradient>
    <linearGradient id="sl-rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e9f1fb"/><stop offset=".5" stop-color="#8ea0b6"/><stop offset="1" stop-color="#4c5b70"/></linearGradient>
  </defs>
  <rect x="5" y="5" width="54" height="54" rx="8" fill="url(#sl-rim)"/>
  <rect x="7" y="7" width="50" height="50" rx="6.5" fill="url(#sl-felt)"/>
  <g transform="rotate(-14 24 36)">
    <rect x="12" y="15" width="25" height="35" rx="3" fill="url(#sl-card)" stroke="#5a6b80" stroke-width=".7"/>
    <path d="M24.5 36C19.5 32.6 18.6 30 18.6 28.4C18.6 26.6 20 25.6 21.4 25.6C22.8 25.6 23.9 26.4 24.5 27.6C25.1 26.4 26.2 25.6 27.6 25.6C29 25.6 30.4 26.6 30.4 28.4C30.4 30 29.5 32.6 24.5 36Z" fill="#1d2430"/>
  </g>
  <g transform="rotate(10 40 36)">
    <rect x="28" y="14" width="25" height="35" rx="3" fill="url(#sl-card)" stroke="#5a6b80" stroke-width=".7"/>
    <path d="M40.5 35C45.5 31.6 46.4 29 46.4 27.4C46.4 25.6 45 24.6 43.6 24.6C42.2 24.6 41.1 25.4 40.5 26.6C39.9 25.4 38.8 24.6 37.4 24.6C36 24.6 34.6 25.6 34.6 27.4C34.6 29 35.5 31.6 40.5 35Z" fill="#c0261c"/>
    <text x="32.6" y="23" font-size="7" font-weight="700" fill="#c0261c" font-family="Georgia,serif">A</text>
  </g>
  <path d="M10 22C12 12 20 8 32 8S52 12 54 22C46 17 40 16 32 16S18 17 10 22Z" fill="#fff" opacity=".22"/>
</svg>`;
