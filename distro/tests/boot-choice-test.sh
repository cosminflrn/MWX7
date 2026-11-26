#!/bin/bash
# Which system the boot menu starts (etc/grub.d/01_mwx7_safe + 45_mwx7_menu), checked in real GRUB under UEFI (QEMU +
# OVMF, no KVM needed, about 15 s per case). A small EFI partition holds a GRUB built with grub-mkstandalone and a menu
# made of the real snippets between stand-ins for GRUB's own parts (00_header with MWX 7's hidden 1 s menu, os-prober's
# timeout as mwx7-grub-names patches it). Each entry prints what started to the serial port and powers off; the case
# then checks which entry started, the menu's timeout and what GRUB left in mwx7.env.
# Needs: grub-efi-amd64-bin (or GRUB_MODDIR=…/x86_64-efi), grub-common, qemu-system-x86, ovmf, mtools, dosfstools.
# Run: distro/tests/boot-choice-test.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GRUBD="$HERE/../desktop/overlay/etc/grub.d"
MODDIR="${GRUB_MODDIR:-/usr/lib/grub/x86_64-efi}"
CODE=/usr/share/OVMF/OVMF_CODE_4M.fd; VARS=/usr/share/OVMF/OVMF_VARS_4M.fd
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
export MTOOLS_SKIP_CHECK=1
ESPID=4D58-3701  # the EFI partition's file system UUID (what 01_mwx7_safe searches for)

# The menu: GRUB's header (default 0, MWX 7's hidden menu), 01_mwx7_safe, the entries, os-prober's timeout, 45_mwx7_menu.
make_cfg() {
{
  cat <<'EOF'
serial --unit=0 --speed=115200
terminal_input serial
terminal_output serial
set default="0"
if [ x$feature_timeout_style = xy ] ; then
  set timeout_style=hidden
  set timeout=1
else
  set timeout=1
fi
EOF
  sed -n "/<<'ENTRY'$/,/^ENTRY$/p" "$GRUBD/01_mwx7_safe" | sed '1d;$d' | sed "s/@ESP@/$ESPID/"
  cat <<EOF
menuentry 'MWX 7' --id gnulinux-simple-test { echo "STARTED MWX7"; halt }
menuentry '${WINTITLE:-Windows}' --id osprober-efi-test { echo "STARTED WINDOWS"; halt }
menuentry 'Repair MWX 7' --id mwx7-repair { echo "STARTED REPAIR"; halt }
menuentry 'MWX 7 (previous version)' --id mwx7-previous { echo "STARTED PREVIOUS"; halt }
EOF
  [ -n "${NO_OSPROBER:-}" ] || cat <<'EOF'
set timeout_style=menu
if [ "${timeout}" -lt 5 ]; then  # MWX 7: at least 5 s
  set timeout=5
fi
EOF
  sh "$GRUBD/45_mwx7_menu"
  echo 'echo "MENU timeout=$timeout style=$timeout_style default=$default"'
} > "$W/grub.cfg"
grub-script-check "$W/grub.cfg" || { echo "FAIL: the menu does not parse"; exit 1; }
}
make_cfg
printf 'search --no-floppy --fs-uuid --set=root %s\nconfigfile ($root)/grub.cfg\n' "$ESPID" > "$W/embed.cfg"
grub-mkstandalone -O x86_64-efi -d "$MODDIR" -o "$W/BOOTX64.EFI" --modules="part_gpt fat serial search loadenv test halt echo" \
  "boot/grub/grub.cfg=$W/embed.cfg" || { echo "FAIL: grub-mkstandalone"; exit 1; }

