import type { AppManifest, MenuItem, VFS } from '../../core/types';
import { h } from '../../ui/dom';
import './mediaplayer.css';

const MUSIC = '/Music';
const AUDIO_EXT = /\.(mp3|ogg|oga|wav|m4a|flac)$/i;
const POINTER = 'mwx-media:';
const BASE = import.meta.env.BASE_URL;

/** Bundled CC0 recordings (see public/media/CREDITS.md). VFS stores text, so the file holds a pointer to the asset. */
const BUNDLED = [
  { file: 'Goldberg Variations - Variatio 1.ogg', src: 'media/music/goldberg-variatio-1.ogg', title: 'Goldberg Variations: Variatio 1', artist: 'Kimiko Ishizaka' },
  { file: 'Goldberg Variations - Variatio 4.ogg', src: 'media/music/goldberg-variatio-4.ogg', title: 'Goldberg Variations: Variatio 4', artist: 'Kimiko Ishizaka' },
  { file: 'Goldberg Variations - Variatio 5.ogg', src: 'media/music/goldberg-variatio-5.ogg', title: 'Goldberg Variations: Variatio 5', artist: 'Kimiko Ishizaka' },
  { file: 'Goldberg Variations - Variatio 2.ogg', src: 'media/music/goldberg-variatio-2.ogg', title: 'Goldberg Variations: Variatio 2', artist: 'Kimiko Ishizaka' },
  { file: 'Goldberg Variations - Variatio 6.ogg', src: 'media/music/goldberg-variatio-6.ogg', title: 'Goldberg Variations: Variatio 6', artist: 'Kimiko Ishizaka' },
  { file: 'Goldberg Variations - Variatio 8.ogg', src: 'media/music/goldberg-variatio-8.ogg', title: 'Goldberg Variations: Variatio 8', artist: 'Kimiko Ishizaka' },
  { file: 'Goldberg Variations - Variatio 10.ogg', src: 'media/music/goldberg-variatio-10.ogg', title: 'Goldberg Variations: Variatio 10', artist: 'Kimiko Ishizaka' },
  { file: 'Goldberg Variations - Variatio 18.ogg', src: 'media/music/goldberg-variatio-18.ogg', title: 'Goldberg Variations: Variatio 18', artist: 'Kimiko Ishizaka' },
];

interface Track {
  path: string;
  title: string;
  artist: string;
  url: string;
}

