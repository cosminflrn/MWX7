# Changelog

Derived from the git history. Newest first.

## v1.0.1
- Snipping Tool redesigned: Windows 7 command bar, New menu with Rectangular, Window and Full-screen snips, glossy icon
- Media Player playlist shows distinct titles (Variatio 1, 2, …) and a different cover colour per track
- Space Pinball opens without a hitch: the hall reverb is built once, when the browser is idle
- Code released under the MIT License
- Linux distro: build works without udev or a vfat kernel module, standalone GRUB boot loader that finds the disk by label

## v1.0.0
- Apps load on demand: faster first boot, each app's code fetched the first time it opens
- My Computer: drag ghost for files, Properties dialog; Internet: favorites, history, clear blocked-site panel
- Media Player: more CC0 tracks, album art, mini player controls in the dock menu
- Snipping Tool, recent files in dock menus, Themes in Settings
- Traffic lights no longer miss a click right after leaving full screen
- Linux distro groundwork (distro/: Debian live-image scripts, not yet tested on hardware)

## v0.9 (0.9.0 to 0.9.29)
- Genie minimize rebuilt off-page: interruptible, frozen glass baked once, one shadow, funnel shape, no flicker
- Performance: no idle animation loops, compositor-driven window dragging, wallpaper always playing, 1080p Meadow default (1440p on large screens)
- Welcome tour with piano music, power-on photo scene with CRT zoom into the BIOS
- New apps and games: Photo Viewer, Task Manager, Sticky Notes, Mines, Solitaire; game tutorials
- Notepad uses the OS Save / Don't Save dialog; calendar follows the 24-hour setting
- End-to-end test suite (boot, every app, genie, drag, Notepad save, clean reload) gates CI and deploys

## v0.8
- Shell v8: correctly sized genie clone, peek fades for minimized windows, lights only when focused, toasts top-right
- BIOS VGA font, new Settings (clock, dock, desktop), Windows 7 style scrollbars and icons

## v0.7 "Crystal" (0.7.1, 0.7.2)
- Glossy Crystal Clear icons, unified tintable glass, flush dock, show desktop
- Internet browser and Media Player; VGA/CRT look for Commander and BIOS
- Exact-state genie with shadow and scroll; Computer details view

## v0.6 "Luna"
- XP glass, full-screen morph, smooth dock, genie, Tango icons, mouse-only input
- Keyboard shortcuts and Terminal removed; Search and Overview naming

## v0.5 "Paint"
- Paint with a Windows 7 style ribbon; Mission Control overview

## v0.4 "Explorer"
- Explorer file manager, Aero switcher, calendar flyout

## v0.3 "Aero"
- Real media: wallpaper videos, avatars, icons, Selawik font; wallpaper engine
- Shell v3: real genie, first-run setup, session-only storage, sampled sounds; MWX Commander

## v0.2 "Fidelity"
- Premium look, boot sequence, sounds, genie
- Virtual file system v2 (IndexedDB), Terminal, Space Pinball

## v0.1 "Genesis"
- Foundation: scaffold, deploy pipeline, window manager, menu bar, dock, Start menu, Spotlight, notifications
- Notepad, Calculator, Settings, About
