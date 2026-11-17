# MWX 7 — project status

Current: v1.21.4 (update channel); last ISO mwx7-1.21.3.339.iso.
17 Nov 2026: installed on Cosmin's real work PC next to Windows 11 (GTX 1070, 144 Hz monitor) — works; NVIDIA driver in use.

## Backlog (next, in priority order)
- Get Apps: "SSL peer certificate or SSH remote key was not OK" from Flathub on the real PC (17 Nov). Check the clock
  (dual boot: Windows keeps local time in the RTC, Linux UTC) and whether the office network inspects TLS with a company
  CA. Fix the dual-boot clock either way (local RTC when Windows is present, or sync on every boot).
- Settings → Updates: "Graphics driver" card: shows the current driver (NVIDIA 550.x / built-in nouveau), "Reinstall
  driver" (reinstall + rebuild the module for the running kernel, offline from the recovery copy when possible, then
  restart), "Switch to built-in / NVIDIA driver", and "The NVIDIA driver didn't start — Reinstall?" when
  mwx7-gpu-fallback had to load nouveau.
- Confirm on the real PC after v1.21.4: hardware cursor smooth, true 144 Hz with the NVIDIA driver, no cursor flicker.
- Setup speed: install as fast as possible; show an estimated time BEFORE it starts (measure the stick's read speed and
  the disk's write speed on the disk page) and a live "about N minutes left". Ideas: recovery copy in the background
  after the first start; copy the squashfs once; no step without visible progress.
- USB stick looks nice in Windows: give the ISO's FAT boot partition the label "MWX 7" + autorun.inf with our own .ico.
  (The ISO 9660 part always shows RAW in Windows — document "click Cancel if Windows offers to format it".)
- USB boot prints a harmless "file boot not found" GRUB message — silence it.
- Title bars stay translucent when blur is off (VMware/software rendering): blur_active() suspected wrong (#217 held).
- Branch protection on main (PR required, 0 approvals, status check CI).

## Rules (product owner: Cosmin)
- Name "MWX 7"; never explain the letters to users.
- Style: Frutiger Aero — Windows 7 / macOS Aqua; as real as possible, never cartoonish. Original consistent glossy icons.
- Aero glass must fully work. Real native apps on the distro, no web apps (except the games, skipped for now).
- No lag, no stutter, no flicker, ever. Everything sharp except glass.
- Desktop + mouse only: no touch, no keyboard shortcuts (only typing, game controls, BIOS/Commander keys). No UI click sound.
- Take ALL real-world possibilities into account before calling something tested (USB stick vs CD, real GPU vs VM).
  Tell expected durations up front.
- Do everything end to end (commit, PR, merge, release); be fast and token-efficient. Add a test for every bug fixed.
- Installed systems get every change through the update channel; no ISO per version.
- Updates: security fixes install automatically; everything else only when the person chooses.
- Repair (keep everything) and Reset to factory rebuild the PC's exact version from the recovery copy, offline.
- Real PC: Gigabyte B450M DS3H (F12 boot menu), Ryzen 2600, GTX 1070, Win11 on a 256 GB SSD + 1 TB HDD, Secure Boot ON
  (never ask to disable it; no MOK by default). MWX 7 in 24.41 GiB next to Windows; Windows must never be at risk.

## Distro
Debian 13 + Wayfire with own plugins (mwx7-decor Aero frames + IPC, mwx7-animate genie), GTK4 shell (bar, dock, Start
menu), desktop layer, native GTK 4 apps, greeter, OOBE/setup (cage), Settings.
CI (distro.yml, KVM): boot tests (bios/uefi/secureboot), autoinstall, session tour with screenshots, and the "free" test:
the real interactive setup from a USB stick image next to a copy of the real PC's Windows layout, proving every old
partition byte-identical and the recovery copy equal to the ISO.
Display: hardware cursor everywhere except VMware; mwx7-refresh picks the highest refresh rate, capped at 60 Hz on
nouveau (no Pascal reclocking → flicker above 60).

## Ops
- Releases: `gh api repos/cosminflrn/MWX7/actions/workflows/distro.yml/dispatches -X POST -f ref=main` (only main, iso
  and tags publish). Merges to main ship through the Updates workflow.
- Writing the stick: Rufus DD mode; on "Write error", diskpart `clean` on the stick first.
