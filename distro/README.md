# MWX 7 as a Linux distro

A tiny Linux that boots straight into MWX 7 full screen, like a console, with no desktop environment, no browser UI and
no network needed. Two outputs:
- **Live ISO** (`build-iso.sh`): runs from the ISO or a USB stick, entirely in memory, never touches the PC's disks.
  Boots on UEFI with Secure Boot on (Microsoft-signed shim, Debian-signed GRUB and kernel), UEFI without it, and legacy
  BIOS. CI builds it on every version tag and attaches it to the GitHub release. **This is the one to try.**
- **Disk image** (`build.sh`): the same system as an installable raw disk image.

To try the ISO on Windows 11 (VirtualBox, Hyper-V or a USB stick), follow [RELEASE_NOTES.md](RELEASE_NOTES.md).

## Design
```
UEFI -> standalone GRUB (finds the disk by label) -> Debian 12 (minbase) -> systemd
   seatd               : hands the screen and input to the kiosk user
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
| `build.sh` | Builds `dist/`, partitions an image, debootstraps, installs the overlay and a standalone UEFI GRUB at the removable-media path. Needs no udev and no vfat kernel module, so it also runs in containers and CI |
| `chroot-setup.sh` | Runs inside the image: packages, `mwx` user, enables services |
| `overlay/etc/systemd/system/*.service` | Static server and kiosk session units |
| `overlay/usr/local/bin/mwx7-kiosk` | Waits for the server, launches cage + Chromium; falls back to CPU rendering if the GPU path crashes |
| `test-qemu.sh` | Boots the disk image in QEMU with UEFI (KVM if available) |
| `build-iso.sh` | Builds the live ISO: Debian + live-boot in a squashfs, hybrid BIOS/UEFI/Secure Boot boot records |
| `smoke-test.sh` | CI boot tests of the ISO: BIOS, UEFI, UEFI with Secure Boot enforced, and MWX 7 loading in Chromium |
| `RELEASE_NOTES.md` | Release text with the Windows 11 how-to |

## Build and test
Prerequisites on a Debian/Ubuntu host: `sudo apt install debootstrap parted dosfstools mtools e2fsprogs squashfs-tools xorriso grub-pc-bin qemu-system-x86 ovmf nodejs npm`.
```bash
sudo ./distro/build-iso.sh   # produces distro/out/mwx7-live.iso (~590 MB)
./distro/smoke-test.sh        # boots it headless four ways
sudo ./distro/build.sh 4      # produces distro/out/mwx7.img (4 GB)
./distro/test-qemu.sh         # try it in a VM
sudo dd if=distro/out/mwx7.img of=/dev/sdX bs=4M status=progress   # real hardware (UEFI)
```

## Status and known gaps
Live ISO, 5 Nov 2026: all four smoke tests pass in QEMU without KVM (BIOS 50 s, UEFI 65 s, Secure Boot 60 s to login;
MWX 7 loaded in Chromium after 90 s). Inside the Secure Boot run the kernel reported `Secure boot enabled` and lockdown.

Disk image, same day: Tested end to end on 5 Nov 2026 (Ubuntu 24.04 host in a container, QEMU 8.2 without KVM): the image builds, boots through
UEFI and GRUB into Debian, seatd and cage start, Chromium opens MWX 7 and the power-on desk scene renders.
Fixed during that run: partitions now come from the partition table (the root filesystem used to overrun the backup GPT
and fail fsck on first boot), seatd added (cage could not open the display from a systemd unit), Xwayland added (cage
refuses to start without it), CPU-rendering fallback for GPUs without a driver (Mesa's software GL crashed on plain
virtio-vga).
- Not yet confirmed: mouse clicks inside the VM (the headless test harness could not deliver them) and audio.
  Run `./distro/test-qemu.sh` on a desktop with KVM and click the power switch to check both.
- Root password is `root` (dev only, set in `chroot-setup.sh`). Ctrl+Alt+F2 opens a login for debugging.
- Planned: read-only root + overlayfs, Plymouth boot splash matching the MWX BIOS, a shutdown button wired to `systemctl poweroff`, GitHub Actions job producing the image, BIOS (legacy) boot.
