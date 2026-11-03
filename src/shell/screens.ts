import { icons } from '../assets/icons';
import { settings } from '../core/settings';
import { play, unlockAudio } from '../core/sound';
import { allWindows, closeWindow } from '../core/wm';
import { h } from '../ui/dom';
import { AVATARS, avatarHtml, avatarPicker } from './avatars';
import { ensureVgaFont, openCommander } from './commander';
import { setGadgetsLive } from './gadgets';
import { createWallpaperLayer } from './wallpapers';

/**
 * Full-screen moments: power button → BIOS POST → boot logo → logon,
 * plus log off and shut down. Everything is an overlay above the desktop.
 */

/** Original cursive "energy" wordmark + five-point star with a sweeping arc, in classic BIOS yellow (hand-drawn paths). */
const POWER_SAVER_BADGE = `
<svg viewBox="0 0 240 120" xmlns="http://www.w3.org/2000/svg" aria-label="Energy Star">
  <g fill="none" stroke="#f4d000" stroke-linecap="round" stroke-linejoin="round">
    <!-- cursive 'energy', letter by letter (e n e r g y), baseline y=70 -->
    <path stroke-width="3.6" d="M22 66 H40 C 42 52, 24 50, 24 62 C 24 74, 38 74, 44 66"/>
    <path stroke-width="3.6" d="M46 70 C 48 60, 50 54, 52 52 C 52 60, 52 66, 54 66 C 56 56, 66 50, 68 58 C 69 64, 68 68, 72 68"/>
    <path stroke-width="3.6" d="M76 66 H94 C 96 52, 78 50, 78 62 C 78 74, 92 74, 98 66"/>
    <path stroke-width="3.6" d="M102 70 C 104 62, 105 56, 106 52 C 107 58, 110 54, 116 52"/>
    <path stroke-width="3.6" d="M130 54 C 120 48, 116 60, 122 64 C 128 66, 132 58, 132 52 C 132 66, 132 80, 124 82 C 118 83, 118 76, 124 76"/>
    <path stroke-width="3.6" d="M138 52 C 138 62, 140 68, 146 66 C 152 64, 156 56, 156 50 C 156 66, 154 82, 146 90 C 140 94, 136 90, 142 88"/>
    <!-- swoosh arc sweeping under the word and up to the star -->
    <path stroke-width="3.4" d="M16 82 C 56 108, 150 112, 196 56"/>
  </g>
  <!-- five-point star riding the end of the arc -->
  <path fill="#f4d000" d="M200 14 l6.4 13 14.3 2-10.4 10.1 2.5 14.2-12.8-6.7-12.8 6.7 2.5-14.2-10.4-10.1 14.3-2z"/>
  <text x="120" y="116" text-anchor="middle" fill="#f4d000" font-family="Arial, Helvetica, sans-serif" font-weight="700"
    font-size="13" letter-spacing="5">ENERGY STAR</text>
</svg>`;

const wait = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));

function fadeOut(el: HTMLElement, ms = 450): Promise<void> {
  return new Promise((resolve) => {
    el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: ms, easing: 'ease', fill: 'forwards' }).onfinish = () => {
      el.remove();
      resolve();
    };
  });
}

/** Lets the user skip an animated step with Esc / Enter / click. */
function skippable(el: HTMLElement): { skipped: () => boolean; dispose: () => void } {
  let skipped = false;
  const onKey = (e: KeyboardEvent) => {
    if (['Escape', 'Enter', ' '].includes(e.key)) skipped = true;
  };
  const onClick = () => (skipped = true);
  window.addEventListener('keydown', onKey);
  el.addEventListener('pointerdown', onClick);
  return {
    skipped: () => skipped,
    dispose: () => {
      window.removeEventListener('keydown', onKey);
      el.removeEventListener('pointerdown', onClick);
    },
  };
}

/* ---------- 1. power switch ---------- */

