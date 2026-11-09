# MWX 7 as a Linux distro

MWX 7 as a real operating system: Debian 13 underneath, the MWX 7 desktop on top. Real windows (Wayfire), the native
MWX 7 shell (status bar, dock, Start menu), Google Chrome, Files, Terminal, and MWX 7 Classic (the website) as an app.
Roadmap to a daily driver: the project doc `claude/mwx7-distro-roadmap.md`.

- **ISO** (`build-iso.sh`, one file per release, `mwx7-<version>.iso`): runs from a VM or a USB stick, never touches
  the PC's disks. Boots on UEFI with Secure Boot on (Microsoft-signed shim, Debian-signed GRUB and kernel), UEFI
  without it, and legacy BIOS. CI builds and boot-tests it on every version bump and publishes the release.
- `build-iso.sh classic` still builds the old web kiosk, only as a debugging aid; it is not released.
- **Disk image** (`build.sh`): the earlier kiosk as a raw disk image; to be replaced by a real installer (stage 3).

To try it on Windows 11 (VMware, VirtualBox or a USB stick), follow [RELEASE_NOTES.md](RELEASE_NOTES.md).

## Design
```
UEFI -> standalone GRUB (finds the disk by label) -> Debian 13 (minbase) -> systemd
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
sudo ./distro/build-iso.sh   # produces distro/out/mwx7.iso (~1.2 GB): the MWX 7 desktop
./distro/smoke-test.sh        # boots it headless four ways
sudo ./distro/build.sh 4      # produces distro/out/mwx7.img (4 GB)
./distro/test-qemu.sh         # try it in a VM
sudo dd if=distro/out/mwx7.img of=/dev/sdX bs=4M status=progress   # real hardware (UEFI)
```

## Status and known gaps
6 Nov 2026, v1.1.1: a VirtualBox tester saw "nothing happens after GRUB": the kiosk failed without saying anything
behind a stray live-boot message. Now: on-screen status and errors, a watchdog that restarts Chromium if MWX 7 has not
loaded (a cold first start could leave a blank page), GPU firmware for real PCs, Debian 13. Debian's kernel has no
simpledrm, so a display needs a real driver (all real GPUs, VirtualBox VMSVGA and VMware have one; vmwgfx is only
loaded on VMware/VirtualBox). CI boots BIOS, UEFI and Secure Boot and each must load MWX 7.

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
