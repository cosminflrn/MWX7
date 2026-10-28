/** Original terminal icon: dark rounded screen, subtle bezel, `>_` prompt. Gradient ids are prefixed `term-`. */
export const terminalIcon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="term-bezel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5b6577"/><stop offset=".5" stop-color="#2c3340"/><stop offset="1" stop-color="#171b23"/></linearGradient>
    <linearGradient id="term-screen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#17202e"/><stop offset="1" stop-color="#080b11"/></linearGradient>
    <linearGradient id="term-gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <radialGradient id="term-glow" cx=".3" cy=".4" r=".7"><stop offset="0" stop-color="#4f9dff" stop-opacity=".28"/><stop offset="1" stop-color="#4f9dff" stop-opacity="0"/></radialGradient>
    <linearGradient id="term-prompt" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9be8b0"/><stop offset="1" stop-color="#5fd0a0"/></linearGradient>
  </defs>
  <rect x="4" y="9" width="56" height="46" rx="9" fill="url(#term-bezel)"/>
  <rect x="4.5" y="9.5" width="55" height="45" rx="8.5" fill="none" stroke="#fff" stroke-opacity=".28"/>
  <rect x="8" y="13" width="48" height="38" rx="5.5" fill="url(#term-screen)"/>
  <rect x="8" y="13" width="48" height="38" rx="5.5" fill="url(#term-glow)"/>
  <path d="M17 24l8 6-8 6" fill="none" stroke="url(#term-prompt)" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="29" y="35" width="11" height="3.4" rx="1.4" fill="#8ab8ff"/>
  <path d="M8 18.5Q8 13 13.5 13h37Q56 13 56 18.5V28Q32 35 8 26z" fill="url(#term-gloss)"/>
</svg>`;
