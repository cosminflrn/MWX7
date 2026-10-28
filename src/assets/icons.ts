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

/** Raster icons (KDE Oxygen, LGPL — see public/media/icons/). */
const png = (name: string) =>
  `<img class="icon-img" alt="" draggable="false" src="${import.meta.env.BASE_URL}media/icons/${name}.png">`;

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

  notepad: png('notepad'),

  calculator: png('calculator'),

  settings: png('settings'),

  about: png('about'),

  folder: png('folder'),

  file: svg(`
    <path d="M15 7h22l13 13v36a2 2 0 0 1-2 2H15a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z" fill="#000" opacity=".12" transform="translate(.8 1.2)"/>
    <path d="M15 7h22l13 13v36a2 2 0 0 1-2 2H15a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z" fill="url(#mx-paper)" stroke="#000" stroke-opacity=".22" stroke-width=".75"/>
    <path d="M37 7v11a2 2 0 0 0 2 2h11" fill="#e3e8ef" stroke="#000" stroke-opacity=".22" stroke-width=".75" stroke-linejoin="round"/>
    <g stroke="#a9b8ca" stroke-width=".9"><path d="M19 28h25M19 33h25M19 38h25M19 43h25M19 48h16"/></g>`),

  computer: png('computer'),

  avatar: png('user'),

  power: png('shutdown'),

  logoff: png('logoff'),

  search: svg(
    `<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
    '0 0 24 24',
  ),
  documents: png('folder-documents'),
  pictures: png('folder-pictures'),
  music: png('folder-music'),
  explorer: png('explorer'),
  trash: png('trash-empty'),
  trashFull: png('trash-full'),
  binoculars: png('search'),
  terminal: png('terminal'),
} as const;

export type IconName = keyof typeof icons;
