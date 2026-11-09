#!/bin/bash
# Builds a live ISO (distro/out/mwx7-live.iso) that runs MWX 7 entirely from RAM: nothing is installed and the PC's
# disks are never touched. Boots on UEFI (Secure Boot on or off) and legacy BIOS, from a VM or a USB stick.
# Needs: Debian/Ubuntu host, root, and:
#   sudo apt install debootstrap squashfs-tools xorriso mtools dosfstools grub-pc-bin nodejs npm
# Usage: sudo ./distro/build-iso.sh [classic|desktop]
#   REUSE_ROOT=1 keeps the Debian system from the last build of the same flavour and only refreshes MWX 7's own files
#   and the desktop packages: minutes instead of a full rebuild, for development. CI always builds from scratch.
#   classic  MWX 7 on the web, full screen (kiosk). The released default for now.
#   desktop  a real Wayfire desktop with the native MWX 7 shell, Google Chrome and real apps (roadmap stage 1).
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
FLAVOR="${1:-desktop}"
case "$FLAVOR" in classic|desktop) ;; *) echo "Unknown flavour $FLAVOR (classic or desktop)" >&2; exit 1 ;; esac
OUT="$HERE/out"; ROOT="$OUT/live-root"; ISO_DIR="$OUT/iso"
ISO="$OUT/mwx7.iso"; [ "$FLAVOR" = classic ] && ISO="$OUT/mwx7-classic.iso"
VERSION="$(node -p "require('$REPO/package.json').version" 2>/dev/null || echo dev)"

cleanup() {  # always release the bind mounts, even on failure
  set +e
  for d in dev/pts dev proc sys; do umount "$ROOT/$d" 2>/dev/null; done
}
trap cleanup EXIT

# 1. Build the OS itself with the normal build (as the invoking user if run through sudo).
echo "==> Building MWX 7 $VERSION (dist/)"
if [ -n "${SUDO_USER:-}" ]; then sudo -u "$SUDO_USER" bash -c "cd '$REPO' && npm ci && npm run build"
else (cd "$REPO" && npm ci && npm run build); fi

# 2. Minimal Debian in a plain directory (no disk image, so no loop devices or partitions are needed).
REUSE=0; [ "${REUSE_ROOT:-0}" = 1 ] && [ -x "$ROOT/usr/bin/apt-get" ] && REUSE=1
rm -rf "$ISO_DIR"; mkdir -p "$ISO_DIR/live" "$ISO_DIR/boot/grub"
if [ $REUSE = 0 ]; then
rm -rf "$ROOT"; mkdir -p "$ROOT"
echo "==> debootstrap (downloads ~300 MB)"
# Debian 13 (trixie): current Mesa, kernel 6.12 and Chromium.
# Older debootstrap releases lack a trixie script; sid\'s is the same.
SCRIPT=/usr/share/debootstrap/scripts/trixie; [ -e "$SCRIPT" ] || SCRIPT=/usr/share/debootstrap/scripts/sid
debootstrap --variant=minbase trixie "$ROOT" http://deb.debian.org/debian "$SCRIPT"
fi

# 3. Same overlay and packages as the disk image, plus live-boot.
cp -a "$HERE/overlay/." "$ROOT/"
rm -rf "$ROOT/opt/mwx7/dist"; mkdir -p "$ROOT/opt/mwx7"; cp -a "$REPO/dist" "$ROOT/opt/mwx7/dist"
cp "$HERE/chroot-setup.sh" "$ROOT/tmp/"
: > "$ROOT/etc/fstab"   # live-boot mounts the root itself
for d in dev dev/pts proc sys; do mount --bind "/$d" "$ROOT/$d"; done
[ $REUSE = 1 ] || chroot "$ROOT" env EXTRA_PKGS="live-boot shim-signed grub-efi-amd64-signed" /tmp/chroot-setup.sh
if [ "$FLAVOR" = desktop ]; then
  cp -a "$HERE/desktop/overlay/." "$ROOT/"
  mkdir -p "$ROOT/usr/share/mwx7/icons"
  cp -a "$REPO/public/media/icons/." "$ROOT/usr/share/mwx7/icons/"
  cp "$REPO/public/media/wallpapers/meadow.jpg" "$ROOT/usr/share/mwx7/wallpaper.jpg"
  cp "$HERE/desktop/setup.sh" "$ROOT/tmp/"
  chroot "$ROOT" /tmp/setup.sh
  rm -f "$ROOT/tmp/setup.sh"
fi
chown -R 1000:1000 "$ROOT/opt/mwx7"
rm -f "$ROOT/tmp/chroot-setup.sh"
for d in dev/pts dev proc sys; do umount "$ROOT/$d"; done

