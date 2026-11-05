#!/bin/bash
# Boots distro/out/mwx7.img in QEMU with UEFI. Needs: qemu-system-x86 ovmf (sudo apt install qemu-system-x86 ovmf).
# Usage: ./distro/test-qemu.sh [path-to-image]   (KVM is used automatically when available)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IMG="${1:-$HERE/out/mwx7.img}"
[ -f "$IMG" ] || { echo "Image not found: $IMG (run build.sh first)" >&2; exit 1; }

# Locate UEFI firmware (path differs between distros). The 4M builds need a writable copy of their VARS file.
FW=""; VARS=""
for f in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd /usr/share/edk2/ovmf/OVMF_CODE.fd /usr/share/qemu/OVMF.fd; do
  [ -f "$f" ] && FW="$f" && break
done
[ -n "$FW" ] || { echo "OVMF firmware not found; install the 'ovmf' package." >&2; exit 1; }
for v in "${FW/CODE/VARS}" /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS.fd; do
  [ -f "$v" ] && [ "$v" != "$FW" ] && VARS="$v" && break
done
PFLASH=(-drive if=pflash,format=raw,readonly=on,file="$FW")
if [ -n "$VARS" ]; then
  cp "$VARS" "${TMPDIR:-/tmp}/mwx7-vars.fd"
  PFLASH+=(-drive if=pflash,format=raw,file="${TMPDIR:-/tmp}/mwx7-vars.fd")
fi

# With KVM use the host CPU. Without it, a conservative model: under pure emulation '-cpu max' advertises
# instructions that crash Chromium (seen with QEMU 8.2 TCG).
if [ -w /dev/kvm ]; then ACCEL=kvm; CPU=host; else ACCEL=tcg; CPU=Nehalem; fi
# snapshot=on keeps the image pristine between test runs. usb-tablet gives an absolute mouse (no grab needed).
# The guest has no 3D in plain virtio-vga, so the kiosk falls back to software rendering after one quick retry.
COMMON=(-machine q35,accel=$ACCEL -cpu $CPU -smp 2 -m 3072 "${PFLASH[@]}"
  -drive file="$IMG",format=raw,if=virtio,snapshot=on -device virtio-vga -device qemu-xhci -device usb-tablet
  -serial mon:stdio)
qemu-system-x86_64 "${COMMON[@]}" -display gtk -device intel-hda -device hda-duplex -audiodev pa,id=snd0 2>/dev/null ||
  exec qemu-system-x86_64 "${COMMON[@]}" -display gtk
