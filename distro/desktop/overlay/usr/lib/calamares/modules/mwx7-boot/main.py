"""Runs after GRUB is installed. Debian's signed GRUB (the one Secure Boot accepts) always reads its first config from
/EFI/debian on the EFI partition, whatever folder it was installed to; without a copy there it stops at a prompt."""
import os
import shutil

import libcalamares


def pretty_name():
    return "Finishing the MWX 7 boot menu"


def run():
    root = libcalamares.globalstorage.value('rootMountPoint')
    efi = os.path.join(root, 'boot/efi/EFI')
    if not os.path.isdir(efi):
        return None  # BIOS install: GRUB reads /boot/grub directly
    ours = next((os.path.join(efi, d, 'grub.cfg') for d in sorted(os.listdir(efi))
                 if d.lower() not in ('boot', 'debian') and os.path.exists(os.path.join(efi, d, 'grub.cfg'))), None)
    if ours:
        for folder in ('debian', 'BOOT'):
            os.makedirs(os.path.join(efi, folder), exist_ok=True)
            shutil.copyfile(ours, os.path.join(efi, folder, 'grub.cfg'))
    # The installer's own module folders were only needed during the installation.
    for leftover in ('usr/lib/calamares',):
        shutil.rmtree(os.path.join(root, leftover), ignore_errors=True)
    return None
