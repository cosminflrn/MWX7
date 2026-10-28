import type { AppManifest, MenuDef } from '../../core/types';
import { h } from '../../ui/dom';
import { Sfx } from './audio';
import { Music } from './music';
import { BALL_SAVE_SECONDS, Game, RANKS } from './game';
import { pinballIcon } from './icon';
import './pinball.css';
import { Renderer } from './render';
import { H, W } from './table';

const SAVE_PATH = '/Documents/.pinball.json';
const STEP = 1 / 240;
const fmt = (n: number) => Math.round(n).toLocaleString('en-US');

export const pinball: AppManifest = {
  id: 'pinball',
  name: 'Space Pinball',
  icon: pinballIcon,
  description: 'Deep-space pinball with ranks and missions',
  keywords: ['game', 'pinball', 'arcade', 'ball', 'space', 'flipper'],
  pinned: false,
  desktop: true,
  singleInstance: true,
  window: { width: 1600, height: 1000, resizable: true, minWidth: 700, minHeight: 560 },

  mount({ win, fs }) {
    const sfx = new Sfx();
    const music = new Music(sfx);
    const game = new Game(sfx);

    // ---- DOM ----
    const canvas = h('canvas', { class: 'pb-canvas', 'aria-label': 'Space Pinball table' });
    const overlay = h('div', { class: 'pb-overlay', hidden: true });
    const stage = h('div', { class: 'pb-stage' }, canvas, overlay);

    const scoreEl = h('div', { class: 'pb-lcd pb-score' }, '0');
    const highEl = h('div', { class: 'pb-lcd pb-high' }, '0');
    const ballsEl = h('div', { class: 'pb-balls' });
    const rankEl = h('div', { class: 'pb-rank' });
    const rankBar = h('div', { class: 'pb-bar-fill' });
    const rankNext = h('div', { class: 'pb-sub' });
    const missionEl = h('div', { class: 'pb-mission' });
    const missionBar = h('div', { class: 'pb-bar-fill pb-bar-amber' });
    const bonusEl = h('div', { class: 'pb-lcd pb-bonus' });
    const saveEl = h('div', { class: 'pb-save' }, 'BALL SAVE');
    const ticker = h('div', { class: 'pb-ticker' });
    const lbl = (t: string) => h('div', { class: 'pb-label' }, t);

    const panel = h(
      'aside',
      { class: 'pb-panel' },
      h('div', { class: 'pb-logo' }, h('span', { class: 'pb-logo-a' }, 'SPACE'), h('span', { class: 'pb-logo-b' }, 'PINBALL')),
      lbl('SCORE'),
      scoreEl,
      lbl('HIGH SCORE'),
      highEl,
      h('div', { class: 'pb-row' }, h('div', {}, lbl('BALL'), ballsEl), saveEl),
      lbl('RANK'),
      h('div', { class: 'pb-card' }, rankEl, h('div', { class: 'pb-bar' }, rankBar), rankNext),
      lbl('MISSION'),
      h('div', { class: 'pb-card' }, missionEl, h('div', { class: 'pb-bar' }, missionBar)),
      lbl('END-OF-BALL BONUS'),
      bonusEl,
      h('div', { class: 'pb-spacer' }),
      ticker,
      h(
        'div',
        { class: 'pb-keys' },
        h('span', {}, h('kbd', {}, '\u2190'), h('kbd', {}, '\u2192'), ' flippers'),
        h('span', {}, h('kbd', {}, '\u2191'), ' hold to launch'),
        h('span', {}, h('kbd', {}, 'F2'), ' new game')
      )
    );
    win.body.classList.add('pb');
    win.body.tabIndex = 0;
    win.body.append(stage, panel);
    win.setTitle('Space Pinball');

    for (let i = 0; i < game.ballsMax; i++) ballsEl.append(h('i', { class: 'pb-ball' }));

    const renderer = new Renderer(canvas, game.world.segs);

    // ---- persistence (ctx.fs only) ----
    void fs
      .read(SAVE_PATH)
      .then((txt) => {
        if (!txt) return;
        const v = (JSON.parse(txt) as { high?: unknown }).high;
        if (typeof v === 'number' && Number.isFinite(v) && v > game.high) game.high = v;
      })
      .catch(() => undefined);
    game.onHigh = (high) => {
      void fs.write(SAVE_PATH, JSON.stringify({ high, saved: Date.now() })).catch(() => undefined);
    };

    // ---- input ----
    const held = new Set<string>();
    const flipKeys: Record<string, 0 | 1> = { ArrowLeft: 0, KeyZ: 0, ShiftLeft: 0, ArrowRight: 1, Slash: 1, ShiftRight: 1 };
    const refreshFlippers = () => {
      game.setFlipper(0, [...held].some((k) => flipKeys[k] === 0));
      game.setFlipper(1, [...held].some((k) => flipKeys[k] === 1));
    };
    const releaseAll = () => {
      held.clear();
      refreshFlippers();
      game.setPlunger(false);
    };
    const isPlunger = (c: string) => c === 'ArrowUp' || c === 'Space' || c === 'ArrowDown';

    win.body.addEventListener('keydown', (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      sfx.unlock();
      music.start();
      if (e.code in flipKeys || isPlunger(e.code)) e.preventDefault();
      if (e.repeat) return;
      if (e.code === 'F2') {
        e.preventDefault();
        return newGame();
      }
      if (e.code === 'KeyM') return toggleMute();
      if (e.code in flipKeys) {
        held.add(e.code);
        refreshFlippers();
      } else if (isPlunger(e.code)) {
        if (game.phase === 'over') newGame();
        else game.setPlunger(true);
      }
    });
    win.body.addEventListener('keyup', (e) => {
      if (e.code in flipKeys) {
        held.delete(e.code);
        refreshFlippers();
      } else if (isPlunger(e.code)) game.setPlunger(false);
    });
    // Mouse / touch: left half = left flipper, right half = right flipper, far right strip = plunger.
    const pointerZone = (e: PointerEvent): 'plunger' | 0 | 1 => {
      const r = canvas.getBoundingClientRect();
      const fx = (e.clientX - r.left) / r.width;
      return fx > 0.9 ? 'plunger' : fx < 0.5 ? 0 : 1;
    };
    const pointerHeld = new Map<number, 'plunger' | 0 | 1>();
    canvas.addEventListener('pointerdown', (e) => {
      win.body.focus();
      sfx.unlock();
      music.start();
      if (game.phase === 'over') return newGame();
      const z = pointerZone(e);
      pointerHeld.set(e.pointerId, z);
      canvas.setPointerCapture(e.pointerId);
      if (z === 'plunger') game.setPlunger(true);
      else game.setFlipper(z, true);
    });
    const pointerUp = (e: PointerEvent) => {
      const z = pointerHeld.get(e.pointerId);
      if (z === undefined) return;
      pointerHeld.delete(e.pointerId);
      if (z === 'plunger') game.setPlunger(false);
      else game.setFlipper(z, false);
    };
    canvas.addEventListener('pointerup', pointerUp);
    canvas.addEventListener('pointercancel', pointerUp);

    // Losing focus never pauses the game, but a key released elsewhere must not stay "held".
    const onBlur = () => releaseAll();
    window.addEventListener('blur', onBlur);

    // ---- menus ----
    const newGame = () => {
      game.persistHigh();
      game.newGame();
      sfx.unlock();
      buildMenus();
    };
    const toggleMute = () => {
      sfx.setMuted(!sfx.muted);
      buildMenus();
    };
    const toggleMusic = () => {
      sfx.unlock();
      music.setEnabled(!music.enabled);
      buildMenus();
    };
    function buildMenus(): void {
      const menus: MenuDef[] = [
        {
          label: 'Game',
          items: [
            { label: 'New Game', shortcut: 'F2', action: newGame },
            { separator: true },
            { label: 'Music', checked: music.enabled, action: toggleMusic },
            { label: 'Mute Sound', shortcut: 'M', checked: sfx.muted, action: toggleMute },
          ],
        },
      ];
      win.setMenus(menus);
    }
    buildMenus();

    // ---- layout: the table fills the window height; the score panel scales with it and sits beside the table ----
    let lastKey = '';
    const PANEL_W = 232;
    const fit = () => {
      const bw = win.body.clientWidth;
      const bh = win.body.clientHeight;
      if (!bw || !bh) return;
      // The panel grows a little faster than the table so wide windows are filled; 520 = its minimum natural height.
      const clamp = (v: number) => Math.max(0.8, Math.min(1.9, v * 1.3, bh / 520));
      let s = Math.min((bh - 8) / H, (bw - PANEL_W * 0.8) / W);
      for (let i = 0; i < 3; i++) s = Math.min((bh - 8) / H, (bw - PANEL_W * clamp(s)) / W);
      s = Math.max(0.2, s);
      const u = clamp(s);
      const cssW = Math.floor(W * s);
      const cssH = Math.floor(H * s);
      const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 3, 1600 / cssW)); // cap texture size on huge screens
      const key = `${cssW}|${cssH}|${dpr}|${u}|${bh}`;
      if (key === lastKey) return;
      lastKey = key;
      stage.style.width = `${cssW}px`;
      stage.style.height = `${cssH}px`;
      // CSS zoom scales the whole panel (text, bars, bezels) with the table.
      panel.style.setProperty('zoom', String(u));
      panel.style.width = `${PANEL_W}px`;
      panel.style.height = `${bh / u}px`;
      renderer.resize(cssW, dpr);
    };
    const ro = new ResizeObserver(fit);
    ro.observe(win.body);
    fit();

    // ---- panel ----
    let shownScore = 0;
    const cache: Record<string, string> = {};
    const set = (k: string, el: HTMLElement, v: string) => {
      if (cache[k] !== v) {
        cache[k] = v;
        el.textContent = v;
      }
    };
    const updatePanel = () => {
      shownScore += (game.score - shownScore) * 0.25;
      if (Math.abs(game.score - shownScore) < 1) shownScore = game.score;
      set('score', scoreEl, fmt(shownScore));
      set('high', highEl, fmt(Math.max(game.high, game.score)));
      [...ballsEl.children].forEach((b, i) => {
        const left = game.phase === 'over' ? false : i >= game.ballNo - 1;
        (b as HTMLElement).classList.toggle('on', left);
        (b as HTMLElement).classList.toggle('cur', i === game.ballNo - 1 && game.phase !== 'over');
      });
      const ri = game.rankIndex;
      const next = RANKS[ri + 1];
      set('rank', rankEl, RANKS[ri].name.toUpperCase());
      const span = next ? next.at - RANKS[ri].at : 1;
      rankBar.style.width = `${next ? ((game.missionsDone - RANKS[ri].at) / span) * 100 : 100}%`;
      set('rankNext', rankNext, next ? `${next.at - game.missionsDone} mission${next.at - game.missionsDone === 1 ? '' : 's'} to ${next.name}` : 'Highest rank achieved');
      const m = game.currentMission;
      set('mission', missionEl, m.goal > 1 ? `${m.text} (${m.prog}/${m.goal})` : m.text);
      missionBar.style.width = `${(m.prog / m.goal) * 100}%`;
      set('bonus', bonusEl, `${fmt(game.bonus)} x${game.mult}`);
      saveEl.classList.toggle('on', game.saveT > 0);
      set('save', saveEl, game.saveT > 0 ? `BALL SAVE ${Math.ceil(game.saveT)}s` : game.phase === 'ready' ? `SAVE ${BALL_SAVE_SECONDS}s` : 'BALL SAVE');
      set('ticker', ticker, game.ticker);
      const ov = game.phase === 'over' ? ['GAME OVER', `Final score ${fmt(game.score)} - press Up or F2`] : null;
      const key = ov ? ov.join('|') : '';
      if (cache.ov !== key) {
        cache.ov = key;
        overlay.hidden = !ov;
        overlay.replaceChildren(...(ov ? [h('div', { class: 'pb-ov-title' }, ov[0]), h('div', { class: 'pb-ov-sub' }, ov[1])] : []));
      }
    };

    // ---- main loop ----
    let raf = 0;
    let last = performance.now();
    let acc = 0;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      // Clamp the delta: after a throttled / hidden tab the first frame must not hand the physics a huge step.
      const dt = Math.min(0.05, Math.max(0, (now - last) / 1000));
      last = now;
      acc += dt;
      let n = 0;
      while (acc >= STEP && n < 24) {
        game.step(STEP);
        acc -= STEP;
        n++;
      }
      if (n >= 24) acc = 0;
      if (canvas.width > 40) renderer.draw(game, now);
      updatePanel();
    };
    raf = requestAnimationFrame(frame);
    setTimeout(() => win.body.focus(), 50);

    win.onBeforeClose(() => {
      game.persistHigh();
      return true;
    });

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener('blur', onBlur);
      game.persistHigh();
      music.dispose();
      sfx.setMuted(true);
      sfx.dispose();
    };
  },
};
