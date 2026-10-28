import { icons } from '../../assets/icons';
import { basename } from '../../core/fs';
import type { AppManifest } from '../../core/types';
import { h } from '../../ui/dom';
import { showSheet } from '../../ui/sheet';
import './notepad.css';

const DOCS = '/Documents';

export const notepad: AppManifest = {
  id: 'notepad',
  name: 'Notepad',
  icon: icons.notepad,
  description: 'Write and save plain text',
  keywords: ['text', 'editor', 'write', 'note', 'txt'],
  pinned: true,
  desktop: true,
  window: { width: 620, height: 440, minWidth: 320, minHeight: 200 },

  mount({ win, args, fs, os }) {
    let path: string | null = null;
    let dirty = false;
    let wrap = true;

    const text = h('textarea', { class: 'np-text', spellcheck: false, wrap: 'soft' });
    const status = h('div', { class: 'np-status' });
    win.body.classList.add('np');
    win.body.append(text, status);

    const updateTitle = () => win.setTitle(`${dirty ? '• ' : ''}${path ? basename(path) : 'Untitled'} — Notepad`);
    const updateStatus = () => {
      const before = text.value.slice(0, text.selectionStart);
      const line = before.split('\n').length;
      const col = before.length - before.lastIndexOf('\n');
      status.textContent = `Ln ${line}, Col ${col}   ·   ${text.value.length} characters`;
    };
    const setDirty = (d: boolean) => {
      if (dirty !== d) {
        dirty = d;
        updateTitle();
      }
    };

    const load = async (p: string) => {
      const content = await fs.read(p);
      if (content === null) {
        os.notify('Notepad', `Couldn't find ${p}`, icons.notepad);
        return;
      }
      path = p;
      text.value = content;
      setDirty(false);
      updateTitle();
      updateStatus();
      text.focus();
    };

    const saveAs = () =>
      showSheet(win.body, (close) => {
        const input = h('input', { class: 'sheet-input', value: path ? basename(path) : 'Untitled.txt' });
        const submit = async () => {
          let name = input.value.trim().replace(/[\\/]/g, '-');
          if (!name) return;
          if (!/\.[a-z0-9]+$/i.test(name)) name += '.txt';
          path = `${DOCS}/${name}`;
          await fs.write(path, text.value);
          setDirty(false);
          updateTitle();
          close();
          text.focus();
        };
        input.addEventListener('keydown', (e) => e.key === 'Enter' && void submit());
        setTimeout(() => input.select(), 0);
        return h(
          'div',
          { class: 'sheet-form' },
          h('label', {}, 'Save As:'),
          input,
          h('div', { class: 'sheet-hint' }, `Where: ${DOCS}`),
          h('div', { class: 'sheet-actions' }, h('button', { class: 'btn', onclick: close }, 'Cancel'), h('button', { class: 'btn primary', onclick: submit }, 'Save')),
        );
      });

    const save = async () => {
      if (!path) return saveAs();
      await fs.write(path, text.value);
      setDirty(false);
    };

    const openDialog = async () => {
      const files = await fs.list(DOCS);
      showSheet(win.body, (close) => {
        const list = h('div', { class: 'sheet-list' });
        if (!files.length) list.append(h('div', { class: 'sheet-hint' }, 'No documents yet.'));
        for (const f of files) {
          list.append(
            h(
              'button',
              {
                class: 'sheet-file',
                ondblclick: () => {
                  close();
                  void load(f.path);
                },
                onclick: (e: MouseEvent) => {
                  list.querySelectorAll('.sel').forEach((n) => n.classList.remove('sel'));
                  (e.currentTarget as HTMLElement).classList.add('sel');
                },
                'data-path': f.path,
              },
              h('span', { html: icons.file }),
              h('span', { class: 'sheet-file-name' }, f.name),
              h('small', {}, new Date(f.modified).toLocaleString()),
            ),
          );
        }
        const openSel = () => {
          const sel = list.querySelector<HTMLElement>('.sel');
          if (!sel) return;
          close();
          void load(sel.dataset.path!);
        };
        return h(
          'div',
          { class: 'sheet-form' },
          h('label', {}, 'Open from Documents'),
          list,
          h('div', { class: 'sheet-actions' }, h('button', { class: 'btn', onclick: close }, 'Cancel'), h('button', { class: 'btn primary', onclick: openSel }, 'Open')),
        );
      });
    };

    const newDoc = () => {
      if (dirty || path) os.launch('notepad');
    };

    const buildMenus = () =>
      win.setMenus([
        {
          label: 'File',
          items: [
            { label: 'New', shortcut: 'Ctrl+N', action: newDoc },
            { label: 'Open…', shortcut: 'Ctrl+O', action: () => void openDialog() },
            { separator: true },
            { label: 'Save', shortcut: 'Ctrl+S', action: () => void save() },
            { label: 'Save As…', action: saveAs },
            { separator: true },
            { label: 'Close', action: () => win.close() },
          ],
        },
        {
          label: 'Edit',
          items: [
            { label: 'Select All', shortcut: 'Ctrl+A', action: () => text.select() },
            {
              label: 'Time/Date',
              shortcut: 'F5',
              action: () => text.setRangeText(new Date().toLocaleString(), text.selectionStart, text.selectionEnd, 'end'),
            },
          ],
        },
        {
          label: 'Format',
          items: [
            {
              label: 'Word Wrap',
              checked: wrap,
              action: () => {
                wrap = !wrap;
                text.wrap = wrap ? 'soft' : 'off';
                buildMenus();
              },
            },
          ],
        },
      ]);

    text.addEventListener('input', () => {
      setDirty(true);
      updateStatus();
    });
    text.addEventListener('keyup', updateStatus);
    text.addEventListener('click', updateStatus);
    win.body.addEventListener('keydown', (e) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void save();
      } else if (mod && e.key.toLowerCase() === 'o') {
        e.preventDefault();
        void openDialog();
      } else if (e.key === 'F5') {
        e.preventDefault();
        text.setRangeText(new Date().toLocaleString(), text.selectionStart, text.selectionEnd, 'end');
        setDirty(true);
      }
    });

    win.onBeforeClose(() => !dirty || confirm('You have unsaved changes. Close anyway?'));

    buildMenus();
    updateTitle();
    updateStatus();
    if (typeof args.path === 'string') void load(args.path);
    else if (args.openDialog) void openDialog();
    setTimeout(() => text.focus(), 50);
  },
};
