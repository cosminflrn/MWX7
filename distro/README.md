# MWX 7 as a Linux distro (groundwork, issue #81)

Goal: a tiny Linux that boots straight into MWX 7 full screen, like a console, with no desktop environment, no browser UI and no network needed.

## Design
```
UEFI -> GRUB -> Debian 12 (minbase) -> systemd
   mwx7-server.service : python3 http.server on 127.0.0.1:8080 serving /opt/mwx7/dist
   mwx7-kiosk.service  : cage (Wayland kiosk compositor) -> Chromium --kiosk http://127.0.0.1:8080/
```
- **Debian minbase + debootstrap**: the simplest route a hobbyist can run (one script, no Packer or live-build config to learn). A single raw disk image works for QEMU and `dd` to USB.
- **cage** runs exactly one app full screen, so there is nothing else to escape to. **Chromium** is used because MWX 7 depends on modern CSS (backdrop blur), video and Web Audio.
- **Offline**: `dist/` is baked into the image; the server only binds to localhost.
- MWX 7 is session-only by design, so the root filesystem is never written by the OS. (A read-only root is a good next step.)

## Files
| File | Purpose |
|---|---|
| `build.sh` | Builds `dist/`, partitions an image, debootstraps, installs the overlay, GRUB (UEFI, removable) |
| `chroot-setup.sh` | Runs inside the image: packages, `mwx` user, enables services |
| `overlay/etc/systemd/system/*.service` | Static server and kiosk session units |
| `overlay/usr/local/bin/mwx7-kiosk` | Waits for the server, launches cage + Chromium |
| `test-qemu.sh` | Boots the image in QEMU with UEFI (KVM if available) |

## Build and test
Prerequisites on a Debian/Ubuntu host: `sudo apt install debootstrap parted dosfstools e2fsprogs qemu-system-x86 ovmf nodejs npm`.
```bash
sudo ./distro/build.sh 4      # produces distro/out/mwx7.img (4 GB)
./distro/test-qemu.sh         # try it in a VM
sudo dd if=distro/out/mwx7.img of=/dev/sdX bs=4M status=progress   # real hardware (UEFI)
```

## Status and known gaps
Scripts are written but not yet run end to end (no root or VM in the authoring environment); expect small fixes on first build.
- Root password is `root` (dev only, set in `chroot-setup.sh`).
- Audio needs a PipeWire user session for `mwx`; verify in QEMU and on hardware.
- Planned: read-only root + overlayfs, Plymouth boot splash matching the MWX BIOS, a shutdown button wired to `systemctl poweroff`, GitHub Actions job producing the image, BIOS (legacy) boot.
