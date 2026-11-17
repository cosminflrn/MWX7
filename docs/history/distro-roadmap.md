# MWX 7 Linux — roadmap to a daily driver

Goal (Cosmin, 6 Nov 2026): his own Linux distro that looks and feels like MWX 7 and that he will daily drive. Step by
step, done right. Not "a browser on top": real Linux apps, real files, real hardware, MWX 7 look. Most of his work is
in the browser (Chrome + Google apps). Must be secure and as bug-free as possible. Tests in VMware Workstation Pro
26H1u1 on his Windows 11 office PC; bare-metal USB test needed later for the GTX 1070. He'll ditch Windows 11 once
MWX 7 is ready, tested and secure.
11 Nov: no installer feel — boot the ISO, do the settings (OOBE), done; the setup must still ask about partitions
(never delete data); optional password ("No password" tick for testing; he'll set one on his own PC); logon screen
shown by default, "go straight to desktop" as an off-by-default setting; no ISO per version — one ISO, then updates
from inside VMware; OS as light and fast as possible; no links to the old website.

## Target machine (office PC, 9 Nov 2026)
Ryzen 5 2600 · GTX 1070 (Pascal) · 16 GB DDR4-3000 · 256 GB SSD (system) · 1 TB 7200 rpm HDD (data). Windows 11 today.
- GTX 1070 needs NVIDIA's proprietary driver (nouveau can't reclock Pascal). Pascal is on NVIDIA's legacy track.
  Secure Boot: DKMS module signed with a MOK key, one-time enrollment at first reboot.
- Games: Steam + Proton; kernel anti-cheat titles (Valorant, Fortnite, CoD…) won't run.

## Approach
Debian 13 base + a thin MWX 7 layer we own, shipped as one package (`mwx7-desktop`). Like Zorin / elementary / Pop!_OS.
- Security: unattended security upgrades, Secure Boot, LUKS (advanced path), nftables default-deny inbound, root
  locked, signed MWX 7 updates.

## Where it stands (v1.9.0, 12 Nov 2026 night)
- **Released ISO**: v1.9.0 → `mwx7-1.9.0.204.iso` (920 MB). The update channel already has 1.9.0.205 (What's new +
  "Updates available" notification), so a fresh install can update at once.
- **Package** `mwx7-desktop` (`distro/desktop/build-deb.sh`): overlay + compiled Wayfire plugins + fonts/icons/
  wallpapers + `whats-new` (newest CHANGELOG section); Depends in `distro/desktop/debian/depends`; preinst diverts
  /etc/nftables.conf and /etc/xdg/user-dirs.defaults; postinst writes os-release, locales, enables services, disables
  wait-online/e2scrub/foot-server/filter-chain, runs mwx7-grub-names and update-grub when /etc/mwx7/installed exists.
  Version = package.json version + commit count on main.
- **Update channel**: apt flat repo on the GitHub release `updates`, signed with the MWX 7 update key
  (`/usr/share/keyrings/mwx7-updates.gpg`, `/etc/apt/sources.list.d/mwx7.sources`). `updates.yml` builds the package in
  debian:trixie on every distro change on main and keeps the 2 newest .debs; it signs only if the `MWX7_UPDATES_KEY`
  secret exists (Claude can't write secrets; key file handed to Cosmin 12 Nov). Until then: download the deb via REST,
  sign Packages/Release with the key, push them to `updates-staging` (relay.yml uploads staging/*). A signed index
  must point at a .deb that still exists (CI deletes older ones). Settings → Updates runs `mwx7-update check|install`
  via pkexec (polkit: sudo group, no prompt); `mwx7-update-notify` (autostart) notifies once per version.
  Verified end to end: CI ISO 204 installed (UEFI, no password) → Settings → Updates → 205 → restart → boots.
  (In the sandbox VM, HTTPS needs the proxy CA; real VMware doesn't.)
- **ISO** (`build-iso.sh`): minbase + package + live-boot + calamares (advanced path); zstd 15 (dev 3). Built by
  pushing main to the `iso` branch; CI build + 3 boot tests take ~6 min with KVM. Boots (BIOS/UEFI/Secure Boot) into
  the **first-start setup** `/usr/share/mwx7/oobe/oobe.py` in cage as live user `mwx` (passwordless sudo, ISO only).
  Pages: language/keyboard/time zone (+ "already installed — remove the ISO" notice), disk, Wi-Fi (skipped when
  online), account, finishing. `install.py`: survey | copy erase|free DISK | finish ANSWERS | ready (serial marker for
  CI). GPT; 512 MB ESP or 1 MB bios_grub; btrfs MWX7 with @ @home @log @cache, zstd:1; unsquashfs on all cores; live
  packages purged (fresh initramfs); grub-install --uefi-secure-boot + stub in /EFI/debian; update-grub.
  Verified in QEMU: UEFI empty disk, BIOS disk with data + free space (data kept), UEFI Secure Boot, CI ISO.
- Logon: passwordless accounts get a "Sign in" button; lock image says "press Enter to unlock". Settings → Account
  (pkexec mwx7-admin): password add/change/remove, picture, autologin. Settings → Updates previews the setup.
- Idle RAM after login ≈ 540 MB used (QEMU, 4 GB).
- Removed in 1.9.0: MWX 7 Classic, local web server/kiosk/classic flavour, Keep settings + persistence, website links.

## Gotchas learned
- GitHub checkouts belong to uid 1001: `cp -a` into the image kept that owner and sudo ignored the sudoers file (setup
  never got root; CI boot tests failed while local ones passed). Copy with `--no-preserve=ownership`; `visudo -c` at
  build. The boot test now logs in on serial and reports the setup log + stack dump (SIGUSR1) as annotations.
- Debian files our package also ships must be dpkg-diverted, or dpkg refuses.
- `lsblk -J -o PATH,...` without NAME prints a flat list; udev fills PARTTYPE a moment after sfdisk.
- `dpkg --configure -a` needs `--force-confold` (greetd conffile prompt) in reused build roots.
- mksquashfs `-e` with wildcards needs `-wildcards`.
- greetd/swaylock/sudo/polkit accept an empty password via pam_unix nullok (passwd -d).
- QEMU `-boot order=cd` means disk first. TCG typing via QMP drops/repeats keys under load: use the serial console.
- CI: ubuntu-24.04 pinned; apt mirror failures on 11 Nov handled; ISO job limit 150 min.
- Proxy (Claude): no tag push, workflow dispatch, Actions logs/secrets, release asset upload, GraphQL, force push.

## Next
1. Cosmin adds the `MWX7_UPDATES_KEY` secret so CI signs updates by itself (then updates-staging is unused).
2. Snapshots before updates (btrfs) with a boot-menu rollback.
3. NVIDIA driver + MOK enrollment; bare-metal USB test on the GTX 1070; install next to Windows on real hardware.
4. Polish: icon + cursor theme, Settings pages for sound / power / Wi-Fi, website rebuilt as a quick try-out.

## Rules carried over
No lag/stutter/flicker; everything sharp; original assets only; desktop + mouse first; test like a human. Decide,
build, verify, ship.
