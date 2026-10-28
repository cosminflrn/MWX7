import { icons } from '../assets/icons';
import { settings } from '../core/settings';
import { play, unlockAudio } from '../core/sound';
import { allWindows, closeWindow } from '../core/wm';
import { h } from '../ui/dom';
import { AVATARS, avatarHtml, avatarPicker } from './avatars';
import { openCommander } from './commander';
import { createWallpaperLayer } from './wallpapers';

/**
 * Full-screen moments: power button → BIOS POST → boot logo → logon,
 * plus log off and shut down. Everything is an overlay above the desktop.
 */

const POWER_GLYPH =
  '<svg viewBox="0 0 64 64"><path d="M22.5 21.5a15 15 0 1 0 19 0" fill="none" stroke="#cfd6df" stroke-width="4.5" stroke-linecap="round"/><path d="M32 13v18" stroke="#cfd6df" stroke-width="4.5" stroke-linecap="round"/></svg>';

/** Original 90s-BIOS-style power-saving badge (star + swoosh), not any real certification mark. */
const POWER_SAVER_BADGE = `
<svg viewBox="0 0 220 96" xmlns="http://www.w3.org/2000/svg" aria-label="MWX Power Saver">
  <defs>
    <linearGradient id="ps-g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2fd0ff"/><stop offset="1" stop-color="#4be37a"/></linearGradient>
  </defs>
  <path d="M10 70 C 50 98, 150 98, 210 30" fill="none" stroke="url(#ps-g)" stroke-width="5" stroke-linecap="round"/>
  <path d="M174 6 l7.2 14.6 16.1 2.3-11.6 11.4 2.7 16-14.4-7.6-14.4 7.6 2.7-16-11.6-11.4 16.1-2.3z" fill="none" stroke="url(#ps-g)" stroke-width="3.4" stroke-linejoin="round"/>
  <text x="12" y="44" fill="#e9f7ff" font-family="Arial, Helvetica, sans-serif" font-style="italic" font-weight="700" font-size="34" letter-spacing="-1">power</text>
  <text x="14" y="66" fill="#7fe0ff" font-family="Arial, Helvetica, sans-serif" font-weight="700" font-size="13" letter-spacing="4.2">MWX SAVER</text>
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

/** Resolves on the first click / key press on (or while showing) `el`. */
function anyInput(el: HTMLElement): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      el.removeEventListener('pointerdown', done);
      window.removeEventListener('keydown', done);
      resolve();
    };
    el.addEventListener('pointerdown', done);
    window.addEventListener('keydown', done);
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

/* ---------- 1. power button ---------- */

async function powerOn(): Promise<void> {
  const btn = h('button', { class: 'power-btn', 'aria-label': 'Power on', html: POWER_GLYPH });
  const screen = h('div', { class: 'screen power' }, btn, h('p', { class: 'power-hint' }, 'Press the power button to start'));
  document.body.append(screen);
  btn.focus();
  await anyInput(screen);
  unlockAudio();
  btn.classList.add('on');
  await wait(450);
  screen.remove();
}

/* ---------- 2. BIOS POST ---------- */

async function bios(): Promise<void> {
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
  play('logoff');
  const screen = await transition('Logging off…');
  allWindows().forEach((w) => closeWindow(w.id, true));
  await wait(1600);
  screen.remove();
  await logon();
}

export async function shutDown(): Promise<void> {
  play('logoff');
  const screen = await transition('Shutting down…');
  allWindows().forEach((w) => closeWindow(w.id, true));
  await wait(2200);
  screen.replaceChildren();
  screen.className = 'screen off';
  await wait(900);
  screen.remove();
  // Powering on again is a real cold boot.
  const btn = h('button', { class: 'power-btn', 'aria-label': 'Power on', html: POWER_GLYPH });
  const off = h('div', { class: 'screen power' }, btn, h('p', { class: 'power-hint' }, 'MWX 7 is off. Press the power button to start'));
  document.body.append(off);
  await anyInput(off);
  location.reload();
}