# 4. Kernel + initrd next to the compressed root. xz keeps the download small; the root is read once into the page
#    cache, so decompression cost is only paid at boot.
cp -L "$ROOT/vmlinuz" "$ISO_DIR/live/vmlinuz"
cp -L "$ROOT/initrd.img" "$ISO_DIR/live/initrd.img"
echo "==> squashfs"
# Development rebuilds trade size for speed (zstd); releases use xz.
COMP=(-comp xz); [ $REUSE = 1 ] && COMP=(-comp zstd -Xcompression-level 3)
mksquashfs "$ROOT" "$ISO_DIR/live/filesystem.squashfs" "${COMP[@]}" -noappend -quiet -e boot/initrd.img-* -e boot/vmlinuz-*

LABEL=""; [ "$FLAVOR" = classic ] && LABEL=" Classic (kiosk)"
# 5. Hybrid ISO: one file that boots on BIOS and UEFI, from optical media or written raw to USB.
#    The second entry copies the whole system into RAM (needs ~4 GB), so a USB stick can be pulled out afterwards.
cat > "$ISO_DIR/boot/grub/grub.cfg" <<GRUB
set timeout=2
set default=0
# console=ttyS0 last makes the serial port the system console, so boot messages stay off the screen (and CI can
# read them); the kernel still logs to the screen too.
menuentry "MWX 7 $VERSION$LABEL" {
  echo "Starting MWX 7 ..."
  linux /live/vmlinuz boot=live components quiet splash loglevel=3 console=tty0 console=ttyS0,115200
  initrd /live/initrd.img
}
menuentry "MWX 7 $VERSION$LABEL (copy to RAM)" {
  echo "Copying MWX 7 into memory, this takes a minute ..."
  linux /live/vmlinuz boot=live components toram quiet splash loglevel=3 console=tty0 console=ttyS0,115200
  initrd /live/initrd.img
}
GRUB
echo "==> ISO"
# UEFI, Secure Boot capable: Microsoft-signed shim -> Debian-signed GRUB (the CD build) -> Debian-signed kernel, the
# same chain Debian's own live images use. The signed GRUB only runs its built-in modules, so grub.cfg sticks to basics.
# Its early config finds the ISO through /.disk/info; the stub grub.cfg next to it covers firmware that sets a prefix.
mkdir -p "$ISO_DIR/.disk"; echo "MWX 7 $VERSION live" > "$ISO_DIR/.disk/info"
EFI_IMG="$OUT/efi.img"; rm -f "$EFI_IMG"
truncate -s 8M "$EFI_IMG"; mkfs.vfat -n MWX7_EFI "$EFI_IMG" >/dev/null
export MTOOLS_SKIP_CHECK=1
cat > "$OUT/efi-stub.cfg" <<'STUB'
search --no-floppy --file --set=root /.disk/info
set prefix=($root)/boot/grub
configfile $prefix/grub.cfg
STUB
mmd -i "$EFI_IMG" ::/EFI ::/EFI/boot
mcopy -i "$EFI_IMG" "$ROOT/usr/lib/shim/shimx64.efi.signed" ::/EFI/boot/bootx64.efi
mcopy -i "$EFI_IMG" "$ROOT/usr/lib/shim/mmx64.efi.signed" ::/EFI/boot/mmx64.efi
mcopy -i "$EFI_IMG" "$ROOT/usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed" ::/EFI/boot/grubx64.efi
mcopy -i "$EFI_IMG" "$OUT/efi-stub.cfg" ::/EFI/boot/grub.cfg
mkdir -p "$ISO_DIR/EFI/boot"; cp "$OUT/efi-stub.cfg" "$ISO_DIR/EFI/boot/grub.cfg"

# Legacy BIOS: an El Torito GRUB core with everything it needs built in, plus a hybrid MBR so a USB stick boots too.
grub-mkimage -O i386-pc-eltorito -p /boot/grub -o "$ISO_DIR/boot/grub/bios.img" \
  biosdisk iso9660 part_msdos part_gpt linux normal search search_fs_file configfile all_video echo test

xorriso -as mkisofs -iso-level 3 -full-iso9660-filenames -joliet -rational-rock -volid MWX7_LIVE \
  -eltorito-boot boot/grub/bios.img -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
  --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
  -append_partition 2 0xef "$EFI_IMG" -appended_part_as_gpt \
  -eltorito-alt-boot -e --interval:appended_partition_2:all:: -no-emul-boot \
  -o "$ISO" "$ISO_DIR" 2>&1 | grep -vE '^xorriso : (UPDATE|NOTE)' || true
rm -f "$EFI_IMG" "$OUT/efi-stub.cfg"
ls -lh "$ISO"
echo "==> Done: $ISO  (how to try it on Windows: distro/RELEASE_NOTES.md)"
