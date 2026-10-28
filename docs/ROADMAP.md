# MWX 7 Roadmap

Each item is a GitHub issue. Labels say which phase it belongs to and which model should take it.

## ✅ Phase 1 — Foundation (v0.1 “Genesis”)
Scaffold, deploy pipeline, window manager (drag/resize/snap/minimize), menu bar, dock, Start menu, Spotlight, notifications, boot/welcome/shutdown screens, Notepad, Calculator, Settings, About, SPEC + CLAUDE.md.

## Phase 2 — Window manager & shell
| Issue | Model | Depends on |
|---|---|---|
| #7  Aero Peek: live window previews on dock hover | opus | — |
| #11  Mission Control: overview of all windows | opus | — |
| #2  Alt+Tab switcher and keyboard window shortcuts | sonnet | — |
| #3  Calendar flyout from the menu bar clock | sonnet | — |
| #10  Desktop icons: drag to arrange, rubber-band select, files on the Desktop | sonnet | VFS v2 |
| ~~#1 VFS v2~~ ✅ | opus | — |

## Phase 3 — Apps
| Issue | Model | Depends on |
|---|---|---|
| #8  Explorer: Finder × XP Explorer file manager | sonnet | VFS v2, icons |
| ~~#4 Terminal~~ ✅ | sonnet | — |
| #9  Paint | sonnet | — |
| ~~#5 Space Pinball~~ ✅ | sonnet | — |
| #6  Icon set for the new apps + Trash | haiku | — |

## Phase 4 — Polish
| Issue | Model | Depends on |
|---|---|---|
| ~~#12 Sounds~~ ✅ | lead | — |
| #13  Trash in the dock | haiku | VFS v2 |
| #14  Touch & small-screen pass | sonnet | — |

## Suggested parallel waves
1. **Wave A (now):** #1 VFS v2 (opus) · #2 Alt+Tab · #3 Calendar · #4 Terminal · #5 Minesweeper (sonnet) · #6 Icons (haiku)
2. **Wave B:** #7 Aero Peek (opus) · #8 Explorer · #9 Paint · #10 Desktop icons (sonnet)
3. **Wave C:** #11 Mission Control (opus) · #12 Sounds · #13 Trash · #14 Touch pass

## ✅ v0.2 “Fidelity”
Premium pass (Aero glass, realistic icons, new logo, Serenity Hill + Blue Wave wallpapers), power → BIOS → boot logo → logon, original sounds (#12), real genie minimize, Start menu glued to the orb, double-click centers windows, VFS v2 with IndexedDB (#1), Terminal (#4), Space Pinball (#5).