/** Original front of a beige 90s tower: drive bays, LEDs, turbo button and the big push POWER switch (drawn here, no third-party art). */
const PC_FRONT = `
<svg class="pc-svg" viewBox="0 0 360 470" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="pcBeige" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#e4dcc6"/><stop offset=".5" stop-color="#dad2bb"/><stop offset="1" stop-color="#c6bea6"/></linearGradient>
    <linearGradient id="pcBay" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cfc7af"/><stop offset="1" stop-color="#ddd5be"/></linearGradient>
    <linearGradient id="pcCap" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ece5d1"/><stop offset=".55" stop-color="#d8d0b9"/><stop offset="1" stop-color="#c3bba3"/></linearGradient>
    <radialGradient id="ledG" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#d9ffd0"/><stop offset=".5" stop-color="#3fe03f"/><stop offset="1" stop-color="#16a416"/></radialGradient>
    <radialGradient id="ledA" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#fff0c4"/><stop offset=".5" stop-color="#ffb81f"/><stop offset="1" stop-color="#d27a00"/></radialGradient>
  </defs>
  <!-- case -->
  <rect x="14" y="8" width="332" height="446" rx="12" fill="#a79f88"/>
  <rect x="14" y="4" width="332" height="446" rx="12" fill="url(#pcBeige)"/>
  <rect x="15" y="5" width="330" height="444" rx="11" fill="none" stroke="#fff8e6" stroke-opacity=".7" stroke-width="1"/>
  <rect x="30" y="20" width="300" height="414" rx="6" fill="none" stroke="#b3ab93" stroke-width="1"/>
  <!-- 5.25" CD-ROM bay -->
  <rect x="42" y="34" width="276" height="50" rx="3" fill="url(#pcBay)" stroke="#a69e86"/>
  <rect x="54" y="46" width="206" height="14" rx="2" fill="#2a2a2a"/>
  <rect x="54" y="46" width="206" height="3" fill="#000" opacity=".5"/>
  <rect x="274" y="48" width="30" height="12" rx="2" fill="#cfc7af" stroke="#9a927c"/>
  <circle cx="289" cy="72" r="2.4" fill="#4b4b3f"/>
  <text x="54" y="76" font-family="Arial,Helvetica,sans-serif" font-size="8" font-weight="700" letter-spacing="1.4" fill="#6f6a58">CD-ROM  16X</text>
  <!-- 3.5" floppy bay -->
  <rect x="42" y="98" width="170" height="40" rx="3" fill="url(#pcBay)" stroke="#a69e86"/>
  <rect x="58" y="112" width="104" height="6" rx="1" fill="#1d1d1d"/>
  <rect x="58" y="112" width="104" height="2" fill="#000" opacity=".6"/>
  <rect x="172" y="108" width="28" height="14" rx="2" fill="#cfc7af" stroke="#9a927c"/>
  <circle cx="186" cy="128" r="2" fill="#4b4b3f"/>
  <text x="58" y="131" font-family="Arial,Helvetica,sans-serif" font-size="7" font-weight="700" letter-spacing="1.2" fill="#6f6a58">3.5"  1.44MB</text>
  <!-- LED panel -->
  <rect x="226" y="98" width="92" height="40" rx="3" fill="#2b2b27" stroke="#8d866f"/>
  <circle class="led led-pwr" cx="248" cy="113" r="5.2" fill="#143d14"/>
  <circle class="led led-hdd" cx="296" cy="113" r="5.2" fill="#4a3208"/>
  <text x="248" y="131" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="7" font-weight="700" letter-spacing=".8" fill="#cfc7af">POWER</text>
  <text x="296" y="131" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="7" font-weight="700" letter-spacing=".8" fill="#cfc7af">HDD</text>
  <!-- turbo -->
  <rect x="42" y="154" width="276" height="42" rx="3" fill="url(#pcBay)" stroke="#a69e86"/>
  <rect x="54" y="163" width="52" height="24" rx="3" fill="#b7af97"/>
  <rect x="54" y="162" width="52" height="23" rx="3" fill="url(#pcCap)" stroke="#8f876f"/>
  <text x="80" y="177" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="8.5" font-weight="700" letter-spacing="1" fill="#5c5748">TURBO</text>
  <rect x="236" y="163" width="68" height="24" rx="2" fill="#120a0a" stroke="#8d866f"/>
  <text x="270" y="182" text-anchor="middle" font-family="'Courier New',monospace" font-size="19" font-weight="700" fill="#ff3b2a" class="seg">66</text>
  <text x="124" y="179" font-family="Arial,Helvetica,sans-serif" font-size="7" font-weight="700" letter-spacing="1.2" fill="#6f6a58">MHz</text>
  <!-- power switch housing -->
  <rect x="56" y="214" width="248" height="142" rx="8" fill="#a79f88"/>
  <rect x="62" y="220" width="236" height="130" rx="6" fill="#2a2923"/>
  <rect x="62" y="220" width="236" height="12" rx="6" fill="#000" opacity=".45"/>
  <g class="cap">
    <rect x="72" y="234" width="216" height="106" rx="7" fill="#9d957d"/>
    <rect x="72" y="228" width="216" height="106" rx="7" fill="url(#pcCap)" stroke="#8b836b"/>
    <rect x="73.5" y="229.5" width="213" height="103" rx="6" fill="none" stroke="#fffdf2" stroke-opacity=".85"/>
    <rect x="96" y="246" width="168" height="62" rx="5" fill="#cbc3ab" stroke="#aaa28a"/>
    <text x="180" y="288" text-anchor="middle" font-family="Arial Black,Arial,Helvetica,sans-serif" font-size="30" font-weight="900" letter-spacing="5" fill="#fbf7e8">POWER</text>
    <text x="180" y="286" text-anchor="middle" font-family="Arial Black,Arial,Helvetica,sans-serif" font-size="30" font-weight="900" letter-spacing="5" fill="#6a6554">POWER</text>
    <circle cx="180" cy="320" r="0" fill="none"/>
  </g>
  <!-- vents -->
  <g stroke="#aaa28a" stroke-width="3" stroke-linecap="round">
    <path d="M70 376h220M70 388h220M70 400h220M70 412h220"/>
  </g>
  <g stroke="#fff8e6" stroke-opacity=".7" stroke-width="1"><path d="M70 378h220M70 390h220M70 402h220M70 414h220"/></g>
  <text x="300" y="430" text-anchor="end" font-family="Arial,Helvetica,sans-serif" font-size="9" font-weight="700" letter-spacing="2" fill="#6f6a58">MWX 486DX2</text>
</svg>`;


