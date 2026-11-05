import { png } from '../../assets/icons';
import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import { menuIcon, openMenu } from '../../ui/menu';
import './snip.css';

const icon = png('snip');

const stamp = () => new Date().toISOString().slice(0, 19).replace('T', ' ').replace(/:/g, '-');

/** Grab one frame of this tab through the browser's own capture (the DOM can't be rasterised faithfully). */
async function grabTab(): Promise<HTMLVideoElement> {
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, preferCurrentTab: true } as DisplayMediaStreamOptions);
  const v = document.createElement('video');
  v.srcObject = stream;
  v.muted = true;
  await v.play();
  await new Promise((r) => setTimeout(r, 250)); // let the first real frame arrive
  return v;
}

type Mode = 'rect' | 'window' | 'full';
const MODES: Record<Mode, string> = { rect: 'Rectangular Snip', window: 'Window Snip', full: 'Full-screen Snip' };

export const impl: Pick<AppManifest, 'mount'> = {
  mount({ win, fs, os }) {
    win.body.classList.add('snip');
    let png: string | null = null;
    let overlay: HTMLElement | null = null;

    let mode: Mode = 'rect';
    const status = h('span', { class: 'snip-status' }, 'Click New to capture. The arrow picks rectangle, window or full screen.');
    const stage = h(
      'div',
      { class: 'snip-stage' },
      h('div', { class: 'snip-empty', html: `${icon}<b>No snip yet</b><span>Click New and drag around what you want to capture.</span>` }),
    );
    const tb = (label: string, ic: string, cls: string) =>
      h('button', { class: `snip-btn ${cls}`, type: 'button' }, h('img', { src: menuIcon(ic), alt: '', draggable: 'false' }), label);
    const btnNew = tb('New', 'new-file', 'snip-new');
    const btnMode = h('button', { class: 'snip-btn snip-mode', type: 'button', title: 'Snip type', 'aria-label': 'Snip type', html: '<svg viewBox="0 0 8 5" width="8" height="5"><path d="M0 0h8L4 5z" fill="currentColor"/></svg>' });
    const btnSave = tb('Save', 'open', 'snip-save');
    const btnCopy = tb('Copy', 'copy', 'snip-copy');
    btnSave.disabled = btnCopy.disabled = true;
    win.body.append(
      h('div', { class: 'snip-bar' }, h('span', { class: 'snip-split' }, btnNew, btnMode), h('span', { class: 'snip-sep' }), btnSave, btnCopy),
      stage,
      h('div', { class: 'snip-foot' }, status),
    );

    const show = (url: string) => {
      png = url;
      stage.replaceChildren(h('img', { class: 'snip-img', src: url, alt: 'Captured snip', draggable: 'false' }));
      btnSave.disabled = btnCopy.disabled = false;
    };

    const capture = async (r: { x: number; y: number; w: number; h: number }) => {
      status.textContent = 'Choose this tab in the browser prompt to capture it…';
      let video: HTMLVideoElement | null = null;
      try {
        video = await grabTab();
        const k = video.videoWidth / window.innerWidth;
        const c = document.createElement('canvas');
        c.width = Math.max(1, Math.round(r.w * k));
        c.height = Math.max(1, Math.round(r.h * k));
        c.getContext('2d')!.drawImage(video, r.x * k, r.y * k, r.w * k, r.h * k, 0, 0, c.width, c.height);
        show(c.toDataURL('image/png'));
        status.textContent = `Captured ${c.width} × ${c.height}.`;
      } catch {
        status.textContent = 'Screen capture was not allowed, so no snip was taken. Click New and allow capturing this tab to try again.';
      } finally {
        (video?.srcObject as MediaStream | null)?.getTracks().forEach((t) => t.stop());
      }
    };

    const startSnip = () => {
      if (overlay) return;
      if (mode === 'full') {
        void capture({ x: 0, y: 0, w: window.innerWidth, h: window.innerHeight });
        return;
      }
      const hint = mode === 'window' ? 'Click a window to capture it. Right-click to cancel.' : 'Drag to select an area. Right-click to cancel.';
      const dim = h('div', { class: `snip-overlay snip-${mode}` }, h('div', { class: 'snip-hint' }, hint));
      const box = h('div', { class: 'snip-sel' });
      dim.append(box);
      overlay = dim;
      document.body.append(dim);
      let x0 = 0;
      let y0 = 0;
      let drag = false;
      let target: DOMRect | null = null;
      const rectOf = (e: PointerEvent) => ({ x: Math.min(x0, e.clientX), y: Math.min(y0, e.clientY), w: Math.abs(e.clientX - x0), h: Math.abs(e.clientY - y0) });
      const place = (r: { x: number; y: number; w: number; h: number }) => {
        box.style.cssText = `left:${r.x}px;top:${r.y}px;width:${r.w}px;height:${r.h}px`;
      };
      // The overlay covers everything, so look underneath it for the window the pointer is over.
      const windowAt = (x: number, y: number): DOMRect | null => {
        for (const el of document.elementsFromPoint(x, y)) {
          if (el === dim || dim.contains(el)) continue;
          const w = el.closest<HTMLElement>('.win');
          return w ? w.getBoundingClientRect() : null;
        }
        return null;
      };
      const end = () => {
        dim.remove();
        overlay = null;
      };
      dim.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        end();
      });
      dim.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        if (mode === 'window') return;
        drag = true;
        x0 = e.clientX;
        y0 = e.clientY;
        dim.setPointerCapture(e.pointerId);
        dim.classList.add('dragging');
      });
      dim.addEventListener('pointermove', (e) => {
        if (mode === 'window') {
          target = windowAt(e.clientX, e.clientY);
          dim.classList.toggle('dragging', !!target);
          if (target) place({ x: target.left, y: target.top, w: target.width, h: target.height });
          return;
        }
        if (drag) place(rectOf(e));
      });
      dim.addEventListener('pointerup', (e) => {
        if (e.button !== 0) return;
        let r: { x: number; y: number; w: number; h: number } | null = null;
        if (mode === 'window') {
          const t = windowAt(e.clientX, e.clientY);
          if (t) r = { x: Math.max(0, t.left), y: Math.max(0, t.top), w: Math.min(t.width, window.innerWidth - t.left), h: Math.min(t.height, window.innerHeight - t.top) };
        } else if (drag) r = rectOf(e);
        end();
        if (!r || r.w < 4 || r.h < 4) return;
        const rr = r;
        setTimeout(() => void capture(rr), 120); // let the overlay leave the frame
      });
    };
    btnMode.addEventListener('click', () => {
      const b = btnMode.getBoundingClientRect();
      openMenu(
        (Object.keys(MODES) as Mode[]).map((m) => ({ label: MODES[m], checked: mode === m, action: () => ((mode = m), startSnip()) })),
        { x: b.left - 40, y: b.bottom + 2 },
      );
    });
    btnNew.addEventListener('click', startSnip);

    btnSave.addEventListener('click', async () => {
      if (!png) return;
      const path = `/Pictures/Snip ${stamp()}.png`;
      await fs.mkdir('/Pictures');
      await fs.write(path, png);
      os.addRecent(path);
      status.textContent = `Saved to ${path}`;
      os.notify('Snipping Tool', 'Snip saved to Pictures.', icon);
    });
    btnCopy.addEventListener('click', async () => {
      if (!png) return;
      try {
        const blob = await (await fetch(png)).blob();
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
        status.textContent = 'Copied to the clipboard.';
      } catch {
        status.textContent = 'The browser would not let us copy the image. Use Save snip instead.';
      }
    });

    return () => overlay?.remove();
  },
};
