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
# thunar / foot: file manager and terminal; NetworkManager: wired + Wi-Fi; polkitd: lets the signed-in user shut down; portals: file pickers and screen sharing
# for Chrome; dbus-user-session: per-user bus for portals and PipeWire.
# Our overlay is copied in first, so keep our config files where a package ships its own (greetd).
apt-get install -y --no-install-recommends -o Dpkg::Options::=--force-confold \
  wayfire swaybg greetd dbus-user-session \
  python3-gi gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 libgtk4-layer-shell0 librsvg2-common \
  thunar foot network-manager polkitd \
  xdg-desktop-portal xdg-desktop-portal-wlr xdg-desktop-portal-gtk \
  adwaita-icon-theme fonts-noto-color-emoji \
  google-chrome-stable

# The kiosk is the "Classic" flavour's session; here greetd starts the desktop.
systemctl disable mwx7-kiosk.service
systemctl enable greetd.service NetworkManager.service
# Chrome's package adds its own copy of the repo line on first run; keep ours only.
rm -f /etc/apt/sources.list.d/google-chrome.sources
