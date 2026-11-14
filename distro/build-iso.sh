#!/bin/bash
# Builds the MWX 7 ISO (distro/out/mwx7.iso). It starts straight into the first-start setup, which puts MWX 7 on the
# PC's disk (asking where first) and sets it up. Boots on UEFI (Secure Boot on or off) and legacy BIOS, from a VM or a
# USB stick.
# Needs: Debian/Ubuntu host, root, git, node, and:
#   sudo apt install debootstrap squashfs-tools xorriso mtools dosfstools grub-pc-bin
# Usage: sudo ./distro/build-iso.sh
#   REUSE_ROOT=1 keeps the Debian system from the last build and only refreshes MWX 7's own files and packages:
#   minutes instead of a full rebuild, for development. CI always builds from scratch.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
OUT="$HERE/out"; ROOT="$OUT/live-root"; ISO_DIR="$OUT/iso"; ISO="$OUT/mwx7.iso"
# 1.9.0 in package.json + the commit count: every build of main gets a higher number, which is what the update
# channel compares (CI checks out the full history for this).
VERSION="$(node -p "require('$REPO/package.json').version").$(git -C "$REPO" rev-list --count HEAD)"

cleanup() {  # always release the bind mounts, even on failure
  set +e
  for d in dev/pts dev proc sys; do umount "$ROOT/$d" 2>/dev/null; done
}
trap cleanup EXIT

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

# 3. MWX 7: the mwx7-desktop package (built inside the image, see desktop/setup.sh) plus the ISO-only files.
rm -rf "$ROOT/tmp/mwx7-src"; mkdir -p "$ROOT/tmp/mwx7-src/distro" "$ROOT/tmp/mwx7-src/public/media/wallpapers"
cp -a "$HERE/desktop" "$ROOT/tmp/mwx7-src/distro/"
cp "$REPO/CHANGELOG.md" "$ROOT/tmp/mwx7-src/"
# The built web apps (npx vite build); without them the image gets no Notepad, Paint, ...
[ -d "$REPO/dist" ] && cp -a "$REPO/dist" "$ROOT/tmp/mwx7-src/dist" || echo "warning: no dist/ (run 'npx vite build'): the image ships without the web apps" >&2
cp -a "$REPO/public/media/icons" "$REPO/public/media/avatars" "$REPO/public/media/pictures" "$ROOT/tmp/mwx7-src/public/media/"
cp "$REPO/public/media/wallpapers/"{meadow,sierra}.{jpg,mp4} "$ROOT/tmp/mwx7-src/public/media/wallpapers/"
# Owned by root whoever checked the repo out (on GitHub the files belong to the runner user, uid 1001, and sudo
# ignores a sudoers file it does not own: the setup could not get root and never appeared).
cp -a --no-preserve=ownership "$HERE/desktop/live/." "$ROOT/"
# Installer pictures for the advanced path: the orb as its logo, MWX 7 wallpapers for the welcome page and the slides.
B="$ROOT/etc/calamares/branding/mwx7"
cp "$HERE/desktop/overlay/usr/share/mwx7/icons/orb.png" "$B/logo.png"
cp "$REPO/public/media/wallpapers/meadow.jpg" "$B/welcome.jpg"
cp "$REPO/public/media/wallpapers/meadow.jpg" "$B/slide1.jpg"
cp "$REPO/public/media/wallpapers/sierra.jpg" "$B/slide2.jpg"
cp "$REPO/public/media/pictures/alpine-lake.jpg" "$B/slide3.jpg"
: > "$ROOT/etc/fstab"   # live-boot mounts the root itself
for d in dev dev/pts proc sys; do mount --bind "/$d" "$ROOT/$d"; done
chroot "$ROOT" env MWX7_VERSION="$VERSION" /tmp/mwx7-src/distro/desktop/setup.sh
mkdir -p "$OUT/deb"; rm -f "$OUT/deb/"*.deb; cp "$ROOT/tmp/mwx7-deb/"*.deb "$OUT/deb/"
rm -rf "$ROOT/tmp/mwx7-src" "$ROOT/tmp/mwx7-deb"
for d in dev/pts dev proc sys; do umount "$ROOT/$d"; done

# 4. Kernel + initrd next to the compressed root. zstd at a high level is nearly as small as xz but unpacks
#    many times faster on every core, which is what makes starting and installing quick.
cp -L "$ROOT/vmlinuz" "$ISO_DIR/live/vmlinuz"
cp -L "$ROOT/initrd.img" "$ISO_DIR/live/initrd.img"
echo "==> squashfs"
LEVEL=15; [ $REUSE = 1 ] && LEVEL=3   # 15: nearly the size of 19 at a fraction of the build time; dev: 3
LEVEL=${SQUASH_LEVEL:-$LEVEL}
mksquashfs "$ROOT" "$ISO_DIR/live/filesystem.squashfs" -comp zstd -Xcompression-level $LEVEL -noappend -quiet -wildcards \
  -e boot/initrd.img-* -e boot/vmlinuz-* -e tmp/* -e var/cache/apt/*.bin

# 5. Hybrid ISO: one file that boots on BIOS and UEFI, from optical media or written raw to USB.
cat > "$ISO_DIR/boot/grub/grub.cfg" <<GRUB
# Straight to the splash: the menu stays hidden unless Esc (or Shift) is held while it waits a moment.
set timeout_style=hidden
set timeout=1
set default=0
# console=ttyS0 last makes the serial port the system console, so boot messages stay off the screen (and CI can
# read them); the kernel still logs to the screen too.
menuentry "Set up MWX 7 $VERSION" {
  linux /live/vmlinuz boot=live components quiet splash plymouth.ignore-serial-consoles loglevel=3 vt.global_cursor_default=0 console=tty0 console=ttyS0,115200
  initrd /live/initrd.img
}
GRUB
echo "==> ISO"
# UEFI, Secure Boot capable: Microsoft-signed shim -> Debian-signed GRUB (the CD build) -> Debian-signed kernel, the
# same chain Debian's own live images use. The signed GRUB only runs its built-in modules, so grub.cfg sticks to basics.
# Its early config finds the ISO through /.disk/info; the stub grub.cfg next to it covers firmware that sets a prefix.
mkdir -p "$ISO_DIR/.disk"; echo "MWX 7 $VERSION setup" > "$ISO_DIR/.disk/info"
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
echo "==> Done: $ISO"
