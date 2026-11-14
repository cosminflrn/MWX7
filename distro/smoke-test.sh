#!/bin/bash
# Headless boot tests for the MWX 7 ISO, run by CI (works without KVM, just slower). Each one boots through the ISO's
# own boot loader and passes only when the MWX 7 first-start setup is on screen (it writes MWX7-SETUP-READY to the
# serial port, which is the system console):
#   bios        legacy BIOS, standard VGA (bochs DRM)
#   uefi        UEFI, virtio GPU
#   secureboot  UEFI with Secure Boot enforced (Microsoft keys), virtio GPU
#   install     UEFI, a blank 24 GB disk: boots the ISO with mwx7.autoinstall=/dev/vda (install.py's test hook: the same
#               "erase disk" code as the setup, user test/test), waits for MWX7-INSTALL-DONE, then boots the installed
#               disk alone and waits for MWX7-LOGON-READY (mwx7-logon-marker.service). Slow without KVM (up to an hour).
#   session     continues from the installed disk (the install test's, or installs first): boots it with an SMBIOS credential
#               that turns on mwx7-session-marker.service, signs in as test over QMP (distro/session-test.py), waits for
#               MWX7-SESSION-READY, takes PNG screenshots (desktop, Start menu, Notepad, traffic-light hover) into out/session/
#               and fails when the shell or Wayfire logged a Python traceback. SESSION_SCALE (default 6 without KVM) stretches waits.
# QEMU's VMware SVGA model is not tested: vmwgfx refuses it ("unsupported hypervisor"), and Debian's kernel has no
# simpledrm fallback, so there is no display by design. Real VMware/VirtualBox and real GPUs all have drivers.
# Needs: qemu-system-x86, ovmf. Usage: ./distro/smoke-test.sh [timeout-seconds per boot, default 900] [tests...]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${MWX7_OUT:-$HERE/out}"; ISO="$OUT/mwx7.iso"; WANT='MWX7-SETUP-READY'
LIMIT="${1:-900}"; shift || true
TESTS=("${@:-bios uefi secureboot}"); read -r -a TESTS <<< "${TESTS[*]}"
[ -f "$ISO" ] || { echo "No ISO at $ISO (run build-iso.sh first)" >&2; exit 1; }
# A character device only: a leftover plain file must not select KVM.
if [ -c /dev/kvm ] && [ -r /dev/kvm ] && [ -w /dev/kvm ]; then ACCEL=kvm; CPU=host; else ACCEL=tcg; CPU=Nehalem; fi

ovmf() {  # $1 = plain | ms (Microsoft keys enrolled, Secure Boot enforced)
  local code=/usr/share/OVMF/OVMF_CODE_4M.fd vars=/usr/share/OVMF/OVMF_VARS_4M.fd
  [ "$1" = ms ] && { code=/usr/share/OVMF/OVMF_CODE_4M.secboot.fd; vars=/usr/share/OVMF/OVMF_VARS_4M.ms.fd; }
  cp "$vars" "$OUT/vars-$1.fd"
  echo "-drive if=pflash,format=raw,readonly=on,file=$code -drive if=pflash,format=raw,file=$OUT/vars-$1.fd"
}

boot() {  # $1 = test name, $2 = machine type, $3 = vga, rest = extra qemu args
  local name="$1" machine="$2" vga="$3"; shift 3
  local log="$OUT/smoke-$name.log" want="$WANT"; rm -f "$log"
  qemu-system-x86_64 -machine "$machine",accel=$ACCEL -cpu $CPU -smp 2 -m 3072 -display none $vga \
    -cdrom "$ISO" -boot d -chardev socket,id=s0,path="$OUT/smoke-$name.sock",server=on,wait=off,logfile="$log" \
    -serial chardev:s0 -no-reboot "$@" &
  local pid=$! t
  for ((t = 0; t < LIMIT; t += 5)); do
    if grep -aqE "$want" "$log" 2>/dev/null; then
      kill $pid 2>/dev/null; wait $pid 2>/dev/null
      echo "PASS $name after ${t}s"; return 0
    fi
    kill -0 $pid 2>/dev/null || { echo "FAIL $name: the VM stopped" >&2; tail -c 3000 "$log" >&2; return 1; }
    sleep 5
  done
  # Log in on the serial console (the ISO's root password is only for this) and collect what the setup said.
  python3 - "$OUT/smoke-$name.sock" <<'PY' >&2 || true
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.settimeout(1)
def say(t, wait):
    s.sendall(t.encode()); end = time.time() + wait; out = b''
    while time.time() < end:
        try:
            out += s.recv(65536)
        except socket.timeout:
            pass
    return out
say('\n', 3); say('root\n', 5); say('root\n', 8)
print(say('echo ===; pkill -USR1 -f oobe.py; sleep 2; tail -60 /tmp/mwx7-oobe.log; '
          'journalctl -b --no-pager -u greetd | tail -8; ls -l /etc/sudoers.d; '
          'ps -eo pid,stat,etime,args | grep -E "python|sudo|cage|timedatectl|nmcli" | grep -v grep\n', 30)
      .decode(errors='replace'))
PY
  kill $pid 2>/dev/null; wait $pid 2>/dev/null
  echo "FAIL $name: no '$want' within ${LIMIT}s" >&2
  tr -d '\r' < "$log" | grep -aiE 'error|fail|segfault|panic|denied|violation|display' | tail -30 >&2
  return 1
}

