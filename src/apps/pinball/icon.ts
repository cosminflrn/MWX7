/** Original 64x64 icon: a chrome ball above a glowing deep-space table, flipper at the bottom. Gradient ids are pb- prefixed. */
export const pinballIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="pb-body" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a2f5a"/><stop offset="1" stop-color="#0a0c22"/></linearGradient>
    <radialGradient id="pb-neb" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#b24cff" stop-opacity=".85"/><stop offset=".5" stop-color="#2b5bd8" stop-opacity=".45"/><stop offset="1" stop-color="#05061a" stop-opacity="0"/></radialGradient>
    <linearGradient id="pb-rail" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4f8ff"/><stop offset=".45" stop-color="#8d98ad"/><stop offset=".55" stop-color="#cfd7e6"/><stop offset="1" stop-color="#4b5467"/></linearGradient>
    <radialGradient id="pb-ball" cx=".36" cy=".3" r=".8"><stop offset="0" stop-color="#ffffff"/><stop offset=".3" stop-color="#cfd8e8"/><stop offset=".7" stop-color="#5d6980"/><stop offset="1" stop-color="#151a28"/></radialGradient>
    <radialGradient id="pb-glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#5df3ff" stop-opacity=".9"/><stop offset="1" stop-color="#5df3ff" stop-opacity="0"/></radialGradient>
    <radialGradient id="pb-bump" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#ffe9a8"/><stop offset=".5" stop-color="#ff9d2e"/><stop offset="1" stop-color="#8a2d00"/></radialGradient>
    <linearGradient id="pb-flip" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".4" stop-color="#9aa6bb"/><stop offset="1" stop-color="#3a4254"/></linearGradient>
  </defs>
  <path d="M10 6 H54 Q58 6 58 10 V56 Q58 60 54 60 H10 Q6 60 6 56 V10 Q6 6 10 6Z" fill="url(#pb-rail)"/>
  <path d="M12 9 H52 Q55 9 55 12 V54 Q55 57 52 57 H12 Q9 57 9 54 V12 Q9 9 12 9Z" fill="url(#pb-body)"/>
  <path d="M12 9 H52 Q55 9 55 12 V54 Q55 57 52 57 H12 Q9 57 9 54 V12 Q9 9 12 9Z" fill="url(#pb-neb)"/>
  <g fill="#fff"><circle cx="16" cy="16" r=".8"/><circle cx="46" cy="14" r=".7"/><circle cx="50" cy="30" r=".6"/><circle cx="14" cy="34" r=".6"/><circle cx="38" cy="22" r=".5"/><circle cx="24" cy="12" r=".5"/></g>
  <circle cx="44" cy="26" r="7.5" fill="url(#pb-glow)"/>
  <circle cx="44" cy="26" r="4.6" fill="url(#pb-bump)" stroke="#fff3c9" stroke-width=".8"/>
  <circle cx="20" cy="30" r="3.4" fill="url(#pb-bump)" stroke="#fff3c9" stroke-width=".7"/>
  <path d="M14 46 L14 40 M50 46 L50 40" stroke="#5df3ff" stroke-width="1.6" stroke-linecap="round" opacity=".9"/>
  <path d="M14 48 L24 54" stroke="#5df3ff" stroke-width="1.2" stroke-linecap="round" opacity=".7"/>
  <path d="M50 48 L40 54" stroke="#5df3ff" stroke-width="1.2" stroke-linecap="round" opacity=".7"/>
  <path d="M17 51 Q18 48.2 21.2 49.4 L31 54.6 Q32.6 55.8 31 57 Q29.8 57.6 28.4 57 L18 54.4 Q16.4 53.6 17 51Z" fill="url(#pb-flip)" stroke="#262c3a" stroke-width=".6"/>
  <ellipse cx="36" cy="44.5" rx="7.5" ry="2.4" fill="#000" opacity=".5"/>
  <circle cx="34" cy="38" r="8.5" fill="url(#pb-ball)" stroke="#0d1220" stroke-width=".6"/>
  <ellipse cx="31.2" cy="34.2" rx="3.2" ry="2" fill="#fff" opacity=".85" transform="rotate(-30 31.2 34.2)"/>
  <path d="M26.5 40 Q34 44.5 41.5 40" stroke="#7fe7ff" stroke-width="1" fill="none" opacity=".55"/>
</svg>`;
