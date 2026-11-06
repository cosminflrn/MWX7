#!/bin/bash
# Headless boot tests for the live ISO, run by CI (works without KVM, just slower). Each one boots through the ISO's
# own boot loader and passes only when Chromium inside the VM has loaded MWX 7's JavaScript from the local server
# (the server's access log reaches the serial port, which is the system console):
#   bios        legacy BIOS, standard VGA (bochs DRM)
#   uefi        UEFI, virtio GPU
#   secureboot  UEFI with Secure Boot enforced (Microsoft keys), virtio GPU
# QEMU's VMware SVGA model is not tested: vmwgfx refuses it ("unsupported hypervisor"), and Debian's kernel has no
# simpledrm fallback, so there is no display by design. Real VMware/VirtualBox and real GPUs all have drivers.
# Needs: qemu-system-x86, ovmf. Usage: ./distro/smoke-test.sh [timeout-seconds per boot, default 900] [tests...]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/out"; ISO="$OUT/mwx7-live.iso"
LIMIT="${1:-900}"; shift || true
TESTS=("${@:-bios uefi secureboot}"); read -r -a TESTS <<< "${TESTS[*]}"
[ -f "$ISO" ] || { echo "No ISO at $ISO (run build-iso.sh first)" >&2; exit 1; }
if [ -w /dev/kvm ]; then ACCEL=kvm; CPU=host; else ACCEL=tcg; CPU=Nehalem; fi

ovmf() {  # $1 = plain | ms (Microsoft keys enrolled, Secure Boot enforced)
  local code=/usr/share/OVMF/OVMF_CODE_4M.fd vars=/usr/share/OVMF/OVMF_VARS_4M.fd
  [ "$1" = ms ] && { code=/usr/share/OVMF/OVMF_CODE_4M.secboot.fd; vars=/usr/share/OVMF/OVMF_VARS_4M.ms.fd; }
  cp "$vars" "$OUT/vars-$1.fd"
  echo "-drive if=pflash,format=raw,readonly=on,file=$code -drive if=pflash,format=raw,file=$OUT/vars-$1.fd"
}

boot() {  # $1 = test name, $2 = machine type, $3 = vga, rest = extra qemu args
  local name="$1" machine="$2" vga="$3"; shift 3
  local log="$OUT/smoke-$name.log" want='GET /assets/.*\.js'; rm -f "$log"
  qemu-system-x86_64 -machine "$machine",accel=$ACCEL -cpu $CPU -smp 2 -m 3072 -display none $vga \
    -cdrom "$ISO" -boot d -serial file:"$log" -no-reboot "$@" &
  local pid=$! t
  for ((t = 0; t < LIMIT; t += 5)); do
    if grep -aqE "$want" "$log" 2>/dev/null; then
      kill $pid 2>/dev/null; wait $pid 2>/dev/null
      echo "PASS $name after ${t}s"; return 0
    fi
    kill -0 $pid 2>/dev/null || { echo "FAIL $name: the VM stopped" >&2; tail -c 3000 "$log" >&2; return 1; }
    sleep 5
  done
  kill $pid 2>/dev/null; wait $pid 2>/dev/null
  echo "FAIL $name: MWX 7 did not load within ${LIMIT}s" >&2
  tr -d '\r' < "$log" | grep -aiE 'error|fail|segfault|panic|denied|violation|display' | tail -30 >&2
  return 1
}

rc=0
for t in "${TESTS[@]}"; do
  case "$t" in
    bios) boot bios pc "-vga std" || rc=1 ;;
    # shellcheck disable=SC2046
    uefi) boot uefi q35 "-device virtio-vga" $(ovmf plain) || rc=1 ;;
    # shellcheck disable=SC2046
    secureboot) boot secureboot "q35,smm=on" "-device virtio-vga" -global driver=cfi.pflash01,property=secure,value=on \
      $(ovmf ms) || rc=1 ;;
    *) echo "unknown test $t" >&2; rc=1 ;;
  esac
done
exit $rc
