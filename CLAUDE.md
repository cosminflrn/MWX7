# CLAUDE.md — instructions for AI agents working on MWX7

Read `SPEC.md` first. It is the source of truth for design and architecture.

## Workflow
- One GitHub issue → one branch (`feat/<issue#>-short-name`) → one PR that says `Closes #<n>`.
- Stay inside the files your issue names. If you must touch `src/core/types.ts`, say so loudly in the PR — it is the shared contract.
- Run `npm run build` before every commit. It must pass with zero errors.
- Keep PRs small and reviewable; put screenshots/GIFs in the PR description for UI changes.

## Commands
- `npm install` — once
- `npm run dev` — local dev server
- `npm run build` — typecheck + production build (CI runs this)

## Hard rules
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
