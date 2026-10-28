/**
 * Ribbon artwork for Paint. Every glyph is a self-contained 32x32 SVG (own gradients, ids prefixed `pt-`)
 * served as an <img> data URI, so duplicate ids across several Paint windows - or a minimized window -
 * can never break the gradients. All drawn from scratch: soft studio lighting, hairline edges.
 */
import { h } from '../../ui/dom';
import { HEART_PATH, POLY, type BrushKind, type ShapeKind } from './draw';

const DEFS = `<defs>
<linearGradient id="pt-bl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9ad0ff"/><stop offset="1" stop-color="#2468c8"/></linearGradient>
<linearGradient id="pt-bd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5b97e0"/><stop offset="1" stop-color="#173f86"/></linearGradient>
<linearGradient id="pt-st" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fafbfc"/><stop offset=".5" stop-color="#b8c3d0"/><stop offset="1" stop-color="#7a8696"/></linearGradient>
<linearGradient id="pt-wd" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f1d3a0"/><stop offset="1" stop-color="#b9803e"/></linearGradient>
<linearGradient id="pt-br" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e9b567"/><stop offset="1" stop-color="#a8681f"/></linearGradient>
<linearGradient id="pt-yl" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff0a0"/><stop offset=".55" stop-color="#f4c52c"/><stop offset="1" stop-color="#c98e08"/></linearGradient>
<linearGradient id="pt-rd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff9d8a"/><stop offset="1" stop-color="#cf2a16"/></linearGradient>
<linearGradient id="pt-pk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffd0d8"/><stop offset="1" stop-color="#e27a90"/></linearGradient>
<linearGradient id="pt-pp" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#dfe7f1"/></linearGradient>
<linearGradient id="pt-gl" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity=".95"/><stop offset="1" stop-color="#bcd9f5" stop-opacity=".55"/></linearGradient>
<radialGradient id="pt-hi" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#fff" stop-opacity=".85"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
</defs>`;

const E = 'stroke="#1b2d46" stroke-opacity=".5" stroke-width=".7"';
const INK = '#2a4a76';

function curve(t: number): [number, number] {
  // the cubic used by every brush-style sample: M5 24 C12 24 18 12 27 8
  const u = 1 - t;
  const p = [
    [5, 24],
    [12, 24],
    [18, 12],
    [27, 8],
  ] as const;
  return [
    u * u * u * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t * t * t * p[3][0],
    u * u * u * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t * t * t * p[3][1],
  ];
}

function brushSample(kind: BrushKind): string {
  if (kind === 'round') return `<path d="M5 24C12 24 18 12 27 8" fill="none" stroke="${INK}" stroke-width="5.2" stroke-linecap="round"/>`;
  let out = '';
  if (kind === 'cal1' || kind === 'cal2') {
    const s = kind === 'cal1' ? 1 : -1;
    for (let i = 0; i <= 26; i++) {
      const [x, y] = curve(i / 26);
      out += `<path d="M${(x - 3 * s).toFixed(1)} ${(y + 3).toFixed(1)}L${(x + 3 * s).toFixed(1)} ${(y - 3).toFixed(1)}" stroke="${INK}" stroke-width="2.2"/>`;
    }
    return out;
  }
  if (kind === 'air' || kind === 'crayon') {
    const n = kind === 'air' ? 120 : 190;
    const rad = kind === 'air' ? 6.5 : 4.6;
    for (let i = 0; i < n; i++) {
      const t = (i + 0.5) / n;
      const [x, y] = curve(t);
      const a = Math.sin(i * 12.9898) * 43758.5453;
      const b = Math.sin(i * 78.233) * 12543.123;
      const ra = a - Math.floor(a);
      const rb = b - Math.floor(b);
      const d = rad * (kind === 'air' ? ra ** 1.5 : Math.sqrt(ra));
      const ang = rb * Math.PI * 2;
      out += `<rect x="${(x + Math.cos(ang) * d).toFixed(1)}" y="${(y + Math.sin(ang) * d).toFixed(1)}" width="${kind === 'air' ? 0.9 : 1.2}" height="${
        kind === 'air' ? 0.9 : 1.2
      }" fill="${INK}" opacity="${(0.45 + 0.5 * ra).toFixed(2)}"/>`;
    }
    return out;
  }
  // oil: bristle streaks
  for (let i = 0; i < 7; i++) {
    const o = (i - 3) * 1.5;
    out += `<path d="M5 24C12 24 18 12 27 8" transform="translate(${o.toFixed(1)} ${(-o).toFixed(1)})" fill="none" stroke="${INK}" stroke-width="${
      1.2 + (i % 3) * 0.5
    }" stroke-linecap="round" opacity="${(0.55 + 0.4 * (((i * 7) % 5) / 4)).toFixed(2)}"/>`;
  }
  return out;
}

