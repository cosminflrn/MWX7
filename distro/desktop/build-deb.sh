#!/bin/bash
# Builds mwx7-desktop_<version>_amd64.deb: everything MWX 7 adds on top of Debian (shell, apps, settings, logon screen,
# first-start setup, Wayfire plugins, theme, fonts, boot menu) in one package. The ISO installs it, and the update
# channel ships new builds of it, so an installed MWX 7 gets every change through Settings -> Updates.
# Runs as root on Debian 13 (CI: a debian:trixie container; build-iso.sh: inside the image being built).
# Usage: MWX7_VERSION=1.9.0.200 ./distro/desktop/build-deb.sh OUT-DIR
#   KEEP_BUILD_DEPS=1 leaves the compilers installed (the ISO build sets 0 so they never ship).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$(mkdir -p "$1" && cd "$1" && pwd)"
V="${MWX7_VERSION:?set MWX7_VERSION}"

BUILD_DEPS="wayfire-dev meson ninja-build g++ pkg-config libcairo2-dev libpango1.0-dev libglm-dev nlohmann-json3-dev dpkg-dev"
# grub-common (grub-mkfont) stays: the installed system needs it anyway.
# shellcheck disable=SC2086
apt-get install -y -qq --no-install-recommends $BUILD_DEPS grub-common >/dev/null

PKG="$(mktemp -d)"; chmod 0755 "$PKG"
trap 'rm -rf "$PKG" /tmp/mwx7-plugin-build' EXIT
cp -a "$HERE/overlay/." "$PKG/"
S="$PKG/usr/share/mwx7"
mkdir -p "$S/icons" "$S/wallpapers" "$PKG/usr/share/fonts/selawik"
cp -a "$REPO/public/media/icons/." "$S/icons/"
cp -a "$REPO/public/media/avatars" "$S/avatars"
cp "$REPO/public/media/wallpapers/meadow.jpg" "$S/wallpaper.jpg"
cp "$REPO/public/media/wallpapers/meadow.jpg" "$REPO/public/media/wallpapers/sierra.jpg" \
   "$REPO/public/media/pictures/"*.jpg "$S/wallpapers/"
# Selawik (OFL) as TTF: Pango loads fonts through HarfBuzz, which can't read the website's WOFF2.
cp -a "$HERE/fonts/selawik/." "$PKG/usr/share/fonts/selawik/"
echo "$V" > "$S/version"
# What's new (Settings -> Updates): the newest section of CHANGELOG.md, bullets only.
awk '/^## /{n++; next} n!=1{next} /^- /{if (b) print b; b=substr($0,3); next} /^  /{sub(/^ +/," "); b=b $0; next}
     END{if (b) print b}' "$REPO/CHANGELOG.md" | sed 's/\*\*//g' > "$S/whats-new" 2>/dev/null || true

# MWX 7's Wayfire plugins (forks of Wayfire's MIT plugins): window frames and animations with the genie minimize.
for p in mwx7-decor mwx7-animate; do
  rm -rf /tmp/mwx7-plugin-build; cp -a "$HERE/$p" /tmp/mwx7-plugin-build
  (cd /tmp/mwx7-plugin-build && meson setup build -Dprefix=/usr >/dev/null && ninja -C build >/dev/null &&
   DESTDIR="$PKG" ninja -C build install >/dev/null)
  test -f "$PKG/usr/lib/x86_64-linux-gnu/wayfire/lib$p.so"
done
# The boot menu's font, in GRUB's own format.
for size in 16 20; do
  grub-mkfont -s $size -o "$PKG/usr/share/grub/themes/mwx7/selawik-$size.pf2" "$PKG/usr/share/fonts/selawik/selawik-regular.ttf"
done

mkdir -p "$PKG/DEBIAN"
DEPS=$(grep -v '^\s*#' "$HERE/debian/depends" | tr -s ' \n' ' ' | sed 's/^ //; s/ $//; s/ /, /g')
RECS=$(grep -v '^\s*#' "$HERE/debian/recommends" | tr -s ' \n' ' ' | sed 's/^ //; s/ $//; s/ /, /g')
cat > "$PKG/DEBIAN/control" <<CONTROL
Package: mwx7-desktop
Version: $V
Architecture: amd64
Maintainer: MWX 7 <noreply@github.com>
Section: x11
Priority: optional
Installed-Size: $(du -sk "$PKG" | cut -f1)
Depends: $DEPS
Recommends: $RECS
Homepage: https://github.com/cosminflrn/MWX7
Description: MWX 7 desktop
 The MWX 7 desktop on Debian: shell, apps, settings, logon screen, first-start setup, window frames and animations,
 theme, fonts and boot menu.
CONTROL
for s in preinst postinst postrm; do install -m 0755 "$HERE/debian/$s" "$PKG/DEBIAN/$s"; done
chmod 0440 "$PKG/etc/sudoers.d/"* 2>/dev/null || true
F="$OUT/mwx7-desktop_${V}_amd64.deb"
dpkg-deb --root-owner-group -Zzstd -b "$PKG" "$F" >/dev/null

if [ "${KEEP_BUILD_DEPS:-1}" = 0 ]; then
  # shellcheck disable=SC2086
  apt-get purge -y -qq $BUILD_DEPS >/dev/null
  apt-get autoremove -y -qq --purge >/dev/null
fi
ls -l "$F"
