#!/bin/bash
# Headless boot tests for the live ISO, run by CI (works without KVM, just slower):
#   bios, uefi, secureboot : the ISO's own boot loaders bring the system up to its login prompt on the serial port
#   app                    : Chromium inside the live system loads MWX 7's JavaScript from the local server
# Needs: qemu-system-x86, ovmf. Usage: ./distro/smoke-test.sh [timeout-seconds per boot, default 900] [tests...]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/out"; ISO="$OUT/mwx7-live.iso"
LIMIT="${1:-900}"; shift || true
TESTS=("${@:-bios uefi secureboot app}"); read -r -a TESTS <<< "${TESTS[*]}"
[ -f "$ISO" ] || { echo "No ISO at $ISO (run build-iso.sh first)" >&2; exit 1; }
if [ -w /dev/kvm ]; then ACCEL=kvm; CPU=host; else ACCEL=tcg; CPU=Nehalem; fi

ovmf() {  # $1 = plain | ms (Microsoft keys enrolled, Secure Boot enforced)
  local code=/usr/share/OVMF/OVMF_CODE_4M.fd vars=/usr/share/OVMF/OVMF_VARS_4M.fd
  [ "$1" = ms ] && { code=/usr/share/OVMF/OVMF_CODE_4M.secboot.fd; vars=/usr/share/OVMF/OVMF_VARS_4M.ms.fd; }
  cp "$vars" "$OUT/vars-$1.fd"
  echo "-drive if=pflash,format=raw,readonly=on,file=$code -drive if=pflash,format=raw,file=$OUT/vars-$1.fd"
}

boot() {  # $1 = test name, $2 = grep pattern that means success, rest = extra qemu args
  local name="$1" want="$2"; shift 2
  local log="$OUT/smoke-$name.log"; rm -f "$log"
  qemu-system-x86_64 -machine q35,accel=$ACCEL,smm=on -cpu $CPU -smp 2 -m 3072 -display none -device virtio-vga \
    -global driver=cfi.pflash01,property=secure,value=on -cdrom "$ISO" -serial file:"$log" -no-reboot "$@" &
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
  echo "FAIL $name: no '$want' within ${LIMIT}s" >&2
  tr -d '\r' < "$log" | grep -aiE 'error|fail|segfault|panic|denied|violation' | tail -30 >&2
  return 1
}

rc=0
for t in "${TESTS[@]}"; do
  case "$t" in
    bios) boot bios 'login:' || rc=1 ;;
    # shellcheck disable=SC2046
    uefi) boot uefi 'login:' $(ovmf plain) || rc=1 ;;
    # shellcheck disable=SC2046
    secureboot) boot secureboot 'login:' $(ovmf ms) || rc=1 ;;
    # Boot the ISO's kernel directly so the journal goes to the serial port, where the server's access log shows up.
    app) boot app 'GET /assets/.*\.js' -kernel "$OUT/iso/live/vmlinuz" -initrd "$OUT/iso/live/initrd.img" \
      -append "boot=live components console=ttyS0,115200 systemd.journald.forward_to_console=1" || rc=1 ;;
    *) echo "unknown test $t" >&2; rc=1 ;;
  esac
done
exit $rc