function shapeGlyph(kind: ShapeKind): string {
  const st = `fill="#dbe9f9" fill-opacity=".7" stroke="${INK}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"`;
  switch (kind) {
    case 'line':
      return `<path d="M5 27L27 5" fill="none" stroke="${INK}" stroke-width="2" stroke-linecap="round"/>`;
    case 'ellipse':
      return `<ellipse cx="16" cy="16" rx="12" ry="9" ${st}/>`;
    case 'rect':
      return `<rect x="5" y="7" width="22" height="18" ${st}/>`;
    case 'round':
      return `<rect x="4.5" y="7" width="23" height="18" rx="5" ${st}/>`;
    case 'heart':
      return `<path transform="translate(4 4) scale(24)" d="${HEART_PATH}" ${st.replace('1.8', '.08')}/>`;
    default: {
      const pts = POLY[kind]!.map(([x, y]) => `${(4 + x * 24).toFixed(1)},${(4 + y * 24).toFixed(1)}`).join(' ');
      return `<polygon points="${pts}" ${st}/>`;
    }
  }
}

function wedges(): string {
  const cols = ['#e8362a', '#f59a1c', '#f4dc2c', '#3fb43a', '#2a9be0', '#7a49c9'];
  let out = '';
  for (let i = 0; i < 6; i++) {
    const a0 = (i * Math.PI) / 3 - Math.PI / 2;
    const a1 = a0 + Math.PI / 3;
    const p = (a: number) => `${(16 + 12.5 * Math.cos(a)).toFixed(2)} ${(16 + 12.5 * Math.sin(a)).toFixed(2)}`;
    out += `<path d="M16 16L${p(a0)}A12.5 12.5 0 0 1 ${p(a1)}Z" fill="${cols[i]}"/>`;
  }
  return out;
}