fails=0
# case NAME WINDOWS(1/0) "ENV ASSIGNMENTS or -" EXPECT-STARTED EXPECT-TIMEOUT EXPECT-STYLE "EXPECT ENV AFTER (grep -x lines, ;-separated) or -"
run_case() {
  local name="$1" win="$2" env="$3" want="$4" wtime="$5" wstyle="$6" after="$7" img="$W/esp.img" log="$W/serial.log"
  make_cfg
  rm -f "$img" "$log"; truncate -s 34M "$img"
  mkfs.vfat -F 32 -i "${ESPID/-/}" "$img" >/dev/null
  mmd -i "$img" ::EFI ::EFI/BOOT ::EFI/MWX7
  mcopy -i "$img" "$W/BOOTX64.EFI" ::EFI/BOOT/BOOTX64.EFI
  mcopy -i "$img" "$W/grub.cfg" ::grub.cfg
  if [ "$win" = 1 ]; then
    mmd -i "$img" ::EFI/Microsoft ::EFI/Microsoft/Boot
    echo fake > "$W/bootmgfw.efi"; mcopy -i "$img" "$W/bootmgfw.efi" ::EFI/Microsoft/Boot/bootmgfw.efi
  fi
  if [ "$env" != - ]; then
    rm -f "$W/mwx7.env"; grub-editenv "$W/mwx7.env" create
    # shellcheck disable=SC2086
    [ "$env" = empty ] || grub-editenv "$W/mwx7.env" set $env
    mcopy -i "$img" "$W/mwx7.env" ::EFI/MWX7/mwx7.env
  fi
  cp "$VARS" "$W/vars.fd"
  timeout 120 qemu-system-x86_64 -machine q35 -m 256 -display none -no-reboot -serial file:"$log" \
    -drive if=pflash,format=raw,readonly=on,file="$CODE" -drive if=pflash,format=raw,file="$W/vars.fd" \
    -drive if=none,id=d,file="$img",format=raw -device virtio-blk-pci,drive=d >/dev/null 2>&1
  local got time style envnow ok=1 line
  got=$(tr -d '\r' < "$log" | grep -ao 'STARTED [A-Z0-9]*' | tail -1 | cut -d' ' -f2)
  line=$(tr -d '\r' < "$log" | grep -ao 'MENU timeout=.*' | tail -1)
  time=$(sed -n 's/.*timeout=\([^ ]*\).*/\1/p' <<< "$line"); style=$(sed -n 's/.*style=\([^ ]*\).*/\1/p' <<< "$line")
  envnow=""
  if mcopy -n -i "$img" ::EFI/MWX7/mwx7.env "$W/env.out" 2>/dev/null; then envnow=$(grub-editenv "$W/env.out" list); fi
  rm -f "$W/env.out"
  [ "$got" = "$want" ] && [ "$time" = "$wtime" ] && [ "$style" = "$wstyle" ] || ok=0
  if [ "$after" != - ]; then
    local IFS=';' l
    for l in $after; do
      if [ "${l:0:1}" = '!' ]; then grep -q "^${l:1}" <<< "$envnow" && ok=0; else grep -qx "$l" <<< "$envnow" || ok=0; fi
    done
  fi
  if tr -d '\r' < "$log" | grep -aqi 'error'; then ok=0; echo "  GRUB said: $(tr -d '\r' < "$log" | grep -ai error | head -3)"; fi
  if [ $ok = 1 ]; then
    echo "PASS $name: $got, menu $style ${time}s"
  else
    echo "FAIL $name: started '$got' (want $want), menu '$style' '${time}s' (want $wstyle ${wstyle:+$wtime}s), env: $(tr '\n' ' ' <<< "$envnow")"
    tr -d '\r' < "$log" | grep -av '^\s*$' | tail -5 | sed 's/^/  | /'
    fails=$((fails + 1))
  fi
}

#        name                                   win env                                          started  time style  env afterwards
run_case "switched on, next to Windows"         1 -                                             WINDOWS  10 menu   -
run_case "switched on, env file empty"          1 empty                                         WINDOWS  10 menu   '!mwx7_next'
run_case "restart from MWX 7"                   1 "mwx7_next=mwx7"                              MWX7     1  hidden '!mwx7_next'
run_case "Restart to Windows"                   1 "mwx7_next=windows"                           WINDOWS  1  hidden '!mwx7_next'
run_case "Windows restarts (after the above)"   1 empty                                         WINDOWS  10 menu   '!mwx7_next'
run_case "unknown value is dropped"             1 "mwx7_next=other"                             WINDOWS  1  hidden '!mwx7_next'
run_case "after an update, 1st start"           1 "mwx7_next=mwx7 mwx7_armed=1 mwx7_tries=0"    MWX7     1  hidden 'mwx7_next=mwx7;mwx7_tries=1;mwx7_armed=1'
run_case "after an update, 2nd start"           1 "mwx7_next=mwx7 mwx7_armed=1 mwx7_tries=1"    MWX7     1  hidden 'mwx7_next=mwx7;mwx7_tries=2'
run_case "after an update, 3rd start: back"     1 "mwx7_next=mwx7 mwx7_armed=1 mwx7_tries=2"    PREVIOUS 1  hidden 'mwx7_next=mwx7;mwx7_tries=2'
run_case "armed, switched on: Windows, no count" 1 "mwx7_armed=1 mwx7_tries=0"                  WINDOWS  10 menu   'mwx7_tries=0;mwx7_armed=1'
run_case "armed, Restart to Windows"            1 "mwx7_next=windows mwx7_armed=1 mwx7_tries=1" WINDOWS  1  hidden '!mwx7_next;mwx7_tries=1'
NO_OSPROBER=1 run_case "no Windows: as before"                0 -                                             MWX7     1  hidden -
NO_OSPROBER=1 run_case "no Windows, restart"                  0 "mwx7_next=mwx7"                              MWX7     1  hidden '!mwx7_next'
NO_OSPROBER=1 run_case "Windows on another disk, Restart to Windows" 0 "mwx7_next=windows" WINDOWS 1 hidden '!mwx7_next'
WINTITLE=Other NO_OSPROBER=1 run_case "Windows gone, stale Restart to Windows" 0 "mwx7_next=windows" MWX7 1 hidden '!mwx7_next'
NO_OSPROBER=1 run_case "no Windows, after an update"          0 "mwx7_armed=1 mwx7_tries=0"                   MWX7     1  hidden 'mwx7_tries=1'
NO_OSPROBER=1 run_case "no Windows, 3rd start: back"          0 "mwx7_armed=1 mwx7_tries=2"                   PREVIOUS 1  hidden 'mwx7_tries=2'
NO_OSPROBER=1 run_case "Windows not found by os-prober" 1 -                                     WINDOWS  10 menu   -
WINTITLE='Windows Boot Manager (on /dev/sda1)' run_case "Windows under another name" 1 -           MWX7     10 menu   -
[ $fails = 0 ] && echo "PASS: all boot choices" || echo "FAIL: $fails case(s)"
exit $((fails > 0))
