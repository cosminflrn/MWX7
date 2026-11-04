import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import { browserIcon } from './icon';
import './browser.css';

const START = 'mwx:start';
const HISTORY = 'mwx:history';
/** Hosts that send X-Frame-Options / frame-ancestors; Chrome gives no readable signal for them, so show the panel at once. */
const NO_FRAME = /(^|\.)(google|bing|youtube|facebook|instagram|twitter|x|linkedin|github|reddit|netflix|amazon|paypal|duckduckgo|yahoo|whatsapp|tiktok|pinterest|twitch|microsoft|apple)\.[a-z.]+$/i;
/** Session-only, shared by every Internet window. */
const favorites: { url: string; title: string }[] = [];
const visits: { url: string; title: string; at: number }[] = [];
const SEARCH = 'https://www.bing.com/search?q=';
const LOAD_TIMEOUT = 15000;

/** Sites verified (no X-Frame-Options / frame-ancestors) to render inside an iframe. */
const TILES: { name: string; url: string; blurb: string; hue: string }[] = [
  { name: 'Wikipedia', url: 'https://en.wikipedia.org/', blurb: 'The free encyclopedia', hue: '#5b6b82' },
  { name: 'OpenStreetMap', url: 'https://www.openstreetmap.org/export/embed.html?bbox=25.95%2C44.38%2C26.25%2C44.5&layer=mapnik', blurb: 'Map of Bucharest', hue: '#4aa35a' },
  { name: 'Internet Archive', url: 'https://archive.org/', blurb: 'Books, music, the web', hue: '#2f6fb8' },
  { name: 'Wikimedia Commons', url: 'https://commons.wikimedia.org/wiki/Main_Page', blurb: 'Free media files', hue: '#c1632c' },
  { name: 'Project Gutenberg', url: 'https://www.gutenberg.org/', blurb: 'Free ebooks', hue: '#8a5a9e' },
  { name: 'Example Domain', url: 'https://example.com/', blurb: 'A tiny test page', hue: '#6d7a8a' },
];

interface Tab {
  title: string;
  hist: string[];
  idx: number;
  pane: HTMLElement;
  frame: HTMLIFrameElement | null;
  timer: number;
  tabEl: HTMLElement;
  tabTitle: HTMLElement;
}

const hostOf = (u: string): string => {
  try {
    return new URL(u).hostname.replace(/^www\./, '');
  } catch {
    return u;
  }
};