/** Original generated cover art: a soft gradient with piano keys and a hue derived from the title, so each track looks distinct. */
function artFor(seed: string): string {
  let n = 0;
  for (const c of seed) n = (n * 31 + c.charCodeAt(0)) >>> 0;
  const hue = n % 360;
  const keys = Array.from({ length: 7 }, (_, i) => `<rect x="${6 + i * 12}" y="50" width="10" height="${i % 3 === 1 ? 34 : 44}" rx="2" fill="#fff" opacity="${0.55 + ((n >> i) & 3) * 0.1}"/>`).join('');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl(${hue} 70% 62%)"/><stop offset="1" stop-color="hsl(${(hue + 50) % 360} 65% 28%)"/></linearGradient></defs><rect width="96" height="96" rx="10" fill="url(#g)"/><circle cx="${30 + (n % 40)}" cy="26" r="${10 + (n % 7)}" fill="#fff" opacity=".22"/><path d="M0 40q24-${10 + (n % 16)} 48 0t48 0" fill="none" stroke="#fff" stroke-width="2" opacity=".35"/>${keys}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const fmt = (s: number): string => {
  if (!Number.isFinite(s) || s < 0) s = 0;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
};

const urlFromContent = (content: string): string | null => {
  if (content.startsWith(POINTER)) return BASE + content.slice(POINTER.length);
  if (content.startsWith('data:audio') || content.startsWith('blob:') || /^https?:\/\//.test(content)) return content;
  return null;
};

async function ensureSeeded(fs: VFS): Promise<void> {
  const existing = (await fs.list(MUSIC)).filter((f) => f.type !== 'dir' && AUDIO_EXT.test(f.name));
  if (existing.length) return;
  await fs.mkdir(MUSIC);
  for (const b of BUNDLED) await fs.write(`${MUSIC}/${b.file}`, POINTER + b.src);
}

async function loadTracks(fs: VFS): Promise<Track[]> {
  const out: Track[] = [];
  for (const f of await fs.list(MUSIC)) {
    if (f.type === 'dir' || !AUDIO_EXT.test(f.name)) continue;
    const url = urlFromContent(f.content);
    if (!url) continue;
    const known = BUNDLED.find((b) => f.content === POINTER + b.src);
    out.push({ path: f.path, url, title: known?.title ?? f.name.replace(AUDIO_EXT, ''), artist: known?.artist ?? 'Unknown artist' });
  }
  return out.sort((a, b) => a.path.localeCompare(b.path, undefined, { numeric: true }));
}

export const impl: Pick<AppManifest, 'mount'> = {
  mount({ win, args, fs, os }) {
    win.body.classList.add('mp');
    let tracks: Track[] = [];
    let index = -1;
    let shuffle = false;
    let repeat: 'off' | 'all' | 'one' = 'off';
    let seeking = false;

    const audio = new Audio();
    audio.preload = 'metadata';
    let actx: AudioContext | null = null;
    let analyser: AnalyserNode | null = null;
    const data = new Uint8Array(64);

    const title = h('div', { class: 'mp-title' }, 'Nothing playing');
    const artist = h('div', { class: 'mp-artist' }, 'Pick a track from the playlist');
    const canvas = h('canvas', { class: 'mp-canvas' });
    const list = h('div', { class: 'mp-list', role: 'listbox' });
    const seek = h('input', { class: 'mp-seek', type: 'range', min: 0, max: 1000, value: 0, 'aria-label': 'Seek' });
    const time = h('span', { class: 'mp-time' }, '0:00 / 0:00');
    const vol = h('input', { class: 'mp-vol', type: 'range', min: 0, max: 100, value: 50, 'aria-label': 'Volume' });
    const volPct = h('span', { class: 'mp-volpct' }, '50%');
    const btn = (cls: string, label: string, onclick: () => void, html = '') => h('button', { class: cls, 'aria-label': label, title: label, onclick, html });
    const shuffleBtn = btn('mp-b mp-toggle', 'Shuffle', () => {
      shuffle = shuffleBtn.classList.toggle('on');
    }, '<svg viewBox="0 0 24 24"><path d="M3 7h4l9 10h5M3 17h4l3-3.4M13 10.4 16 7h5M18 4l3 3-3 3M18 14l3 3-3 3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>');
    const repeatBtn = btn('mp-b mp-toggle', 'Repeat: off', () => {
      repeat = repeat === 'off' ? 'all' : repeat === 'all' ? 'one' : 'off';
      repeatBtn.classList.toggle('on', repeat !== 'off');
      repeatBtn.dataset.mode = repeat === 'one' ? '1' : '';
      repeatBtn.title = `Repeat: ${repeat}`;
    }, '<svg viewBox="0 0 24 24"><path d="M4 11V9a3 3 0 0 1 3-3h12M16 3l3 3-3 3M20 13v2a3 3 0 0 1-3 3H5M8 21l-3-3 3-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>');
    const prev = btn('mp-b mp-skip', 'Previous', () => step(-1), '<svg viewBox="0 0 24 24"><path d="M6 5v14M19 5v14L8.500 12z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>');
    const next = btn('mp-b mp-skip', 'Next', () => step(1), '<svg viewBox="0 0 24 24"><path d="M18 5v14M5 5v14l10.500-7z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>');
    const play = btn('mp-play', 'Play', () => toggle());
    const setPlayIcon = (playing: boolean) => {
      play.classList.toggle('playing', playing);
      play.setAttribute('aria-label', playing ? 'Pause' : 'Play');
      play.title = playing ? 'Pause' : 'Play';
    };

    const stage = h('div', { class: 'mp-stage' }, canvas, h('div', { class: 'mp-np' }, title, artist));
    win.body.append(
      h('div', { class: 'mp-main' }, stage, h('aside', { class: 'mp-side' }, h('div', { class: 'mp-side-h' }, 'Playlist'), list)),
      h('div', { class: 'mp-bar' }, h('div', { class: 'mp-seekrow' }, seek, time),
        h('div', { class: 'mp-ctrls' }, h('div', { class: 'mp-grp' }, shuffleBtn, repeatBtn), h('div', { class: 'mp-transport' }, prev, play, next), h('div', { class: 'mp-grp mp-volgrp' }, h('span', { class: 'mp-vi', html: '<svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4Z" fill="currentColor"/><path d="M16 9a4 4 0 0 1 0 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>' }), vol, volPct))),
    );

    const renderList = () => {
      list.replaceChildren();
      if (!tracks.length) list.append(h('div', { class: 'mp-empty' }, 'No audio files in your Music folder.'));
      tracks.forEach((t, i) =>
        list.append(
          h('button', { class: `mp-item${i === index ? ' cur' : ''}`, role: 'option', ondblclick: () => select(i, true), onclick: () => select(i, true) },
            h('img', { class: 'mp-art', src: artFor(t.title), alt: '', draggable: false }), h('span', { class: 'mp-it' }, h('b', {}, t.title), h('small', {}, t.artist))),
        ),
      );
    };

    const ensureAudioGraph = () => {
      if (actx) return;
      try {
        actx = new AudioContext();
        analyser = actx.createAnalyser();
        analyser.fftSize = 128;
        analyser.smoothingTimeConstant = 0.82;
        actx.createMediaElementSource(audio).connect(analyser);
        analyser.connect(actx.destination);
      } catch {
        actx = null;
        analyser = null;
      }
    };

    const select = (i: number, autoplay: boolean) => {
      if (i < 0 || i >= tracks.length) return;
      index = i;
      const t = tracks[i];
      audio.src = t.url;
      title.textContent = t.title;
      artist.textContent = t.artist;
      win.setTitle(`${t.title} — Media Player`);
      list.querySelectorAll('.cur').forEach((n) => n.classList.remove('cur'));
      list.children[i]?.classList.add('cur');
      if (autoplay) void start();
    };

    const start = async () => {
      ensureAudioGraph();
      try {
        await actx?.resume();
        await audio.play();
      } catch {
        /* interrupted by another load, or blocked: the button stays in the paused state */
      }
    };

    const toggle = () => {
      if (index < 0) return select(0, true);
      if (audio.paused) void start();
      else audio.pause();
    };

    const step = (d: number, auto = false) => {
      if (!tracks.length) return;
      if (shuffle && tracks.length > 1) {
        let n = index;
        while (n === index) n = Math.floor(Math.random() * tracks.length);
        return select(n, true);
      }
      const n = index + d;
      if (n >= tracks.length || n < 0) {
        if (auto && repeat === 'off') return;
        return select((n + tracks.length) % tracks.length, true);
      }
      select(n, true);
    };

    audio.addEventListener('play', () => setPlayIcon(true));
    audio.addEventListener('pause', () => setPlayIcon(false));
    audio.addEventListener('ended', () => (repeat === 'one' ? void start() : step(1, true)));
    audio.addEventListener('timeupdate', () => {
      if (!seeking && audio.duration) seek.value = String((audio.currentTime / audio.duration) * 1000);
      time.textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration)}`;
    });
    audio.addEventListener('error', () => {
      if (audio.src) artist.textContent = "This file couldn't be played";
    });
    seek.addEventListener('input', () => {
      seeking = true;
      if (audio.duration) time.textContent = `${fmt((+seek.value / 1000) * audio.duration)} / ${fmt(audio.duration)}`;
    });
    seek.addEventListener('change', () => {
      if (audio.duration) audio.currentTime = (+seek.value / 1000) * audio.duration;
      seeking = false;
    });
    const setVol = () => {
      audio.volume = +vol.value / 100;
      vol.style.setProperty('--p', `${vol.value}%`);
      volPct.textContent = `${vol.value}%`;
    };
    vol.addEventListener('input', setVol);
    setVol();

    /* ---------- visualizer: bars radiating from a glossy disc ("album art" fallback) ---------- */
    const g = canvas.getContext('2d')!;
    let raf = 0;
    let spin = 0;
    const levels = new Float32Array(48);
    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      const w = canvas.clientWidth;
      const hh = canvas.clientHeight;
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(hh * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(hh * dpr);
      }
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, hh);
      const playing = !audio.paused && !audio.ended;
      if (analyser && playing) analyser.getByteFrequencyData(data);
      else data.fill(0);
      for (let i = 0; i < levels.length; i++) {
        const v = playing && !analyser ? 0.35 + 0.25 * Math.sin(now / 180 + i) : data[Math.floor((i / levels.length) * 40)] / 255;
        levels[i] += (v - levels[i]) * 0.3;
      }
      const cx = w / 2;
      const cy = hh / 2 - 16;
      const r = Math.max(40, Math.min(w, hh) * 0.2);
      const glow = g.createRadialGradient(cx, cy, r * 0.5, cx, cy, r * 3.2);
      glow.addColorStop(0, 'rgba(60,140,255,0.35)');
      glow.addColorStop(1, 'rgba(60,140,255,0)');
      g.fillStyle = glow;
      g.fillRect(0, 0, w, hh);
      const n = levels.length;
      g.lineCap = 'round';
      for (let i = 0; i < n * 2; i++) {
        const lv = levels[i < n ? i : 2 * n - 1 - i];
        const a = (i / (n * 2)) * Math.PI * 2 - Math.PI / 2;
        const len = 4 + lv * r * 1.5;
        g.strokeStyle = `hsl(${28 + (i / (n * 2)) * 190} 95% ${55 + lv * 15}%)`;
        g.lineWidth = Math.max(2, (r * 6.28) / (n * 2) - 2);
        g.beginPath();
        g.moveTo(cx + Math.cos(a) * (r + 8), cy + Math.sin(a) * (r + 8));
        g.lineTo(cx + Math.cos(a) * (r + 8 + len), cy + Math.sin(a) * (r + 8 + len));
        g.stroke();
      }
      if (playing) spin += 0.004;
      // Disc: dark glossy vinyl-like cover with an orange centre label
      g.save();
      g.translate(cx, cy);
      const body = g.createRadialGradient(-r * 0.3, -r * 0.4, r * 0.1, 0, 0, r);
      body.addColorStop(0, '#46546a');
      body.addColorStop(0.6, '#1a212d');
      body.addColorStop(1, '#080b11');
      g.fillStyle = body;
      g.beginPath();
      g.arc(0, 0, r, 0, 7);
      g.fill();
      g.strokeStyle = 'rgba(255,255,255,0.07)';
      g.lineWidth = 1;
      for (let k = 0.45; k < 0.95; k += 0.11) {
        g.beginPath();
        g.arc(0, 0, r * k, 0, 7);
        g.stroke();
      }
      g.rotate(spin);
      const label = g.createLinearGradient(0, -r * 0.34, 0, r * 0.34);
      label.addColorStop(0, '#ffc86a');
      label.addColorStop(1, '#e0620f');
      g.fillStyle = label;
      g.beginPath();
      g.arc(0, 0, r * 0.34, 0, 7);
      g.fill();
      g.fillStyle = 'rgba(255,255,255,0.9)';
      g.beginPath();
      g.moveTo(-r * 0.1, -r * 0.16);
      g.lineTo(r * 0.2, 0);
      g.lineTo(-r * 0.1, r * 0.16);
      g.fill();
      g.restore();
      const shine = g.createLinearGradient(0, cy - r, 0, cy);
      shine.addColorStop(0, 'rgba(255,255,255,0.3)');
      shine.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = shine;
      g.beginPath();
      g.ellipse(cx, cy - r * 0.45, r * 0.8, r * 0.5, 0, Math.PI, 0);
      g.fill();
    };
    raf = requestAnimationFrame(draw);

    /* ---------- boot ---------- */
    void (async () => {
      await ensureSeeded(fs);
      tracks = await loadTracks(fs);
      const wanted = typeof args.path === 'string' ? args.path : null;
      if (wanted && !tracks.some((t) => t.path === wanted)) {
        const content = await fs.read(wanted);
        const url = content ? urlFromContent(content) : null;
        if (url) tracks.unshift({ path: wanted, url, title: wanted.split('/').pop()!.replace(AUDIO_EXT, ''), artist: 'Unknown artist' });
      }
      renderList();
      const at = wanted ? tracks.findIndex((t) => t.path === wanted) : -1;
      if (at >= 0) select(at, true);
    })();

    // Mini player in the dock's right-click menu (see OSApi.setJumpList).
    os.setJumpList('mediaplayer', () => [
      { label: index >= 0 ? `${tracks[index]?.title ?? ''}` : 'Nothing playing', disabled: true },
      { label: audio.paused ? 'Play' : 'Pause', action: toggle },
      { label: 'Previous', action: () => step(-1) },
      { label: 'Next', action: () => step(1) },
    ] as MenuItem[]);

    win.setMenus([
      { label: 'Play', items: [
        { label: 'Play / Pause', action: toggle },
        { label: 'Previous', action: () => step(-1) },
        { label: 'Next', action: () => step(1) },
      ] },
    ]);

    return () => {
      os.setJumpList('mediaplayer', null);
      cancelAnimationFrame(raf);
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
      void actx?.close();
    };
  },
};
