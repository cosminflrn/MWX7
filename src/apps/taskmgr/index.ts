import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import './taskmgr.css';

const STEP = 5; // CSS px between 1 Hz samples
const GRID = 16;
const SYSTEM_PROCESSES = 5; // shell, window manager, filesystem, sound, search

interface Graph {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  data: number[];
  w: number;
  h: number;
  dpr: number;
}

const fmtUp = (ms: number): string => {
  const s = Math.floor(ms / 1000);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${Math.floor(s / 86400)}:${p(Math.floor((s % 86400) / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
};

export const impl: Pick<AppManifest, 'mount'> = {
  mount({ win, os }) {
    win.body.classList.add('tm');
    win.setTitle('Task Manager');

    let tab: 'apps' | 'perf' = 'perf';
    let selected: string | null = null;
    let sig = '';
    let cpu = 0;
    let memPct = 0;
    let memMB = 0;
    let lastSample = performance.now();
    let sampleCount = 0;

    /* ---------- Applications ---------- */
    const list = h('div', { class: 'tm-list', role: 'listbox', 'aria-label': 'Open windows' });
    const endBtn = h('button', { class: 'btn', onclick: () => {
      if (!selected) return;
      os.closeWindow(selected, true);
      selected = null;
      setTimeout(refreshList, 260);
      refreshList();
    } }, 'End Task');
    const switchBtn = h('button', { class: 'btn', onclick: () => selected && os.focusWindow(selected) }, 'Switch To');
    const appsPage = h('div', { class: 'tm-page' }, list, h('div', { class: 'tm-actions' }, switchBtn, endBtn));

    const iconFor = (appId: string): string => os.apps().find((a) => a.id === appId)?.icon ?? '';
    const refreshList = () => {
      const wins = os.windows().reverse();
      const next = wins.map((w) => `${w.id}|${w.title}|${w.minimized}`).join('\n') + `#${selected}`;
      endBtn.disabled = switchBtn.disabled = !selected || !wins.some((w) => w.id === selected);
      if (next === sig) return;
      sig = next;
      if (selected && !wins.some((w) => w.id === selected)) selected = null;
      list.replaceChildren(
        h('div', { class: 'tm-head' }, h('span', {}, 'Task'), h('span', {}, 'Status')),
        ...wins.map((w) =>
          h('button', { class: `tm-row${w.id === selected ? ' sel' : ''}`, role: 'option', 'aria-selected': w.id === selected,
            onclick: () => {
              selected = w.id;
              refreshList();
            },
            ondblclick: () => os.focusWindow(w.id) },
          h('span', {}, h('span', { class: 'tm-ic', html: iconFor(w.appId) }), h('span', { class: 'tm-t' }, w.title)),
          h('span', {}, w.minimized ? 'Minimized' : 'Running')),
        ),
      );
      endBtn.disabled = switchBtn.disabled = !selected;
      statProcs.textContent = String(wins.length + SYSTEM_PROCESSES);
      stProcs.textContent = `Processes: ${wins.length + SYSTEM_PROCESSES}`;
    };

    /* ---------- Performance ---------- */
    const mkGraph = (): Graph => {
      const canvas = h('canvas', {});
      return { canvas, ctx: canvas.getContext('2d')!, data: [], w: 0, h: 0, dpr: 1 };
    };
    const cpuG = mkGraph();
    const memG = mkGraph();
    const cpuBig = h('div', { class: 'tm-big' }, '0%');
    const memBig = h('div', { class: 'tm-big' }, '0 MB');
    const card = (label: string, big: HTMLElement, g: Graph) =>
      h('div', { class: 'tm-card' }, h('div', { class: 'tm-gauge' }, h('div', { class: 'tm-lbl' }, label), big),
        h('div', { class: 'tm-graph' }, g.canvas));
    const statUp = h('b', {}, '0:00:00:00');
    const statProcs = h('b', {}, '0');
    const statWins = h('b', {}, '0');
    const statHeap = h('b', {}, '—');
    const stat = (label: string, el: HTMLElement) => h('div', {}, h('small', {}, label), el);
    const perfPage = h('div', { class: 'tm-page tm-perf on' },
      card('CPU Usage', cpuBig, cpuG), card('Memory', memBig, memG),
      h('div', { class: 'tm-stats' }, stat('Up Time', statUp), stat('Processes', statProcs), stat('Open windows', statWins), stat('JS heap', statHeap)));

    const stProcs = h('span', {}, 'Processes: 0');
    const stCpu = h('span', {}, 'CPU Usage: 0%');
    const stMem = h('span', {}, 'Physical Memory: 0%');

    const tabBtn = (id: 'apps' | 'perf', label: string) => h('button', { class: `tm-tab${id === tab ? ' on' : ''}`, role: 'tab', 'data-tab': id, onclick: () => setTab(id) }, label);
    const tabs = h('div', { class: 'tm-tabs', role: 'tablist' }, tabBtn('perf', 'Performance'), tabBtn('apps', 'Applications'));
    win.body.append(tabs, appsPage, perfPage, h('div', { class: 'tm-status' }, stProcs, stCpu, stMem));

    const setTab = (t: 'apps' | 'perf') => {
      tab = t;
      tabs.querySelectorAll<HTMLElement>('.tm-tab').forEach((b) => b.classList.toggle('on', b.dataset.tab === t));
      appsPage.classList.toggle('on', t === 'apps');
      perfPage.classList.toggle('on', t === 'perf');
      if (t === 'perf') {
        resize(cpuG);
        resize(memG);
        startDraw();
      }
    };

    /** Keep the backing store at device resolution so lines stay crisp. */
    const resize = (g: Graph) => {
      const dpr = window.devicePixelRatio || 1;
      const w = g.canvas.clientWidth;
      const hh = g.canvas.clientHeight;
      if (!w || !hh) return;
      g.dpr = dpr;
      g.w = w;
      g.h = hh;
      g.canvas.width = Math.round(w * dpr);
      g.canvas.height = Math.round(hh * dpr);
    };
    const ro = new ResizeObserver(() => {
      resize(cpuG);
      resize(memG);
    });
    // Observe the containers: the absolutely-positioned canvases only change size through them.
    for (const g of [cpuG, memG]) {
      ro.observe(g.canvas);
      if (g.canvas.parentElement) ro.observe(g.canvas.parentElement);
    }
    ro.observe(win.body);

    // CPU estimate: long tasks reported by the browser plus timer lateness, i.e. how busy the main thread was.
    let busyMs = 0;
    let po: PerformanceObserver | null = null;
    try {
      po = new PerformanceObserver((l) => l.getEntries().forEach((e) => (busyMs += e.duration)));
      po.observe({ entryTypes: ['longtask'] });
    } catch {
      po = null;
    }
    let lagExpect = performance.now() + 50;
    const lagTimer = window.setInterval(() => {
      const now = performance.now();
      busyMs += Math.max(0, now - lagExpect);
      lagExpect = now + 50;
    }, 50);
    const lagTick = window.setInterval(() => (lagExpect = performance.now() + 50), 10_000);

    const born = performance.now();
    const sample = () => {
      const now = performance.now();
      const dt = Math.max(1, now - lastSample);
      lastSample = now;
      const nWins = os.windows().length;
      const base = 1.5 + nWins * 0.35 + Math.random() * 1.6;
      const target = Math.min(100, base + (busyMs / dt) * 100);
      busyMs = 0;
      cpu = Math.round(cpu * 0.35 + target * 0.65);

      const perf = performance as Performance & { memory?: { usedJSHeapSize: number } };
      const total = ((navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 8) * 1024;
      let heap = 0;
      if (perf.memory) {
        heap = perf.memory.usedJSHeapSize / 1048576;
        memMB = 900 + heap * 1.4 + nWins * 20;
      } else {
        memMB = 1000 + nWins * 42 + 25 * Math.sin(now / 9000) + Math.random() * 6;
      }
      memMB = Math.min(total * 0.95, memMB);
      memPct = Math.round((memMB / total) * 100);

      for (const [g, v] of [[cpuG, cpu], [memG, memPct]] as Array<[Graph, number]>) {
        g.data.push(v);
        if (g.data.length > 400) g.data.shift();
      }
      sampleCount++;
      cpuBig.innerHTML = `${cpu}%`;
      memBig.innerHTML = `${(memMB / 1024).toFixed(2)} GB<small>${memPct}% used</small>`;
      stCpu.textContent = `CPU Usage: ${cpu}%`;
      stMem.textContent = `Physical Memory: ${memPct}%`;
      statUp.textContent = fmtUp(now - born);
      statWins.textContent = String(nWins);
      statHeap.textContent = perf.memory ? `${heap.toFixed(0)} MB` : 'n/a';
      refreshList();
    };

    const draw = (g: Graph, frac: number, color: string) => {
      // Cheap self-heal: a maximize/restore can change the box without the observer having fired yet (or after the tab was hidden).
      if (g.canvas.clientWidth !== g.w || g.canvas.clientHeight !== g.h || (window.devicePixelRatio || 1) !== g.dpr) resize(g);
      const { ctx, w, h: hh, dpr } = g;
      if (!w || !hh) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, w, hh);
      // 1 device pixel grid lines, scrolling with the data
      const snap = (v: number) => Math.round(v * dpr) / dpr + 0.5 / dpr;
      ctx.strokeStyle = '#0f5a1f';
      ctx.lineWidth = 1 / dpr;
      ctx.beginPath();
      const off = ((sampleCount + frac) * STEP) % GRID;
      for (let x = w - off; x > -GRID; x -= GRID) {
        ctx.moveTo(snap(x), 0);
        ctx.lineTo(snap(x), hh);
      }
      for (let y = hh - 0.5; y > 0; y -= GRID) {
        const yy = snap(y);
        ctx.moveTo(0, yy);
        ctx.lineTo(w, yy);
      }
      ctx.stroke();
      const d = g.data;
      if (!d.length) return;
      const n = d.length;
      const pt = (j: number): [number, number] => [w + STEP * (1 - frac) - STEP * (n - 1 - j), hh - 1 - (d[j] / 100) * (hh - 2)];
      const from = Math.max(0, n - Math.ceil(w / STEP) - 3);
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, w, hh);
      ctx.clip();
      ctx.beginPath();
      let first = true;
      for (let j = from; j < n; j++) {
        const [x, y] = pt(j);
        if (first) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        first = false;
      }
      const [lx] = pt(n - 1);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.lineJoin = 'round';
      ctx.stroke();
      ctx.lineTo(lx, hh);
      ctx.lineTo(pt(from)[0], hh);
      ctx.fillStyle = 'rgba(61, 255, 98, 0.16)';
      ctx.fill();
      ctx.restore();
    };

    // The scrolling is driven by rAF only while the Performance tab is visible; hidden pages stop it for free.
    let raf = 0;
    const frame = () => {
      raf = 0;
      if (tab !== 'perf') return;
      const frac = Math.min(1, (performance.now() - lastSample) / 1000);
      draw(cpuG, frac, '#3dff62');
      draw(memG, frac, '#3dff62');
      raf = requestAnimationFrame(frame);
    };
    const startDraw = () => {
      if (!raf) raf = requestAnimationFrame(frame);
    };

    sample();
    setTab('perf');
    const timer = window.setInterval(sample, 1000);

    return () => {
      clearInterval(timer);
      clearInterval(lagTimer);
      clearInterval(lagTick);
      cancelAnimationFrame(raf);
      po?.disconnect();
      ro.disconnect();
    };
  },
};
