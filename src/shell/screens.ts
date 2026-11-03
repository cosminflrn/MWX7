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

/**
 * Photo: a beige 1990s tower + CRT on a desk (public/media/boot/pc-crt.jpg, Pexels, see CREDITS.md), 1920x1280.
 * Everything that must stay registered to the photo (hit area, glass, LED) is positioned in % of the photo box,
 * and the box is cover-cropped for any viewport aspect, so alignment holds when the window is resized.
 */
const PHOTO_ASPECT = 1.5;
/** CRT glass corners in photo fractions: top-left, top-right, bottom-right, bottom-left. */
const GLASS: [number, number][] = [
  [472 / 1920, 294 / 1280],
  [888 / 1920, 266 / 1280],
  [832 / 1920, 732 / 1280],
  [414 / 1920, 688 / 1280],
];
const GLASS_CLIP = `polygon(${GLASS.map(([u, v]) => `${(u * 100).toFixed(2)}% ${(v * 100).toFixed(2)}%`).join(',')})`;
const SWITCH = { u: 1582 / 1920, v: 970 / 1280 };

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const smooth = (a: number, b: number, t: number) => {
  const x = Math.min(1, Math.max(0, (t - a) / (b - a)));
  return x * x * (3 - 2 * x);
};

type Pt = [number, number];

/** matrix3d that maps a w x h box (origin 0 0) onto an arbitrary quad (Heckbert's unit-square projection). */
function quadMatrix(w: number, h: number, q: Pt[]): string {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = q;
  const dx1 = x1 - x2, dx2 = x3 - x2, dy1 = y1 - y2, dy2 = y3 - y2;
  const sx = x0 - x1 + x2 - x3, sy = y0 - y1 + y2 - y3;
  const den = dx1 * dy2 - dx2 * dy1;
  const g = Math.abs(sx) + Math.abs(sy) < 1e-9 ? 0 : (sx * dy2 - dx2 * sy) / den;
  const hh = Math.abs(sx) + Math.abs(sy) < 1e-9 ? 0 : (dx1 * sy - sx * dy1) / den;
  const a = x1 - x0 + g * x1, b = x3 - x0 + hh * x3, d = y1 - y0 + g * y1, e = y3 - y0 + hh * y3;
  return `matrix3d(${a / w},${d / w},0,${g / w},${b / h},${e / h},0,${hh / h},0,0,1,0,${x0},${y0},0,1)`;
}

const BIOS_INTRO = (): string[] => [
  'MWX Systems BIOS v7.03.2026, A Web-Native Firmware',
  'Copyright (C) 2026, MWX Systems, Inc.',
  '',
  'MWX 7 Reference Board  Rev. 7.0',
  '',
  `Main Processor   : Browser Core x${navigator.hardwareConcurrency || 4} @ 3.20 GHz`,
];
const BIOS_FOOT = 'Press DEL to run Setup, F12 for Boot Menu, ESC to skip\n10/28/2026-MWX7-7.03-BIOS';

/** Cover-crop the photo, but never so tight that the glass and the power switch (u 0.2..0.86) leave the viewport. */
function layout(vw: number, vh: number) {
  let SW = Math.max(vw, vh * PHOTO_ASPECT);
  if (vw / SW < 0.74) SW = Math.max(vw / 0.74, vh * PHOTO_ASPECT * 0.55);
  const SH = SW / PHOTO_ASPECT;
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  const left = SW >= vw ? clamp(vw / 2 - 0.53 * SW, vw - SW, 0) : (vw - SW) / 2;
  const top = SH >= vh ? clamp(vh / 2 - 0.5 * SH, vh - SH, 0) : (vh - SH) / 2;
  return { SW, SH, left, top };
}

