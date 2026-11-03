import { h } from '../../ui/dom';

/** "How to play" popup: a glossy Win7-style dialog laid over the app window, shown on every open. Selectors are scoped under `scope`. */
export function showTutorial(body: HTMLElement, scope: string, title: string, lines: string[], onClose?: () => void): void {
  const css = `
.${scope} .gt-back { position: absolute; inset: 0; z-index: 50; display: grid; place-items: center; background: rgba(10, 25, 50, 0.35); font: 12px/1.4 var(--font-ui); }
.${scope} .gt-dlg { width: min(300px, 92%); border: 1px solid #5d7fa8; border-radius: 6px; background: linear-gradient(#fbfdff, #e8f0fa); color: #1c2b3f; box-shadow: 0 8px 26px rgba(0, 20, 50, 0.55), inset 0 0 0 1px rgba(255, 255, 255, 0.8); overflow: hidden; }
.${scope} .gt-title { padding: 6px 12px; font-weight: 600; color: #0f3f86; background: linear-gradient(#e9f3fd, #c9ddf3 50%, #b9d1ec 51%, #d3e5f7); border-bottom: 1px solid #9db8d8; }
.${scope} .gt-list { margin: 0; padding: 10px 14px 6px 28px; display: grid; gap: 4px; }
.${scope} .gt-foot { display: flex; justify-content: flex-end; padding: 8px 12px; background: linear-gradient(#f2f6fb, #dfe9f5); border-top: 1px solid #c6d5e8; }
.${scope} .gt-ok { min-width: 78px; height: 24px; border: 1px solid #1c4e8f; border-radius: 4px; color: #fff; font: 600 12px var(--font-ui); text-shadow: 0 1px 1px rgba(0, 30, 80, 0.55); cursor: pointer; background: linear-gradient(#7db6ee 0%, #4a8fd9 48%, #2a6fc4 52%, #3d8ae0 100%); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.55); }
.${scope} .gt-ok:hover { background: linear-gradient(#a2d0f8 0%, #6aa9ec 48%, #3d84dc 52%, #62adf2 100%); }`;
  const ok = h('button', { class: 'gt-ok' }, 'Got it');
  const back = h('div', { class: 'gt-back', role: 'dialog', 'aria-label': title },
    h('style', {}, css),
    h('div', { class: 'gt-dlg' },
      h('div', { class: 'gt-title' }, title),
      h('ul', { class: 'gt-list' }, ...lines.map((l) => h('li', {}, l))),
      h('div', { class: 'gt-foot' }, ok)));
  ok.addEventListener('click', () => { back.remove(); onClose?.(); });
  body.append(back);
  ok.focus();
}
