MWX 7 as its own operating system: a live ISO that boots straight into MWX 7, full screen, offline.
It runs from the ISO (or a USB stick) and never installs anything or touches your disks. Turn it off and your PC is
exactly as it was.

## Try it on Windows 11 in a window (safest)
1. Install [VirtualBox](https://www.virtualbox.org/wiki/Downloads) (free).
2. **New** → name `MWX 7`, ISO image: the `mwx7-…-live.iso` below, Type **Linux**, Version **Debian (64-bit)**.
   Tick **Skip Unattended Installation**.
3. Hardware: **3072 MB** memory, **2** CPUs. Tick **Enable EFI**. Hard disk: **Do Not Add a Virtual Hard Disk**.
4. Before starting: **Settings → Display** → Graphics Controller **VMSVGA**, Video Memory **128 MB**.
5. **Start**. GRUB shows the menu for 2 seconds, then "Starting MWX 7 ...". About a minute later you are at the MWX 7
   power switch. If a message appears instead, a photo of it is all that is needed to fix it.

Hyper-V (Windows 11 Pro) works too: Quick Create → Local installation source → the ISO, then turn **Secure Boot off**
under Settings → Security before starting.

## Try it on the real PC from a USB stick
1. Write the ISO to a USB stick (4 GB or larger, its contents are erased) with [Rufus](https://rufus.ie):
   pick the ISO, click **Start**, and choose **Write in DD Image mode** when asked.
2. Restart the PC, open the boot menu (often F12, F11, F8 or Esc right after power-on) and pick the USB stick.
   If it refuses to start, turn off **Secure Boot** in the firmware settings for the test.
3. Pull the stick out and restart to be back in Windows. Nothing on the PC was changed.

The boot menu's second entry, **copy to RAM**, loads everything into memory (needs about 4 GB), so the stick can be
removed while MWX 7 runs.

Checksum: compare the `.sha256` file with `Get-FileHash .\mwx7-…-live.iso` in PowerShell.
