#!/bin/bash
# Runs inside the chroot after chroot-setup.sh, for the "desktop" flavour: a real Wayfire desktop with the native
# MWX 7 shell, Google Chrome and real apps, instead of the full-screen web kiosk.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Google's own Chrome repository, so Chrome updates itself like on Windows. The key is pinned to this one source.
install -d -m 0755 /etc/apt/keyrings
python3 -c "import urllib.request; open('/etc/apt/keyrings/google-chrome.asc','wb').write(urllib.request.urlopen('https://dl.google.com/linux/linux_signing_key.pub').read())"
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.asc] https://dl.google.com/linux/chrome/deb/ stable main" \
  > /etc/apt/sources.list.d/google-chrome.list
apt-get update -qq

# wayfire: compositor (glass blur, animations); greetd: logs the user in straight into the session;
# GTK4 + layer-shell + PyGObject: the native MWX 7 status bar and dock; swaybg: wallpaper;
# thunar / foot: file manager and terminal; NetworkManager (+ its connection editor for Wi-Fi/VPN): networking; polkitd: lets the signed-in user shut down; portals: file pickers and screen sharing
# for Chrome; dbus-user-session: per-user bus for portals and PipeWire;
# open-vm-tools / spice-vdagent / qemu-guest-agent: VM integration (window resizing, clipboard, clean shutdown); each
# only starts on its own hypervisor.
# Our overlay is copied in first, so keep our config files where a package ships its own (greetd).
apt-get install -y --no-install-recommends -o Dpkg::Options::=--force-confold \
  wayfire swaybg greetd dbus-user-session \
  python3-gi gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 libgtk4-layer-shell0 librsvg2-common \
  thunar foot network-manager network-manager-gnome polkitd mako-notifier libnotify-bin \
  plymouth plymouth-themes wlr-randr \
  xdg-desktop-portal xdg-desktop-portal-wlr xdg-desktop-portal-gtk \
  adwaita-icon-theme fonts-noto-color-emoji gsettings-desktop-schemas dconf-gsettings-backend libglib2.0-bin \
  open-vm-tools spice-vdagent qemu-guest-agent \
  google-chrome-stable \
  calamares qt6-wayland qml6-module-qtquick qml6-module-qtquick-window squashfs-tools rsync dosfstools btrfs-progs e2fsprogs efibootmgr os-prober \
  grub-efi-amd64 grub-pc-bin cryptsetup cryptsetup-initramfs \
  sudo systemd-zram-generator unattended-upgrades nftables locales util-linux-extra \
  swaylock swayidle lxpolkit xdg-user-dirs

# Smaller download: the installer's disk tools need *a* password-prompt agent, and left to itself apt picked ukui-polkit,
# which pulls in OpenCV and map libraries (~150 MB); lxpolkit is 47 kB. Chromium was only there for MWX 7 Classic,
# which now opens in Google Chrome as an app window (~380 MB less).
apt-get purge -y ukui-polkit chromium chromium-common chromium-sandbox 2>/dev/null || true
apt-get autoremove -y --purge

