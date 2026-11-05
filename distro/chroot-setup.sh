#!/bin/bash
# Runs INSIDE the new root (called by build.sh via chroot). Installs the kiosk stack and enables services.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# EXTRA_PKGS: set by build-iso.sh to add live-boot (boots the root from a squashfs with a RAM overlay).

cat > /etc/apt/sources.list <<APT
deb http://deb.debian.org/debian bookworm main
deb http://deb.debian.org/debian bookworm-updates main
deb http://deb.debian.org/debian-security bookworm-security main
APT
apt-get update
# linux-image + grub-efi-amd64-bin (build.sh makes a standalone EFI loader, no grub-install); cage/chromium for the kiosk; mesa/libinput for graphics and mouse;
# seatd hands cage the screen and input (a logind session started from a unit is not attached to the seat);
# fonts-dejavu so UI text never falls back to nothing; python3 for the static server.
apt-get install -y --no-install-recommends \
  linux-image-amd64 grub-efi-amd64-bin initramfs-tools systemd-sysv dbus libpam-systemd \
  cage seatd xwayland chromium python3 mesa-utils libgl1-mesa-dri libinput10 fonts-dejavu-core \
  alsa-utils pipewire pipewire-pulse wireplumber rtkit ca-certificates ${EXTRA_PKGS:-}
apt-get clean

# Unprivileged kiosk user with access to GPU, input and sound.
useradd -m -s /bin/bash -G video,render,input,audio mwx
echo 'root:root' | chpasswd   # dev convenience only; change before sharing an image
echo mwx7 > /etc/hostname

# Boot to the graphical target; no getty on tty1 (the kiosk takes it). tty2 keeps a login for debugging.
systemctl set-default graphical.target
systemctl enable seatd.service mwx7-server.service mwx7-kiosk.service
systemctl disable getty@tty1.service || true