/** Original illustration of a retro room (1600x900, drawn here): wall, window, poster, wooden desk, switched-off CRT, keyboard, mug. */
const ROOM = `
<svg class="room-svg" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="rmWall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8a6a4e"/><stop offset=".55" stop-color="#a98562"/><stop offset="1" stop-color="#b7926b"/></linearGradient>
    <radialGradient id="rmLight" cx=".3" cy=".25" r=".8"><stop offset="0" stop-color="#ffe3a8" stop-opacity=".35"/><stop offset="1" stop-color="#ffe3a8" stop-opacity="0"/></radialGradient>
    <linearGradient id="rmVig" x1="0" x2="1"><stop offset="0" stop-color="#000" stop-opacity=".5"/><stop offset=".22" stop-color="#000" stop-opacity="0"/><stop offset=".78" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/></linearGradient>
    <linearGradient id="rmSky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3b5f8f"/><stop offset=".6" stop-color="#e9a56a"/><stop offset="1" stop-color="#f7d08a"/></linearGradient>
    <linearGradient id="rmTop" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b9824f"/><stop offset="1" stop-color="#9a683c"/></linearGradient>
    <linearGradient id="rmFront" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7d5030"/><stop offset="1" stop-color="#5a3721"/></linearGradient>
    <linearGradient id="rmFloor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a2618"/><stop offset="1" stop-color="#1d120a"/></linearGradient>
    <linearGradient id="rmCrt" x1="0" x2="1"><stop offset="0" stop-color="#e2dac4"/><stop offset=".5" stop-color="#d6cdb5"/><stop offset="1" stop-color="#bdb59d"/></linearGradient>
    <radialGradient id="rmGlass" cx=".35" cy=".3" r=".9"><stop offset="0" stop-color="#2c3436"/><stop offset=".6" stop-color="#141a1c"/><stop offset="1" stop-color="#0a0d0e"/></radialGradient>
    <radialGradient id="rmShadow"><stop offset="0" stop-color="#1a0d04" stop-opacity=".55"/><stop offset="1" stop-color="#1a0d04" stop-opacity="0"/></radialGradient>
    <pattern id="rmGrain" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(2)"><path d="M0 7h14" stroke="#000" stroke-opacity=".05"/></pattern>
  </defs>
  <!-- wall + wainscot -->
  <rect width="1600" height="640" fill="url(#rmWall)"/>
  <rect width="1600" height="640" fill="url(#rmLight)"/>
  <rect y="470" width="1600" height="170" fill="#6e4d37"/>
  <rect y="466" width="1600" height="8" fill="#c8a47a"/><rect y="474" width="1600" height="3" fill="#000" opacity=".25"/>
  <g stroke="#000" stroke-opacity=".18" stroke-width="2"><path d="M200 477v163M420 477v163M640 477v163M860 477v163M1080 477v163M1300 477v163M1520 477v163"/></g>
  <!-- window -->
  <g>
    <rect x="270" y="92" width="330" height="330" rx="3" fill="#e8d9bd" stroke="#6b4a31" stroke-width="8"/>
    <rect x="288" y="110" width="294" height="294" fill="url(#rmSky)"/>
    <path d="M288 330 L360 270 L420 318 L500 244 L582 316 V404 H288Z" fill="#2a3a4e" opacity=".85"/>
    <path d="M288 366 L380 322 L470 360 L582 330 V404 H288Z" fill="#1c2735" opacity=".9"/>
    <circle cx="500" cy="196" r="18" fill="#fff2c0" opacity=".9"/>
    <path d="M435 110v294M288 257h294" stroke="#e8d9bd" stroke-width="9"/><path d="M435 110v294M288 257h294" stroke="#6b4a31" stroke-opacity=".45" stroke-width="1.5"/>
    <rect x="256" y="418" width="358" height="14" rx="2" fill="#c8a47a" stroke="#6b4a31" stroke-width="2"/>
    <!-- curtains -->
    <path d="M262 80 Q300 110 296 250 Q292 380 270 428 L240 428 L240 80Z" fill="#a0432e"/>
    <path d="M608 80 Q570 110 574 250 Q578 380 600 428 L630 428 L630 80Z" fill="#a0432e"/>
    <path d="M262 80 Q272 250 270 428M282 90 Q290 250 284 428M608 80 Q598 250 600 428M588 90 Q580 250 586 428" stroke="#000" stroke-opacity=".2" stroke-width="3" fill="none"/>
    <rect x="228" y="70" width="414" height="12" rx="6" fill="#4b2f1d"/>
    <!-- sun patch on the wall -->
    <path d="M640 200 L980 300 L990 560 L640 440Z" fill="#ffe6a8" opacity=".08"/>
  </g>
  <!-- poster -->
  <g transform="rotate(-1.5 1190 270)">
    <rect x="1100" y="132" width="180" height="250" fill="#000" opacity=".25" transform="translate(5 7)"/>
    <rect x="1100" y="132" width="180" height="250" fill="#f1e6cc"/>
    <rect x="1112" y="144" width="156" height="170" fill="#274a6e"/>
    <circle cx="1190" cy="250" r="44" fill="#ee8a4a"/><rect x="1112" y="250" width="156" height="64" fill="#274a6e"/>
    <path d="M1112 314 L1160 262 L1196 296 L1230 254 L1268 314Z" fill="#14283f"/>
    <path d="M1112 270h156M1112 282h156M1112 294h156" stroke="#274a6e" stroke-width="3" opacity=".9"/>
    <rect x="1130" y="328" width="120" height="9" fill="#274a6e" opacity=".85"/><rect x="1150" y="346" width="80" height="6" fill="#274a6e" opacity=".5"/>
    <rect x="1170" y="124" width="40" height="16" fill="#e8dfa8" opacity=".75" transform="rotate(-4 1190 132)"/>
  </g>
  <!-- shelf with books -->
  <rect x="1340" y="300" width="220" height="12" rx="2" fill="#5a3721"/><rect x="1340" y="312" width="220" height="4" fill="#000" opacity=".25"/>
  <g>
    <rect x="1356" y="238" width="26" height="62" fill="#3d6a58"/><rect x="1384" y="228" width="22" height="72" fill="#b55a3c"/><rect x="1408" y="246" width="30" height="54" fill="#d6b45a"/><rect x="1440" y="236" width="20" height="64" fill="#36507a"/>
    <rect x="1472" y="262" width="52" height="38" rx="3" fill="#e8dfc8"/><path d="M1480 262v-10M1496 262v-16M1512 262v-10" stroke="#3d6a58" stroke-width="5" stroke-linecap="round"/>
  </g>
  <!-- desk top (perspective plane), front lip, apron, floor -->
  <rect y="640" width="1600" height="36" fill="url(#rmTop)"/>
  <path d="M0 676 H1600 V700 H0Z" fill="#c89862"/><rect y="700" width="1600" height="6" fill="#000" opacity=".2"/>
  <rect y="640" width="1600" height="36" fill="url(#rmGrain)"/>
  <path d="M0 656 Q500 650 1000 658 T1600 654M0 668 Q600 664 1100 670 T1600 666" stroke="#6b4426" stroke-opacity=".25" stroke-width="1.5" fill="none"/>
  <rect y="706" width="1600" height="76" fill="url(#rmFront)"/>
  <g>
    <rect x="300" y="718" width="360" height="52" rx="3" fill="#6a4128" stroke="#2f1a0e" stroke-width="2"/><rect x="450" y="738" width="60" height="9" rx="4" fill="#d3b27a"/>
    <rect x="940" y="718" width="360" height="52" rx="3" fill="#6a4128" stroke="#2f1a0e" stroke-width="2"/><rect x="1090" y="738" width="60" height="9" rx="4" fill="#d3b27a"/>
  </g>
  <rect y="782" width="1600" height="118" fill="url(#rmFloor)"/>
  <path d="M0 830H1600M0 868H1600" stroke="#000" stroke-opacity=".35" stroke-width="2"/>
  <!-- objects on the desk -->
  <ellipse cx="800" cy="664" rx="270" ry="20" fill="url(#rmShadow)"/>
  <!-- CRT monitor, switched off -->
  <g>
    <path d="M668 392 L728 354 H872 L932 392Z" fill="#b4ac95"/>
    <rect x="640" y="388" width="320" height="238" rx="16" fill="url(#rmCrt)" stroke="#9d957c" stroke-width="2"/>
    <rect x="642" y="390" width="316" height="234" rx="15" fill="none" stroke="#fffbe9" stroke-opacity=".7" stroke-width="2"/>
    <rect x="662" y="406" width="276" height="188" rx="22" fill="#a8a08a"/>
    <rect x="668" y="412" width="264" height="176" rx="18" fill="url(#rmGlass)" stroke="#6f6853" stroke-width="2"/>
    <path d="M684 424 Q760 418 830 424 Q770 440 700 470 Q680 480 684 424Z" fill="#fff" opacity=".13"/>
    <ellipse cx="900" cy="560" rx="22" ry="12" fill="#fff" opacity=".04"/>
    <rect x="662" y="602" width="106" height="12" rx="3" fill="#cbc3ab"/><path d="M670 608h90" stroke="#9d957c" stroke-width="2" stroke-dasharray="2 4"/>
    <circle cx="912" cy="608" r="5" fill="#3b3a32"/><circle cx="930" cy="608" r="3.4" fill="#4a2a12"/>
    <path d="M778 626 H822 L836 644 H764Z" fill="#c7bea6"/>
    <ellipse cx="800" cy="650" rx="86" ry="14" fill="#cbc3ab" stroke="#9d957c" stroke-width="2"/><ellipse cx="800" cy="646" rx="80" ry="10" fill="#e0d8c2"/>
  </g>
  <!-- keyboard -->
  <g>
    <path d="M648 666 L952 666 L972 696 L628 696Z" fill="#000" opacity=".28" transform="translate(0 4)"/>
    <path d="M652 658 L948 658 L970 692 L630 692Z" fill="#d3cab2" stroke="#a79f88" stroke-width="2" stroke-linejoin="round"/>
    <path d="M660 664 L940 664 L956 686 L644 686Z" fill="#bfb7a0"/>
    <g stroke="#e9e1ca" stroke-width="5" stroke-linecap="round" opacity=".95">
      <path d="M666 669h268M662 675h276M657 681h286M672 686h256"/>
    </g>
    <g stroke="#a79f88" stroke-width="1" opacity=".7"><path d="M690 666l-6 22M722 666l-6 22M754 666l-4 22M786 666l-2 22M818 666v22M850 666l2 22M882 666l4 22M914 666l6 22"/></g>
  </g>
  <!-- mouse + pad -->
  <path d="M1000 670 H1100 L1112 700 H988Z" fill="#2c4a6e" opacity=".9"/>
  <path d="M1040 676 Q1058 668 1070 678 L1072 692 Q1056 698 1038 692Z" fill="#d9d0b8" stroke="#a79f88" stroke-width="1.5"/>
  <path d="M1056 672 V684" stroke="#a79f88" stroke-width="1.5"/>
  <path d="M1054 672 Q1000 650 966 668" stroke="#b8b09a" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- mug with steam -->
  <g>
    <ellipse cx="548" cy="664" rx="34" ry="8" fill="#1a0d04" opacity=".35"/>
    <path d="M520 612 H576 L572 662 Q548 672 524 662Z" fill="#d94d38"/>
    <path d="M520 612 H576 L574 632 Q548 640 522 632Z" fill="#000" opacity=".1"/>
    <ellipse cx="548" cy="612" rx="28" ry="7" fill="#6b3a22"/><ellipse cx="548" cy="611" rx="25" ry="5" fill="#4a2814"/>
    <path d="M576 622 Q600 624 596 642 Q592 656 573 654" fill="none" stroke="#d94d38" stroke-width="7" stroke-linecap="round"/>
    <path d="M530 618 L530 656" stroke="#fff" stroke-opacity=".3" stroke-width="4" stroke-linecap="round"/>
    <path d="M540 596 Q532 584 542 572 Q552 560 544 548M556 598 Q566 586 558 576" fill="none" stroke="#fff" stroke-opacity=".22" stroke-width="3" stroke-linecap="round"/>
  </g>
  <!-- tower contact shadow (the tower itself is an HTML overlay with the real power switch) -->
  <ellipse cx="1155" cy="654" rx="140" ry="13" fill="#1a0d04" opacity=".5"/>
  <rect width="1600" height="900" fill="url(#rmVig)"/>
</svg>`;

