/**
 * MWX 7 original icon set — realistic style: soft studio lighting, fine
 * hairline edges, subtle gradients, no thick outlines or toy gloss.
 * All artwork is original; never paste in Apple / Microsoft icons.
 * Shared gradients live once in ICON_DEFS (injected into <body> at boot).
 * App-specific icons may also live in src/apps/<id>/icon.ts with their own defs.
 */

export const ICON_DEFS = `
<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">
  <defs>
    <linearGradient id="mx-gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".85"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>

    <!-- logo -->
    <radialGradient id="mx-orb-glass" cx=".5" cy=".38" r=".72"><stop offset="0" stop-color="#2f78dc"/><stop offset=".55" stop-color="#0d3482"/><stop offset="1" stop-color="#041338"/></radialGradient>
    <radialGradient id="mx-orb-glow" cx=".5" cy="1" r=".62"><stop offset="0" stop-color="#7fe9ff" stop-opacity=".85"/><stop offset=".6" stop-color="#3aa8ff" stop-opacity=".25"/><stop offset="1" stop-color="#3aa8ff" stop-opacity="0"/></radialGradient>
    <linearGradient id="mx-b-red" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff9a6e"/><stop offset="1" stop-color="#e42a1d"/></linearGradient>
    <linearGradient id="mx-b-green" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#b7f06a"/><stop offset="1" stop-color="#2f9a1c"/></linearGradient>
    <linearGradient id="mx-b-blue" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8fd8ff"/><stop offset="1" stop-color="#1468d6"/></linearGradient>
    <linearGradient id="mx-b-yellow" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff08a"/><stop offset="1" stop-color="#f09a08"/></linearGradient>

    <!-- materials -->
    <linearGradient id="mx-paper" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#eef1f5"/></linearGradient>
    <linearGradient id="mx-binding" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5c9be6"/><stop offset="1" stop-color="#1f5bb0"/></linearGradient>
    <linearGradient id="mx-alu" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f3f5f8"/><stop offset=".5" stop-color="#d3d9e0"/><stop offset="1" stop-color="#aab4bf"/></linearGradient>
    <linearGradient id="mx-lcd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2d3a33"/><stop offset="1" stop-color="#18211c"/></linearGradient>
    <linearGradient id="mx-key" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#59616c"/><stop offset="1" stop-color="#333a43"/></linearGradient>
    <linearGradient id="mx-key-o" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffb24d"/><stop offset="1" stop-color="#e6780a"/></linearGradient>
    <linearGradient id="mx-steel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f6f8fa"/><stop offset=".45" stop-color="#b9c3cf"/><stop offset="1" stop-color="#6c7988"/></linearGradient>
    <linearGradient id="mx-steel-d" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8d99a8"/><stop offset="1" stop-color="#3e4855"/></linearGradient>
    <radialGradient id="mx-info" cx=".42" cy=".32" r=".75"><stop offset="0" stop-color="#7cc4ff"/><stop offset=".55" stop-color="#1f74d8"/><stop offset="1" stop-color="#0a3c8f"/></radialGradient>
    <linearGradient id="mx-folder-back" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e2ad3f"/><stop offset="1" stop-color="#b9821c"/></linearGradient>
    <linearGradient id="mx-folder" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe7a3"/><stop offset=".5" stop-color="#f7cd62"/><stop offset="1" stop-color="#e9ad33"/></linearGradient>
    <linearGradient id="mx-avatar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fc3f0"/><stop offset="1" stop-color="#2f6aad"/></linearGradient>
    <linearGradient id="mx-silhouette" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#d7e3f0"/></linearGradient>
    <linearGradient id="mx-red" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6866b"/><stop offset=".5" stop-color="#d9381f"/><stop offset="1" stop-color="#a51e0e"/></linearGradient>
    <linearGradient id="mx-amber" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffd27a"/><stop offset=".5" stop-color="#eda125"/><stop offset="1" stop-color="#bf700a"/></linearGradient>
    <linearGradient id="mx-screen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5aa9f0"/><stop offset="1" stop-color="#103f8f"/></linearGradient>
    <linearGradient id="mx-bezel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3b4350"/><stop offset="1" stop-color="#14181e"/></linearGradient>
  </defs>
</svg>`;

