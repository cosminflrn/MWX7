/**
 * MWX7 original icon set. All artwork here is original — never paste in
 * Apple / Microsoft icons. Gradients live once in ICON_DEFS (injected into
 * <body> at boot), so every icon can reference them by id.
 */

export const ICON_DEFS = `
<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">
  <defs>
    <linearGradient id="mx-paper" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e3eaf3"/></linearGradient>
    <linearGradient id="mx-blue" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7cc0ff"/><stop offset="1" stop-color="#1c66c8"/></linearGradient>
    <linearGradient id="mx-gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".9"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <radialGradient id="mx-orb" cx=".5" cy=".7" r=".65"><stop offset="0" stop-color="#8af5d8"/><stop offset=".45" stop-color="#1fa3c9"/><stop offset="1" stop-color="#0a3a88"/></radialGradient>
    <linearGradient id="mx-steel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5f6b7b"/><stop offset="1" stop-color="#262d37"/></linearGradient>
    <linearGradient id="mx-lcd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e0f7d0"/><stop offset="1" stop-color="#a6d895"/></linearGradient>
    <linearGradient id="mx-folder" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe591"/><stop offset="1" stop-color="#f2b11e"/></linearGradient>
    <linearGradient id="mx-folder-back" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6c444"/><stop offset="1" stop-color="#cf930a"/></linearGradient>
    <linearGradient id="mx-gear" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c9d3df"/><stop offset="1" stop-color="#66768a"/></linearGradient>
    <linearGradient id="mx-info" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#63b8ff"/><stop offset="1" stop-color="#0c56c0"/></linearGradient>
    <linearGradient id="mx-avatar" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffbe5c"/><stop offset="1" stop-color="#e2550f"/></linearGradient>
    <linearGradient id="mx-red" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff8a6b"/><stop offset="1" stop-color="#d1301a"/></linearGradient>
    <linearGradient id="mx-amber" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffd36b"/><stop offset="1" stop-color="#e08a00"/></linearGradient>
  </defs>
</svg>`;

const svg = (body: string, vb = '0 0 64 64') => `<svg viewBox="${vb}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${body}</svg>`;