install_test() {
  local disk="$OUT/smoke-install.qcow2" t0=$SECONDS
  local ilog="$OUT/smoke-install.log" blog="$OUT/smoke-install-boot.log" limit="${INSTALL_LIMIT:-3600}" pid t
  rm -f "$disk" "$ilog" "$blog"; qemu-img create -q -f qcow2 "$disk" 24G
  # The ISO's kernel and initrd, started directly: that is how the extra kernel option gets in without editing GRUB.
  local kdir; kdir="$(mktemp -d)"
  xorriso -osirrox on -indev "$ISO" -extract /live/vmlinuz "$kdir/vmlinuz" -extract /live/initrd.img "$kdir/initrd.img" \
    >/dev/null 2>&1 || { echo "FAIL install: cannot extract the kernel from the ISO" >&2; return 1; }
  # shellcheck disable=SC2046
  qemu-system-x86_64 -machine q35,accel=$ACCEL -cpu $CPU -smp 2 -m "${MWX7_MEM:-3072}" -display none -device virtio-vga $(ovmf plain) \
    -cdrom "$ISO" -drive if=none,id=d0,file="$disk",format=qcow2 -device virtio-blk-pci,drive=d0 \
    -kernel "$kdir/vmlinuz" -initrd "$kdir/initrd.img" \
    -append "boot=live components quiet loglevel=3 console=ttyS0,115200 mwx7.autoinstall=/dev/vda" \
    -chardev socket,id=s0,path="$OUT/smoke-install.sock",server=on,wait=off,logfile="$ilog" -serial chardev:s0 -no-reboot &
  pid=$!
  for ((t = 0; t < limit; t += 10)); do
    if grep -aq 'MWX7-INSTALL-FAILED' "$ilog" 2>/dev/null; then
      kill $pid 2>/dev/null; wait $pid 2>/dev/null
      echo "FAIL install: $(tr -d '\r' < "$ilog" | grep -a 'MWX7-INSTALL-FAILED' | tail -1)" >&2; return 1
    fi
    # The hook powers the VM off when the install is done.
    if ! kill -0 $pid 2>/dev/null; then
      grep -aq 'MWX7-INSTALL-DONE' "$ilog" && break
      echo "FAIL install: the VM stopped before MWX7-INSTALL-DONE" >&2; tail -c 3000 "$ilog" >&2; return 1
    fi
    sleep 10
  done
  if kill -0 $pid 2>/dev/null; then
    kill $pid; wait $pid 2>/dev/null; echo "FAIL install: no MWX7-INSTALL-DONE within ${limit}s" >&2; tail -c 3000 "$ilog" >&2; return 1
  fi
  local t1=$((SECONDS - t0)); echo "install finished after ${t1}s"
  # shellcheck disable=SC2046
  qemu-system-x86_64 -machine q35,accel=$ACCEL -cpu $CPU -smp 2 -m "${MWX7_MEM:-3072}" -display none -device virtio-vga $(ovmf plain) \
    -drive if=none,id=d0,file="$disk",format=qcow2 -device virtio-blk-pci,drive=d0 \
    -chardev socket,id=s0,path="$OUT/smoke-install.sock",server=on,wait=off,logfile="$blog" -serial chardev:s0 -no-reboot &
  pid=$!
  for ((t = 0; t < LIMIT; t += 5)); do
    if grep -aq 'MWX7-LOGON-READY' "$blog" 2>/dev/null; then
      kill $pid 2>/dev/null; wait $pid 2>/dev/null; echo "PASS install: installed in ${t1}s, logon screen after ${t}s"; return 0
    fi
    kill -0 $pid 2>/dev/null || { echo "FAIL install: the installed system stopped" >&2; tail -c 3000 "$blog" >&2; return 1; }
    sleep 5
  done
  kill $pid 2>/dev/null; wait $pid 2>/dev/null
  echo "FAIL install: no MWX7-LOGON-READY within ${LIMIT}s" >&2; tail -c 3000 "$blog" >&2; return 1
}

session_test() {
  # Continues from the installed disk of the install test (installs first when it is not there): signs in as test, then
  # session-test.py takes screenshots over QMP into $OUT/session/ and fails when the shell logged a traceback.
  local disk="$OUT/smoke-install.qcow2" slog="$OUT/smoke-session.log" scale=1 pid rc
  [ -f "$disk" ] || install_test || return 1
  [ "$ACCEL" = kvm ] || scale="${SESSION_SCALE:-6}"
  rm -rf "$OUT/session" "$slog" "$OUT/session.qmp"; mkdir -p "$OUT/session"
  # SMBIOS credential: lets mwx7-session-marker.service (root, serial marker + crash report) run; absent on every real PC.
  # shellcheck disable=SC2046
  qemu-system-x86_64 -machine q35,accel=$ACCEL -cpu $CPU -smp 2 -m "${MWX7_MEM:-3072}" -display none -device virtio-vga $(ovmf plain) \
    -device qemu-xhci -device usb-tablet \
    -drive if=none,id=d0,file="$disk",format=qcow2 -device virtio-blk-pci,drive=d0 \
    -smbios type=11,value=io.systemd.credential:mwx7.test=1 \
    -qmp unix:"$OUT/session.qmp",server=on,wait=off \
    -chardev socket,id=s0,path="$OUT/smoke-session.sock",server=on,wait=off,logfile="$slog" -serial chardev:s0 -no-reboot &
  pid=$!
  python3 "$HERE/session-test.py" "$OUT/session.qmp" "$slog" "$OUT/session" "$scale"; rc=$?
  kill $pid 2>/dev/null; wait $pid 2>/dev/null
  if [ $rc -eq 0 ]; then echo "PASS session: signed in, shell up, screenshots in $OUT/session"; return 0; fi
  echo "FAIL session (screenshots and logs in $OUT/session and $slog)" >&2; tail -c 3000 "$slog" >&2; return 1
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
    install) install_test || rc=1 ;;
    session) session_test || rc=1 ;;
    *) echo "unknown test $t" >&2; rc=1 ;;
  esac
done
exit $rc
