# If MWX 7 does not start

Do not panic: your files are safe, and MWX 7 has three ways back. Try them in this order. You never need to type anything.

## 1. Wait for the automatic fix (after an update)

When an update is installed, MWX 7 keeps a copy of the version before it. If the new version does not reach the sign-in
screen on two starts in a row, the PC starts the previous version by itself on the third start. When you sign in you
will see a message. Open **Settings, Updates** and choose:

- **Keep the previous version** to stay on it for good, or
- do nothing and a newer update will be offered later.

This only protects updates that change things the PC needs to start (the system core, the screen drivers, the sign-in
screen). It works on PCs that start in UEFI mode, which is nearly every PC made since 2012.

## 2. Repair MWX 7 (keeps everything)

1. Turn the PC off (hold the power button for five seconds) and turn it on again.
2. As soon as it starts, **hold the Esc key** until a menu appears. If MWX 7 starts anyway, restart and try again, a
   little earlier.
3. Click or use the arrow keys to choose **Repair MWX 7** and press Enter.
4. The Repair screen opens with two buttons. Click **Repair, keeping my files**.
5. Wait. It takes a few minutes and works without internet. Do not turn off the PC. It restarts by itself.

Repair puts MWX 7 itself back in order. Your accounts, files, apps and settings stay as they are.

If the Repair screen does not appear within a minute (for example the screen cannot start at all), the PC does the same
repair by itself, with messages on a plain screen.

If it says it did not work, nothing was changed. Restart, and try again, or go on to the next step. The first time you
repair an older PC, MWX 7 may need the internet once to fetch its recovery copy; the message tells you.

## 3. Reset to factory (starts again as new)

This **deletes everything** on this PC: accounts, files, apps and settings. Only use it if Repair did not help, and
only after you have copied what you need somewhere else.

1. Open the boot menu as in step 2 and choose **Repair MWX 7**.
2. Click **Reset to factory**.
3. Read the warning. Click **Delete everything and reset** only if you are sure. **Back** changes your mind.
4. When it restarts, MWX 7 welcomes you as on a new PC.

## Menu choices

- **Repair MWX 7** opens the Repair screen above.
- **MWX 7 (previous version)** starts the system as it was before the last update. Use it if the new version starts but
  something is wrong.
- **Restart** on the Repair screen restarts the PC without changing anything.

## If nothing helps

Start the PC from the MWX 7 USB stick (or a fresh download from the MWX 7 releases page) and choose **Set up MWX 7**.
Take care at the disk page: pick the option that keeps what is on the disk if you want to keep your files, and read
every confirmation before you click.

## For people who look after MWX 7

- The boot entries come from `/etc/grub.d/42_mwx7` and `/etc/grub.d/01_mwx7_safe`.
- Repair runs `/boot/mwx7-recovery/mwx7-repair` (a copy of `bin/mwx7-repair`, `oobe/install.py`, `oobe/repair.py` and
  `oobe/oobe.css` made by `update-grub`) through `systemd.run=` on the kernel command line, so it does not depend on
  `/usr/share/mwx7` or the package state. It calls `install.py reinstall keep|clean`.
- The recovery copy is the btrfs subvolume `@recovery`: the ISO MWX 7 was installed from plus this PC's updated
  packages. Repair and Reset read only that, no internet.
- Safe boot: `mwx7-bootcount arm` (run by `mwx7-update` after an update that touched boot-critical packages) writes
  `mwx7_armed=1` to `EFI/MWX7/mwx7.env` on the EFI partition. GRUB counts starts in `mwx7_tries`; at the third start it
  picks `mwx7-previous`. `mwx7-boot-ok.service` resets it 15 seconds after the sign-in screen is up, and a Repair clears it.