# --- Installer and installed-system groundwork ---------------------------------------------------------------------
# calamares (+ Qt's Wayland plugin): the installer; it copies this very system from the live medium, so everything an
# installed MWX 7 needs is installed here: both GRUBs (UEFI with Secure Boot, and BIOS), disk encryption, btrfs.
# sudo: administration without a root login; zram: swap in compressed RAM; unattended-upgrades: daily security fixes;
# nftables: a firewall that lets nothing unasked in; swaylock/swayidle: lock screen (Super+L, after 10 idle minutes).
# Real UTF-8 locales (English and Romanian); without them programs fall back to plain ASCII "C".
sed -i -E 's/^# (en_US|en_GB|ro_RO)\.UTF-8 UTF-8/\1.UTF-8 UTF-8/' /etc/locale.gen
locale-gen >/dev/null
update-locale LANG=en_US.UTF-8
chmod 0440 /etc/sudoers.d/mwx7-live
# sudo looks the host name up; without this line every sudo prints a warning and waits.
grep -q '127.0.1.1' /etc/hosts 2>/dev/null || printf '127.0.0.1\tlocalhost\n127.0.1.1\tmwx7\n' >> /etc/hosts
chmod 0755 /usr/local/bin/mwx7-install /usr/local/bin/mwx7-greeter-session
systemctl enable nftables.service
# ldconfig.service rebuilds the library cache whenever /etc looks older than /usr, which on a live image is every boot
# (6 s on the way to the desktop). The image's cache is current, and installing packages refreshes it anyway.
systemctl mask ldconfig.service
# MWX 7's name where programs look for the system's name. Diverted so Debian's base-files updates don't put theirs
# back; ID_LIKE tells package tools that this is Debian underneath.
dpkg-divert --quiet --add --rename --divert /usr/lib/os-release.debian /usr/lib/os-release 2>/dev/null || true
V=$(cat /usr/share/mwx7/version)
cat > /usr/lib/os-release <<OSR
PRETTY_NAME="MWX 7 $V"
NAME="MWX 7"
VERSION_ID="$V"
VERSION="$V"
VERSION_CODENAME=trixie
ID=mwx7
ID_LIKE=debian
HOME_URL="https://cosminflrn.github.io/MWX7/"
SUPPORT_URL="https://github.com/cosminflrn/MWX7/issues"
BUG_REPORT_URL="https://github.com/cosminflrn/MWX7/issues"
OSR
sed -i "s/@VERSION@/$V/g" /etc/calamares/branding/mwx7/branding.desc

fc-cache -f /usr/share/fonts/selawik >/dev/null
# MWX 7 theme and font as the GTK defaults (90_mwx7.gschema.override).
glib-compile-schemas /usr/share/glib-2.0/schemas

# MWX 7's own Wayfire plugins, forks of Wayfire's MIT plugins: window frames (desktop/mwx7-decor) and animations with
# the genie minimize (desktop/mwx7-animate). Compile against Debian's wayfire-dev, install, then remove the toolchain
# again so it doesn't ship.
BUILD_DEPS="wayfire-dev meson ninja-build g++ pkg-config libcairo2-dev libpango1.0-dev libglm-dev nlohmann-json3-dev"
apt-get install -y --no-install-recommends $BUILD_DEPS
for p in mwx7-decor mwx7-animate; do
  (cd /tmp/$p && meson setup build --wipe -Dprefix=/usr >/dev/null && ninja -C build && ninja -C build install)
  rm -rf /tmp/$p
  test -f /usr/lib/x86_64-linux-gnu/wayfire/lib$p.so
done
apt-get purge -y $BUILD_DEPS
apt-get autoremove -y --purge

# MWX 7 boot splash; -R rebuilds the initramfs so the splash starts as early as possible.
plymouth-set-default-theme -R mwx7

# The name shown in the Start menu (the live user has no password; an installed system asks at setup).
usermod -c 'MWX 7 User' mwx
# A known password, so the logon and lock screens can be tried without installing (the installer removes this user).
echo 'mwx:mwx7' | chpasswd

# Bucharest time until MWX 7 Settings can pick the time zone.
ln -sf /usr/share/zoneinfo/Europe/Bucharest /etc/localtime
echo Europe/Bucharest > /etc/timezone

# The kiosk is the "Classic" flavour's session; here greetd starts the desktop.
systemctl disable mwx7-kiosk.service
systemctl enable greetd.service NetworkManager.service
# Chrome reads first-run defaults from next to its binary: use the system window frame (so Chrome gets MWX 7's glass
# frame and traffic lights like every app) and skip the welcome and default-browser prompts.
install -m 0644 /usr/share/mwx7/chrome/initial_preferences /opt/google/chrome/initial_preferences
# Chrome's package adds its own copy of the repo line on first run; keep ours only.
rm -f /etc/apt/sources.list.d/google-chrome.sources
