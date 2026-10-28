# MWX7 — Product & Technical Spec

> The dream desktop: **macOS polish, Windows XP warmth, Windows 7 glass** — in one browser tab, hosted on GitHub Pages.

## 1. Design direction (fixed hybrid)

MWX7 is **one** coherent design, not a theme switcher. Each part borrows the best idea from one OS:

| Area | Source | MWX7 behaviour |
|---|---|---|
| Global menu bar | macOS | Top bar shows the focused app's menus, plus Spotlight and the clock |
| Dock | macOS + Win7 | Centered glass dock with magnification and launch bounce; Win7 superbar rules: click focused app = minimize, glow under running apps, right-click = jump list |
| Start orb + Start menu | XP + Win7 | Glowing orb as the first dock item; XP two-column menu (apps left, places right, user header, Log Off / Turn Off footer) |
| Window frames | Win7 | Aero glass frame around a white content pane, glossy title highlight |
| Window controls | macOS | Traffic lights on the left, glyphs on hover |
| Window management | Win7 | Aero Snap (drag to edges), shake/peek later |
| Search | macOS | Spotlight overlay, `Ctrl+Space` |
| Notifications | macOS | Glass banners top-right |
| Dialogs | macOS | Sheets slide down from the title bar |
| Desktop icons | XP | Left column, single-click select, double-click open |
| Moments | XP + Win7 | Boot screen with marching bar, XP "welcome" log-off screen, Win7 shutdown |

**Originality rule:** recreate the *feel*, never the assets. No Apple/Microsoft logos, icons, wallpapers (no Bliss), sounds, cursors or shipped system fonts. All artwork lives in `src/assets/` and `src/shell/wallpapers.ts` and is original SVG/CSS.

## 2. Architecture

```
src/
  main.ts              boot sequence: defs → apps → fs seed → shell → boot screen
  core/                NO DOM UI here except the window frame
    types.ts           ← the public contract (AppManifest, AppContext, WindowHandle, VFS, OSApi)
    events.ts          typed event bus
    wm.ts              window manager (open/focus/minimize/close, drag, resize, snap)
    os.ts              launch(), notify(), the OSApi object handed to apps
    registry.ts        app registry
    fs.ts              virtual filesystem (localStorage now, IndexedDB later — same async API)
    settings.ts        persisted user settings
  shell/               desktop, menubar, dock, startmenu, spotlight, notifications, screens, wallpapers
  ui/                  shared helpers: dom.ts (h()), menu.ts (popup menus), sheet.ts
  apps/<id>/           one folder per app: index.ts (+ optional <id>.css)
  styles/              tokens.css (design tokens), base, window, shell
  assets/icons.ts      original SVG icon set + shared gradient defs
```

### Dependency rules
- `apps/*` may import: `core/types`, `ui/*`, `assets/*`, and `core/fs` path helpers. **Never** `core/wm`, `core/os` or another app — use `ctx.os` / `ctx.fs`.
- `shell/*` may import `core/*` and `ui/*`, never `apps/*`.
- `core/*` never imports `shell/*` or `apps/*`. Shell ↔ core talk through the event bus.

## 3. The app contract

```ts
export const myApp: AppManifest = {
  id: 'my-app', name: 'My App', icon: icons.myApp,
  description: 'One line for Start menu & Spotlight',
  keywords: ['extra', 'search', 'words'],
  pinned: false, desktop: false, singleInstance: false,
  window: { width: 600, height: 420, minWidth: 300, minHeight: 200, resizable: true },
  mount({ win, args, fs, os }) {
    win.body.append(/* your UI */);
    win.setTitle('…'); win.setMenus([{ label: 'File', items: [...] }]);
    win.onBeforeClose(() => true);   // return false to cancel
    return () => { /* cleanup timers/listeners */ };
  },
};
```
Register it with one line in `src/apps/index.ts`.

- `args` — launch arguments, e.g. `os.launch('notepad', { path: '/Documents/a.txt' })`.
- `fs` — async VFS: `list(dir) / all() / read / write / remove / exists`. Paths are absolute (`/Documents/x.txt`).
- `os` — `launch`, `notify`, `apps`, `settings.get/set`.
- Scope app CSS under a class you add to `win.body` (e.g. `.np`) — never style global selectors.

## 4. Visual rules
- Use tokens from `src/styles/tokens.css`; add a token instead of hard-coding a recurring color.
- Glass = gradient + `backdrop-filter`; content panes are opaque (readability first).
- Selection / hover highlight: the blue gradient `#5aa6f5 → #2273d8`.
- Motion: 120–320 ms, `cubic-bezier(.2,.8,.2,1)` for enter, `ease-in` for exit.
- Icons: 64×64 viewBox SVG, gradients from `ICON_DEFS`, drop shadow comes from CSS.

## 5. Quality bar for every PR
- `npm run build` passes (strict TypeScript, no unused code).
- No console errors; works in latest Chrome, Firefox, Safari.
- Desktop first, but nothing breaks at 380 px wide.
- Keyboard: Escape closes popups; apps handle their own shortcuts on `win.body`.
- Accessibility: buttons are `<button>`, icons have `aria-label` where they are the only content.

## 6. Out of scope (for now)
Real networking, multi-user, a real browser app (iframes of third-party sites are blocked anyway), audio files we didn't make.
