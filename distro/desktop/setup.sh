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
  google-chrome-stable

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
