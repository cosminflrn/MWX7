MWX 7 as a real operating system: Linux (Debian 13) with the MWX 7 desktop. Real windows, real apps, Google Chrome
(sign in for your bookmarks and passwords), Files and Terminal, plus MWX 7 Classic as an app. It runs from the ISO or
a USB stick without touching your disks, and from 1.7.0 it can also be **installed** (see below).

**Preview:** running from the ISO, nothing is saved between restarts. An installed MWX 7 keeps everything.
The live session's password is **mwx7** (for Lock and Log Off → logon screen).

## Try it on Windows 11 in a window (safest)
**VMware Workstation Pro** (free):
1. **File → New Virtual Machine → Typical** → Installer disc image: the `mwx7-…iso` below.
2. Linux, **Debian 13.x 64-bit** (or 12.x). Keep the default 20 GB disk (empty until you install MWX 7 to it).
3. **Customize Hardware**: Memory **4096 MB**, **2+** processors, Display → tick **Accelerate 3D graphics**.
4. After Finish: **VM → Settings → Options → Advanced → Firmware type UEFI**.
5. Power on. After about a minute you are on the MWX 7 desktop. Click inside to use it, **Ctrl+Alt** to leave.

**VirtualBox** (free): New VM → Linux, Debian (64-bit), **4096 MB**, 2 CPUs, **Enable EFI**, no hard disk; Display →
**VMSVGA**, **Enable 3D Acceleration**, 128 MB video memory. Attach the ISO and start.

## Install it (in the virtual machine first)
1. On the MWX 7 desktop click **Install MWX 7** in the dock (the drive icon).
2. Location and keyboard: Bucharest and US English are preselected.
3. Partitions: **Erase disk** uses the whole (virtual) disk. Tick **Encrypt system** to protect it with a passphrase.
4. Your name and a password (6+ characters), then **Install** → **Install Now**. It takes 5–15 minutes.
5. **Restart now**. In VMware disconnect the ISO first (**VM → Settings → CD/DVD → untick Connected**), or it boots
   the ISO again. You arrive at the MWX 7 logon screen.

What an installed MWX 7 has: your own account (root is locked, `sudo` asks for your password), btrfs with compression,
swap in compressed RAM, a firewall that lets nothing unasked in, and daily automatic security updates.

**On a real PC:** "Erase disk" deletes everything on the chosen disk, Windows included. Installing next to Windows is
possible through **Manual partitioning** but has not been tested enough yet; keep to the virtual machine for now.

To update the live ISO: **VM → Settings → CD/DVD** → choose the newer ISO. No new VM needed.

## Try it on the real PC from a USB stick
1. Write the ISO to a USB stick (4 GB or larger, its contents are erased) with [Rufus](https://rufus.ie):
   pick the ISO, click **Start**, and choose **Write in DD Image mode** when asked.
2. Restart the PC, open the boot menu (often F12, F11, F8 or Esc right after power-on) and pick the USB stick.
   It works with Secure Boot on.
3. Pull the stick out and restart to be back in Windows. Nothing on the PC was changed.

Checksum: compare the `.sha256` file with `Get-FileHash .\mwx7-….iso` in PowerShell.
