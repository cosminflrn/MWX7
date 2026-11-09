MWX 7 as a real operating system: Linux (Debian 13) with the MWX 7 desktop. Real windows, real apps, Google Chrome
(sign in for your bookmarks and passwords), Files and Terminal, plus MWX 7 Classic as an app. It runs from the ISO or
a USB stick and never installs anything or touches your disks.

**Early preview:** the MWX 7 look is being rebuilt natively stage by stage, so some parts are still plain. Nothing is
saved between restarts yet.

## Try it on Windows 11 in a window (safest)
**VMware Workstation Pro** (free):
1. **File → New Virtual Machine → Typical** → Installer disc image: the `mwx7-…iso` below.
2. Linux, **Debian 13.x 64-bit** (or 12.x). Keep the default disk (it stays empty).
3. **Customize Hardware**: Memory **4096 MB**, **2+** processors, Display → tick **Accelerate 3D graphics**.
4. After Finish: **VM → Settings → Options → Advanced → Firmware type UEFI**.
5. Power on. After about a minute you are on the MWX 7 desktop. Click inside to use it, **Ctrl+Alt** to leave.

**VirtualBox** (free): New VM → Linux, Debian (64-bit), **4096 MB**, 2 CPUs, **Enable EFI**, no hard disk; Display →
**VMSVGA**, **Enable 3D Acceleration**, 128 MB video memory. Attach the ISO and start.

To update: **VM → Settings → CD/DVD** → choose the newer ISO. No new VM needed.

## Try it on the real PC from a USB stick
1. Write the ISO to a USB stick (4 GB or larger, its contents are erased) with [Rufus](https://rufus.ie):
   pick the ISO, click **Start**, and choose **Write in DD Image mode** when asked.
2. Restart the PC, open the boot menu (often F12, F11, F8 or Esc right after power-on) and pick the USB stick.
   It works with Secure Boot on.
3. Pull the stick out and restart to be back in Windows. Nothing on the PC was changed.

Checksum: compare the `.sha256` file with `Get-FileHash .\mwx7-….iso` in PowerShell.
