#!/bin/bash
# Builds a bootable UEFI disk image (distro/out/mwx7.img) that boots straight into MWX 7.
# Needs: Debian/Ubuntu host, root, and: debootstrap parted dosfstools mtools e2fsprogs nodejs npm
#        (sudo apt install debootstrap parted dosfstools mtools e2fsprogs nodejs npm). Works without udev (containers, CI).
# Usage: sudo ./distro/build.sh [image-size-in-GB, default 4]
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
OUT="$HERE/out"; IMG="$OUT/mwx7.img"; MNT="$OUT/mnt"
SIZE_GB="${1:-4}"
LROOT=""; LESP=""

cleanup() {  # always release mounts and the loop device, even on failure
  set +e
  for d in dev/pts dev proc sys ""; do umount "$MNT/$d" 2>/dev/null; done
  [ -n "$LESP" ] && losetup -d "$LESP"; [ -n "$LROOT" ] && losetup -d "$LROOT"
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
# One loop device per partition (by byte offset) instead of --partscan: partition nodes like loop0p1 only appear
# when udev is running, which is not the case in containers and many CI hosts.
# Offsets and sizes come from the partition table itself: GPT keeps a backup table at the end of the disk, so a
# filesystem that simply ran to the end of the image would be larger than its partition and fail fsck on first boot.
part() { parted -m -s "$IMG" unit B print | awk -F: -v n="$1" '$1 == n { sub("B", "", $2); sub("B", "", $4); print $2, $4 }'; }
read -r ESP_OFF ESP_LEN < <(part 1)
read -r ROOT_OFF ROOT_LEN < <(part 2)
LESP="$(losetup --find --show --offset "$ESP_OFF" --sizelimit "$ESP_LEN" "$IMG")"
LROOT="$(losetup --find --show --offset "$ROOT_OFF" --sizelimit "$ROOT_LEN" "$IMG")"
mkfs.vfat -F32 -n MWX7ESP "$LESP"; mkfs.ext4 -q -L mwx7root "$LROOT"
# The ESP is written with mtools later rather than mounted, so hosts without the vfat module work too.
mount "$LROOT" "$MNT"; mkdir -p "$MNT/boot/efi"

# 3. Minimal Debian.
echo "==> debootstrap (downloads ~300 MB)"
# Debian 13 (trixie): current Mesa, kernel 6.12 and Chromium.
# Older debootstrap releases lack a trixie script; sid\'s is the same.
SCRIPT=/usr/share/debootstrap/scripts/trixie; [ -e "$SCRIPT" ] || SCRIPT=/usr/share/debootstrap/scripts/sid
debootstrap --variant=minbase trixie "$MNT" http://deb.debian.org/debian "$SCRIPT"

# 4. Overlay (systemd units, kiosk launcher) and the built site.
cp -a "$HERE/overlay/." "$MNT/"
mkdir -p "$MNT/opt/mwx7"; cp -a "$REPO/dist" "$MNT/opt/mwx7/dist"
cp "$HERE/chroot-setup.sh" "$MNT/tmp/"
printf 'LABEL=mwx7root / ext4 defaults,noatime 0 1\nLABEL=MWX7ESP /boot/efi vfat umask=0077,nofail 0 2\n' > "$MNT/etc/fstab"

# 5. Install packages and enable services inside the chroot.
for d in dev dev/pts proc sys; do mount --bind "/$d" "$MNT/$d"; done
chroot "$MNT" /tmp/chroot-setup.sh
chown -R 1000:1000 "$MNT/opt/mwx7" 2>/dev/null || true   # first useradd user is uid 1000

# 6. Bootloader: a standalone GRUB at the removable-media path (EFI/BOOT/BOOTX64.EFI, no NVRAM entry, works in QEMU
#    and from USB). Its embedded config finds the root by label and boots the /vmlinuz and /initrd.img symlinks, so it
#    needs no grub-probe of the build host's devices and keeps working after kernel updates.
cat > "$MNT/tmp/grub-embed.cfg" <<'GRUB'
search --no-floppy --label mwx7root --set=root
set timeout=0
linux /vmlinuz root=LABEL=mwx7root ro console=tty0 console=ttyS0,115200 quiet splash loglevel=3
initrd /initrd.img
boot
GRUB
chroot "$MNT" grub-mkstandalone -O x86_64-efi -o /tmp/BOOTX64.EFI \
  --modules="part_gpt ext2 search_label linux normal all_video" "boot/grub/grub.cfg=/tmp/grub-embed.cfg"
export MTOOLS_SKIP_CHECK=1  # loop devices have no floppy geometry; mtools would only warn
mmd -i "$LESP" ::/EFI ::/EFI/BOOT
mcopy -i "$LESP" "$MNT/tmp/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI
rm -f "$MNT/tmp/grub-embed.cfg" "$MNT/tmp/BOOTX64.EFI"
rm -f "$MNT/tmp/chroot-setup.sh"

echo "==> Done: $IMG  (test: ./distro/test-qemu.sh; write to USB: sudo dd if=$IMG of=/dev/sdX bs=4M status=progress)"