export const icons = {
  orb: svg(`
    <circle cx="32" cy="32" r="29" fill="url(#mx-orb)" stroke="rgba(255,255,255,.6)" stroke-width="2"/>
    <path d="M32 13C34 26 38 30 51 32C38 34 34 38 32 51C30 38 26 34 13 32C26 30 30 26 32 13Z" fill="#fff"/>
    <ellipse cx="32" cy="18" rx="19" ry="11" fill="url(#mx-gloss)" opacity=".75"/>`),

  notepad: svg(`
    <rect x="11" y="7" width="42" height="52" rx="5" fill="url(#mx-paper)" stroke="#8796a8" stroke-width="1.5"/>
    <path d="M11 12a5 5 0 0 1 5-5h32a5 5 0 0 1 5 5v6H11z" fill="url(#mx-blue)"/>
    <g stroke="#b2c3d8" stroke-width="2" stroke-linecap="round"><path d="M18 27h28M18 34h28M18 41h28M18 48h18"/></g>
    <g fill="#eef3f9" stroke="#56677c" stroke-width="1.2"><circle cx="20" cy="7" r="2.6"/><circle cx="32" cy="7" r="2.6"/><circle cx="44" cy="7" r="2.6"/></g>`),

  calculator: svg(`
    <rect x="12" y="5" width="40" height="54" rx="7" fill="url(#mx-steel)"/>
    <rect x="17" y="10" width="30" height="12" rx="2.5" fill="url(#mx-lcd)"/>
    <rect x="32" y="14" width="12" height="4" rx="1" fill="#3f6b33" opacity=".7"/>
    <g fill="#e4e9ef">
      <rect x="17" y="27" width="6" height="6" rx="1.5"/><rect x="25" y="27" width="6" height="6" rx="1.5"/><rect x="33" y="27" width="6" height="6" rx="1.5"/>
      <rect x="17" y="35" width="6" height="6" rx="1.5"/><rect x="25" y="35" width="6" height="6" rx="1.5"/><rect x="33" y="35" width="6" height="6" rx="1.5"/>
      <rect x="17" y="43" width="6" height="6" rx="1.5"/><rect x="25" y="43" width="6" height="6" rx="1.5"/><rect x="33" y="43" width="6" height="6" rx="1.5"/>
      <rect x="17" y="51" width="14" height="5" rx="1.5"/><rect x="33" y="51" width="6" height="5" rx="1.5"/>
    </g>
    <g fill="#ff9f2e"><rect x="41" y="27" width="6" height="6" rx="1.5"/><rect x="41" y="35" width="6" height="6" rx="1.5"/><rect x="41" y="43" width="6" height="13" rx="1.5"/></g>
    <rect x="12" y="5" width="40" height="22" rx="7" fill="url(#mx-gloss)" opacity=".22"/>`),

  settings: svg(`
    <circle cx="32" cy="32" r="20" fill="none" stroke="url(#mx-gear)" stroke-width="9" stroke-dasharray="7 5.566"/>
    <circle cx="32" cy="32" r="16.5" fill="url(#mx-gear)" stroke="#56647a" stroke-width="1"/>
    <circle cx="32" cy="32" r="7" fill="#2b3442"/>
    <circle cx="32" cy="32" r="7" fill="none" stroke="#a9b6c6" stroke-width="1.5"/>
    <ellipse cx="32" cy="24" rx="13" ry="7" fill="url(#mx-gloss)" opacity=".45"/>`),

  about: svg(`
    <circle cx="32" cy="32" r="26" fill="url(#mx-info)" stroke="#0a479f" stroke-width="1.5"/>
    <ellipse cx="32" cy="19" rx="18" ry="10" fill="url(#mx-gloss)" opacity=".7"/>
    <circle cx="32" cy="20" r="3.8" fill="#fff"/>
    <rect x="28.5" y="27" width="7" height="20" rx="3" fill="#fff"/>`),

  folder: svg(`
    <path d="M6 16a4 4 0 0 1 4-4h14l5 5h25a4 4 0 0 1 4 4v29a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4z" fill="url(#mx-folder-back)"/>
    <path d="M6 24a4 4 0 0 1 4-4h44a4 4 0 0 1 4 4v26a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4z" fill="url(#mx-folder)"/>
    <path d="M6 24a4 4 0 0 1 4-4h44a4 4 0 0 1 4 4v6H6z" fill="#fff" opacity=".35"/>`),

  file: svg(`
    <path d="M16 6h22l12 12v38a3 3 0 0 1-3 3H16a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3z" fill="url(#mx-paper)" stroke="#8796a8" stroke-width="1.5"/>
    <path d="M38 6v9a3 3 0 0 0 3 3h9" fill="#dfe7f1" stroke="#8796a8" stroke-width="1.5" stroke-linejoin="round"/>
    <g stroke="#9fb3c9" stroke-width="2" stroke-linecap="round"><path d="M20 30h24M20 37h24M20 44h16"/></g>`),

  avatar: svg(`
    <rect width="64" height="64" rx="10" fill="url(#mx-avatar)"/>
    <circle cx="32" cy="25" r="11" fill="#fff" opacity=".93"/>
    <path d="M11 58c2-12 10-18 21-18s19 6 21 18z" fill="#fff" opacity=".93"/>
    <rect width="64" height="30" rx="10" fill="url(#mx-gloss)" opacity=".3"/>`),

  power: svg(`
    <rect x="2" y="2" width="60" height="60" rx="12" fill="url(#mx-red)"/>
    <path d="M22 20a17 17 0 1 0 20 0" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round"/>
    <path d="M32 12v20" stroke="#fff" stroke-width="6" stroke-linecap="round"/>`),

  logoff: svg(`
    <rect x="2" y="2" width="60" height="60" rx="12" fill="url(#mx-amber)"/>
    <path d="M26 18H18v28h8" fill="none" stroke="#fff" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M28 32h20M40 23l9 9-9 9" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>`),

  search: svg(
    `<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>`,
    '0 0 24 24',
  ),
} as const;

export type IconName = keyof typeof icons;