const svg = (body: string, vb = '0 0 64 64') => `<svg viewBox="${vb}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${body}</svg>`;

/** Pinwheel blade pointing up; rotated four times for the logo. */
const BLADE = 'M32 30.8C28.6 25.6 27.6 17.4 33.4 10.8C39.5 15 41 23.4 33.8 30.6Z';

const logoMark = `
  <g transform="rotate(-14 32 32)">
    <path d="${BLADE}" fill="url(#mx-b-red)"/>
    <path d="${BLADE}" fill="url(#mx-b-green)" transform="rotate(90 32 32)"/>
    <path d="${BLADE}" fill="url(#mx-b-blue)" transform="rotate(180 32 32)"/>
    <path d="${BLADE}" fill="url(#mx-b-yellow)" transform="rotate(270 32 32)"/>
    <g fill="none" stroke="#fff" stroke-opacity=".45" stroke-width=".6">
      <path d="M33.3 11.6C30 16 29.4 22 31.6 28"/>
      <path d="M33.3 11.6C30 16 29.4 22 31.6 28" transform="rotate(90 32 32)"/>
      <path d="M33.3 11.6C30 16 29.4 22 31.6 28" transform="rotate(180 32 32)"/>
      <path d="M33.3 11.6C30 16 29.4 22 31.6 28" transform="rotate(270 32 32)"/>
    </g>
  </g>`;