function powerScreen(hint: string) {
  const sw = h('button', { class: 'power-btn', 'aria-label': 'Power on' });
  const pc = h('div', { class: 'pc', html: PC_FRONT }, sw);
  const scene = h('div', { class: 'scene' }, h('div', { class: 'scene-art', html: ROOM }), pc);
  const screen = h('div', { class: 'screen power' }, scene, h('p', { class: 'power-hint' }, hint));
  document.body.append(screen);
  return { screen, pc, pressed: new Promise<void>((r) => sw.addEventListener('click', () => r(), { once: true })) };
}

async function powerOn(): Promise<void> {
  const { screen, pc, pressed } = powerScreen('Push the power switch to start');
  await pressed;
  unlockAudio();
  play('switch');
  pc.classList.add('pressed');
  await wait(110);
  pc.classList.add('on');
  play('spinup');
  await wait(2500);
  screen.remove();
}

/* ---------- 2. BIOS POST ---------- */

async function bios(): Promise<void> {
  ensureVgaFont();
  const text = h('pre', { class: 'bios-text' });
  const screen = h(
    'div',
    { class: 'screen bios' },
    h('div', { class: 'bios-badge', html: POWER_SAVER_BADGE }),
    text,
    h('pre', { class: 'bios-foot' }, 'Press DEL to run Setup, F12 for Boot Menu, ESC to skip\n10/28/2026-MWX7-7.03-BIOS'),
  );
  document.body.append(screen);
  const skip = skippable(screen);
  // DEL opens MWX Commander; the POST resumes when it closes.
  let wantSetup = false;
  const onDel = (e: KeyboardEvent) => {
    if (e.key === 'Delete') wantSetup = true;
  };
  window.addEventListener('keydown', onDel);
  const checkpoint = async () => {
    if (!wantSetup) return;
    wantSetup = false;
    await openCommander();
  };
  const out = (s: string) => (text.textContent += s);
  const line = async (s: string, ms = 120) => {
    out(s + '\n');
    await checkpoint();
    if (!skip.skipped()) await wait(ms);
  };

  const threads = navigator.hardwareConcurrency || 4;
  const memMB = ((navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 8) * 1024;

  await line('MWX Systems BIOS v7.03.2026, A Web-Native Firmware', 60);
  await line('Copyright (C) 2026, MWX Systems, Inc.', 260);
  await line('');
  await line('MWX 7 Reference Board  Rev. 7.0', 200);
  await line('');
  await line(`Main Processor   : Browser Core x${threads} @ 3.20 GHz`, 220);
  out('Memory Testing   : ');
  const memLine = text.textContent!.length;
  const steps = 28;
  for (let i = 1; i <= steps && !skip.skipped(); i++) {
    text.textContent = text.textContent!.slice(0, memLine) + `${Math.round(((memMB * 1024) / steps) * i)}K`;
    await checkpoint();
    await wait(32);
  }
  text.textContent = text.textContent!.slice(0, memLine) + `${memMB * 1024}K OK\n`;
  play('post');
  if (!skip.skipped()) await wait(380);
  await line('');
  await line('Detecting drives ...', 420);
  await line('  Primary Master   : MWX-SSD 512GB  (NVMe)', 160);
  await line('  Primary Slave    : None', 120);
  await line('  Secondary Master : DVD-RW Optical Drive', 160);
  await line('  Secondary Slave  : None', 260);
  await line('');
  await line('USB Devices      : 1 Keyboard, 1 Mouse, 0 Storage', 300);
  await line('');
  out('Verifying DMI Pool Data ');
  for (let i = 0; i < 10 && !skip.skipped(); i++) {
    out('.');
    await wait(55);
  }
  await line('');
  await line('Boot from Hard Disk ...', 500);
  await checkpoint();
  window.removeEventListener('keydown', onDel);
  skip.dispose();
  screen.remove();
}

/* ---------- 3. boot logo ---------- */

async function bootLogo(): Promise<void> {
  const screen = h(
    'div',
    { class: 'screen bootlogo' },
    h(
      'div',
      { class: 'bl-stage' },
      h('span', { class: 'bl-light r' }),
      h('span', { class: 'bl-light g' }),
      h('span', { class: 'bl-light b' }),
      h('span', { class: 'bl-light y' }),
      h('div', { class: 'bl-orb', html: icons.orb }),
    ),
    h('div', { class: 'bl-text' }, 'Starting MWX 7'),
    h('div', { class: 'bl-copy' }, '© MWX Systems'),
  );
  document.body.append(screen);
  const skip = skippable(screen);
  for (let t = 0; t < 3600 && !skip.skipped(); t += 100) await wait(100);
  skip.dispose();
  await fadeOut(screen, 350);
}

/* ---------- 4. logon ---------- */

export async function logon(): Promise<void> {
  const user = settings.get().userName;
  const bg = createWallpaperLayer('meadow');
  const arrow = h('button', { class: 'logon-go', 'aria-label': 'Sign in', html: '<svg viewBox="0 0 24 24"><path d="M5 12h12M12 6l6 6-6 6" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>' });
  const tile = h('button', { class: 'logon-tile', 'aria-label': `Sign in as ${user}` }, h('span', { class: 'logon-pic', html: avatarHtml() }));
  const center = h(
    'div',
    { class: 'logon-center' },
    tile,
    h('div', { class: 'logon-name' }, user),
    h('div', { class: 'logon-row' }, h('span', { class: 'logon-hint' }, 'Click your picture to sign in'), arrow),
  );
  const powerBtn = h('button', { class: 'logon-power', title: 'Shut down', html: icons.power });
  const screen = h(
    'div',
    { class: 'screen logon' },
    h('div', { class: 'logon-bg' }, bg.el),
    h('div', { class: 'logon-shade' }),
    center,
    h('div', { class: 'logon-brand' }, h('span', { html: icons.orb }), h('b', {}, 'MWX'), h('span', { class: 'logon-seven' }, '7')),
    powerBtn,
  );
  document.body.append(screen);
  screen.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 500, easing: 'ease' });
  removeCurtain();

  await new Promise<void>((resolve) => {
    const go = () => {
      window.removeEventListener('keydown', onKey);
      resolve();
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Enter' && go();
    tile.addEventListener('click', go);
    arrow.addEventListener('click', go);
    window.addEventListener('keydown', onKey);
    powerBtn.addEventListener('click', () => {
      window.removeEventListener('keydown', onKey);
      screen.remove();
      shutDown();
    });
  });

  unlockAudio();
  center.replaceChildren(h('div', { class: 'logon-spinner' }), h('div', { class: 'logon-welcome' }, 'Welcome'));
  await wait(1300);
  play('startup');
  await fadeOut(screen, 700);
  bg.destroy();
  setGadgetsLive(true);
}

