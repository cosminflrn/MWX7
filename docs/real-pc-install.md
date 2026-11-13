# Installing MWX 7 on a real PC (checklist)

Written for the Ryzen 5 2600 PC with an NVIDIA card, currently running Windows 11 on UEFI. Read it once before you start.

## 1. Before anything: back up

- Copy everything you care about to an external drive or cloud: documents, photos, browser bookmarks, game saves.
- Write down your Windows licence and Wi-Fi password. Windows 11 usually re-activates by itself from your Microsoft account.
- If Windows uses **BitLocker / "device encryption"** (common on Windows 11), find your recovery key at
  https://account.microsoft.com/devices/recoverykey and save it. Changing boot settings can make Windows ask for it.
- Best option for a first try: **install MWX 7 on its own disk** (an old SSD, or unplug the Windows disk while installing).
  Then Windows cannot be touched at all.

## 2. Make the USB stick

- Download `mwx7.iso` from the GitHub releases. Use a stick of 8 GB or more; everything on it is erased.
- Write it with **Rufus** (choose "DD image mode" if it asks) or **balenaEtcher**. Do not just copy the file onto the stick.
- Optional: check the download is complete (the file size matches the release page).

## 3. BIOS / UEFI settings

Start the PC and press Del or F2 (Ryzen boards) to enter the BIOS.

