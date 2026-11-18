# CLAUDE.md — instructions for AI agents working on MWX7

Read `SPEC.md` first. It is the source of truth for design and architecture.
Current state of the distro and the real PC: `docs/STATUS.md`; install/recovery: `docs/real-pc-install.md`, `docs/recovery.md`.

## Cosmin's vision (owner)
- "MWX 7" (with a space) — the best of macOS, Windows XP and Windows 7; what the letters mean stays an enigma. Premium and
  finished, close to the real OSes but never 1:1 copies. Frutiger Aero look, as real as possible: real photos/footage,
  nothing hand-drawn or childish.
- The goal is his own Debian-based distro that he daily-drives on his work PC (specs in `docs/STATUS.md`; 144 Hz by
  default). It must look like MWX 7 natively (not a browser on top), be secure and bug-free. He works mostly in Chrome
  and Google apps.
- On the distro, apps are real native apps (games skipped for now) and normal OS keyboard shortcuts stay
  (Alt+Tab, Alt+F4, Win+arrows, Win+L…). The no-shortcuts rule below applies only to the web concept.
- One ISO per release (the real desktop distro, no web/kiosk variant), signed. Feels preinstalled: boots into an OOBE
  with no visible installer, but setup still asks about partitions and never deletes user data. Logon screen by
  default; straight-to-desktop is opt-in. The bootable USB should show up nicely in Windows (named, MWX 7 icon).
- His PC also runs Windows 11 — losing that install or his files is unacceptable. Secure Boot stays on, no MOK or
  blue-screen steps. The NVIDIA GPU must "just work" with no manual setup.
- Updates (Settings → Updates): optional and discreet — a status bar icon, install manually or when prompted at
  shutdown/restart; only security fixes install automatically. No background pre-download, resumable downloads,
  installed at shutdown outside the session, restart only when needed, "previous version" fallback. Include a
  "reinstall display driver" button.
- Settings has Repair (keep everything; also from the boot menu) and Reset to factory (absolutely clean), both from the
  on-disk copy, no download; after a reset, setup asks before updating.
- The old MWX 7 website is not linked from the distro; later the site should mimic the real distro as a try-before-download.
- No false "Run failed" GitHub emails: keep CI workflows from failing for non-issues.

## How Cosmin wants you to work
- You are the architect and decide; he gives the vision. Do everything yourself — don't ask whether to commit, just
  commit and ship. Don't put him to work (diagnostics, logs, screenshots): find the cause and the fix yourself.
- Commits authored as Cosmin Florian <cosmin@dazoot.ro>.
- Get each fix fully right the first time and verify it; he hates repeating himself. Consider ALL real-world paths
  (how he will actually install/use it), not just the convenient one.
- No lag, no stutters, everything sharp (no pixelation or blur, except glass effects) — this rule applies to every project.
- Be fast and token-efficient; keep messages short; say expected durations up front before long steps.

## Workflow
- One GitHub issue → one branch (`feat/<issue#>-short-name`) → one PR that says `Closes #<n>`.
- Stay inside the files your issue names. If you must touch `src/core/types.ts`, say so loudly in the PR — it is the shared contract.
- Run `npm run build` before every commit and `npm test` before every PR. Both must pass.
- Keep PRs small and reviewable; put screenshots/GIFs in the PR description for UI changes.

## Commands
- `npm install` — once
- `npm run dev` — local dev server
- `npm run build` — typecheck + production build (CI runs this)
- `npm test` — build + end-to-end checks in Chromium (tests/*.spec.ts). Must pass before every PR; deploys are blocked when it fails. Add a test for every bug you fix.

## Hard rules
0. **Desktop + mouse only.** No touch handling, and no keyboard shortcuts (they clash with the host OS when MWX 7 runs in a browser). Typing in text fields, game controls and the BIOS/Commander keys are the only keyboard input.
1. **Original assets only.** Never copy Apple/Microsoft icons, wallpapers, logos, sounds or fonts. Draw SVG yourself.
2. **App isolation.** Apps live in `src/apps/<id>/` and use only `ctx.win`, `ctx.fs`, `ctx.os`, `src/ui/*`, `src/assets/*`. No importing other apps or `core/wm` / `core/os`.
3. **Scoped CSS.** Add a class to `win.body` and prefix every app selector with it.
4. **No new dependencies** without a reason written in the PR (bundle size matters on Pages).
5. **No frameworks.** Vanilla TypeScript + the `h()` helper from `src/ui/dom.ts`.
6. Persist only via `ctx.fs` or `ctx.os.settings` — never touch `localStorage` directly in an app.

## Style
- TypeScript strict, 2-space indent, single quotes, semicolons, ~130 char lines.
- Use design tokens from `src/styles/tokens.css`.
- Comments explain *why*, not what.

## Model routing (labels on issues)
- `model:opus` — core systems, cross-cutting changes, tricky interaction (window manager, snap, animations).
- `model:sonnet` — self-contained apps and shell features.
- `model:haiku` — icons, copy, small CSS fixes, docs.
