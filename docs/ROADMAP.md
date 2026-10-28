# MWX7 Roadmap

Each item is a GitHub issue. Labels say which phase it belongs to and which model should take it.

## ✅ Phase 1 — Foundation (v0.1 “Genesis”)
Scaffold, deploy pipeline, window manager (drag/resize/snap/minimize), menu bar, dock, Start menu, Spotlight, notifications, boot/welcome/shutdown screens, Notepad, Calculator, Settings, About, SPEC + CLAUDE.md.

## Phase 2 — Window manager & shell
| Issue | Model | Depends on |
|---|---|---|
| Aero Peek: live window previews on dock hover | opus | — |
| Mission Control: overview of all windows | opus | — |
| Alt+Tab switcher and keyboard window shortcuts | sonnet | — |
| Calendar flyout from the menu bar clock | sonnet | — |
| Desktop icons: drag to arrange, rubber-band select, files on the Desktop | sonnet | VFS v2 |
| VFS v2: IndexedDB backend with real folders | opus | — |

## Phase 3 — Apps
| Issue | Model | Depends on |
|---|---|---|
| Explorer: Finder × XP Explorer file manager | sonnet | VFS v2, icons |
| Terminal with built-in commands | sonnet | — |
| Paint | sonnet | — |
| Minesweeper | sonnet | — |
| Icon set for the new apps + Trash | haiku | — |

## Phase 4 — Polish
| Issue | Model | Depends on |
|---|---|---|
| Original UI sounds synthesized with Web Audio | sonnet | — |
| Trash in the dock | haiku | VFS v2 |
| Touch & small-screen pass | sonnet | — |

## Suggested parallel waves
1. **Wave A (now):** VFS v2 (opus) · Alt+Tab (sonnet) · Calendar (sonnet) · Terminal (sonnet) · Minesweeper (sonnet) · Icons (haiku)
2. **Wave B:** Aero Peek (opus) · Explorer (sonnet) · Paint (sonnet) · Desktop icons (sonnet)
3. **Wave C:** Mission Control (opus) · Sounds · Trash · Touch pass
