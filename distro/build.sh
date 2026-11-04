#!/bin/bash
# Builds a bootable UEFI disk image (distro/out/mwx7.img) that boots straight into MWX 7.
# Needs: Debian/Ubuntu host, root, and: debootstrap parted dosfstools e2fsprogs grub-efi-amd64-bin
#        (sudo apt install debootstrap parted dosfstools e2fsprogs kpartx nodejs npm)
# Usage: sudo ./distro/build.sh [image-size-in-GB, default 4]
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
OUT="$HERE/out"; IMG="$OUT/mwx7.img"; MNT="$OUT/mnt"
SIZE_GB="${1:-4}"
LOOP=""

cleanup() {  # always release mounts and the loop device, even on failure
  set +e
  for d in dev/pts dev proc sys boot/efi ""; do umount "$MNT/$d" 2>/dev/null; done
  [ -n "$LOOP" ] && losetup -d "$LOOP"
}
trap cleanup EXIT

# 1. Build the OS itself with the normal build (as the invoking user if run through sudo).
echo "==> Building MWX 7 (dist/)"
if [ -n "${SUDO_USER:-}" ]; then sudo -u "$SUDO_USER" bash -c "cd '$REPO' && npm ci && npm run build"
else (cd "$REPO" && npm ci && npm run build); fi

# 2. Partition: 256 MB EFI system partition + the rest ext4.
mkdir -p "$OUT" "$MNT"
rm -f "$IMG"; truncate -s "${SIZE_GB}G" "$IMG"
parted -s "$IMG" mklabel gpt mkpart ESP fat32 1MiB 257MiB set 1 esp on mkpart root ext4 257MiB 100%
LOOP="$(losetup --find --show --partscan "$IMG")"
mkfs.vfat -F32 "${LOOP}p1"; mkfs.ext4 -q -L mwx7root "${LOOP}p2"
mount "${LOOP}p2" "$MNT"; mkdir -p "$MNT/boot/efi"; mount "${LOOP}p1" "$MNT/boot/efi"

# 3. Minimal Debian.
echo "==> debootstrap (downloads ~300 MB)"
debootstrap --variant=minbase bookworm "$MNT" http://deb.debian.org/debian

# 4. Overlay (systemd units, kiosk launcher) and the built site.
cp -a "$HERE/overlay/." "$MNT/"
mkdir -p "$MNT/opt/mwx7"; cp -a "$REPO/dist" "$MNT/opt/mwx7/dist"
cp "$HERE/chroot-setup.sh" "$MNT/tmp/"
printf 'LABEL=mwx7root / ext4 defaults,noatime 0 1\nPARTLABEL=ESP /boot/efi vfat umask=0077 0 2\n' > "$MNT/etc/fstab"

# 5. Install packages and enable services inside the chroot.
for d in dev dev/pts proc sys; do mount --bind "/$d" "$MNT/$d"; done
chroot "$MNT" /tmp/chroot-setup.sh
chown -R 1000:1000 "$MNT/opt/mwx7" 2>/dev/null || true   # first useradd user is uid 1000

# 6. Bootloader. --removable writes EFI/BOOT/BOOTX64.EFI so no NVRAM entry is needed (works in QEMU and on USB).
chroot "$MNT" grub-install --target=x86_64-efi --efi-directory=/boot/efi --removable --no-nvram
sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=3"/' "$MNT/etc/default/grub"
chroot "$MNT" update-grub
rm -f "$MNT/tmp/chroot-setup.sh"

echo "==> Done: $IMG  (test: ./distro/test-qemu.sh; write to USB: sudo dd if=$IMG of=/dev/sdX bs=4M status=progress)"
