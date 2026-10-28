import { icons } from '../assets/icons';
import { bus } from '../core/events';
import { fs } from '../core/fs';
import { launch } from '../core/os';
import { listApps } from '../core/registry';
import { h } from '../ui/dom';

interface Result {
  kind: 'Applications' | 'Documents';
  title: string;
  subtitle: string;
  icon: string;
  run: () => void;
}

/** macOS Spotlight (Ctrl+Space) searching apps and documents. */
export function mountSpotlight(): void {
  let overlay: HTMLElement | null = null;

  const close = () => {
    overlay?.remove();
    overlay = null;
  };

  /** 4 = name starts with q, 3 = a word in the name starts with q, 2 = text contains q, 1 = fuzzy name match */
  const score = (q: string, name: string, ...rest: string[]) => {
    if (!q) return 1;
    const n = name.toLowerCase();
    if (n.startsWith(q)) return 4;
    if (n.split(/[\s._-]+/).some((w) => w.startsWith(q))) return 3;
    if ([n, ...rest].join(' ').toLowerCase().includes(q)) return 2;
    // loose subsequence on the name only ("ntp" → notepad)
    let i = 0;
    for (const c of n) if (c === q[i]) i++;
    return i === q.length ? 1 : 0;
  };

  const search = async (raw: string): Promise<Result[]> => {
    const q = raw.trim().toLowerCase();
    if (!q) return [];
    const apps = listApps().map((a) => ({
      s: score(q, a.name, a.description ?? '', ...(a.keywords ?? [])),
      r: { kind: 'Applications', title: a.name, subtitle: a.description ?? '', icon: a.icon, run: () => launch(a.id) } as Result,
    }));
    const files = (await fs.all()).map((f) => ({
      s: score(q, f.name, f.content.slice(0, 2000)),
      r: { kind: 'Documents', title: f.name, subtitle: f.path, icon: icons.file, run: () => launch('notepad', { path: f.path }) } as Result,
    }));
    const hits = [...apps, ...files.sort((a, b) => b.s - a.s).slice(0, 6)].filter((x) => x.s > 0);
    // The best hit's group comes first (like Spotlight's "Top Hit"), groups stay together.
    const best = hits.reduce((m, x) => (x.s > m.s ? x : m), hits[0]);
    const order = best?.r.kind === 'Documents' ? ['Documents', 'Applications'] : ['Applications', 'Documents'];
    return order.flatMap((k) => hits.filter((x) => x.r.kind === k).sort((a, b) => b.s - a.s).map((x) => x.r));
  };

  const open = () => {
    if (overlay) {
      overlay.querySelector('input')?.focus();
      return;
    }
    const input = h('input', { class: 'sp-input', type: 'text', placeholder: 'Spotlight Search', spellcheck: false, autocomplete: 'off' });
    const list = h('div', { class: 'sp-results' });
    const box = h('div', { class: 'sp-box' }, h('div', { class: 'sp-bar' }, h('span', { class: 'sp-glass', html: icons.search }), input), list);
    overlay = h('div', { class: 'sp-overlay', onpointerdown: (e: PointerEvent) => e.target === overlay && close() }, box);
    document.body.append(overlay);
    input.focus();

    let results: Result[] = [];
    let sel = 0;
    let token = 0;

    const draw = () => {
      list.replaceChildren();
      let lastKind = '';
      results.forEach((r, i) => {
        if (r.kind !== lastKind) {
          list.append(h('div', { class: 'sp-group' }, r.kind));
          lastKind = r.kind;
        }
        list.append(
          h(
            'button',
            {
              class: `sp-row${i === sel ? ' sel' : ''}`,
              onpointermove: () => {
                if (sel !== i) {
                  sel = i;
                  draw();
                }
              },
              onclick: () => {
                close();
                r.run();
              },
            },
            h('span', { class: 'sp-row-icon', html: r.icon }),
            h('span', { class: 'sp-row-title' }, r.title),
            h('span', { class: 'sp-row-sub' }, r.subtitle),
          ),
        );
      });
      if (!results.length && input.value.trim()) list.append(h('div', { class: 'sp-empty' }, 'No results'));
      box.classList.toggle('has-results', list.childElementCount > 0);
    };

    const update = async () => {
      const t = ++token;
      const r = await search(input.value);
      if (t !== token) return;
      results = input.value.trim() ? r : [];
      sel = 0;
      draw();
    };

    input.addEventListener('input', update);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') close();
      else if (e.key === 'ArrowDown') {
        e.preventDefault();
        sel = Math.min(sel + 1, results.length - 1);
        draw();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        sel = Math.max(sel - 1, 0);
        draw();
      } else if (e.key === 'Enter' && results[sel]) {
        // Without this the Enter "lands" in whatever the launched app focuses.
        e.preventDefault();
        const r = results[sel];
        close();
        r.run();
      }
    });
  };

  bus.on('spotlight:open', open);
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.code === 'Space') {
      e.preventDefault();
      if (overlay) close();
      else open();
    }
  });
}