- **Boot mode: UEFI** (not CSM / Legacy). Windows 11 already needs this.
- **Secure Boot:** MWX 7 boots with it on (it uses Microsoft-signed shim and Debian's signed GRUB). If the stick does not
  start, switch Secure Boot off for the install and try again. NVIDIA's driver is the one thing Secure Boot gets in the
  way of (see step 7).
- Put the USB stick first in the boot order, or use the boot menu key (F11 or F12 on most boards).
- Leave "Fast Boot" / "Ultra fast boot" off while installing if the stick is not found.
- Also in Windows, turn off **Fast Startup** (Control Panel, Power Options, "Choose what the power buttons do") if you
  want to share a disk with Windows later. Fast Startup leaves Windows' disk half-asleep and unsafe to touch.

## 4. What the installer does to the disk

On the "Where should MWX 7 go?" page every disk is listed with its **model, size, type (NVMe/SATA/USB) and device name**.
Check these against what you know about your PC. The USB stick you started from is shown greyed out and is never touched.

You get one of these, depending on the disk:

| You choose | What happens |
| --- | --- |
| An **empty** disk | MWX 7 is installed on all of it. |
| **Use the free space** | Only unused space is used. Nothing existing is changed or deleted. Needs 20 GB or more of free space. |
| **Install alongside Windows** | Shown when the disk has Windows. MWX 7 shrinks the Windows partition for you, uses the room it frees, and adds itself to the existing EFI partition (never formatted). You pick the size with a slider. See "Install alongside Windows" below. |
| **Erase this disk and use all of it** | Everything on that disk is deleted: Windows, files, all partitions. You must tick a box that names the disk. There is no undo. |
| **Advanced: choose partitions yourself** | The full installer (Calamares). This is the way to put MWX 7 next to Windows on one disk. |

Layout it creates: a 512 MB EFI partition, then one btrfs partition (with compression) for the whole system. No swap
partition (it uses compressed RAM instead).

The disk list also says what is on each disk, found by reading it (nothing is written): for example "Windows 11 · BitLocker on".

Before anything is changed, a final screen lists exactly what will happen (which partition is shrunk to what size, what is
created, what is erased). Nothing is written until you press "Install MWX 7" there; "Go back" changes nothing.

### Install alongside Windows

What it does, in this order (it stops at the first problem and Windows is only touched after every check has passed):

1. Checks: UEFI mode, GPT disk with an EFI partition that has at least 15 MB free, Windows **not** BitLocker-encrypted, Windows
   shut down completely, the NTFS volume healthy (`ntfsresize --info`).
2. Test run of the shrink (`ntfsresize --no-action`), which must succeed.
3. Shrinks the Windows file system (`ntfsresize`), then its partition (`parted resizepart`, with `sfdisk` as fallback), then
   creates the MWX 7 partition in the freed gap. The EFI partition is reused, not formatted; the other partitions
   (MSR, Recovery) are not touched.
4. Installs MWX 7 there and adds Windows to the boot menu (GRUB's os-prober; if that finds nothing, a direct entry for
   `EFI/Microsoft/Boot/bootmgfw.efi`). The menu shows for 5 seconds.

Limits: MWX 7 gets at least **40 GB**; Windows keeps at least **30 GB free** after shrinking (the slider only offers what fits).
If either does not fit, free space inside Windows first (Disk Cleanup, uninstall programs), then restart and shut down.

It refuses, with the reason on screen, when:

- **BitLocker / device encryption is on:** "Turn off BitLocker in Windows first, or back up your recovery key." Turning it off
  (Settings, Privacy & security, Device encryption, or Control Panel, BitLocker) decrypts the disk, which takes a while.
- **Windows was not shut down completely** (Fast Startup or hibernation): in Windows open Control Panel, Power Options,
  "Choose what the power buttons do", "Change settings that are currently unavailable", untick "Turn on fast startup".
  Then choose **Restart** once and shut the PC down. (Shutdown with Fast Startup on still counts as hibernation.)
- The disk is not GPT/UEFI, or the volume needs a disk check (run `chkdsk /f` in Windows first).

If the power fails or the install stops midway: after the shrink step Windows still works (a smaller file system in a
partition is harmless; the order guarantees it). Back up first anyway.

For developers: `MWX7_INSTALL_DRYRUN=1 install.py copy alongside DISK GIB` runs the checks and prints the commands that would
change the disk (`DRYRUN ...`) without running them. `python3 distro/tests/test_install_alongside.py` checks the logic with a
fake disk.

Resizing Windows yourself first (Disk Management, Shrink Volume, leave 60 GB or more unallocated) and then picking "Use the
free space" or Advanced still works too.

## 5. Installing

1. Boot from the stick. The MWX 7 setup appears. Join Wi-Fi if you have no cable (the setup needs the internet only for updates).
2. Pick the disk and the option from step 4. Read the disk name twice before ticking an erase box.
3. Answer the questions (name, password, language, keyboard, time zone). The copy runs in the background (a few minutes).
4. When it says it is done, restart and **remove the USB stick** when the screen goes black.

## 6. First boot: what to check

- The boot menu is hidden when MWX 7 is the only system (hold Esc to show it). With Windows present it shows for 5 seconds.
- If the PC boots straight into Windows again: enter the BIOS boot menu and pick "MWX7" (or "Debian"), or move it first in
  the boot order. (Windows updates sometimes put Windows first again.)
- Check: sound, Wi-Fi/Ethernet, Bluetooth, the screen's resolution and refresh rate, both monitors, sleep and wake.
- The first start uses the open-source **nouveau** driver for NVIDIA. It works for the desktop; it is slower in games and
  may not use the full refresh rate or the best power saving.
- Settings, Updates: install any updates. CPU microcode and Wi-Fi/graphics firmware are already included.
- If you see a black screen after the logo: press Ctrl+Alt+F3 for a text console, or reboot and pick the previous
  version/Repair from the boot menu (hold Esc).

## 7. NVIDIA driver (optional, after the first boot works)

1. Connect to the internet. Open **Settings, Display** and press **Use the NVIDIA driver**. It adds Debian's non-free
   packages, installs the kernel headers (DKMS builds the driver for this PC) and the driver. It takes several minutes.
2. **Secure Boot ON?** Unsigned drivers are blocked. Settings tells you what to do: at the next start a blue screen
   (MOK manager) appears; choose **Enroll MOK, Continue, Yes**, type the password `mwx7mwx7`, then Reboot. The simpler
   alternative is switching Secure Boot off in the BIOS.
3. Restart. Check it worked: open a Terminal and run `lsmod | grep nvidia` (it should list nvidia modules; nothing listed means it is still on nouveau).
4. If the screen is black or broken afterwards: choose Repair / the previous version from the boot menu, or from the text
   console (Ctrl+Alt+F3) run `sudo /usr/share/mwx7/bin/mwx7-admin nvidia remove` (or `sudo apt remove --purge nvidia-driver`) and reboot.
   Settings, Display, "Remove the NVIDIA driver" does the same when the desktop works.

Debian 13 ships driver version 550. Very old cards (GeForce 700 series and older) are not supported by it; stay on nouveau.

## 8. Known limits (not done yet)

- "Install alongside" needs Windows on a GPT disk with its EFI partition on the same disk and no BitLocker; anything else
  goes through Advanced. It has been checked against a fake disk and a dry run, not yet on a real Windows disk.
- The installer does not install Secure Boot keys for you; Debian's signed boot chain is used as is.
- Windows updates or "Reset this PC" can reorder or remove the EFI boot entries. The MWX 7 files stay in `EFI/MWX7`
  (and `EFI/BOOT` when MWX 7 owns the EFI partition); re-add the entry from the BIOS boot menu if needed.
- Only tested in VMware so far. Treat the first real install as a test: back up and keep the Windows recovery key.
