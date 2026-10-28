import { basename } from '../../core/fs';
import type { AppManifest, MenuDef } from '../../core/types';
import { h } from '../../ui/dom';
import { dialog, pickPicture } from './dialogs';
import {
  airPuff,
  brushDot,
  brushSegment,
  constrainPoint,
  drawShape,
  eraseLine,
  eraserSide,
  floodFill,
  invertColors,
  makeCanvas,
  pencilLine,
  scaled,
  SHAPES,
  SIZES,
  toHex,
  transformed,
  type BrushKind,
  type ShapeKind,
  type ShapeStyle,
  type Transform,
} from './draw';
import { PICS, SAVE_RE, loadImage } from './files';
import { glyph } from './glyphs';
import { paintIcon } from './icon';
import { closePopup, col, group, openPopup, popMenu, rbtn, row, splitBig, type PopItem } from './ribbon';
import './paint.css';

type ToolId = 'pencil' | 'brush' | 'eraser' | 'fill' | 'picker' | 'text' | 'shape' | 'select' | 'magnifier';
type TabId = 'home' | 'view' | 'text';

const DEFAULT_W = 800;
const DEFAULT_H = 560;
const MAX_DIM = 5000;
const HISTORY_STEPS = 30;
const HISTORY_BYTES = 240 * 1024 * 1024;
const ZOOMS = [1, 2, 4];

const PALETTE = [
  '#000000', '#7f7f7f', '#880015', '#ed1c24', '#ff7f27', '#fff200', '#22b14c', '#00a2e8', '#3f48cc', '#a349a4',
  '#ffffff', '#c3c3c3', '#b97a57', '#ffaec9', '#ffc90e', '#efe4b0', '#b5e61d', '#99d9ea', '#7092be', '#c8bfe7',
  '#404040', '#e3e3e3', '#5a3825', '#f4a6b8', '#ffd24d', '#2e7d32', '#00bfa5', '#7e57c2',
];

const BRUSHES: { kind: BrushKind; label: string }[] = [
  { kind: 'round', label: 'Brush' },
  { kind: 'cal1', label: 'Calligraphy brush 1' },
  { kind: 'cal2', label: 'Calligraphy brush 2' },
  { kind: 'air', label: 'Airbrush' },
  { kind: 'oil', label: 'Oil brush' },
  { kind: 'crayon', label: 'Crayon' },
];

const SHAPE_NAMES: Record<ShapeKind, string> = {
  line: 'Line',
  ellipse: 'Oval',
  rect: 'Rectangle',
  round: 'Rounded rectangle',
  triangle: 'Isosceles triangle',
  rtriangle: 'Right triangle',
  diamond: 'Diamond',
  pentagon: 'Pentagon',
  hexagon: 'Hexagon',
  star: 'Five-point star',
  arrow: 'Right arrow',
  heart: 'Heart',
};

const FONTS: Record<string, string> = {
  'Segoe UI': "'Segoe UI', 'Selawik', sans-serif",
  Arial: 'Arial, Helvetica, sans-serif',
  Verdana: 'Verdana, Geneva, sans-serif',
  'Trebuchet MS': "'Trebuchet MS', sans-serif",
  Georgia: 'Georgia, serif',
  'Times New Roman': "'Times New Roman', Times, serif",
  'Courier New': "'Courier New', monospace",
};
const FONT_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36, 48, 72];

interface Snap {
  w: number;
  h: number;
  data: ImageData;
}

interface Sel {
  x: number;
  y: number;
  w: number;
  h: number;
  /** Lifted pixels. null while the rectangle is only a marquee over untouched canvas. */
  src: HTMLCanvasElement | null;
}

type Drag =
  | { t: 'free'; tool: 'pencil' | 'brush' | 'eraser'; col: string; lx: number; ly: number; timer?: number }
  | { t: 'shape'; sx: number; sy: number; ex: number; ey: number; fg: string; bg: string }
  | { t: 'marquee'; sx: number; sy: number }
  | { t: 'move'; px: number; py: number; ox: number; oy: number; copy: boolean }
  | { t: 'scale'; dir: string; px: number; py: number; o: { x: number; y: number; w: number; h: number } }
  | { t: 'grow'; dx: boolean; dy: boolean };