export const icons = {
  /** The MWX 7 orb: dark glass sphere, four-colour pinwheel, Win7-style shine. */
  orb: svg(`
    <circle cx="32" cy="32" r="30.6" fill="#021029" opacity=".55"/>
    <circle cx="32" cy="32" r="29.6" fill="url(#mx-orb-glass)"/>
    <circle cx="32" cy="32" r="29.6" fill="url(#mx-orb-glow)"/>
    ${logoMark}
    <circle cx="32" cy="32" r="2.2" fill="#fff" opacity=".85"/>
    <path d="M10 26C12 14 21 6.5 32 6.5S52 14 54 26C47 21 40 19.4 32 19.4S17 21 10 26Z" fill="url(#mx-gloss)" opacity=".62"/>
    <circle cx="32" cy="32" r="29.6" fill="none" stroke="#bfe6ff" stroke-opacity=".55" stroke-width="1"/>`),

  /** Just the mark, for places that already provide their own background. */
  mark: svg(logoMark),

  notepad: svg(`
    <rect x="13" y="9" width="40" height="50" rx="2.5" fill="#000" opacity=".12" transform="translate(1 1.5)"/>
    <rect x="12" y="8" width="40" height="50" rx="2.5" fill="url(#mx-paper)" stroke="#000" stroke-opacity=".18" stroke-width=".75"/>
    <path d="M12 10.5A2.5 2.5 0 0 1 14.5 8h35A2.5 2.5 0 0 1 52 10.5V17H12z" fill="url(#mx-binding)"/>
    <path d="M12 16.4h40" stroke="#0d3a7a" stroke-opacity=".5" stroke-width=".75"/>
    <path d="M12 9h40" stroke="#fff" stroke-opacity=".5" stroke-width=".75"/>
    <g stroke="#9cb8de" stroke-width=".9"><path d="M17 25h30M17 31h30M17 37h30M17 43h30M17 49h22"/></g>
    <path d="M21 18v38" stroke="#e8726a" stroke-opacity=".55" stroke-width=".8"/>
    <g fill="#e9edf2" stroke="#5d6b7c" stroke-width=".7"><rect x="18" y="5.5" width="3.2" height="7" rx="1.6"/><rect x="30.4" y="5.5" width="3.2" height="7" rx="1.6"/><rect x="42.8" y="5.5" width="3.2" height="7" rx="1.6"/></g>`),

  calculator: svg(`
    <rect x="13" y="6" width="38" height="54" rx="6" fill="#000" opacity=".15" transform="translate(.8 1.5)"/>
    <rect x="13" y="6" width="38" height="54" rx="6" fill="url(#mx-alu)" stroke="#000" stroke-opacity=".25" stroke-width=".75"/>
    <rect x="13.6" y="6.6" width="36.8" height="52.8" rx="5.5" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width=".75"/>
    <rect x="17.5" y="10.5" width="29" height="11" rx="1.8" fill="url(#mx-lcd)"/>
    <path d="M17.5 12.5a2 2 0 0 1 2-2h25a2 2 0 0 1 2 2v2.5h-29z" fill="#fff" opacity=".08"/>
    <g fill="#9ee6a8" opacity=".9"><rect x="33" y="14.5" width="2" height="4.5" rx=".4"/><rect x="37" y="14.5" width="3.4" height="4.5" rx=".4"/><rect x="42" y="14.5" width="2.6" height="4.5" rx=".4"/></g>
    <g fill="url(#mx-key)">
      <rect x="17.5" y="26" width="6.2" height="6" rx="1.3"/><rect x="25.4" y="26" width="6.2" height="6" rx="1.3"/><rect x="33.3" y="26" width="6.2" height="6" rx="1.3"/>
      <rect x="17.5" y="34" width="6.2" height="6" rx="1.3"/><rect x="25.4" y="34" width="6.2" height="6" rx="1.3"/><rect x="33.3" y="34" width="6.2" height="6" rx="1.3"/>
      <rect x="17.5" y="42" width="6.2" height="6" rx="1.3"/><rect x="25.4" y="42" width="6.2" height="6" rx="1.3"/><rect x="33.3" y="42" width="6.2" height="6" rx="1.3"/>
      <rect x="17.5" y="50" width="14.1" height="5.5" rx="1.3"/><rect x="33.3" y="50" width="6.2" height="5.5" rx="1.3"/>
    </g>
    <g fill="url(#mx-key-o)"><rect x="41.2" y="26" width="5.3" height="6" rx="1.3"/><rect x="41.2" y="34" width="5.3" height="6" rx="1.3"/><rect x="41.2" y="42" width="5.3" height="13.5" rx="1.3"/></g>`),

  settings: svg(`
    <g transform="translate(.6 1.4)" opacity=".18"><circle cx="32" cy="32" r="22.5" fill="#000"/></g>
    <circle cx="32" cy="32" r="20" fill="none" stroke="url(#mx-steel-d)" stroke-width="9.5" stroke-dasharray="7.2 5.366"/>
    <circle cx="32" cy="32" r="20" fill="none" stroke="url(#mx-steel)" stroke-width="8" stroke-dasharray="6.6 5.966" stroke-dashoffset="-.3"/>
    <circle cx="32" cy="32" r="16.8" fill="url(#mx-steel)" stroke="#55606e" stroke-width=".75"/>
    <circle cx="32" cy="32" r="12.2" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width=".8"/>
    <circle cx="32" cy="32" r="11.4" fill="none" stroke="#5c6876" stroke-opacity=".45" stroke-width=".8"/>
    <circle cx="32" cy="32" r="6.2" fill="url(#mx-steel-d)" stroke="#2c333c" stroke-width=".75"/>
    <circle cx="32" cy="32" r="3" fill="#1a1f25"/>`),

  about: svg(`
    <circle cx="32" cy="33.5" r="26" fill="#000" opacity=".15"/>
    <circle cx="32" cy="32" r="26" fill="url(#mx-info)"/>
    <circle cx="32" cy="32" r="25.4" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width=".8"/>
    <path d="M11 27C13 16 21.5 8.5 32 8.5S51 16 53 27C46 23 39.5 21.5 32 21.5S18 23 11 27Z" fill="url(#mx-gloss)" opacity=".55"/>
    <circle cx="32" cy="20.5" r="3.6" fill="#fff"/>
    <path d="M27.5 27.5h7v15.5h2.6v3.8H27v-3.8h2.6V31.3h-2.1z" fill="#fff"/>`),

  folder: svg(`
    <path d="M6 15.5A2.5 2.5 0 0 1 8.5 13H23l4 4.5h28.5A2.5 2.5 0 0 1 58 20v31a2.5 2.5 0 0 1-2.5 2.5h-47A2.5 2.5 0 0 1 6 51z" fill="url(#mx-folder-back)"/>
    <rect x="11" y="19" width="42" height="30" rx="1" fill="#fff" transform="rotate(-2 32 34)"/>
    <rect x="13" y="21" width="40" height="28" rx="1" fill="#f3f6fa"/>
    <path d="M4.6 27.2A2.5 2.5 0 0 1 7.1 24.5h49.8a2.5 2.5 0 0 1 2.5 2.8l-2.3 24.5a2.5 2.5 0 0 1-2.5 2.2H9.4a2.5 2.5 0 0 1-2.5-2.2z" fill="url(#mx-folder)"/>
    <path d="M7.1 25.2h49.8" stroke="#fff" stroke-opacity=".8" stroke-width=".9"/>
    <path d="M4.6 27.2A2.5 2.5 0 0 1 7.1 24.5h49.8a2.5 2.5 0 0 1 2.5 2.8l-2.3 24.5a2.5 2.5 0 0 1-2.5 2.2H9.4a2.5 2.5 0 0 1-2.5-2.2z" fill="none" stroke="#a5711a" stroke-opacity=".55" stroke-width=".75"/>`),

  file: svg(`
    <path d="M15 7h22l13 13v36a2 2 0 0 1-2 2H15a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z" fill="#000" opacity=".12" transform="translate(.8 1.2)"/>
    <path d="M15 7h22l13 13v36a2 2 0 0 1-2 2H15a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z" fill="url(#mx-paper)" stroke="#000" stroke-opacity=".22" stroke-width=".75"/>
    <path d="M37 7v11a2 2 0 0 0 2 2h11" fill="#e3e8ef" stroke="#000" stroke-opacity=".22" stroke-width=".75" stroke-linejoin="round"/>
    <g stroke="#a9b8ca" stroke-width=".9"><path d="M19 28h25M19 33h25M19 38h25M19 43h25M19 48h16"/></g>`),

  computer: svg(`
    <rect x="6" y="9" width="52" height="36" rx="3" fill="url(#mx-bezel)"/>
    <rect x="9.5" y="12.5" width="45" height="29" rx="1" fill="url(#mx-screen)"/>
    <path d="M9.5 12.5h45L28 41.5H9.5z" fill="#fff" opacity=".1"/>
    <path d="M26 45h12l2 8H24z" fill="url(#mx-alu)"/>
    <rect x="18" y="52.5" width="28" height="3.5" rx="1.75" fill="url(#mx-alu)" stroke="#000" stroke-opacity=".2" stroke-width=".6"/>`),

  avatar: svg(`
    <rect width="64" height="64" rx="6" fill="url(#mx-avatar)"/>
    <circle cx="48" cy="14" r="16" fill="#fff" opacity=".12"/>
    <circle cx="32" cy="25" r="11" fill="url(#mx-silhouette)"/>
    <path d="M10 64c1.5-14 10.5-21.5 22-21.5S52.5 50 54 64z" fill="url(#mx-silhouette)"/>
    <rect width="64" height="64" rx="6" fill="none" stroke="#fff" stroke-opacity=".35"/>`),

  power: svg(`
    <rect x="3" y="3" width="58" height="58" rx="10" fill="url(#mx-red)"/>
    <path d="M3 13A10 10 0 0 1 13 3h38a10 10 0 0 1 10 10v12C48 21 40 20 32 20S16 21 3 25z" fill="url(#mx-gloss)" opacity=".45"/>
    <path d="M22.5 21.5a15 15 0 1 0 19 0" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"/>
    <path d="M32 14v18" stroke="#fff" stroke-width="5" stroke-linecap="round"/>`),

  logoff: svg(`
    <rect x="3" y="3" width="58" height="58" rx="10" fill="url(#mx-amber)"/>
    <path d="M3 13A10 10 0 0 1 13 3h38a10 10 0 0 1 10 10v12C48 21 40 20 32 20S16 21 3 25z" fill="url(#mx-gloss)" opacity=".45"/>
    <path d="M27 18H18v28h9" fill="none" stroke="#fff" stroke-width="4.5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M28 32h20M40 24l8 8-8 8" fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>`),

  search: svg(
    `<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
    '0 0 24 24',
  ),
} as const;

export type IconName = keyof typeof icons;