/* ---------- 3b. first-run setup (Windows 7 OOBE style) ---------- */

async function setup(): Promise<void> {
  let picked = AVATARS[0] ?? '';
  const name = h('input', {
    class: 'oobe-input',
    type: 'text',
    maxLength: 20,
    spellcheck: false,
    autocomplete: 'off',
    placeholder: 'Type a user name (for example, Alex)',
  });
  const pc = h('div', { class: 'oobe-pc' }, 'Computer name: MWX-PC');
  const next = h('button', { class: 'oobe-next', disabled: true }, 'Next');
  const error = h('div', { class: 'oobe-error' });
  name.addEventListener('input', () => {
    const v = name.value.trim();
    next.disabled = !v;
    pc.textContent = `Computer name: ${(v ? v.replace(/[^a-z0-9]/gi, '').toUpperCase().slice(0, 12) || 'MWX' : 'MWX')}-PC`;
    error.textContent = '';
  });
  const picker = avatarPicker(picked, (url) => (picked = url));
  const dialog = h(
    'div',
    { class: 'oobe-window' },
    h('div', { class: 'oobe-titlebar' }, h('span', { class: 'oobe-title-icon', html: icons.orb }), 'Set Up MWX 7'),
    h(
      'div',
      { class: 'oobe-body' },
      h('div', { class: 'oobe-brand' }, h('span', { html: icons.orb }), h('b', {}, 'MWX'), h('span', { class: 'oobe-seven' }, '7')),
      h('h1', {}, 'Choose a user name and a picture for your account'),
      h('p', { class: 'oobe-lead' }, 'This is how you will appear on the logon screen and in the Start menu.'),
      h('label', { class: 'oobe-label' }, 'User name:', name),
      pc,
      h('div', { class: 'oobe-label' }, 'Account picture:'),
      picker,
      error,
    ),
    h('div', { class: 'oobe-footer' }, h('span', { class: 'oobe-copy' }, 'MWX Systems'), next),
  );
  const screen = h('div', { class: 'screen oobe' }, h('div', { class: 'oobe-bg' }), dialog);
  document.body.append(screen);
  dialog.animate([{ opacity: 0, transform: 'scale(.97)' }, { opacity: 1, transform: 'none' }], { duration: 450, easing: 'cubic-bezier(.2,.8,.2,1)' });
  window.setTimeout(() => name.focus(), 60);

  await new Promise<void>((resolve) => {
    const submit = () => {
      const v = name.value.trim();
      if (!v) {
        error.textContent = 'Please type a user name.';
        name.focus();
        return;
      }
      settings.set({ userName: v, avatar: picked });
      resolve();
    };
    next.addEventListener('click', submit);
    name.addEventListener('keydown', (e) => e.key === 'Enter' && submit());
  });
  await fadeOut(screen, 400);
}

