/** Picture files in the virtual disk: PNG/JPEG hold a data URL as text, SVG holds raw markup. */
import type { FileEntry, VFS } from '../../core/types';

export const PICS = '/Pictures';
export const IMG_RE = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;
/** Formats Paint can write back. Anything else (e.g. an opened SVG) is saved as a new PNG. */
export const SAVE_RE = /\.(png|jpe?g)$/i;

const isSvg = (s: string) => /<svg[\s>]/i.test(s);

export interface ImageUrl {
  url: string;
  revoke: () => void;
}

export function contentToUrl(content: string): ImageUrl | null {
  if (content.startsWith('data:image')) return { url: content, revoke: () => {} };
  if (isSvg(content)) {
    const url = URL.createObjectURL(new Blob([content], { type: 'image/svg+xml' }));
    return { url, revoke: () => URL.revokeObjectURL(url) };
  }
  return null;
}

export async function loadImage(content: string): Promise<HTMLImageElement | null> {
  const src = contentToUrl(content);
  if (!src) return null;
  try {
    const img = new Image();
    img.src = src.url;
    await img.decode();
    return img;
  } catch {
    return null;
  } finally {
    // decode() has finished, so the bitmap no longer needs the Blob URL
    src.revoke();
  }
}

export async function listPictures(fs: VFS): Promise<FileEntry[]> {
  await fs.mkdir(PICS);
  const files = await fs.list(PICS);
  return files.filter((f) => f.type !== 'dir' && IMG_RE.test(f.name)).sort((a, b) => a.name.localeCompare(b.name));
}