function powerScreen(hint: string) {
  const pct = (n: number) => `${(n * 100).toFixed(3)}%`;
  const photo = h('img', { class: 'pw-photo', src: `${import.meta.env.BASE_URL}media/boot/pc-crt.jpg`, alt: '', draggable: 'false' });
  const sheen = h('div', { class: 'pw-sheen' });
  sheen.style.clipPath = GLASS_CLIP;
  const spill = h('div', { class: 'pw-spill' });
  spill.style.left = pct((GLASS[0][0] + GLASS[2][0]) / 2);
  spill.style.top = pct((GLASS[0][1] + GLASS[2][1]) / 2);
  const led = h('i', { class: 'pw-led' });
  led.style.left = pct(SWITCH.u);
  led.style.top = pct(SWITCH.v - 0.026);
  const dent = h('i', { class: 'pw-dent' });
  dent.style.left = pct(SWITCH.u);
  dent.style.top = pct(SWITCH.v);
  const sw = h('button', { class: 'power-btn', 'aria-label': 'Power on' }, h('i', { class: 'pw-ring' }));
  sw.style.left = pct(SWITCH.u);
  sw.style.top = pct(SWITCH.v);
  const scene = h('div', { class: 'scene' }, photo, sheen, spill, dent, led, sw);
  const veil = h('div', { class: 'pw-veil' });
  // The monitor image: same look as the real BIOS screen (class "bios"), mapped onto the glass by a matrix3d quad.
  const text = h('pre', { class: 'bios-text' });
  const foot = h('pre', { class: 'bios-foot' }, BIOS_FOOT);
  foot.style.opacity = '0';
  const fx = h('div', { class: 'crt-fx' });
  const crt = h('div', { class: 'bios crt-img' }, text, foot, fx);
  const hintEl = h('p', { class: 'power-hint' }, hint);
  const screen = h('div', { class: 'screen power' }, scene, veil, crt, hintEl);
  document.body.append(screen);

  // ----- camera: idle push-in + pointer parallax, then the zoom into the glass -----
  const t0 = performance.now();
  let px = 0, py = 0, tpx = 0, tpy = 0;
  const onMove = (e: PointerEvent) => {
    tpx = (e.clientX / innerWidth - 0.5) * 2;
    tpy = (e.clientY / innerHeight - 0.5) * 2;
  };
  window.addEventListener('pointermove', onMove);
  let zoomStart = -1;
  let zoomDur = 2300;
  let zoomFrom = { s: 1, gx: 0, gy: 0 };
  let crtOn = -1;
  let done: (() => void) | null = null;
  const cam = { s: 1, tx: 0, ty: 0 };
  let bw = 0, bh = 0;
  const gc: Pt = [(GLASS[0][0] + GLASS[2][0]) / 2, (GLASS[0][1] + GLASS[2][1]) / 2];
  const glassH = ((GLASS[3][1] - GLASS[0][1]) + (GLASS[2][1] - GLASS[1][1])) / 2;

  function frame(now: number) {
    if (!screen.isConnected) {
      window.removeEventListener('pointermove', onMove);
      return;
    }
    const vw = innerWidth, vh = innerHeight;
    const { SW, SH, left, top } = layout(vw, vh);
    const Cx = left + SW / 2, Cy = top + SH / 2;
    px += (tpx - px) * 0.04;
    py += (tpy - py) * 0.04;
    const idleT = (now - t0) / 1000;
    const sIdle = 1.045 + 0.03 * (1 - Math.exp(-idleT / 25));
    let s = sIdle;
    let tx = -px * SW * 0.008, ty = -py * SH * 0.006;
    let p = 0;
    // viewport position of a photo fraction under camera (s, tx, ty)
    const at = (u: number, v: number, cs: number, cx: number, cy: number): Pt => [Cx + cx + cs * (u - 0.5) * SW, Cy + cy + cs * (v - 0.5) * SH];
    if (zoomStart >= 0) {
      p = Math.min(1, (now - zoomStart) / zoomDur);
      const e = ease(p);
      const sEnd = (vh * 1.0) / (glassH * SH);
      s = Math.exp(lerp(Math.log(zoomFrom.s), Math.log(sEnd), e));
      const gx = lerp(zoomFrom.gx, vw / 2, e), gy = lerp(zoomFrom.gy, vh / 2, e);
      tx = gx - Cx - s * (gc[0] - 0.5) * SW;
      ty = gy - Cy - s * (gc[1] - 0.5) * SH;
    }
    if (zoomStart < 0) Object.assign(cam, { s, tx, ty });
    scene.style.left = `${left}px`;
    scene.style.top = `${top}px`;
    scene.style.width = `${SW}px`;
    scene.style.height = `${SH}px`;
    scene.style.transform = `translate3d(${tx}px,${ty}px,0) scale(${s})`;

    if (crtOn >= 0) {
      // 4:3 slice of the real BIOS screen, so text keeps its proportions on the glass
      const nbw = Math.round(vh * (4 / 3));
      if (nbw !== bw || vh !== bh) {
        bw = nbw;
        bh = vh;
        crt.style.width = `${bw}px`;
        crt.style.height = `${bh}px`;
      }
      const glass = GLASS.map(([u, v]) => at(u, v, s, tx, ty));
      const target: Pt[] = [[0, 0], [bw, 0], [bw, bh], [0, bh]];
      const q = smooth(0.5, 1, p);
      const quad = glass.map((c, i) => [lerp(c[0], target[i][0], q), lerp(c[1], target[i][1], q)] as Pt);
      crt.style.transform = p >= 1 ? 'none' : quadMatrix(bw, bh, quad);
      fx.style.opacity = String(1 - q);
      crt.style.borderRadius = `${(1 - q) * 36}px`;
      const glow = 1 - smooth(0.55, 0.9, p);
      scene.style.opacity = String(glow);
      veil.style.opacity = String(smooth(0.35, 0.8, p));
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  const pressed = new Promise<void>((r) => sw.addEventListener('click', () => r(), { once: true }));

  /** Power-on: LED, CRT lights up and types the first BIOS lines, camera dives into the glass. Resolves at the identity frame. */
  async function run(): Promise<void> {
    ensureVgaFont();
    void document.fonts.load("32px 'Web437 IBM VGA 8x16'");
    hintEl.style.opacity = '0';
    scene.classList.add('pressed');
    await wait(110);
    scene.classList.add('on');
    play('spinup');
    await wait(450);
    // degauss-style flash, then the phosphor settles
    bw = Math.round(innerHeight * (4 / 3));
    bh = innerHeight;
    crt.style.width = `${bw}px`;
    crt.style.height = `${bh}px`;
    crt.style.display = 'block';
    crtOn = performance.now();
    crt.animate([{ opacity: 0 }, { opacity: 0.9, offset: 0.12 }, { opacity: 0.45, offset: 0.3 }, { opacity: 1 }], { duration: 420, fill: 'forwards' });
    scene.classList.add('lit');
    await wait(520);
    for (const [i, l] of BIOS_INTRO().entries()) {
      text.textContent += l + '\n';
      if (i === 1) foot.style.opacity = '1';
      await wait(l ? 230 : 120);
    }
    await wait(420);
    // dive
    const L = layout(innerWidth, innerHeight);
    zoomFrom = {
      s: cam.s,
      gx: L.left + L.SW / 2 + cam.tx + cam.s * (gc[0] - 0.5) * L.SW,
      gy: L.top + L.SH / 2 + cam.ty + cam.s * (gc[1] - 0.5) * L.SH,
    };
    zoomDur = 2300;
    zoomStart = performance.now();
    await new Promise<void>((r) => (done = r));
  }
  // resolve `done` when the zoom ends (checked on a timer to keep the render loop free of logic)
  const poll = window.setInterval(() => {
    if (zoomStart >= 0 && performance.now() - zoomStart >= zoomDur + 30) {
      window.clearInterval(poll);
      done?.();
    }
    if (!screen.isConnected) window.clearInterval(poll);
  }, 40);

  return { screen, pc: scene, pressed, run, text };
}

async function powerOn(): Promise<{ screen: HTMLElement }> {
  const { screen, pressed, run } = powerScreen('Push the power switch to start');
  await pressed;
  unlockAudio();
  play('switch');
  await run();
  return { screen };
}

/* ---------- 2. BIOS POST ---------- */

async function bios(prev?: HTMLElement): Promise<void> {
  ensureVgaFont();
  const text = h('pre', { class: 'bios-text' });
  const screen = h(
    'div',
    { class: 'screen bios' },
    h('div', { class: 'bios-badge', html: POWER_SAVER_BADGE }),
    text,
    h('pre', { class: 'bios-foot' }, BIOS_FOOT),
  );
  document.body.append(screen);
  if (prev) {
    // Continues the CRT image exactly: same intro text already on screen, power-saver badge fades in as the glass clears.
    text.textContent = BIOS_INTRO().join('\n') + '\n';
    screen.querySelector('.bios-badge')?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 500, easing: 'ease-out' });
    requestAnimationFrame(() => requestAnimationFrame(() => prev.remove()));
  }
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

  const memMB = ((navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 8) * 1024;

  if (!prev) for (const l of BIOS_INTRO().slice(0, 5)) await line(l, l ? 160 : 60);
  if (!prev) await line(BIOS_INTRO()[5], 220);
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
  const { screen } = await powerOn();
  await bios(screen);
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
