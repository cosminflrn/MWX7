/** Original 64x64 icon: a white-bordered landscape print with sun, mountains and a blue glass sheen. Ids are ph- prefixed. */
export const photosIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="ph-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4aa3f0"/><stop offset="1" stop-color="#bfe4ff"/></linearGradient>
    <linearGradient id="ph-far" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7f9cc0"/><stop offset="1" stop-color="#4c6a94"/></linearGradient>
    <linearGradient id="ph-near" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4fae5e"/><stop offset="1" stop-color="#1f6b3a"/></linearGradient>
    <linearGradient id="ph-card" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#d9e2ee"/></linearGradient>
    <linearGradient id="ph-shine" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".6"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <clipPath id="ph-clip"><rect x="9" y="11" width="46" height="35" rx="1.500"/></clipPath>
  </defs>
  <g transform="rotate(-5 32 32)" opacity=".55"><rect x="8" y="9" width="48" height="44" rx="3" fill="#8aa0bd"/></g>
  <rect x="6" y="8" width="52" height="48" rx="3" fill="url(#ph-card)" stroke="#5b7391" stroke-opacity=".6" stroke-width=".7"/>
  <g clip-path="url(#ph-clip)">
    <rect x="9" y="11" width="46" height="35" fill="url(#ph-sky)"/>
    <circle cx="43" cy="21" r="4.500" fill="#fff7c9"/>
    <path d="M9 40 22 24l8 10 7-8 18 16v4H9Z" fill="url(#ph-far)"/>
    <path d="M22 24l3 3.600-3-1.200-2.600 2.200Z" fill="#fff" opacity=".8"/>
    <path d="M9 42c9-5 18-6 28-3s14 2 18 0v7H9Z" fill="url(#ph-near)"/>
    <path d="M9 11h46v13C44 20 24 20 9 25Z" fill="url(#ph-shine)" opacity=".5"/>
  </g>
  <rect x="9" y="11" width="46" height="35" rx="1.500" fill="none" stroke="#10304f" stroke-opacity=".4" stroke-width=".6"/>
  <rect x="6" y="8" width="52" height="48" rx="3" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width=".6"/>
</svg>`;
