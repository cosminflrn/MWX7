# MWX7

**MWX 7** (with a space) is Cosmin's dream desktop OS: the best of macOS, Windows XP and Windows 7 in one coherent design.
What the letters mean stays an enigma. Two parts share this repo:
- **The distro** (`distro/`): Debian 13 + Wayfire, native GTK 4 shell and apps. This is the real goal: Cosmin daily-drives
  it on his work PC, next to Windows 11.
- **The web concept** (`src/`, GitHub Pages): the original browser mockup. Later it should mimic the distro as a
  try-before-download.

This file is context, not a rulebook. You are the architect: Cosmin gives the vision, you decide how. If something here, in
the docs or in the code is outdated or there's a better way, change it and update the note.

## Vision
- Premium and finished, Frutiger Aero (Windows 7 glass + macOS Aqua), as real as possible: real photos/footage, never
  cartoonish, never 1:1 copies of Apple/Microsoft assets.
- No lag, stutter or flicker; everything sharp except glass. 144 Hz on his monitor by default.
- The distro is a real OS: native apps, normal keyboard shortcuts, GPU (NVIDIA) works with no manual setup. It feels
  preinstalled: one signed ISO, OOBE with no visible installer, but setup asks about partitions and never touches user data.
- Updates are optional and discreet (status bar icon, install manually or at shutdown); only security fixes install by
  themselves. Repair and Reset to factory work offline from the on-disk copy.
- His PC (specs in `docs/STATUS.md`) is also his work machine: Windows and his files must never be at risk; Secure Boot
  stays on, no MOK or blue-screen steps.

## How to work
- Do everything end to end yourself: build, test, commit, ship. Don't ask him to run diagnostics or send logs; find the
  cause yourself. Think through how he will really install and use it, not just the convenient path.
- Fast and token-efficient; short messages; say expected durations before long steps. Suggest improvements proactively.
- One branch: commit straight to `main` (author Cosmin Florian <cosmin@dazoot.ro>). Run `npm run build` / `npm test` for
  web changes; add a test for every bug you fix. Avoid CI runs that fail for non-issues (he gets the emails).
- Every distro change on main ships to installed systems through the update channel (`updates.yml`). Bumping the
  version in `package.json` builds, tests and publishes the ISO by itself (`distro.yml`); only the newest release is kept.

## Where things are
- `docs/STATUS.md`: current version, backlog, real PC, ops. Keep it current.
- `SPEC.md`: web concept design and architecture. `docs/real-pc-install.md`, `docs/recovery.md`: install and recovery.
- `docs/ROADMAP.md`; `docs/history/`: old plans, read only if needed.