const ART = {
  paste: `<rect x="4" y="6" width="19" height="23" rx="2.5" fill="url(#pt-br)" ${E}/><rect x="9" y="3" width="9" height="6.5" rx="1.8" fill="url(#pt-st)" ${E}/><rect x="11" y="11.5" width="18" height="18" rx="1" fill="url(#pt-pp)" ${E}/><path d="M14 16.5h12M14 20.5h12M14 24.5h8" stroke="#6a93c9" stroke-width="1.3" stroke-linecap="round"/>`,
  cut: `<path d="M9.4 3h2.7l9.2 16-2.5 1.6z" fill="url(#pt-st)" ${E}/><path d="M22.6 3h-2.7l-9.2 16 2.5 1.6z" fill="url(#pt-st)" ${E}/><circle cx="11" cy="25" r="3.5" fill="none" stroke="url(#pt-rd)" stroke-width="2.6"/><circle cx="21" cy="25" r="3.5" fill="none" stroke="url(#pt-rd)" stroke-width="2.6"/><circle cx="16" cy="17" r="1.1" fill="#586373"/>`,
  copy: `<path d="M5 4h13l4 4v16H5z" fill="url(#pt-pp)" ${E}/><path d="M18 4v4h4" fill="none" ${E}/><path d="M12 10h12l5 5v15H12z" fill="url(#pt-pp)" ${E}/><path d="M24 10v5h5" fill="none" ${E}/><path d="M15.5 20.5h10M15.5 24h10M15.5 27.5h6" stroke="#6a93c9" stroke-width="1.3" stroke-linecap="round"/>`,
  select: `<rect x="5" y="7" width="22" height="18" fill="#cfe5fb" fill-opacity=".65" stroke="#2468c8" stroke-width="1.5" stroke-dasharray="3.2 2.4"/>`,
  crop: `<rect x="9" y="9" width="14" height="14" fill="#cfe5fb" fill-opacity=".75"/><path d="M8 2v22h22M2 8h22v22" fill="none" stroke="#35506f" stroke-width="2.6" stroke-linejoin="miter"/>`,
  resize: `<rect x="4" y="4" width="24" height="24" fill="none" stroke="#8aa0bb" stroke-width="1.3" stroke-dasharray="3 2.4"/><rect x="4" y="16" width="12" height="12" fill="url(#pt-bl)" ${E}/><path d="M18 14L26 6M26 6h-6M26 6v6" fill="none" stroke="#25507f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`,
  rotate: `<rect x="11" y="13" width="10" height="8" rx="1" fill="url(#pt-bl)" ${E}/><path d="M6.5 16A9.5 9.5 0 0 1 23.5 10.5" fill="none" stroke="#25507f" stroke-width="2.6" stroke-linecap="round"/><path d="M28 5.5L27.6 15 19.5 11.8z" fill="#25507f"/>`,
  pencil: `<g transform="rotate(45 16 16)"><rect x="13" y="1.5" width="6" height="4" rx="1.4" fill="url(#pt-pk)" ${E}/><rect x="12.8" y="5" width="6.4" height="3" fill="url(#pt-st)" ${E}/><rect x="13" y="8" width="6" height="14" fill="url(#pt-yl)" ${E}/><path d="M13 22h6l-3 7z" fill="url(#pt-wd)" ${E}/><path d="M15 26.6h2L16 29z" fill="#3a3f48"/></g>`,
  fill: `<path d="M7.5 12.5L10 25.5Q16 29 22 25.5L24.5 12.5z" fill="url(#pt-st)" ${E}/><ellipse cx="16" cy="12.5" rx="8.5" ry="3.2" fill="#e5ebf2" ${E}/><ellipse cx="16" cy="12.8" rx="6.6" ry="2.2" fill="url(#pt-bl)"/><path d="M8 12.5C5 3.5 27 3.5 24 12.5" fill="none" stroke="#7d8999" stroke-width="1.4"/><path d="M27.5 19.5q-2.8 4.2 0 6.2q2.8-2 0-6.2z" fill="url(#pt-bl)" ${E}/>`,
  text: `<path fill-rule="evenodd" d="M16 3.5L6 28h4.2l2.1-5.4h7.4l2.1 5.4H26zM13.6 19.3L16 12.8l2.4 6.5z" fill="url(#pt-bd)" ${E}/>`,
  eraser: `<g transform="rotate(-35 16 16)"><rect x="5" y="10" width="22" height="12" rx="2.2" fill="url(#pt-pk)" ${E}/><path d="M5 12.2a2.2 2.2 0 0 1 2.2-2.2H13v12H7.2A2.2 2.2 0 0 1 5 19.8z" fill="url(#pt-bd)" ${E}/><path d="M6 11h20" stroke="#fff" stroke-opacity=".6"/></g>`,
  picker: `<g transform="rotate(42 16 16)"><rect x="12.5" y="1.5" width="7" height="6" rx="3" fill="#43505f" ${E}/><rect x="13.8" y="7" width="4.4" height="14" rx="1" fill="url(#pt-gl)" ${E}/><rect x="14.3" y="14" width="3.4" height="7" fill="url(#pt-bl)"/><path d="M14 21h4l-2 8.5z" fill="url(#pt-gl)" ${E}/></g>`,
  magnifier: `<path d="M20 20l8 8" stroke="url(#pt-br)" stroke-width="4.6" stroke-linecap="round"/><circle cx="13" cy="13" r="8.4" fill="url(#pt-gl)" stroke="url(#pt-st)" stroke-width="2.6"/><circle cx="13" cy="13" r="9.6" fill="none" stroke="#1b2d46" stroke-opacity=".45" stroke-width=".7"/>`,
  brush: `<g transform="rotate(40 16 16)"><rect x="13.6" y="1.5" width="4.8" height="15" rx="2.4" fill="url(#pt-bd)" ${E}/><rect x="13.1" y="15.5" width="5.8" height="6" fill="url(#pt-st)" ${E}/><path d="M13.1 21.5C12.6 27 14 30 16 30.5c2-.5 3.4-3.5 2.9-9z" fill="url(#pt-bl)" ${E}/></g>`,
  zoomin: `<path d="M20 20l8 8" stroke="url(#pt-br)" stroke-width="4.6" stroke-linecap="round"/><circle cx="13" cy="13" r="8.4" fill="url(#pt-gl)" stroke="url(#pt-st)" stroke-width="2.6"/><path d="M9 13h8M13 9v8" stroke="#25507f" stroke-width="2" stroke-linecap="round"/>`,
  zoomout: `<path d="M20 20l8 8" stroke="url(#pt-br)" stroke-width="4.6" stroke-linecap="round"/><circle cx="13" cy="13" r="8.4" fill="url(#pt-gl)" stroke="url(#pt-st)" stroke-width="2.6"/><path d="M9 13h8" stroke="#25507f" stroke-width="2" stroke-linecap="round"/>`,
  zoom100: `<path d="M20 20l8 8" stroke="url(#pt-br)" stroke-width="4.6" stroke-linecap="round"/><circle cx="13" cy="13" r="8.4" fill="url(#pt-gl)" stroke="url(#pt-st)" stroke-width="2.6"/><path d="M9.5 11.5h7M9.5 14.5h7" stroke="#25507f" stroke-width="1.8" stroke-linecap="round"/>`,
  size: `<g fill="${INK}"><rect x="3" y="5" width="26" height="1.4" rx=".5"/><rect x="3" y="10" width="26" height="3" rx="1"/><rect x="3" y="16.5" width="26" height="5" rx="1.5"/><rect x="3" y="24" width="26" height="7" rx="2"/></g>`,
  outline: `<rect x="5" y="6" width="22" height="20" rx="2" fill="none" stroke="${INK}" stroke-width="3"/>`,
  fillcol: `<rect x="5" y="6" width="22" height="20" rx="2" fill="url(#pt-bl)" ${E}/><rect x="5" y="6" width="22" height="10" rx="2" fill="url(#pt-hi)"/>`,
  editcolors: `${wedges()}<circle cx="16" cy="16" r="12.5" fill="url(#pt-hi)"/><circle cx="16" cy="16" r="12.9" fill="none" stroke="#1b2d46" stroke-opacity=".5" stroke-width=".8"/><circle cx="16" cy="16" r="3.6" fill="#fff" ${E}/>`,
  save: `<path d="M4 6a2 2 0 0 1 2-2h18l4 4v18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" fill="url(#pt-bd)" ${E}/><rect x="9" y="4.5" width="13" height="8" rx="1" fill="url(#pt-st)" ${E}/><rect x="17.5" y="5.8" width="2.8" height="5" fill="#506074"/><rect x="8" y="17" width="16" height="11" rx="1" fill="url(#pt-pp)" ${E}/><path d="M10.5 21h11M10.5 24.5h11" stroke="#6a93c9" stroke-width="1.2"/>`,
  undo: `<path d="M10 10.5H19a7 7 0 0 1 0 14H11" fill="none" stroke="url(#pt-bd)" stroke-width="3.4" stroke-linecap="round"/><path d="M3.5 10.5L12 4.5v12z" fill="#2468c8"/>`,
  redo: `<path d="M22 10.5H13a7 7 0 0 0 0 14h8" fill="none" stroke="url(#pt-bd)" stroke-width="3.4" stroke-linecap="round"/><path d="M28.5 10.5L20 4.5v12z" fill="#2468c8"/>`,
  cursor: `<path d="M9 4v21l5.2-4.6 3.6 7.4 3.4-1.6-3.6-7.2H23z" fill="#fff" stroke="#243142" stroke-width="1.8" stroke-linejoin="round"/>`,
  selsize: `<rect x="5" y="8" width="22" height="16" fill="none" stroke="#243142" stroke-width="2" stroke-dasharray="4 3"/>`,
  canvassize: `<rect x="5" y="5" width="22" height="22" fill="none" stroke="#243142" stroke-width="2.2"/><path d="M5 27L13 19M5 27h6M5 27v-6M27 5L19 13M27 5h-6M27 5v6" fill="none" stroke="#243142" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`,
};

export type GlyphName = keyof typeof ART | `brush-${BrushKind}` | `shape-${ShapeKind}`;

const cache = new Map<string, string>();

function artFor(name: GlyphName): string {
  if (name.startsWith('brush-')) return brushSample(name.slice(6) as BrushKind);
  if (name.startsWith('shape-')) return shapeGlyph(name.slice(6) as ShapeKind);
  return ART[name as keyof typeof ART];
}

export function glyphUri(name: GlyphName): string {
  let uri = cache.get(name);
  if (!uri) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">${DEFS}${artFor(name)}</svg>`;
    uri = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    cache.set(name, uri);
  }
  return uri;
}

export function glyph(name: GlyphName, size = 16): HTMLImageElement {
  return h('img', { class: 'pt-gl', src: glyphUri(name), width: size, height: size, alt: '', draggable: false });
}