function removeCurtain(): void {
  const c = document.getElementById('curtain');
  if (c) c.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, fill: 'forwards' }).onfinish = () => c.remove();
}

/**
 * Every session is a cold boot of a fresh machine: power button → BIOS →
 * boot logo → first-run setup → logon. (MWX 7 remembers nothing on purpose.)
 */
export async function startup(): Promise<void> {
  await powerOn();
  await bios();
  await bootLogo();
  await setup();
  await logon();
}

/* ---------- session end ---------- */

async function transition(message: string): Promise<HTMLElement> {
  const bg = createWallpaperLayer('meadow');
  const screen = h(
    'div',
    { class: 'screen logon' },
    h('div', { class: 'logon-bg' }, bg.el),
    h('div', { class: 'logon-shade' }),
    h('div', { class: 'logon-center' }, h('div', { class: 'logon-spinner' }), h('div', { class: 'logon-welcome' }, message)),
  );
  document.body.append(screen);
  screen.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 400 });
  return screen;
}

export async function logOff(): Promise<void> {
  setGadgetsLive(false);
  play('logoff');
  const screen = await transition('Logging off…');
  allWindows().forEach((w) => closeWindow(w.id, true));
  await wait(1600);
  screen.remove();
  await logon();
}

export async function shutDown(): Promise<void> {
  setGadgetsLive(false);
  play('logoff');
  const screen = await transition('Shutting down…');
  allWindows().forEach((w) => closeWindow(w.id, true));
  await wait(2200);
  screen.replaceChildren();
  screen.className = 'screen off';
  await wait(900);
  screen.remove();
  // Powering on again is a real cold boot.
  const off = powerScreen('MWX 7 is off. Push the power switch to start');
  await off.pressed;
  off.pc.classList.add('pressed');
  await wait(220);
  location.reload();
}