/** Turns address-bar text into either a URL to show or a search query. */
function resolve(text: string): { url?: string; query?: string } {
  const t = text.trim();
  if (!t) return {};
  if (t === START || t === HISTORY) return { url: t };
  if (/^https?:\/\//i.test(t)) return { url: t };
  if (!/\s/.test(t) && /^[^\s/]+\.[a-z]{2,}(:\d+)?([/?#].*)?$/i.test(t)) return { url: `https://${t}` };
  return { query: t };
}

export const browser: AppManifest = {
  id: 'browser',
  name: 'Internet',
  icon: browserIcon,
  description: 'Browse the web',
  keywords: ['browser', 'web', 'internet', 'www', 'search', 'wikipedia'],
  pinned: true,
  desktop: true,
  window: { width: 1100, height: 720, minWidth: 520, minHeight: 360 },

  mount({ win, args }) {
    win.body.classList.add('br');
    const tabs: Tab[] = [];
    let cur: Tab | null = null;

    const back = h('button', { class: 'br-nav br-back', 'aria-label': 'Back', title: 'Back' }, h('span', { class: 'br-glyph' }));
    const fwd = h('button', { class: 'br-nav br-fwd', 'aria-label': 'Forward', title: 'Forward' }, h('span', { class: 'br-glyph' }));
    const reload = h('button', { class: 'br-tool', 'aria-label': 'Reload', title: 'Reload', html: '&#8635;' });
    const home = h('button', { class: 'br-tool', 'aria-label': 'Home', title: 'Home', html: '&#8962;' });
    const address = h('input', { class: 'br-address', type: 'text', spellcheck: false, 'aria-label': 'Address', placeholder: 'Search or type an address' });
    const star = h('button', { class: 'br-tool br-star', 'aria-label': 'Add to Favorites', title: 'Add to Favorites', html: '&#9734;' });
    const histBtn = h('button', { class: 'br-tool br-histbtn', 'aria-label': 'History', title: 'History', html: '&#128339;' });
    const favBar = h('div', { class: 'br-favbar', hidden: true });
    const go = h('button', { class: 'br-tool br-go', 'aria-label': 'Go', title: 'Go', html: '&#10140;' });
    const tabStrip = h('div', { class: 'br-tabs' });
    const newTabBtn = h('button', { class: 'br-newtab', 'aria-label': 'New tab', title: 'New tab' }, '+');
    const content = h('div', { class: 'br-content' });
    const statusText = h('span', { class: 'br-status-t' });
    const outside = h('a', {
      class: 'br-outside',
      href: '#',
      onclick: (e: Event) => {
        e.preventDefault();
        if (cur && !urlOf(cur).startsWith('mwx:')) openOutside(urlOf(cur));
      },
    }, 'Open in a new tab');
    const status = h('div', { class: 'br-status' }, statusText, outside);

    const toolbar = h('div', { class: 'br-toolbar' }, h('div', { class: 'br-navgroup' }, back, fwd), reload, home, h('div', { class: 'br-addrwrap' }, address, star, go), histBtn);
    win.body.append(h('div', { class: 'br-tabbar' }, tabStrip, newTabBtn), toolbar, favBar, content, status);

    const openOutside = (url: string) => window.open(url, '_blank', 'noopener,noreferrer');
    const search = (q: string) => openOutside(SEARCH + encodeURIComponent(q));
    const urlOf = (t: Tab) => t.hist[t.idx];

    const buildStart = (): HTMLElement => {
      const box = h('input', { class: 'br-sbox', type: 'text', spellcheck: false, 'aria-label': 'Search the web', placeholder: 'Search the web' });
      const submit = () => box.value.trim() && search(box.value.trim());
      box.addEventListener('keydown', (e) => e.key === 'Enter' && submit());
      const tiles = h('div', { class: 'br-tiles' });
      for (const t of TILES) {
        tiles.append(
          h(
            'button',
            { class: 'br-tile', onclick: () => navigate(t.url) },
            h('span', { class: 'br-tile-ico', style: `--hue:${t.hue}` }, t.name[0]),
            h('span', { class: 'br-tile-name' }, t.name),
            h('small', {}, t.blurb),
          ),
        );
      }
      return h(
        'div',
        { class: 'br-start' },
        h('div', { class: 'br-start-in' },
          h('div', { class: 'br-logo' }, h('span', { html: browserIcon }), h('span', { class: 'br-logo-t' }, 'Internet')),
          h('div', { class: 'br-search' }, box, h('button', { class: 'br-sbtn', onclick: submit }, 'Search')),
          h('div', { class: 'br-hint' }, 'Searches open in a new browser tab. Sites below can be shown right here.'),
          tiles,
        ),
      );
    };

    const favicon = (url: string, cls: string): HTMLElement => {
      const wrap = h('span', { class: cls }, hostOf(url)[0]?.toUpperCase() ?? '?');
      const img = new Image();
      img.referrerPolicy = 'no-referrer';
      img.alt = '';
      img.onload = () => wrap.replaceChildren(img);
      try {
        img.src = new URL('/favicon.ico', url).href;
      } catch {
        /* keep the letter */
      }
      return wrap;
    };

    const showBlocked = (t: Tab, url: string) => {
      clearTimeout(t.timer);
      t.pane.querySelector('.br-blocked')?.remove();
      t.pane.querySelector('iframe')?.remove();
      t.pane.append(
        h(
          'div',
          { class: 'br-blocked' },
          h('div', { class: 'br-blocked-card' },
            favicon(url, 'br-blocked-fav'),
            h('div', { class: 'br-blocked-site' }, hostOf(url)),
            h('h2', {}, "This page can't be shown here"),
            h('p', {}, `${hostOf(url)} doesn't allow itself to be displayed inside another window. It will work fine in its own browser tab.`),
            h('button', { class: 'br-primary br-big', onclick: () => openOutside(url) }, 'Open in a new tab'),
            h('div', { class: 'br-blocked-url' }, url),
          ),
        ),
      );
      setStatus('Blocked from displaying here');
    };

    const buildHistory = (): HTMLElement => {
      const rows = h('div', { class: 'br-hist-list' });
      if (!visits.length) rows.append(h('div', { class: 'br-hist-empty' }, 'No pages visited yet in this session.'));
      for (const v of [...visits].reverse())
        rows.append(
          h('button', { class: 'br-hist-row', onclick: () => navigate(v.url) },
            favicon(v.url, 'br-hist-fav'),
            h('span', { class: 'br-hist-t' }, v.title),
            h('span', { class: 'br-hist-u' }, v.url),
            h('span', { class: 'br-hist-at' }, new Date(v.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))),
        );
      return h('div', { class: 'br-hist' }, h('div', { class: 'br-hist-in' }, h('h2', {}, 'History'), h('p', {}, 'Pages you opened since MWX 7 started.'), rows));
    };

    const renderFavBar = () => {
      favBar.hidden = !favorites.length;
      favBar.replaceChildren(
        ...favorites.map((f) =>
          h('button', { class: 'br-fav', title: f.url, onclick: () => navigate(f.url) }, favicon(f.url, 'br-fav-ico'), h('span', {}, f.title)),
        ),
      );
      if (cur) sync();
    };

    const toggleFavorite = () => {
      if (!cur) return;
      const url = urlOf(cur);
      if (url === START || url === HISTORY) return;
      const at = favorites.findIndex((f) => f.url === url);
      if (at >= 0) favorites.splice(at, 1);
      else favorites.push({ url, title: cur.title });
      renderFavBar();
    };

    const setStatus = (s: string) => {
      statusText.textContent = s;
    };

    const render = (t: Tab) => {
      const url = urlOf(t);
      t.pane.replaceChildren();
      clearTimeout(t.timer);
      t.frame = null;
      if (url === START || url === HISTORY) {
        t.title = url === START ? 'Start page' : 'History';
        t.pane.append(url === START ? buildStart() : buildHistory());
        setStatus('Done');
      } else if (NO_FRAME.test(hostOf(url))) {
        t.title = hostOf(url);
        visits.push({ url, title: t.title, at: Date.now() });
        showBlocked(t, url);
      } else {
        visits.push({ url, title: hostOf(url), at: Date.now() });
        const frame = h('iframe', {
          class: 'br-frame',
          title: hostOf(url),
          // Sandboxed so framed pages can't navigate the OS itself; popups allowed for links that open elsewhere.
          sandbox: 'allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox',
          referrerpolicy: 'no-referrer',
        });
        t.frame = frame;
        t.title = hostOf(url);
        setStatus(`Opening ${hostOf(url)}…`);
        // A blocked frame still fires `load`; Firefox leaves it at about:blank, which we can read. Chrome's error
        // page is cross-origin (throws) so we can't tell, which is why the status bar keeps an "open outside" link.
        frame.addEventListener('load', () => {
          clearTimeout(t.timer);
          try {
            if (frame.contentWindow?.location.href === 'about:blank') return showBlocked(t, url);
          } catch {
            /* cross-origin: loaded something */
          }
          setStatus('Done');
        });
        t.timer = window.setTimeout(() => showBlocked(t, url), LOAD_TIMEOUT);
        frame.src = url;
        t.pane.append(frame);
      }
      sync();
    };

    const navigate = (url: string, t: Tab | null = cur) => {
      if (!t) return;
      t.hist = t.hist.slice(0, t.idx + 1);
      t.hist.push(url);
      t.idx = t.hist.length - 1;
      render(t);
    };

    const sync = () => {
      if (!cur) return;
      const url = urlOf(cur);
      address.value = url === START || url === HISTORY ? '' : url;
      const faved = favorites.some((f) => f.url === url);
      star.innerHTML = faved ? '&#9733;' : '&#9734;';
      star.classList.toggle('on', faved);
      star.title = star.ariaLabel = faved ? 'Remove from Favorites' : 'Add to Favorites';
      star.disabled = url === START || url === HISTORY;
      back.disabled = cur.idx <= 0;
      fwd.disabled = cur.idx >= cur.hist.length - 1;
      cur.tabTitle.textContent = cur.title;
      win.setTitle(`${cur.title} — Internet`);
    };

    const select = (t: Tab) => {
      cur = t;
      for (const x of tabs) {
        x.tabEl.classList.toggle('on', x === t);
        x.pane.hidden = x !== t;
      }
      sync();
    };

    const addTab = (url = START) => {
      const tabTitle = h('span', { class: 'br-tab-t' }, 'New tab');
      const closeBtn = h('button', { class: 'br-tab-x', 'aria-label': 'Close tab', title: 'Close tab' }, '×');
      const tabEl = h('div', { class: 'br-tab' }, tabTitle, closeBtn);
      const pane = h('div', { class: 'br-pane' });
      const t: Tab = { title: 'New tab', hist: [url], idx: 0, pane, frame: null, timer: 0, tabEl, tabTitle };
      tabEl.addEventListener('mousedown', (e) => {
        if (e.target !== closeBtn) select(t);
      });
      closeBtn.addEventListener('click', () => closeTab(t));
      tabs.push(t);
      tabStrip.append(tabEl);
      content.append(pane);
      select(t);
      render(t);
    };

    const closeTab = (t: Tab) => {
      if (tabs.length === 1) return win.close();
      const i = tabs.indexOf(t);
      clearTimeout(t.timer);
      tabs.splice(i, 1);
      t.tabEl.remove();
      t.pane.remove();
      if (cur === t) select(tabs[Math.min(i, tabs.length - 1)]);
    };

    const step = (d: number) => {
      if (!cur) return;
      const n = cur.idx + d;
      if (n < 0 || n >= cur.hist.length) return;
      cur.idx = n;
      render(cur);
    };

    const submitAddress = () => {
      const r = resolve(address.value);
      if (r.query) search(r.query);
      else if (r.url) navigate(r.url);
    };

    back.addEventListener('click', () => step(-1));
    fwd.addEventListener('click', () => step(1));
    reload.addEventListener('click', () => cur && render(cur));
    home.addEventListener('click', () => cur && urlOf(cur) !== START && navigate(START));
    go.addEventListener('click', submitAddress);
    star.addEventListener('click', toggleFavorite);
    histBtn.addEventListener('click', () => cur && urlOf(cur) !== HISTORY && navigate(HISTORY));
    address.addEventListener('keydown', (e) => e.key === 'Enter' && submitAddress());
    address.addEventListener('focus', () => address.select());
    newTabBtn.addEventListener('click', () => addTab());
    win.setMenus([
      { label: 'File', items: [
        { label: 'New Tab', action: () => addTab() },
        { label: 'Close Tab', action: () => cur && closeTab(cur) },
        { separator: true },
        { label: 'Open Page in New Browser Tab', action: () => cur && !urlOf(cur).startsWith('mwx:') && openOutside(urlOf(cur)) },
      ] },
      { label: 'Go', items: [
        { label: 'Back', action: () => step(-1) },
        { label: 'Forward', action: () => step(1) },
        { label: 'Reload', action: () => cur && render(cur) },
        { label: 'History', action: () => cur && urlOf(cur) !== HISTORY && navigate(HISTORY) },
        { label: 'Start Page', action: () => cur && urlOf(cur) !== START && navigate(START) },
      ] },
    ]);

    renderFavBar();
    addTab(typeof args.url === 'string' && args.url ? args.url : START);

    return () => tabs.forEach((t) => clearTimeout(t.timer));
  },
};
