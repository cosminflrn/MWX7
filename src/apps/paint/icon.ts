/**
 * Paint app icon: a wooden painter's palette with four glossy paint blobs and a brush resting across it.
 * Original artwork, soft studio lighting, hairline edges. Gradient ids are prefixed `pt-`; the registry
 * turns SVGs with <defs> into <img> data URIs, so they stay self-contained.
 */
export const paintIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="pt-wood" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4dcb0"/><stop offset=".55" stop-color="#dcae6c"/><stop offset="1" stop-color="#b57d3a"/></linearGradient>
    <linearGradient id="pt-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff2d4" stop-opacity=".9"/><stop offset="1" stop-color="#fff2d4" stop-opacity="0"/></linearGradient>
    <radialGradient id="pt-red" cx=".38" cy=".3" r=".8"><stop offset="0" stop-color="#ff9c86"/><stop offset=".6" stop-color="#e0301b"/><stop offset="1" stop-color="#a81a0b"/></radialGradient>
    <radialGradient id="pt-yel" cx=".38" cy=".3" r=".8"><stop offset="0" stop-color="#fff6a8"/><stop offset=".6" stop-color="#f6c421"/><stop offset="1" stop-color="#c58c06"/></radialGradient>
    <radialGradient id="pt-grn" cx=".38" cy=".3" r=".8"><stop offset="0" stop-color="#c4f58c"/><stop offset=".6" stop-color="#46ad2c"/><stop offset="1" stop-color="#25741a"/></radialGradient>
    <radialGradient id="pt-blu" cx=".38" cy=".3" r=".8"><stop offset="0" stop-color="#a8dcff"/><stop offset=".6" stop-color="#2b7ee0"/><stop offset="1" stop-color="#1450a8"/></radialGradient>
    <radialGradient id="pt-hole" cx=".5" cy=".6" r=".6"><stop offset="0" stop-color="#7c5a30"/><stop offset="1" stop-color="#4a3319"/></radialGradient>
    <linearGradient id="pt-handle" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7fb6f2"/><stop offset=".45" stop-color="#2d73cf"/><stop offset="1" stop-color="#173f86"/></linearGradient>
    <linearGradient id="pt-ferrule" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fafbfd"/><stop offset=".5" stop-color="#b7c2cf"/><stop offset="1" stop-color="#6f7c8c"/></linearGradient>
    <linearGradient id="pt-bristle" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2a6fd0"/><stop offset=".5" stop-color="#5aa2f0"/><stop offset="1" stop-color="#1c55ad"/></linearGradient>
  </defs>
  <path d="M30 7C14 7 4 18.5 4 31c0 15.5 12.5 26 28 26 6.2 0 9.6-3.2 9.6-7.2 0-4.2-4.2-5.4-4.2-9.4 0-3.6 3.4-4.4 9-4.4 8.6 0 13.6-5.2 13.6-11.6C60 13.8 47 7 30 7z"
        fill="url(#pt-wood)" stroke="#5a3a14" stroke-opacity=".55" stroke-width=".8" stroke-linejoin="round"/>
  <path d="M30 8.2C15 8.2 5.3 18.8 5.3 31" fill="none" stroke="url(#pt-rim)" stroke-width="1.6" stroke-linecap="round"/>
  <ellipse cx="17" cy="42" rx="4.4" ry="3.6" fill="url(#pt-hole)" stroke="#4a3319" stroke-opacity=".6" stroke-width=".7"/>
  <ellipse cx="17" cy="40.6" rx="3.4" ry="1.5" fill="#000" opacity=".16"/>
  <g stroke="#000" stroke-opacity=".28" stroke-width=".7">
    <ellipse cx="15.5" cy="25" rx="5.6" ry="5" fill="url(#pt-red)"/>
    <ellipse cx="27.5" cy="16.5" rx="5.6" ry="5" fill="url(#pt-yel)"/>
    <ellipse cx="41" cy="18" rx="5.4" ry="4.8" fill="url(#pt-grn)"/>
    <ellipse cx="51" cy="28.5" rx="5.2" ry="4.6" fill="url(#pt-blu)"/>
  </g>
  <g fill="#fff" opacity=".7">
    <ellipse cx="13.6" cy="22.8" rx="2" ry="1.2"/>
    <ellipse cx="25.6" cy="14.3" rx="2" ry="1.2"/>
    <ellipse cx="39.2" cy="15.9" rx="1.9" ry="1.1"/>
    <ellipse cx="49.3" cy="26.5" rx="1.9" ry="1.1"/>
  </g>
  <g transform="translate(22 30) rotate(-38) scale(.84)">
    <path d="M0 0c-2.2 2.6-2.4 6.4-2.4 9.2h4.8c0-2.8-.2-6.6-2.4-9.2z" fill="url(#pt-bristle)" stroke="#0f2f6a" stroke-opacity=".5" stroke-width=".7" transform="translate(0 0)"/>
    <rect x="-3" y="8.6" width="6" height="9" rx="1" fill="url(#pt-ferrule)" stroke="#2a3340" stroke-opacity=".5" stroke-width=".7"/>
    <path d="M-3 12.2h6M-3 14.4h6" stroke="#fff" stroke-opacity=".45" stroke-width=".6"/>
    <path d="M-2.4 17.4h4.8l.9 24.2a3.3 3.3 0 0 1-6.6 0z" fill="url(#pt-handle)" stroke="#0f2f6a" stroke-opacity=".6" stroke-width=".7"/>
    <path d="M-1.2 19.5l-.3 19" stroke="#fff" stroke-opacity=".55" stroke-width="1" stroke-linecap="round"/>
  </g>
</svg>`;
