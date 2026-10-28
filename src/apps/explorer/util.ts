import type { FileEntry } from '../../core/types';

/** Virtual location for the "Computer" view; real folders are plain VFS paths. */
export const COMPUTER = '::computer';
export const TRASH = '/Trash';
export const DRIVE_NAME = 'Local Disk (C:)';
/** The VFS has no quota, so the drive reports a fixed, believable capacity. */
export const DRIVE_CAPACITY = 64 * 1024 ** 3;

const PROTECTED = new Set(['/', '/Desktop', '/Documents', '/Pictures', '/Music', '/Trash']);
export const isProtected = (path: string): boolean => PROTECTED.has(path);

export interface Item {
  path: string;
  name: string;
  dir: boolean;
  modified: number;
  size: number;
  kind: string;
  /** Only kept for images — it is the thumbnail / preview source. */
  content: string;
  drive?: boolean;
}

const encoder = new TextEncoder();

const TEXT_EXT = new Set(['txt', 'md', 'log', 'json', 'csv', 'ini', 'cfg']);
const IMAGE_EXT = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp']);
const KINDS: Record<string, string> = {
  txt: 'Text Document',
  log: 'Text Document',
  md: 'Markdown Document',
  json: 'JSON File',
  csv: 'CSV File',
  ini: 'Configuration Settings',
  cfg: 'Configuration Settings',
  png: 'PNG Image',
  jpg: 'JPEG Image',
  jpeg: 'JPEG Image',
  gif: 'GIF Image',
  webp: 'WebP Image',
  bmp: 'Bitmap Image',
  svg: 'SVG Image',
};

export const extOf = (name: string): string => {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(i + 1).toLowerCase() : '';
};
export const isImage = (name: string): boolean => IMAGE_EXT.has(extOf(name));
export const isText = (name: string): boolean => TEXT_EXT.has(extOf(name));

export function kindOf(name: string, dir: boolean): string {
  if (dir) return 'File folder';
  const ext = extOf(name);
  return KINDS[ext] ?? (ext ? `${ext.toUpperCase()} File` : 'File');
}

export function toItem(e: FileEntry): Item {
  const dir = e.type === 'dir';
  return {
    path: e.path,
    name: e.name,
    dir,
    modified: e.modified,
    size: dir ? 0 : encoder.encode(e.content).length,
    kind: kindOf(e.name, dir),
    content: !dir && isImage(e.name) ? e.content : '',
  };
}

const urlCache = new Map<string, string>();

/** Image files are stored either as a data URL (png/jpg) or as raw SVG text. */
export function imageUrl(it: Item): string {
  const key = `${it.path}|${it.modified}`;
  let url = urlCache.get(key);
  if (!url) {
    url = it.content.startsWith('data:') ? it.content : `data:image/svg+xml;charset=utf-8,${encodeURIComponent(it.content)}`;
    if (urlCache.size > 200) urlCache.clear();
    urlCache.set(key, url);
  }
  return url;
}

/** Windows-style details-pane size: "1.52 KB". */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} ${bytes === 1 ? 'byte' : 'bytes'}`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let v = bytes / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u++;
  }
  return `${v < 10 ? v.toFixed(2) : v < 100 ? v.toFixed(1) : Math.round(v)} ${units[u]}`;
}

/** Windows-style Size column: whole kilobytes, at least 1 KB. */
export const formatSizeColumn = (bytes: number): string => `${Math.max(1, Math.ceil(bytes / 1024)).toLocaleString()} KB`;

export function formatDate(ms: number): string {
  if (!ms) return '';
  return new Date(ms).toLocaleString(undefined, { year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export const joinPath = (dir: string, name: string): string => (dir === '/' ? `/${name}` : `${dir}/${name}`);

export const plural = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`;