export const paint: AppManifest = {
  id: 'paint',
  name: 'Paint',
  icon: paintIcon,
  description: 'Draw, paint and edit pictures',
  keywords: ['draw', 'image', 'picture', 'bitmap', 'brush', 'png', 'canvas', 'edit'],
  pinned: false,
  desktop: false,
  window: { width: 1120, height: 700, minWidth: 420, minHeight: 360 },

  mount({ win, args, fs, os }) {
    /* ============================== state ============================== */
    let tool: ToolId = 'pencil';
    let prevTool: ToolId = 'pencil';
    let brush: BrushKind = 'round';
    let shape: ShapeKind = 'line';
    let size = 1;
    let outline: 'solid' | 'none' = 'solid';
    let fillMode: 'none' | 'solid' = 'none';
    let color1 = '#000000';
    let color2 = '#ffffff';
    let slot: 1 | 2 = 1;
    let custom: string[] = [];
    let zoom = 1;
    let tolerance = 15; // percent of the 0-255 channel range
    let showGrid = false;
    let showStatus = true;
    let path: string | null = null;
    let dirty = false;
    let drag: Drag | null = null;
    let sel: Sel | null = null;
    let clip: HTMLCanvasElement | null = null;
    let tab: TabId = 'home';
    let hist: Snap[] = [];
    let hi = -1;
    let forceClose = false;
    const font = { family: 'Segoe UI', pt: 12, bold: false, italic: false, underline: false, opaque: false };
    let textBox: { el: HTMLTextAreaElement; x: number; y: number } | null = null;

    /* ============================== canvas ============================== */
    const main = h('canvas', { class: 'pt-main', width: DEFAULT_W, height: DEFAULT_H });
    const ctx = main.getContext('2d', { willReadFrequently: true })!;
    const over = h('canvas', { class: 'pt-over', width: DEFAULT_W, height: DEFAULT_H });
    const octx = over.getContext('2d')!;
    const grid = h('div', { class: 'pt-grid' });
    const selBox = h('div', { class: 'pt-selbox', hidden: true });
    for (const d of ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']) selBox.append(h('i', { class: `pt-sh pt-sh-${d}`, 'data-dir': d }));
    const growPrev = h('div', { class: 'pt-growprev', hidden: true });
    const gripE = h('i', { class: 'pt-grip pt-grip-e', 'data-grow': 'e' });
    const gripS = h('i', { class: 'pt-grip pt-grip-s', 'data-grow': 's' });
    const gripSE = h('i', { class: 'pt-grip pt-grip-se', 'data-grow': 'se', title: 'Resize the canvas' });
    const sheet = h('div', { class: 'pt-sheet', 'data-tool': tool }, main, over, grid, selBox, growPrev, gripE, gripS, gripSE);
    const work = h('div', { class: 'pt-work' }, h('div', { class: 'pt-sheet-wrap' }, sheet));

    const fillWhite = () => {
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, main.width, main.height);
    };
    fillWhite();

    /* ============================== chrome refs ============================== */
    const posText = h('span', {}, '');
    const selText = h('span', {}, '');
    const sizeText = h('span', {}, '');
    const zoomText = h('span', { class: 'pt-zoom-pct' }, '100%');
    const zoomRange = h('input', { class: 'pt-zoom-range', type: 'range', min: 0, max: ZOOMS.length - 1, step: 1, value: 0, 'aria-label': 'Zoom' });
    const status = h(
      'div',
      { class: 'pt-status' },
      h('span', { class: 'pt-st-cell pt-st-pos' }, glyph('cursor'), posText),
      h('span', { class: 'pt-st-cell pt-st-sel' }, glyph('selsize'), selText),
      h('span', { class: 'pt-st-cell pt-st-size' }, glyph('canvassize'), sizeText),
      h('span', { class: 'pt-st-fill' }),
      h('span', { class: 'pt-st-tol' }, 'Tolerance', h('input', { class: 'pt-tol-range', type: 'range', min: 0, max: 60, step: 1, value: tolerance, 'aria-label': 'Fill tolerance' }), h('b', {}, `${tolerance}%`)),
      h(
        'span',
        { class: 'pt-st-zoom' },
        zoomText,
        h('button', { class: 'pt-zbtn', type: 'button', 'aria-label': 'Zoom out', onclick: () => stepZoom(-1) }, '−'),
        zoomRange,
        h('button', { class: 'pt-zbtn', type: 'button', 'aria-label': 'Zoom in', onclick: () => stepZoom(1) }, '+'),
      ),
    );
    const tolBox = status.querySelector<HTMLElement>('.pt-st-tol')!;
    const tolRange = tolBox.querySelector<HTMLInputElement>('input')!;
    const tolLabel = tolBox.querySelector<HTMLElement>('b')!;

    /* ============================== history ============================== */
    const snapshot = (): Snap => ({ w: main.width, h: main.height, data: ctx.getImageData(0, 0, main.width, main.height) });

    function sizeCanvas(w: number, hgt: number): void {
      main.width = over.width = w;
      main.height = over.height = hgt;
      applyZoom();
    }

    function resetHistory(): void {
      hist = [snapshot()];
      hi = 0;
      refresh();
    }

    function pushHist(): void {
      hist.length = hi + 1;
      hist.push(snapshot());
      // bounded by step count AND memory: a huge canvas keeps fewer undo levels instead of exhausting the tab
      let bytes = hist.reduce((n, s) => n + s.data.data.length, 0);
      while (hist.length > 2 && (hist.length > HISTORY_STEPS + 1 || bytes > HISTORY_BYTES)) bytes -= hist.shift()!.data.data.length;
      hi = hist.length - 1;
      setDirty(true);
      refresh();
    }

    function restore(i: number): void {
      const s = hist[i]!;
      if (main.width !== s.w || main.height !== s.h) sizeCanvas(s.w, s.h);
      ctx.putImageData(s.data, 0, 0);
    }

    function undo(): void {
      closePopup();
      if (textBox) cancelText();
      if (sel?.src) {
        // an unplaced selection hasn't entered the history: undoing just takes it back
        dropSel();
        restore(hi);
        refresh();
        return;
      }
      dropSel();
      if (hi > 0) {
        restore(--hi);
        setDirty(true);
      }
      refresh();
    }

    function redo(): void {
      closePopup();
      if (textBox) cancelText();
      dropSel();
      if (hi < hist.length - 1) {
        restore(++hi);
        setDirty(true);
      }
      refresh();
    }

    function setDirty(d: boolean): void {
      dirty = d;
      win.setTitle(`${dirty ? '• ' : ''}${path ? basename(path) : 'Untitled'} - Paint`);
    }

    /* ============================== zoom / geometry ============================== */
    function applyZoom(): void {
      const w = main.width * zoom;
      const hh = main.height * zoom;
      for (const el of [sheet, main, over, grid]) {
        el.style.width = `${w}px`;
        el.style.height = `${hh}px`;
      }
      sheet.dataset.zoom = String(zoom);
      const g = zoom >= 4 && showGrid;
      grid.hidden = !g;
      grid.style.backgroundSize = `${zoom}px ${zoom}px`;
      sizeText.textContent = `${main.width} × ${main.height}px`;
      zoomText.textContent = `${zoom * 100}%`;
      zoomRange.value = String(ZOOMS.indexOf(zoom));
      updateSelBox();
      fitTextBox();
    }

    function setZoom(z: number, ax?: number, ay?: number): void {
      if (z === zoom || !ZOOMS.includes(z)) return;
      const r = z / zoom;
      // keep the point under the pointer (or the viewport centre) where it was
      const x = ax ?? work.clientWidth / 2;
      const y = ay ?? work.clientHeight / 2;
      const sl = (work.scrollLeft + x) * r - x;
      const st = (work.scrollTop + y) * r - y;
      zoom = z;
      applyZoom();
      work.scrollLeft = sl;
      work.scrollTop = st;
      refresh();
    }

    function stepZoom(dir: number, ax?: number, ay?: number): void {
      const i = ZOOMS.indexOf(zoom) + dir;
      if (i >= 0 && i < ZOOMS.length) setZoom(ZOOMS[i]!, ax, ay);
    }

    const toImage = (e: { clientX: number; clientY: number }) => {
      const r = main.getBoundingClientRect();
      return { x: (e.clientX - r.left) / zoom, y: (e.clientY - r.top) / zoom };
    };
    const clampX = (v: number) => Math.max(0, Math.min(main.width, v));
    const clampY = (v: number) => Math.max(0, Math.min(main.height, v));

    /* ============================== selection ============================== */
    function updateSelBox(): void {
      selBox.hidden = !sel;
      if (!sel) {
        selText.textContent = '';
        return;
      }
      selBox.style.left = `${sel.x * zoom}px`;
      selBox.style.top = `${sel.y * zoom}px`;
      selBox.style.width = `${sel.w * zoom}px`;
      selBox.style.height = `${sel.h * zoom}px`;
      selText.textContent = `${sel.w} × ${sel.h}px`;
    }

    function renderFloat(): void {
      octx.clearRect(0, 0, over.width, over.height);
      if (sel?.src) {
        octx.imageSmoothingEnabled = sel.w !== sel.src.width || sel.h !== sel.src.height;
        octx.drawImage(sel.src, sel.x, sel.y, sel.w, sel.h);
      }
    }

    /** Pick up the pixels under the marquee. Moving leaves colour 2 behind; Ctrl-drag copies instead. */
    function lift(copy: boolean): void {
      if (!sel || sel.src) return;
      const c = makeCanvas(sel.w, sel.h);
      c.getContext('2d')!.drawImage(main, -sel.x, -sel.y);
      sel.src = c;
      if (!copy) {
        ctx.fillStyle = color2;
        ctx.fillRect(sel.x, sel.y, sel.w, sel.h);
      }
      renderFloat();
    }

    /** Throw the selection away without touching the bitmap (the caller restores or keeps it). */
    function dropSel(): void {
      sel = null;
      octx.clearRect(0, 0, over.width, over.height);
      updateSelBox();
      refresh();
    }

    function commitSel(): void {
      if (!sel) return;
      if (sel.src) {
        ctx.imageSmoothingEnabled = sel.w !== sel.src.width || sel.h !== sel.src.height;
        ctx.drawImage(sel.src, sel.x, sel.y, sel.w, sel.h);
        ctx.imageSmoothingEnabled = true;
        dropSel();
        pushHist();
      } else dropSel();
    }

    function selectAll(): void {
      commitSel();
      commitText();
      setTool('select');
      sel = { x: 0, y: 0, w: main.width, h: main.height, src: null };
      updateSelBox();
      refresh();
    }

    function deleteSel(): void {
      if (!sel) return;
      if (!sel.src) {
        ctx.fillStyle = color2;
        ctx.fillRect(sel.x, sel.y, sel.w, sel.h);
      }
      dropSel();
      pushHist();
    }

    function selCanvas(): HTMLCanvasElement | null {
      if (!sel) return null;
      lift(true);
      const c = makeCanvas(sel.w, sel.h);
      const k = c.getContext('2d')!;
      k.imageSmoothingEnabled = true;
      k.drawImage(sel.src!, 0, 0, sel.w, sel.h);
      return c;
    }

    async function toSystemClipboard(c: HTMLCanvasElement): Promise<void> {
      try {
        const blob = await new Promise<Blob | null>((r) => c.toBlob(r, 'image/png'));
        if (blob && navigator.clipboard && typeof ClipboardItem !== 'undefined') {
          await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
        }
      } catch {
        /* the in-app clipboard still works when the browser refuses */
      }
    }

    function copySel(cut: boolean): void {
      if (!sel) return;
      const hadSrc = !!sel.src;
      const c = selCanvas();
      if (!c) return;
      clip = c;
      void toSystemClipboard(c);
      if (cut) {
        if (!hadSrc) {
          ctx.fillStyle = color2;
          ctx.fillRect(sel.x, sel.y, sel.w, sel.h);
        } else {
          // the hole was already left behind when it was lifted; just discard the floating pixels
        }
        dropSel();
        pushHist();
      } else if (!hadSrc) {
        // lift(true) created a float for a plain copy; keep the marquee unlifted so nothing changes
        sel.src = null;
        renderFloat();
      }
    }

    function growTo(w: number, hh: number): void {
      if (w <= main.width && hh <= main.height) return;
      const tmp = makeCanvas(main.width, main.height);
      tmp.getContext('2d')!.drawImage(main, 0, 0);
      sizeCanvas(Math.max(w, main.width), Math.max(hh, main.height));
      ctx.fillStyle = color2;
      ctx.fillRect(0, 0, main.width, main.height);
      ctx.drawImage(tmp, 0, 0);
    }

    /** Drop an image onto the canvas as a floating selection at the top-left of what the user can see. */
    function pasteCanvas(c: HTMLCanvasElement): void {
      closePopup();
      commitText();
      commitSel();
      if (c.width > main.width || c.height > main.height) {
        growTo(c.width, c.height);
        pushHist();
      }
      setTool('select');
      const x = Math.max(0, Math.min(main.width - c.width, Math.floor((work.scrollLeft - 6) / zoom)));
      const y = Math.max(0, Math.min(main.height - c.height, Math.floor((work.scrollTop - 6) / zoom)));
      sel = { x, y, w: c.width, h: c.height, src: c };
      renderFloat();
      updateSelBox();
      setDirty(true);
      refresh();
    }

    async function bitmapToCanvas(blob: Blob): Promise<HTMLCanvasElement | null> {
      try {
        const bmp = await createImageBitmap(blob);
        const c = makeCanvas(bmp.width, bmp.height);
        c.getContext('2d')!.drawImage(bmp, 0, 0);
        bmp.close();
        return c;
      } catch {
        return null;
      }
    }

    async function pasteFromClipboard(): Promise<void> {
      try {
        const items = await navigator.clipboard.read();
        for (const it of items) {
          const type = it.types.find((t) => t.startsWith('image/'));
          if (type) {
            const c = await bitmapToCanvas(await it.getType(type));
            if (c) return pasteCanvas(c);
          }
        }
      } catch {
        /* permission denied or unsupported: fall back to the in-app clipboard */
      }
      if (clip) pasteCanvas(clip);
      else os.notify('Paint', 'There is no picture on the clipboard.', paintIcon);
    }

    function pasteFromFile(): void {
      closePopup();
      void pickPicture(win.body, fs, 'Paste from', 'Paste', async (f) => {
        const img = await loadImage(f.content);
        if (!img) return os.notify('Paint', `${f.name} could not be opened.`, paintIcon);
        const c = makeCanvas(img.naturalWidth || 400, img.naturalHeight || 300);
        c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height);
        pasteCanvas(c);
      });
    }

    function cropToSelection(): void {
      if (!sel) return;
      closePopup();
      const { x, y, w, h: hh, src } = sel;
      if (src) {
        ctx.imageSmoothingEnabled = w !== src.width || hh !== src.height;
        ctx.drawImage(src, x, y, w, hh);
        ctx.imageSmoothingEnabled = true;
      }
      const c = makeCanvas(w, hh);
      const k = c.getContext('2d')!;
      k.fillStyle = color2;
      k.fillRect(0, 0, w, hh);
      k.drawImage(main, -x, -y);
      sel = null;
      octx.clearRect(0, 0, over.width, over.height);
      sizeCanvas(w, hh);
      ctx.drawImage(c, 0, 0);
      updateSelBox();
      pushHist();
    }

    function applyTransform(how: Transform): void {
      closePopup();
      commitText();
      if (sel) {
        lift(false);
        const s = sel;
        const base = s.w === s.src!.width && s.h === s.src!.height ? s.src! : scaled(s.src!, s.w, s.h);
        s.src = transformed(base, how);
        s.w = s.src.width;
        s.h = s.src.height;
        renderFloat();
        updateSelBox();
        setDirty(true);
        return;
      }
      const t = transformed(main, how);
      sizeCanvas(t.width, t.height);
      ctx.drawImage(t, 0, 0);
      pushHist();
    }

    function doInvert(): void {
      commitSel();
      invertColors(ctx);
      pushHist();
    }

    function clearImage(): void {
      commitSel();
      commitText();
      ctx.fillStyle = color2;
      ctx.fillRect(0, 0, main.width, main.height);
      pushHist();
    }

    /** Resize/skew-free: whole image, or the selection if there is one. */
    function resizeDialog(): void {
      closePopup();
      commitText();
      const tw = sel ? sel.w : main.width;
      const th = sel ? sel.h : main.height;
      let mode: 'pct' | 'px' = 'pct';
      const hIn = h('input', { class: 'sheet-input pt-num', type: 'number', min: 1, value: 100 });
      const vIn = h('input', { class: 'sheet-input pt-num', type: 'number', min: 1, value: 100 });
      const keep = h('input', { type: 'checkbox', checked: true, id: 'pt-keep' });
      const unit = h('span', { class: 'pt-unit' }, '%');
      const radio = (id: 'pct' | 'px', label: string) =>
        h('label', { class: 'pt-radio' }, h('input', { type: 'radio', name: 'pt-rs', checked: id === 'pct', onchange: () => setMode(id) }), label);
      const setMode = (m: 'pct' | 'px') => {
        mode = m;
        hIn.value = String(m === 'pct' ? 100 : tw);
        vIn.value = String(m === 'pct' ? 100 : th);
        unit.textContent = m === 'pct' ? '%' : 'px';
      };
      const ratio = tw / th;
      hIn.addEventListener('input', () => {
        if (keep.checked) {
          const v = Number(hIn.value);
          vIn.value = String(mode === 'pct' ? v : Math.max(1, Math.round(v / ratio)));
        }
      });
      vIn.addEventListener('input', () => {
        if (keep.checked) {
          const v = Number(vIn.value);
          hIn.value = String(mode === 'pct' ? v : Math.max(1, Math.round(v * ratio)));
        }
      });
      dialog(
        win.body,
        'Resize',
        [
          h('div', { class: 'pt-fieldset' }, h('div', { class: 'pt-legend' }, 'Resize by'), radio('pct', 'Percentage'), radio('px', 'Pixels')),
          h('div', { class: 'pt-fields' }, h('label', {}, 'Horizontal:'), hIn, unit, h('label', {}, 'Vertical:'), vIn, unit.cloneNode(true)),
          h('label', { class: 'pt-radio' }, keep, 'Maintain aspect ratio'),
        ],
        [
          {
            label: 'OK',
            primary: true,
            action: () => {
              const a = Number(hIn.value);
              const b = Number(vIn.value);
              if (!(a > 0) || !(b > 0)) return false;
              const nw = Math.min(MAX_DIM, Math.max(1, Math.round(mode === 'pct' ? (tw * a) / 100 : a)));
              const nh = Math.min(MAX_DIM, Math.max(1, Math.round(mode === 'pct' ? (th * b) / 100 : b)));
              if (sel) {
                lift(false);
                const s = sel;
                s.src = scaled(s.w === s.src!.width && s.h === s.src!.height ? s.src! : scaled(s.src!, s.w, s.h), nw, nh);
                s.w = nw;
                s.h = nh;
                renderFloat();
                updateSelBox();
                setDirty(true);
              } else {
                const t = scaled(main, nw, nh);
                sizeCanvas(nw, nh);
                ctx.drawImage(t, 0, 0);
                pushHist();
              }
            },
          },
          { label: 'Cancel', action: () => {} },
        ],
        320,
      );
    }

    /* ============================== text tool ============================== */
    const fontPx = () => (font.pt * 96) / 72;
    const lineH = () => Math.round(fontPx() * 1.25);
    const cssFont = () =>
      `${font.italic ? 'italic ' : ''}${font.bold ? 'bold ' : ''}${fontPx()}px ${FONTS[font.family]}`;

    function fitTextBox(): void {
      if (!textBox) return;
      const { el, x, y } = textBox;
      const z = zoom;
      const m = octx;
      m.save();
      m.font = cssFont();
      const lines = el.value.split('\n');
      const wpx = Math.max(60, ...lines.map((l) => m.measureText(l || ' ').width)) + 10;
      m.restore();
      el.style.left = `${x * z}px`;
      el.style.top = `${y * z}px`;
      el.style.width = `${wpx * z}px`;
      el.style.height = `${lines.length * lineH() * z}px`;
      el.style.font = cssFont().replace(/[\d.]+px/, `${fontPx() * z}px`);
      el.style.lineHeight = `${lineH() * z}px`;
      el.style.color = color1;
      el.style.background = font.opaque ? color2 : 'transparent';
      el.style.textDecoration = font.underline ? 'underline' : 'none';
    }

    function startText(x: number, y: number): void {
      commitText();
      const el = h('textarea', { class: 'pt-textbox', spellcheck: false, wrap: 'off', rows: 1, 'aria-label': 'Text' });
      textBox = { el, x: Math.floor(x), y: Math.floor(y) };
      el.addEventListener('input', fitTextBox);
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          e.stopPropagation();
          cancelText();
        }
      });
      el.addEventListener('pointerdown', (e) => e.stopPropagation());
      sheet.append(el);
      fitTextBox();
      el.focus();
      showTab('text');
    }

    function cancelText(): void {
      textBox?.el.remove();
      textBox = null;
      refresh();
    }

    function commitText(): void {
      if (!textBox) return;
      const { el, x, y } = textBox;
      const text = el.value;
      el.remove();
      textBox = null;
      if (!text.trim()) return;
      const lh = lineH();
      const lines = text.split('\n');
      ctx.save();
      ctx.font = cssFont();
      ctx.textBaseline = 'alphabetic';
      if (font.opaque) {
        const wpx = Math.max(60, ...lines.map((l) => ctx.measureText(l || ' ').width)) + 10;
        ctx.fillStyle = color2;
        ctx.fillRect(x, y, wpx, lines.length * lh);
      }
      ctx.fillStyle = color1;
      const m = ctx.measureText('Hg');
      const asc = m.fontBoundingBoxAscent ?? fontPx() * 0.8;
      const desc = m.fontBoundingBoxDescent ?? fontPx() * 0.2;
      lines.forEach((ln, i) => {
        // centre the glyph box in the line box, exactly as CSS does in the editing textarea
        const base = y + i * lh + (lh - (asc + desc)) / 2 + asc;
        ctx.fillText(ln, x, base);
        if (font.underline && ln) {
          ctx.fillRect(x, Math.round(base + fontPx() * 0.12), ctx.measureText(ln).width, Math.max(1, Math.round(fontPx() / 14)));
        }
      });
      ctx.restore();
      pushHist();
    }

    /* ============================== tools ============================== */
    function setTool(t: ToolId): void {
      if (t !== 'text') commitText();
      if (t !== 'select' && tool === 'select') commitSel();
      if (t === 'picker' && tool !== 'picker') prevTool = tool;
      tool = t;
      sheet.dataset.tool = t;
      if (t === 'text') showTab('text');
      else if (tab === 'text') showTab('home');
      syncRibbon();
      refresh();
    }

    function shapeStyle(fg: string, bg: string): ShapeStyle {
      const stroke = outline === 'solid' || shape === 'line';
      const fill = fillMode === 'solid' && shape !== 'line';
      return { stroke: stroke ? fg : null, fill: fill ? (stroke ? bg : fg) : null, width: size };
    }

    function samplePixel(x: number, y: number): string | null {
      if (x < 0 || y < 0 || x >= main.width || y >= main.height) return null;
      const d = ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1).data;
      return toHex(d[0]!, d[1]!, d[2]!);
    }

    /* ============================== pointer handling ============================== */
    const inSel = (x: number, y: number) => !!sel && x >= sel.x && y >= sel.y && x < sel.x + sel.w && y < sel.y + sel.h;

    function onDown(e: PointerEvent): void {
      if (e.button !== 0 && e.button !== 2) return;
      closePopup();
      win.body.focus({ preventScroll: true });
      const target = e.target as HTMLElement;
      const dir = target.dataset.dir;
      const grow = target.dataset.grow;
      if (grow) {
        e.preventDefault();
        commitSel();
        commitText();
        drag = { t: 'grow', dx: grow.includes('e'), dy: grow.includes('s') };
        sheet.setPointerCapture(e.pointerId);
        return;
      }
      const p = toImage(e);
      const x = Math.floor(p.x);
      const y = Math.floor(p.y);
      const right = e.button === 2;
      const fg = right ? color2 : color1;
      const bg = right ? color1 : color2;
      if (e.button === 2) e.preventDefault();

      if (dir && sel) {
        sheet.setPointerCapture(e.pointerId);
        drag = { t: 'scale', dir, px: p.x, py: p.y, o: { x: sel.x, y: sel.y, w: sel.w, h: sel.h } };
        return;
      }

      if (tool === 'select') {
        sheet.setPointerCapture(e.pointerId);
        if (sel && inSel(p.x, p.y)) {
          drag = { t: 'move', px: p.x, py: p.y, ox: sel.x, oy: sel.y, copy: e.ctrlKey };
        } else {
          commitSel();
          const sx = Math.round(clampX(p.x));
          const sy = Math.round(clampY(p.y));
          drag = { t: 'marquee', sx, sy };
          sel = { x: sx, y: sy, w: 0, h: 0, src: null };
        }
        return;
      }

      if (tool === 'text') {
        // a click on the canvas commits the current box and starts a fresh one at that spot
        startText(p.x, p.y);
        return;
      }
      commitText();
      if (sel) commitSel();

      if (tool === 'magnifier') {
        stepZoom(right ? -1 : 1, e.clientX - work.getBoundingClientRect().left, e.clientY - work.getBoundingClientRect().top);
        return;
      }
      if (tool === 'picker') {
        const c = samplePixel(x, y);
        if (c) {
          if (right) setColor(2, c, false);
          else setColor(1, c, false);
        }
        setTool(prevTool);
        return;
      }
      if (tool === 'fill') {
        if (floodFill(ctx, x, y, fg, Math.round((tolerance / 100) * 255))) pushHist();
        return;
      }

      sheet.setPointerCapture(e.pointerId);
      if (tool === 'shape') {
        drag = { t: 'shape', sx: x, sy: y, ex: x, ey: y, fg, bg };
        return;
      }
      // pencil / brush / eraser
      const t = tool as 'pencil' | 'brush' | 'eraser';
      const colr = t === 'eraser' ? bg : fg;
      const d: Drag = { t: 'free', tool: t, col: colr, lx: t === 'brush' ? p.x : x, ly: t === 'brush' ? p.y : y };
      drag = d;
      if (t === 'pencil') pencilLine(ctx, x, y, x, y, colr);
      else if (t === 'eraser') eraseLine(ctx, x, y, x, y, eraserSide(size), colr);
      else {
        brushDot(ctx, brush, size, colr, p.x, p.y);
        // a held airbrush keeps spraying while the pointer is still
        if (brush === 'air') d.timer = window.setInterval(() => airPuff(ctx, size, colr, d.lx, d.ly), 24);
      }
    }

    function onMove(e: PointerEvent): void {
      const p = toImage(e);
      const inside = p.x >= 0 && p.y >= 0 && p.x < main.width && p.y < main.height;
      posText.textContent = inside ? `${Math.floor(p.x)}, ${Math.floor(p.y)}px` : '';
      if (!drag) {
        if (tool === 'select') sheet.classList.toggle('over-sel', inSel(p.x, p.y));
        return;
      }
      const d = drag;
      switch (d.t) {
        case 'free': {
          const nx = d.tool === 'brush' ? p.x : Math.floor(p.x);
          const ny = d.tool === 'brush' ? p.y : Math.floor(p.y);
          if (d.tool === 'pencil') pencilLine(ctx, d.lx, d.ly, nx, ny, d.col);
          else if (d.tool === 'eraser') eraseLine(ctx, d.lx, d.ly, nx, ny, eraserSide(size), d.col);
          else brushSegment(ctx, brush, size, d.col, d.lx, d.ly, nx, ny);
          d.lx = nx;
          d.ly = ny;
          break;
        }
        case 'shape': {
          let ex = Math.floor(p.x);
          let ey = Math.floor(p.y);
          if (e.shiftKey) [ex, ey] = constrainPoint(shape, d.sx, d.sy, ex, ey);
          d.ex = ex;
          d.ey = ey;
          octx.clearRect(0, 0, over.width, over.height);
          drawShape(octx, shape, d.sx, d.sy, ex, ey, shapeStyle(d.fg, d.bg));
          selText.textContent = `${Math.abs(Math.round(ex) - d.sx) + 1} × ${Math.abs(Math.round(ey) - d.sy) + 1}px`;
          break;
        }
        case 'marquee': {
          if (!sel) break;
          const ex = Math.round(clampX(p.x));
          const ey = Math.round(clampY(p.y));
          sel.x = Math.min(d.sx, ex);
          sel.y = Math.min(d.sy, ey);
          sel.w = Math.abs(ex - d.sx);
          sel.h = Math.abs(ey - d.sy);
          updateSelBox();
          break;
        }
        case 'move': {
          if (!sel) break;
          const dx = Math.round(p.x - d.px);
          const dy = Math.round(p.y - d.py);
          if (!sel.src && (Math.abs(dx) > 0 || Math.abs(dy) > 0)) lift(d.copy);
          if (sel.src) {
            sel.x = d.ox + dx;
            sel.y = d.oy + dy;
            renderFloat();
            updateSelBox();
          }
          break;
        }
        case 'scale': {
          if (!sel) break;
          lift(false);
          const dx = Math.round(p.x - d.px);
          const dy = Math.round(p.y - d.py);
          let { x, y, w, h: hh } = d.o;
          if (d.dir.includes('e')) w = Math.max(1, d.o.w + dx);
          if (d.dir.includes('s')) hh = Math.max(1, d.o.h + dy);
          if (d.dir.includes('w')) {
            w = Math.max(1, d.o.w - dx);
            x = d.o.x + d.o.w - w;
          }
          if (d.dir.includes('n')) {
            hh = Math.max(1, d.o.h - dy);
            y = d.o.y + d.o.h - hh;
          }
          Object.assign(sel, { x, y, w, h: hh });
          renderFloat();
          updateSelBox();
          break;
        }
        case 'grow': {
          const r = sheet.getBoundingClientRect();
          const nw = d.dx ? Math.min(MAX_DIM, Math.max(1, Math.round((e.clientX - r.left) / zoom))) : main.width;
          const nh = d.dy ? Math.min(MAX_DIM, Math.max(1, Math.round((e.clientY - r.top) / zoom))) : main.height;
          growPrev.hidden = false;
          growPrev.style.width = `${nw * zoom}px`;
          growPrev.style.height = `${nh * zoom}px`;
          growPrev.dataset.w = String(nw);
          growPrev.dataset.h = String(nh);
          sizeText.textContent = `${nw} × ${nh}px`;
          break;
        }
      }
    }

    function onUp(): void {
      if (!drag) return;
      const d = drag;
      drag = null;
      switch (d.t) {
        case 'free':
          if (d.timer) clearInterval(d.timer);
          pushHist();
          break;
        case 'shape':
          octx.clearRect(0, 0, over.width, over.height);
          selText.textContent = '';
          drawShape(ctx, shape, d.sx, d.sy, d.ex, d.ey, shapeStyle(d.fg, d.bg));
          pushHist();
          break;
        case 'marquee':
          if (!sel || sel.w < 1 || sel.h < 1) dropSel();
          else {
            updateSelBox();
            refresh();
          }
          break;
        case 'move':
        case 'scale':
          refresh();
          break;
        case 'grow': {
          growPrev.hidden = true;
          const nw = Number(growPrev.dataset.w || main.width);
          const nh = Number(growPrev.dataset.h || main.height);
          if (nw !== main.width || nh !== main.height) {
            const tmp = makeCanvas(main.width, main.height);
            tmp.getContext('2d')!.drawImage(main, 0, 0);
            sizeCanvas(nw, nh);
            ctx.fillStyle = color2;
            ctx.fillRect(0, 0, nw, nh);
            ctx.drawImage(tmp, 0, 0);
            pushHist();
          } else sizeText.textContent = `${main.width} × ${main.height}px`;
          growPrev.dataset.w = '';
          growPrev.dataset.h = '';
          break;
        }
      }
    }

    sheet.addEventListener('pointerdown', onDown);
    sheet.addEventListener('pointermove', onMove);
    sheet.addEventListener('pointerup', onUp);
    sheet.addEventListener('pointercancel', onUp);
    sheet.addEventListener('pointerleave', () => !drag && (posText.textContent = ''));
    sheet.addEventListener('contextmenu', (e) => e.preventDefault());
    // The browser would move focus to the window body on mousedown and steal it from a text box we just opened.
    sheet.addEventListener('mousedown', (e) => {
      if ((e.target as HTMLElement).tagName !== 'TEXTAREA') e.preventDefault();
    });

    work.addEventListener(
      'wheel',
      (e) => {
        if (!e.ctrlKey && !e.metaKey) return;
        e.preventDefault();
        const r = work.getBoundingClientRect();
        stepZoom(e.deltaY < 0 ? 1 : -1, e.clientX - r.left, e.clientY - r.top);
      },
      { passive: false },
    );

    /* ============================== colours ============================== */
    const c1Sw = h('span', { class: 'pt-cswatch' });
    const c2Sw = h('span', { class: 'pt-cswatch' });
    const c1Btn = h('button', { class: 'pt-rb big pt-colorbtn', type: 'button', title: 'Color 1 (foreground color)', onclick: () => ((slot = 1), syncColors()) }, c1Sw, h('span', { class: 'pt-rb-l' }, 'Color 1'));
    const c2Btn = h('button', { class: 'pt-rb big pt-colorbtn', type: 'button', title: 'Color 2 (background color)', onclick: () => ((slot = 2), syncColors()) }, c2Sw, h('span', { class: 'pt-rb-l' }, 'Color 2'));
    const customSlots = [0, 1].map(() => h('button', { class: 'pt-sw pt-sw-empty', type: 'button', 'aria-label': 'Custom color', disabled: true }));

    function setColor(which: 1 | 2, hex: string, remember: boolean): void {
      if (which === 1) color1 = hex;
      else color2 = hex;
      if (remember && !PALETTE.includes(hex)) custom = [hex, ...custom.filter((c) => c !== hex)].slice(0, 2);
      syncColors();
      fitTextBox();
    }

    function syncColors(): void {
      c1Sw.style.background = color1;
      c2Sw.style.background = color2;
      c1Btn.classList.toggle('active', slot === 1);
      c2Btn.classList.toggle('active', slot === 2);
      customSlots.forEach((b, i) => {
        const c = custom[i];
        b.disabled = !c;
        b.classList.toggle('pt-sw-empty', !c);
        b.style.background = c ?? '';
        b.title = c ? c.toUpperCase() : 'Custom color';
        b.onclick = c ? () => setColor(slot, c, false) : null;
        b.oncontextmenu = c ? (e) => (e.preventDefault(), setColor(2, c, false)) : null;
      });
    }

    const swatches = PALETTE.map((c) =>
      h('button', {
        class: 'pt-sw',
        type: 'button',
        style: `background:${c}`,
        title: c.toUpperCase(),
        'aria-label': `Color ${c}`,
        onclick: () => setColor(slot, c, false),
        oncontextmenu: (e: Event) => {
          e.preventDefault();
          setColor(2, c, false);
        },
      }),
    );
    const colorPicker = h('input', {
      class: 'pt-colorinput',
      type: 'color',
      value: color1,
      'aria-label': 'Edit colors',
      oninput: (e: Event) => setColor(slot, (e.target as HTMLInputElement).value, false),
      onchange: (e: Event) => setColor(slot, (e.target as HTMLInputElement).value, true),
    });
    colorPicker.addEventListener('click', () => {
      colorPicker.value = slot === 1 ? color1 : color2;
    });

    /* ============================== ribbon ============================== */
    const toolBtns = new Map<ToolId, HTMLElement>();
    const shapeBtns = new Map<ShapeKind, HTMLElement>();
    const sizeBtn = rbtn({ icon: 'size', label: 'Size', big: true, caret: true, title: 'Size', onclick: (e) => openPopup(win.body, e.currentTarget as HTMLElement, sizeMenu()) });

    const toolButton = (id: ToolId, icon: Parameters<typeof rbtn>[0]['icon'], title: string, on?: () => void) => {
      const b = rbtn({ icon, title, onclick: on ?? (() => setTool(id)) });
      toolBtns.set(id, b);
      return b;
    };

    const outlineBtn = rbtn({ icon: 'outline', label: 'Outline', caret: true, title: 'Outline', onclick: (e) => openPopup(win.body, e.currentTarget as HTMLElement, popMenu([
      { label: 'Solid color', checked: outline === 'solid', action: () => (outline = 'solid') },
      { label: 'No outline', checked: outline === 'none', action: () => (outline = 'none') },
    ])) });
    const fillBtn = rbtn({ icon: 'fillcol', label: 'Fill', caret: true, title: 'Fill', onclick: (e) => openPopup(win.body, e.currentTarget as HTMLElement, popMenu([
      { label: 'No fill', checked: fillMode === 'none', action: () => (fillMode = 'none') },
      { label: 'Solid color', checked: fillMode === 'solid', action: () => (fillMode = 'solid') },
    ])) });

    const shapeGrid = h('div', { class: 'pt-shapes' });
    for (const k of SHAPES) {
      const b = rbtn({
        icon: `shape-${k}`,
        title: SHAPE_NAMES[k],
        cls: 'pt-shape',
        onclick: () => {
          shape = k;
          setTool('shape');
        },
      });
      shapeBtns.set(k, b);
      shapeGrid.append(b);
    }

    function sizeMenu(): HTMLElement {
      const el = h('div', { class: 'pt-menu pt-size-menu', role: 'menu' });
      for (const s of SIZES) {
        el.append(
          h(
            'button',
            {
              class: `pt-mi${s === size ? ' on' : ''}`,
              type: 'button',
              onclick: () => {
                size = s;
                closePopup();
                syncRibbon();
              },
            },
            h('span', { class: 'pt-size-line' }, h('i', { style: `height:${s}px` })),
            h('span', { class: 'pt-mi-l' }, `${s}px`),
          ),
        );
      }
      return el;
    }

    function brushMenu(): HTMLElement {
      const el = h('div', { class: 'pt-brushes' });
      for (const b of BRUSHES) {
        el.append(
          h(
            'button',
            {
              class: `pt-brush${tool === 'brush' && brush === b.kind ? ' on' : ''}`,
              type: 'button',
              title: b.label,
              onclick: () => {
                brush = b.kind;
                closePopup();
                setTool('brush');
              },
            },
            glyph(`brush-${b.kind}`, 32),
            h('span', {}, b.label),
          ),
        );
      }
      return el;
    }

    const brushSplit = splitBig({
      icon: 'brush',
      label: 'Brushes',
      title: 'Brushes',
      onMain: () => setTool('brush'),
      onMenu: (a) => openPopup(win.body, a, brushMenu()),
    });
    toolBtns.set('brush', brushSplit.querySelector<HTMLElement>('.pt-split-top')!);

    const selectSplit = splitBig({
      icon: 'select',
      label: 'Select',
      onMain: () => setTool('select'),
      onMenu: (a) =>
        openPopup(
          win.body,
          a,
          popMenu([
            { label: 'Rectangular selection', icon: 'select', checked: tool === 'select', action: () => setTool('select') },
            { label: 'Select all', shortcut: 'Ctrl+A', action: selectAll },
            { label: 'Delete', shortcut: 'Del', disabled: !sel, action: deleteSel },
          ]),
        ),
    });
    toolBtns.set('select', selectSplit.querySelector<HTMLElement>('.pt-split-top')!);

    const rotateBtn = rbtn({ icon: 'rotate', label: 'Rotate', caret: true, title: 'Rotate or flip', onclick: (e) => openPopup(win.body, e.currentTarget as HTMLElement, popMenu([
      { label: 'Rotate right 90°', action: () => applyTransform('rotR') },
      { label: 'Rotate left 90°', action: () => applyTransform('rotL') },
      { label: 'Rotate 180°', action: () => applyTransform('rot180') },
      'sep',
      { label: 'Flip vertical', action: () => applyTransform('flipV') },
      { label: 'Flip horizontal', action: () => applyTransform('flipH') },
    ])) });

    const cutBtn = rbtn({ icon: 'cut', label: 'Cut', title: 'Cut (Ctrl+X)', onclick: () => copySel(true) });
    const copyBtn = rbtn({ icon: 'copy', label: 'Copy', title: 'Copy (Ctrl+C)', onclick: () => copySel(false) });
    const cropBtn = rbtn({ icon: 'crop', label: 'Crop', title: 'Crop to selection', onclick: cropToSelection });
    const resizeBtn = rbtn({ icon: 'resize', label: 'Resize', title: 'Resize and skew', onclick: resizeDialog });

    const pasteSplit = splitBig({
      icon: 'paste',
      label: 'Paste',
      title: 'Paste (Ctrl+V)',
      onMain: () => void pasteFromClipboard(),
      onMenu: (a) =>
        openPopup(
          win.body,
          a,
          popMenu([
            { label: 'Paste', shortcut: 'Ctrl+V', action: () => void pasteFromClipboard() },
            { label: 'Paste from…', action: pasteFromFile },
          ]),
        ),
    });

    const homePanel = h(
      'div',
      { class: 'pt-panel', 'data-tab': 'home' },
      group('Clipboard', pasteSplit, col(cutBtn, copyBtn)),
      group('Image', selectSplit, col(cropBtn, resizeBtn, rotateBtn)),
      group(
        'Tools',
        h(
          'div',
          { class: 'pt-toolgrid' },
          toolButton('pencil', 'pencil', 'Pencil'),
          toolButton('fill', 'fill', 'Fill with color'),
          toolButton('text', 'text', 'Text'),
          toolButton('eraser', 'eraser', 'Eraser'),
          toolButton('picker', 'picker', 'Color picker'),
          toolButton('magnifier', 'magnifier', 'Magnifier (right-click to zoom out)'),
        ),
      ),
      group('Brushes', brushSplit),
      group('Shapes', shapeGrid, col(outlineBtn, fillBtn)),
      group('Size', sizeBtn),
      group(
        'Colors',
        c1Btn,
        c2Btn,
        h('div', { class: 'pt-palette' }, ...swatches, ...customSlots),
        h('div', { class: 'pt-editcolors' }, rbtn({ icon: 'editcolors', label: 'Edit colors', big: true, title: 'Edit colors' }), colorPicker),
      ),
    );

    const viewPanel = h(
      'div',
      { class: 'pt-panel', 'data-tab': 'view', hidden: true },
      group(
        'Zoom',
        rbtn({ icon: 'zoomin', label: 'Zoom in', big: true, onclick: () => stepZoom(1) }),
        rbtn({ icon: 'zoomout', label: 'Zoom out', big: true, onclick: () => stepZoom(-1) }),
        rbtn({ icon: 'zoom100', label: '100%', big: true, onclick: () => setZoom(1) }),
      ),
      group(
        'Show or hide',
        col(
          checkbox('Gridlines', () => showGrid, (v) => ((showGrid = v), applyZoom())),
          checkbox('Status bar', () => showStatus, (v) => ((showStatus = v), (status.hidden = !v))),
        ),
      ),
    );

    const fontSel = h(
      'select',
      { class: 'pt-select pt-font', 'aria-label': 'Font family', onchange: () => ((font.family = fontSel.value), fitTextBox()) },
      ...Object.keys(FONTS).map((f) => h('option', { value: f, style: `font-family:${FONTS[f]}` }, f)),
    );
    const sizeSel = h(
      'select',
      { class: 'pt-select pt-fsize', 'aria-label': 'Font size', onchange: () => ((font.pt = Number(sizeSel.value)), fitTextBox()) },
      ...FONT_SIZES.map((s) => h('option', { value: s, selected: s === font.pt }, String(s))),
    );
    fontSel.value = font.family;
    const fmtBtn = (label: string, title: string, key: 'bold' | 'italic' | 'underline', style: string) => {
      const b = h('button', { class: 'pt-rb pt-fmt', type: 'button', title, 'aria-label': title, 'aria-pressed': 'false', style, onclick: () => {
        font[key] = !font[key];
        b.classList.toggle('active', font[key]);
        b.setAttribute('aria-pressed', String(font[key]));
        fitTextBox();
      } }, label);
      return b;
    };
    const opaqueBtn = rbtn({ label: 'Opaque', title: 'Fill the text box with Color 2', onclick: () => ((font.opaque = true), syncRibbon(), fitTextBox()) });
    const transBtn = rbtn({ label: 'Transparent', title: 'Draw text over the picture', onclick: () => ((font.opaque = false), syncRibbon(), fitTextBox()) });
    const textPanel = h(
      'div',
      { class: 'pt-panel', 'data-tab': 'text', hidden: true },
      group(
        'Font',
        col(row(fontSel, sizeSel), row(fmtBtn('B', 'Bold', 'bold', 'font-weight:700'), fmtBtn('I', 'Italic', 'italic', 'font-style:italic;font-family:Georgia,serif'), fmtBtn('U', 'Underline', 'underline', 'text-decoration:underline'))),
      ),
      group('Background', col(opaqueBtn, transBtn)),
    );

    function checkbox(label: string, get: () => boolean, set: (v: boolean) => void): HTMLElement {
      const input = h('input', { type: 'checkbox', checked: get(), onchange: () => set(input.checked) });
      return h('label', { class: 'pt-check' }, input, label);
    }

    const tabBtns = new Map<TabId, HTMLElement>();
    const mkTab = (id: TabId, label: string, cls = '') => {
      const b = h('button', { class: `pt-tab ${cls}`, type: 'button', role: 'tab', onclick: () => showTab(id) }, label);
      tabBtns.set(id, b);
      return b;
    };
    const fileBtn = h('button', { class: 'pt-filebtn', type: 'button', onclick: (e: MouseEvent) => openPopup(win.body, e.currentTarget as HTMLElement, fileMenu()) }, h('span', {}, 'Paint'), h('i', { class: 'pt-caret' }));
    const qSave = rbtn({ icon: 'save', title: 'Save (Ctrl+S)', cls: 'pt-q', onclick: () => void save() });
    const qUndo = rbtn({ icon: 'undo', title: 'Undo (Ctrl+Z)', cls: 'pt-q', onclick: undo });
    const qRedo = rbtn({ icon: 'redo', title: 'Redo (Ctrl+Y)', cls: 'pt-q', onclick: redo });
    const tabs = h('div', { class: 'pt-tabs', role: 'tablist' }, fileBtn, h('span', { class: 'pt-qa' }, qSave, qUndo, qRedo), mkTab('home', 'Home'), mkTab('view', 'View'), mkTab('text', 'Text', 'pt-tab-ctx'));
    const ribbon = h('div', { class: 'pt-ribbon' }, homePanel, viewPanel, textPanel);

    function showTab(t: TabId): void {
      tab = t;
      closePopup();
      for (const [id, b] of tabBtns) {
        b.classList.toggle('active', id === t);
        b.setAttribute('aria-selected', String(id === t));
      }
      for (const p of [homePanel, viewPanel, textPanel]) p.hidden = p.dataset.tab !== t;
      tabBtns.get('text')!.hidden = !(tool === 'text' || t === 'text');
    }

    function syncRibbon(): void {
      for (const [id, b] of toolBtns) b.classList.toggle('active', id === tool);
      for (const [k, b] of shapeBtns) b.classList.toggle('active', tool === 'shape' && k === shape);
      sizeBtn.title = `Size: ${size}px`;
      opaqueBtn.classList.toggle('active', font.opaque);
      transBtn.classList.toggle('active', !font.opaque);
      tolBox.hidden = tool !== 'fill';
      tabBtns.get('text')!.hidden = !(tool === 'text' || tab === 'text');
      syncColors();
    }

    /** Cheap, idempotent: enabled states + menu bar. Called after anything that changes what is possible. */
    function refresh(): void {
      qUndo.disabled = hi <= 0 && !sel?.src;
      qRedo.disabled = hi >= hist.length - 1;
      const has = !!sel;
      cutBtn.disabled = !has;
      copyBtn.disabled = !has;
      cropBtn.disabled = !has;
      updateSelBox();
      buildMenus();
    }

    /* ============================== file I/O ============================== */
    const stripExt = (n: string) => n.replace(/\.[a-z0-9]+$/i, '');

    function newImage(): void {
      commitText();
      sel = null;
      octx.clearRect(0, 0, over.width, over.height);
      sizeCanvas(DEFAULT_W, DEFAULT_H);
      fillWhite();
      path = null;
      resetHistory();
      setDirty(false);
    }

    async function openFile(p: string): Promise<void> {
      const content = await fs.read(p);
      const img = content === null ? null : await loadImage(content);
      if (!img) {
        os.notify('Paint', `${basename(p)} could not be opened as a picture.`, paintIcon);
        return;
      }
      commitText();
      sel = null;
      octx.clearRect(0, 0, over.width, over.height);
      let w = img.naturalWidth || DEFAULT_W;
      let hh = img.naturalHeight || DEFAULT_H;
      if (Math.max(w, hh) > MAX_DIM) {
        const k = MAX_DIM / Math.max(w, hh);
        w = Math.round(w * k);
        hh = Math.round(hh * k);
      }
      sizeCanvas(w, hh);
      fillWhite();
      ctx.drawImage(img, 0, 0, w, hh);
      path = p;
      resetHistory();
      setDirty(false);
    }

    async function writeTo(p: string): Promise<void> {
      commitSel();
      commitText();
      await fs.mkdir(PICS);
      const jpeg = /\.jpe?g$/i.test(p);
      await fs.write(p, main.toDataURL(jpeg ? 'image/jpeg' : 'image/png', 0.92));
      path = p;
      setDirty(false);
    }

    async function save(then?: () => void): Promise<void> {
      if (path && SAVE_RE.test(path)) {
        await writeTo(path);
        then?.();
      } else saveAs(then);
    }

    function saveAs(then?: () => void): void {
      closePopup();
      const base = path ? stripExt(basename(path)) : 'Untitled';
      const input = h('input', { class: 'sheet-input', value: `${base}.png`, 'aria-label': 'File name', spellcheck: false });
      const warn = h('div', { class: 'pt-warn', hidden: true });
      let armed = '';
      setTimeout(() => input.setSelectionRange(0, base.length), 30);
      dialog(
        win.body,
        'Save As',
        [h('label', {}, 'File name:'), input, h('div', { class: 'sheet-hint' }, 'Save in: Pictures · PNG (.png) or JPEG (.jpg)'), warn],
        [
          {
            label: 'Save',
            primary: true,
            action: async () => {
              let name = input.value.trim().replace(/[\\/]/g, '-');
              if (!name) return false;
              if (!SAVE_RE.test(name)) name = `${name.replace(/\.(svg|gif|bmp|webp)$/i, '').replace(/\.+$/, '')}.png`;
              const target = `${PICS}/${name}`;
              if (target !== path && (await fs.exists(target)) && armed !== target) {
                armed = target;
                warn.hidden = false;
                warn.textContent = `${name} already exists. Press Save again to replace it.`;
                return false;
              }
              await writeTo(target);
              then?.();
            },
          },
          { label: 'Cancel', action: () => {} },
        ],
      );
      input.addEventListener('input', () => ((armed = ''), (warn.hidden = true)));
    }

    function openDialog(): void {
      closePopup();
      guard(() => void pickPicture(win.body, fs, 'Open', 'Open', (f) => void openFile(f.path)));
    }

    /** Ask what to do with unsaved work, then continue with `proceed`. */
    function guard(proceed: () => void): void {
      if (!dirty) return proceed();
      const name = path ? basename(path) : 'Untitled';
      dialog(
        win.body,
        'Paint',
        [h('div', { class: 'pt-confirm' }, `Do you want to save changes to ${name}?`)],
        [
          { label: 'Save', primary: true, action: () => void save(proceed) },
          {
            label: "Don't Save",
            action: () => {
              proceed();
            },
          },
          { label: 'Cancel', action: () => {} },
        ],
      );
    }

    win.onBeforeClose(() => {
      if (!dirty || forceClose) return true;
      guard(() => {
        forceClose = true;
        win.close();
      });
      return false;
    });

    /* ============================== menus ============================== */
    const fileMenu = (): HTMLElement =>
      popMenu([
        { label: 'New', shortcut: 'Ctrl+N', action: () => guard(newImage) },
        { label: 'Open…', shortcut: 'Ctrl+O', action: openDialog },
        'sep',
        { label: 'Save', shortcut: 'Ctrl+S', action: () => void save() },
        { label: 'Save as…', shortcut: 'Ctrl+Shift+S', action: () => saveAs() },
        'sep',
        { label: 'Exit', action: () => win.close() },
      ]);

    function buildMenus(): void {
      const hasSel = !!sel;
      const zoomItem = (z: number): PopItem => ({ label: `${z * 100}%`, checked: zoom === z, action: () => setZoom(z) });
      const toMenu = (items: (PopItem | 'sep')[]) =>
        items.map((i) => (i === 'sep' ? { separator: true } : { label: i.label, shortcut: i.shortcut, checked: i.checked, disabled: i.disabled, action: i.action }));
      const menus: MenuDef[] = [
        {
          label: 'File',
          items: [
            { label: 'New', shortcut: 'Ctrl+N', action: () => guard(newImage) },
            { label: 'Open…', shortcut: 'Ctrl+O', action: openDialog },
            { separator: true },
            { label: 'Save', shortcut: 'Ctrl+S', action: () => void save() },
            { label: 'Save as…', shortcut: 'Ctrl+Shift+S', action: () => saveAs() },
            { separator: true },
            { label: 'Close', action: () => win.close() },
          ],
        },
        {
          label: 'Edit',
          items: [
            { label: 'Undo', shortcut: 'Ctrl+Z', disabled: hi <= 0 && !sel?.src, action: undo },
            { label: 'Redo', shortcut: 'Ctrl+Y', disabled: hi >= hist.length - 1, action: redo },
            { separator: true },
            { label: 'Cut', shortcut: 'Ctrl+X', disabled: !hasSel, action: () => copySel(true) },
            { label: 'Copy', shortcut: 'Ctrl+C', disabled: !hasSel, action: () => copySel(false) },
            { label: 'Paste', shortcut: 'Ctrl+V', action: () => void pasteFromClipboard() },
            { label: 'Paste from…', action: pasteFromFile },
            { label: 'Delete', shortcut: 'Del', disabled: !hasSel, action: deleteSel },
            { separator: true },
            { label: 'Select all', shortcut: 'Ctrl+A', action: selectAll },
          ],
        },
        {
          label: 'Image',
          items: [
            { label: 'Crop to selection', disabled: !hasSel, action: cropToSelection },
            { label: 'Resize…', action: resizeDialog },
            { separator: true },
            ...toMenu([
              { label: 'Rotate right 90°', action: () => applyTransform('rotR') },
              { label: 'Rotate left 90°', action: () => applyTransform('rotL') },
              { label: 'Rotate 180°', action: () => applyTransform('rot180') },
              'sep',
              { label: 'Flip vertical', action: () => applyTransform('flipV') },
              { label: 'Flip horizontal', action: () => applyTransform('flipH') },
            ]),
            { separator: true },
            { label: 'Invert colors', action: doInvert },
            { label: 'Clear image', action: clearImage },
          ],
        },
        {
          label: 'View',
          items: [
            { label: 'Zoom in', disabled: zoom === ZOOMS[ZOOMS.length - 1], action: () => stepZoom(1) },
            { label: 'Zoom out', disabled: zoom === 1, action: () => stepZoom(-1) },
            { separator: true },
            ...toMenu(ZOOMS.map(zoomItem)),
            { separator: true },
            { label: 'Gridlines', checked: showGrid, action: () => ((showGrid = !showGrid), applyZoom(), refresh()) },
            { label: 'Status bar', checked: showStatus, action: () => ((showStatus = !showStatus), (status.hidden = !showStatus), refresh()) },
          ],
        },
      ];
      win.setMenus(menus);
    }

    /* ============================== keyboard / clipboard events ============================== */
    win.body.tabIndex = -1;
    win.body.addEventListener('keydown', (e) => {
      const t = e.target as HTMLElement;
      const typing = t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.tagName === 'SELECT';
      const mod = e.ctrlKey || e.metaKey;
      const k = e.key.toLowerCase();
      if (mod && k === 's') {
        e.preventDefault();
        if (e.shiftKey) saveAs();
        else void save();
      } else if (mod && k === 'o') {
        e.preventDefault();
        openDialog();
      } else if (mod && k === 'n') {
        e.preventDefault();
        guard(newImage);
      } else if (typing) {
        return; // let text boxes and fields keep their own undo, selection and clipboard
      } else if (mod && k === 'z') {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if (mod && k === 'y') {
        e.preventDefault();
        redo();
      } else if (mod && k === 'a') {
        e.preventDefault();
        selectAll();
      } else if (mod && (k === 'c' || k === 'x') && sel) {
        e.preventDefault();
        copySel(k === 'x');
      } else if (mod && k === 'v') {
        // let the browser fire a real paste event, which can read images without a permission prompt
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (sel) {
          e.preventDefault();
          deleteSel();
        }
      } else if (e.key === 'Escape') {
        if (sel) commitSel();
      } else if (sel && e.key.startsWith('Arrow')) {
        e.preventDefault();
        const dx = e.key === 'ArrowLeft' ? -1 : e.key === 'ArrowRight' ? 1 : 0;
        const dy = e.key === 'ArrowUp' ? -1 : e.key === 'ArrowDown' ? 1 : 0;
        lift(false);
        sel.x += dx;
        sel.y += dy;
        renderFloat();
        updateSelBox();
        setDirty(true);
      }
    });

    win.body.addEventListener('paste', (e) => {
      const t = e.target as HTMLElement;
      if (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT') return;
      const file = [...(e.clipboardData?.items ?? [])].find((i) => i.type.startsWith('image/'))?.getAsFile();
      e.preventDefault();
      if (file) void bitmapToCanvas(file).then((c) => (c ? pasteCanvas(c) : undefined));
      else if (clip) pasteCanvas(clip);
    });

    /* ============================== wiring ============================== */
    zoomRange.addEventListener('input', () => setZoom(ZOOMS[Number(zoomRange.value)]!));
    tolRange.addEventListener('input', () => {
      tolerance = Number(tolRange.value);
      tolLabel.textContent = `${tolerance}%`;
    });
    // pressing a ribbon button must not steal focus from the text box mid-edit
    ribbon.addEventListener('pointerdown', (e) => {
      const t = e.target as HTMLElement;
      if (textBox && !t.closest('select, input')) e.preventDefault();
    });

    win.body.classList.add('pt');
    win.body.append(tabs, ribbon, work, status);
    showTab('home');
    syncRibbon();
    applyZoom();
    resetHistory();
    setDirty(false);

    if (typeof args.path === 'string') void openFile(args.path);
    setTimeout(() => win.body.focus({ preventScroll: true }), 50);

    return () => {
      closePopup();
      if (drag?.t === 'free' && drag.timer) clearInterval(drag.timer);
    };
  },
};
