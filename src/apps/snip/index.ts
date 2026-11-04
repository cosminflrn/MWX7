import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import './snip.css';

const icon = `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="10" width="52" height="38" rx="4" fill="#e8f1fb" stroke="#4a6f9c" stroke-width="2.5" stroke-dasharray="6 4"/><circle cx="20" cy="50" r="7" fill="none" stroke="#c0392b" stroke-width="4"/><circle cx="44" cy="50" r="7" fill="none" stroke="#c0392b" stroke-width="4"/><path d="M24 44 L42 22 M40 44 L22 22" stroke="#6d7b8c" stroke-width="4" stroke-linecap="round"/></svg>`;

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

export const snip: AppManifest = {
  id: 'snip',
  name: 'Snipping Tool',
  icon,
  description: 'Capture a part of the screen',
  keywords: ['screenshot', 'capture', 'screen', 'crop'],
  singleInstance: true,
  window: { width: 560, height: 420, minWidth: 380, minHeight: 280 },

  mount({ win, fs, os }) {
    win.body.classList.add('snip');
    let png: string | null = null;
    let overlay: HTMLElement | null = null;

    const status = h('span', { class: 'snip-status' }, 'Click New, then drag a rectangle around what you want to capture.');
    const stage = h('div', { class: 'snip-stage' }, h('div', { class: 'snip-empty' }, 'Nothing captured yet.'));
    const btnNew = h('button', { class: 'btn snip-new', type: 'button' }, 'New');
    const btnSave = h('button', { class: 'btn snip-save', type: 'button', disabled: true }, 'Save snip');
    const btnCopy = h('button', { class: 'btn snip-copy', type: 'button', disabled: true }, 'Copy');
    win.body.append(h('div', { class: 'snip-bar' }, btnNew, btnSave, btnCopy), stage, h('div', { class: 'snip-foot' }, status));

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
      const dim = h('div', { class: 'snip-overlay' }, h('div', { class: 'snip-hint' }, 'Drag to select an area. Right-click to cancel.'));
      const box = h('div', { class: 'snip-sel' });
      dim.append(box);
      overlay = dim;
      document.body.append(dim);
      let x0 = 0;
      let y0 = 0;
      let drag = false;
      const rectOf = (e: PointerEvent) => ({ x: Math.min(x0, e.clientX), y: Math.min(y0, e.clientY), w: Math.abs(e.clientX - x0), h: Math.abs(e.clientY - y0) });
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
        drag = true;
        x0 = e.clientX;
        y0 = e.clientY;
        dim.setPointerCapture(e.pointerId);
        dim.classList.add('dragging');
      });
      dim.addEventListener('pointermove', (e) => {
        if (!drag) return;
        const r = rectOf(e);
        box.style.cssText = `left:${r.x}px;top:${r.y}px;width:${r.w}px;height:${r.h}px`;
      });
      dim.addEventListener('pointerup', (e) => {
        if (!drag) return;
        const r = rectOf(e);
        end();
        if (r.w < 4 || r.h < 4) return;
        setTimeout(() => void capture(r), 120); // let the dim overlay leave the frame
      });
    };
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
