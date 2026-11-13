#!/bin/bash
# Runs inside the image being built (called by build-iso.sh through chroot). Builds and installs the mwx7-desktop
# package, which pulls in everything MWX 7 needs, then adds what only the ISO needs: the first-start setup's user and
# rights, the installer for the "advanced" path, and live-boot.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
SRC=/tmp/mwx7-src

cat > /etc/apt/sources.list <<APT
deb http://deb.debian.org/debian trixie main non-free-firmware
deb http://deb.debian.org/debian trixie-updates main non-free-firmware
deb http://deb.debian.org/debian-security trixie-security main non-free-firmware
APT
apt-get update -qq
# A development rebuild (REUSE_ROOT=1) may start from a system an earlier failed build left half-installed.
dpkg --force-confold --configure -a >/dev/null 2>&1 || true
apt-get -f install -y -qq -o Dpkg::Options::=--force-confold >/dev/null 2>&1 || apt-get purge -y -qq mwx7-desktop >/dev/null 2>&1 || true
apt-get install -y -qq --no-install-recommends python3 ca-certificates >/dev/null
# Google's own Chrome repository, so Chrome updates itself like on Windows. The key is pinned to this one source.
install -d -m 0755 /etc/apt/keyrings
python3 -c "import urllib.request; open('/etc/apt/keyrings/google-chrome.asc','wb').write(urllib.request.urlopen('https://dl.google.com/linux/linux_signing_key.pub').read())"
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.asc] https://dl.google.com/linux/chrome/deb/ stable main" \
  > /etc/apt/sources.list.d/google-chrome.list
apt-get update -qq

echo mwx7 > /etc/hostname
grep -q '127.0.1.1' /etc/hosts 2>/dev/null || printf '127.0.0.1\tlocalhost\n127.0.1.1\tmwx7\n' >> /etc/hosts

# MWX 7 itself. KEEP_BUILD_DEPS=0: the compilers are removed again so they never ship.
KEEP_BUILD_DEPS=0 "$SRC/distro/desktop/build-deb.sh" /tmp/mwx7-deb
# Firmware and CPU microcode are for real PCs (Wi-Fi, graphics, audio; CPU bug fixes): the installed system is a copy of this
# image, so what is here is what a bare-metal install gets. mokutil is for Secure Boot (NVIDIA driver signing).
# --force-confold: our overlay's config files win over a package's own (greetd ships a config.toml).
apt-get install -y --no-install-recommends -o Dpkg::Options::=--force-confold /tmp/mwx7-deb/mwx7-desktop_*.deb \
  google-chrome-stable firmware-amd-graphics firmware-intel-graphics firmware-misc-nonfree firmware-realtek \
  firmware-iwlwifi firmware-atheros firmware-mediatek firmware-brcm80211 firmware-linux-free firmware-sof-signed \
  amd64-microcode intel-microcode mokutil open-vm-tools spice-vdagent qemu-guest-agent cryptsetup cryptsetup-initramfs \
  live-boot squashfs-tools calamares qt6-wayland qml6-module-qtquick qml6-module-qtquick-window
# The ISO starts the first-start setup, not the logon screen: its greetd config wins over the package's, even when the
# build root kept the package's from an earlier build.
install -m 0644 "$SRC/distro/desktop/live/etc/greetd/config.toml" /etc/greetd/config.toml
# Smaller download: left to itself apt picks ukui-polkit as the installer's password prompt (OpenCV and map libraries,
# ~150 MB); lxpolkit is 47 kB.
apt-get purge -y -qq ukui-polkit 2>/dev/null || true
apt-get autoremove -y -qq --purge
rm -f /etc/apt/sources.list.d/google-chrome.sources
/opt/google/chrome/google-chrome --version >/dev/null 2>&1 &&
  install -m 0644 /usr/share/mwx7/chrome/initial_preferences /opt/google/chrome/initial_preferences

# The live user that runs the first-start setup (the setup replaces it with the person's own account).
id mwx >/dev/null 2>&1 || useradd -m -s /bin/bash -c 'MWX 7 Setup' -G video,render,input,audio,netdev mwx
chmod 0440 /etc/sudoers.d/mwx7-live
chown root:root /etc/sudoers.d/mwx7-live
visudo -c >/dev/null  # stop the build if sudo would reject its configuration
chmod 0755 /usr/local/bin/mwx7-install
sed -i "s/@VERSION@/$(cat /usr/share/mwx7/version)/g" /etc/calamares/branding/mwx7/branding.desc
# Only for debugging the ISO from its serial console; the first-start setup locks root on the installed system.
echo 'root:root' | chpasswd
# Bucharest time until the first-start setup picks the time zone.
ln -sf /usr/share/zoneinfo/Europe/Bucharest /etc/localtime
echo Europe/Bucharest > /etc/timezone
systemctl set-default graphical.target
systemctl disable getty@tty1.service >/dev/null 2>&1 || true  # greetd owns tty1
# live-boot writes a network config on start and complains loudly on screen when the folder is missing.
mkdir -p /etc/network
# The splash in the initramfs (and live-boot's scripts) need a fresh one.
update-initramfs -u -k all >/dev/null
apt-get clean
