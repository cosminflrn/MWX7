# MWX 7 — weekend plan (Fri 13 → Mon 16 Nov 2026)

Cosmin is away until Monday 09:00. Claude leads; helpers (brief: scratchpad/brief.txt — they open PRs, never merge;
spawn from inside /home/claude/mwx7) build, Claude reviews, tests and merges (scratchpad/merge.sh N) and releases.
Wave checks: Sat 16:00, 21:00; Sun 02:30, 10:00, 16:00, 21:00; Mon 02:30; report Mon 08:30.

## Usage budget (from Sat 14 Nov 12:14: weekly limit 52% used, resets Fri 17:59; "runs out tomorrow at this pace")
- Cosmin needs usage Mon–Fri too → stop starting new work when the weekly meter reaches ~70%.
- At most 2 Sonnet helpers at a time, none on Opus; short briefs; prefer CI (GitHub minutes) over local test loops.
- Wave checks stay light: read notifications, merge finished PRs, log, sleep.

## In flight
- Title bar right end shows the desktop through it around the traffic lights (CI screenshots; timing-dependent;
  not caused by #205 — bisected with test/deco-A, test/deco-B, test/no205 branches)
- Session test tour: every main app opened in the CI VM, screenshots + traceback check

## Backlog (only if budget allows)
- Screen reader toggle (Orca) in Ease of Access, if it resolves without heavy deps
- Fix app UI bugs the session tour reports

## Done (13–14 Nov)
#124–#147: Aero Peek/Shake removed, Start lists all, Win7 bin, Repair/Reset, Get Apps, native games,
Bluetooth/Printers/NVIDIA/Backup, safe boot, Open/Save dialogs, clipboard/battery/brightness, live wallpapers, widgets,
lights with symbols, app icon in the bar, first lag fixes, X11 in VMware.
#148–#158 (v1.13.0): clock without seconds (idle 42%→3%), widget grid, VMware pointer, Super+V, real-PC readiness,
EFI fallback, apps/Settings polish, desktop paints the wallpaper, CI distro syntax check.
#159–#169 (v1.14.0): Animations level, Start search + calendar, Get Apps v2, Media Player, Explorer v2, install
alongside Windows, notification center, Sound/Display settings, Paint v2, Notepad tabs, Calculator modes, Photos v2.
#171–#175 (v1.15.0): boot look, updater v2, web sync, lock screen v2, Welcome Center.
#177–#180 (v1.16.0): printing, keyboard/a11y + Super opens Start, accounts + default apps, Power/Storage/Security.
#182–#187 (v1.17.0): Snipping Tool v2, Task Manager v2, FreeCell/Spider/Hearts, app theme, multi-monitor, Ease of Access.
#189–#195 (v1.18.0): launch feedback, Settings lazy pages, ISO build fixes, Network page + VPN, AutoPlay + shares.
#197–#199 (v1.19.0 #200): recovery flow, automated install test, Start menu Recent items / pins / content search.
#201–#211 (v1.20.0 #212, ISO on the GitHub release): CI builds the ISO and runs boot + install + real sign-in tests on
KVM (~10 min) with desktop/Start/app screenshots; drag/hover perf (no title-bar redraw while dragging, cached light
textures, shell subscribes only to used IPC events, blur really off without acceleration); Reader (PDF), Calendar,
zip folders, previous versions (hourly btrfs snapshots of @home), screen recording, .exe → Bottles, fwupd firmware
updates, Terminal look, OOBE polish; foot.ini dpkg-divert (#207) fixed a file conflict that broke updates.
#213: title bars near-opaque when blur is off. #215: only main/iso/tags publish the ISO (branch tests don't).

## Log / notes
- CI is the real-session test bed (no DRM in this container: Wayfire can't run here, even headless).
- Releases: tag pushes are refused for this session → dispatch distro.yml on main to publish the ISO for package.json's version.
- Measuring: `top -b -d 20 -n 2` via setsid into a file; per-client commits with WAYLAND_DEBUG=client.
- VM can't reach GitHub over TLS; check dependency resolution with `apt-get install -s` in the live-root chroot.
- Lesson: never commit during a conflicted rebase — check `git status` first.
- grub-reboot on btrfs can't clear next_entry → fresh test disks via `distro/smoke-test.sh 1100 install` (no serial getty).
- gtkrun.sh must unmount proc/dev/sys of the build root, or mksquashfs packs /proc.
