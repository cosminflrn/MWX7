#!/bin/bash
# Signs and publishes the MWX 7 update channel from a machine that holds the update key, for when the
# MWX7_UPDATES_KEY secret is not set in GitHub (updates.yml then uploads the package only).
# Usage: GNUPGHOME=<dir with the key> ./distro/sign-updates.sh   (needs gh, gpg, apt-ftparchive or a Debian chroot)
set -euo pipefail
R=cosminflrn/MWX7
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
cd "$W"
gh release download updates -R "$R" -p '*.deb'
apt-ftparchive packages . > Packages
gzip -9kn Packages
apt-ftparchive -o APT::FTPArchive::Release::Origin="MWX 7" -o APT::FTPArchive::Release::Label="MWX 7" \
  -o APT::FTPArchive::Release::Suite=updates release . > Release
gpg --batch --yes --clearsign -o InRelease Release
gpg --batch --yes -abs -o Release.gpg Release
gh release upload updates -R "$R" --clobber Packages Packages.gz Release Release.gpg InRelease
grep -h '^Version' Packages
