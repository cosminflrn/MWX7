# MWX 7 as a Linux distro

MWX 7 as a real operating system: Debian 13 underneath, the MWX 7 desktop on top. Real windows (Wayfire with MWX 7's
own frame and animation plugins), the native MWX 7 shell (status bar, dock, Start menu), Settings, a logon and lock
screen, Google Chrome, Files and Terminal. Roadmap: the project doc `claude/mwx7-distro-roadmap.md`.

## How it fits together
- **`mwx7-desktop` package** (`desktop/build-deb.sh`): everything MWX 7 adds to Debian — `desktop/overlay/` (shell,
  apps, Settings, logon screen, first-start setup, theme, boot menu), the compiled Wayfire plugins, fonts, icons and
  wallpapers. Its dependencies (`desktop/debian/depends`) are the whole desktop, so a new dependency reaches every PC
  with the next update.
- **Update channel** (`.github/workflows/updates.yml`): every change on main builds the package in a Debian 13
  container and publishes it, signed with the MWX 7 update key (secret `MWX7_UPDATES_KEY`, public part in
  `overlay/usr/share/keyrings/`), to the `updates` release. Installed systems use it as an apt source
  (`overlay/etc/apt/sources.list.d/mwx7.sources`); Settings → Updates runs `mwx7-update` through pkexec.
- **ISO** (`build-iso.sh`, built by hand from the Actions tab or for a version tag): Debian minbase + the package +
  live-boot in a zstd squashfs. It boots (BIOS, UEFI, Secure Boot) straight into the **first-start setup**
  (`overlay/usr/share/mwx7/oobe/`, ISO-only files in `desktop/live/`): language, disk, Wi-Fi, account. As soon as the
  disk is chosen, `install.py` partitions it (GPT; EFI or BIOS boot partition; btrfs with zstd and @ subvolumes),
  unpacks the squashfs on every core and installs GRUB, while the person fills in the rest. Then it applies the
  answers, and the PC restarts into the logon screen. Calamares stays on the ISO as the "Advanced" path (partitions by
  hand, next to Windows, encryption).

## Build and test
Prerequisites on a Debian/Ubuntu host: `sudo apt install debootstrap squashfs-tools xorriso mtools dosfstools
grub-pc-bin qemu-system-x86 ovmf nodejs git`.
```bash
sudo ./distro/build-iso.sh              # distro/out/mwx7.iso and distro/out/deb/mwx7-desktop_<version>_amd64.deb
REUSE_ROOT=1 sudo -E ./distro/build-iso.sh   # development: reuse the Debian system from the last build
./distro/smoke-test.sh                  # boots it headless (BIOS, UEFI, Secure Boot) until the setup is on screen
```
The version is `package.json`'s plus the commit count (1.9.0.214), so every build of main is newer than the last.
