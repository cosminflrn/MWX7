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
const PANEL_W = 232;
/** Chrome around the window body: title bar (30) on top, 8px glass frame on the other three sides, plus a 1px border all round. */
const FRAME_X = 18;
const FRAME_Y = 40;
const MENUBAR_H = 30;
const DOCK_RESERVE = 70;

/**
 * Fixed-size window that hugs the content: table + score panel at 1:1, scaled down uniformly when the screen
 * cannot hold it (the OS would otherwise clamp one axis and leave gaps).
 */
function fitWindow(): { width: number; height: number; resizable: false } {
  const cw = W + PANEL_W;
  const availH = (typeof window === 'undefined' ? 900 : window.innerHeight) - MENUBAR_H - DOCK_RESERVE - 24;
  const availW = (typeof window === 'undefined' ? 1600 : window.innerWidth) - 40;
  const s = Math.min(1, (availH - FRAME_Y) / H, (availW - FRAME_X) / cw);
  return { width: Math.floor(cw * s) + FRAME_X, height: Math.floor(H * s) + FRAME_Y, resizable: false };
}
const WINDOW = fitWindow();
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
  window: WINDOW,

  mount({ win, fs }) {
    const sfx = new Sfx();
    const music = new Music(sfx);
    const game = new Game(sfx);
    // Music starts the moment the app opens. The boot clicks have already unlocked audio for the page; if not, `wake` retries on first input.
    sfx.unlock();
    music.start();

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
        h('span', {}, h('kbd', {}, 'M'), ' mute'),
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
      wake();
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
    // Desktop only, keyboard only: there is deliberately no mouse / touch handling for gameplay.
    // Audio fallback: if the browser still holds the context suspended at mount, the first click or key in the window starts it.
    const wake = () => {
      if (sfx.ctx && sfx.ctx.state === 'running') return;
      sfx.unlock();
      music.start();
    };
    win.body.addEventListener('pointerdown', wake, true);
    win.body.addEventListener('keydown', wake, true);

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
            { label: 'New Game', action: newGame },
            { separator: true },
            { label: 'Music', checked: music.enabled, action: toggleMusic },
            { label: 'Mute Sound', checked: sfx.muted, action: toggleMute },
          ],
        },
      ];
      win.setMenus(menus);
    }
    buildMenus();

    // ---- layout: the window is sized to the content; scale table and panel uniformly, the panel absorbs rounding slack ----
    let lastKey = '';
    const fit = () => {
      const bw = win.body.clientWidth;
      const bh = win.body.clientHeight;
      if (!bw || !bh) return;
      const s = Math.max(0.2, Math.min(bh / H, bw / (W + PANEL_W)));
      const cssW = Math.floor(W * s);
      const cssH = Math.floor(H * s);
      const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 3, 1600 / cssW)); // cap texture size on huge screens
      const key = `${cssW}|${cssH}|${dpr}|${bw}|${bh}`;
      if (key === lastKey) return;
      lastKey = key;
      stage.style.width = `${cssW}px`;
      stage.style.height = `${cssH}px`;
      // CSS zoom scales the whole panel (text, bars, bezels) with the table.
      panel.style.setProperty('zoom', String(s));
      panel.style.width = `${(bw - cssW) / s}px`;
      panel.style.height = `${bh / s}px`;
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
