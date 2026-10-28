/** Win7-style dialogs, shown as sheets that slide from the title bar (see ui/sheet.ts). */
import { h } from '../../ui/dom';
import { showSheet } from '../../ui/sheet';
import { contentToUrl, listPictures } from './files';
import type { FileEntry, VFS } from '../../core/types';

export interface DlgBtn {
  label: string;
  primary?: boolean;
  /** Return false to keep the dialog open (e.g. validation failed). */
  action: (close: () => void) => void | boolean | Promise<void | boolean>;
}

export function dialog(host: HTMLElement, title: string, body: Node[], buttons: DlgBtn[], width = 360): () => void {
  // hand focus back to the window unless another sheet (the closing one is still animating out) took over
  const refocus = () => setTimeout(() => host.querySelectorAll('.sheet-backdrop').length <= 1 && host.focus({ preventScroll: true }), 0);
  const close = showSheet(host, (close) => {
    const run = async (b: DlgBtn) => {
      if ((await b.action(close)) !== false) {
        close();
        refocus();
      }
    };
    const root = h(
      'div',
      { class: 'sheet-form pt-dlg', style: `width:${width}px;max-width:100%` },
      h('div', { class: 'pt-dlg-body' }, h('div', { class: 'pt-dlg-title' }, title), ...body),
      h(
        'div',
        { class: 'sheet-actions' },
        ...buttons.map((b) => h('button', { class: `btn${b.primary ? ' primary' : ''}`, type: 'button', onclick: () => void run(b) }, b.label)),
      ),
    );
    const primary = buttons.find((b) => b.primary);
    root.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') refocus();
      const t = e.target as HTMLElement;
      if (e.key === 'Enter' && primary && t.tagName !== 'BUTTON' && t.tagName !== 'SELECT') {
        e.preventDefault();
        void run(primary);
      }
    });
    return root;
  });
  return () => {
    close();
    refocus();
  };
}

/** Browse /Pictures with thumbnails. `onPick` gets the chosen file. */
export async function pickPicture(host: HTMLElement, fs: VFS, title: string, okLabel: string, onPick: (f: FileEntry) => void): Promise<void> {
  const files = await listPictures(fs);
  const urls: (() => void)[] = [];
  const list = h('div', { class: 'pt-files', role: 'listbox', tabindex: 0 });
  let selected: FileEntry | null = null;
  let choose: (f: FileEntry) => void = () => {};

  if (!files.length) list.append(h('div', { class: 'sheet-hint', style: 'padding:10px' }, 'There are no pictures in this folder yet.'));
  for (const f of files) {
    const u = contentToUrl(f.content);
    if (u) urls.push(u.revoke);
    const row = h(
      'div',
      {
        class: 'pt-file',
        role: 'option',
        onclick: () => {
          list.querySelectorAll('.sel').forEach((n) => n.classList.remove('sel'));
          row.classList.add('sel');
          selected = f;
        },
        ondblclick: () => {
          choose(f);
        },
      },
      h('span', { class: 'pt-thumb' }, u ? h('img', { src: u.url, alt: '', draggable: false }) : null),
      h('span', { class: 'pt-file-name' }, f.name),
      h('small', {}, new Date(f.modified).toLocaleDateString()),
    );
    list.append(row);
  }

  const close = dialog(
    host,
    title,
    [h('label', {}, 'Look in: Pictures'), list],
    [
      {
        label: okLabel,
        primary: true,
        action: (close) => {
          if (!selected) return false;
          const f = selected;
          close();
          onPick(f);
        },
      },
      { label: 'Cancel', action: () => {} },
    ],
    420,
  );
  choose = (f) => {
    close();
    onPick(f);
  };
  // thumbnails own Blob URLs; release them shortly after the sheet is gone
  const obs = new MutationObserver(() => {
    if (!host.querySelector('.pt-files')) {
      urls.forEach((r) => r());
      obs.disconnect();
    }
  });
  obs.observe(host, { childList: true });
}
