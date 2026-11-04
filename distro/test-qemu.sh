#!/bin/bash
# Boots distro/out/mwx7.img in QEMU with UEFI. Needs: qemu-system-x86 ovmf (sudo apt install qemu-system-x86 ovmf).
# Usage: ./distro/test-qemu.sh [path-to-image]   (KVM is used automatically when available)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IMG="${1:-$HERE/out/mwx7.img}"
[ -f "$IMG" ] || { echo "Image not found: $IMG (run build.sh first)" >&2; exit 1; }

# Locate UEFI firmware (path differs between distros).
FW=""
for f in /usr/share/OVMF/OVMF_CODE.fd /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/edk2/ovmf/OVMF_CODE.fd /usr/share/qemu/OVMF.fd; do
  [ -f "$f" ] && FW="$f" && break
done
[ -n "$FW" ] || { echo "OVMF firmware not found; install the 'ovmf' package." >&2; exit 1; }

ACCEL=tcg; [ -w /dev/kvm ] && ACCEL=kvm
# virtio-vga-gl is smoother but needs host GL; plain virtio-vga works everywhere. usb-tablet gives an absolute mouse (no capture needed).
exec qemu-system-x86_64 -machine q35,accel=$ACCEL -cpu max -smp 2 -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file="$FW" \
  -drive file="$IMG",format=raw,if=virtio \
  -device virtio-vga -display gtk -device qemu-xhci -device usb-tablet \
  -device intel-hda -device hda-duplex -audiodev pa,id=snd0 2>/dev/null || \
exec qemu-system-x86_64 -machine q35,accel=$ACCEL -cpu max -smp 2 -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file="$FW" -drive file="$IMG",format=raw,if=virtio \
  -device virtio-vga -display gtk -device qemu-xhci -device usb-tablet
