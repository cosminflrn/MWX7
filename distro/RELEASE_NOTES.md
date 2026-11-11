MWX 7 as a real operating system: Linux (Debian 13) with the MWX 7 desktop. Real windows, real apps, Google Chrome
(sign in for your bookmarks and passwords), Files and Terminal.

Start the ISO and you are in the **MWX 7 setup**: pick your language, where MWX 7 goes, your name and picture, and a
password (or tick **No password**). MWX 7 copies itself to the disk while you fill that in, restarts, and you sign in.
After that it updates itself: **Settings → Updates → Check for updates**. You never need a newer ISO for a PC that
already has MWX 7.

## In VMware Workstation Pro (Windows 11)
1. **File → New Virtual Machine → Typical** → Installer disc image: the `mwx7-…iso` below.
2. Linux, **Debian 13.x 64-bit** (or 12.x). Disk: **60 GB** (at least 20), stored on your fastest drive.
3. **Customize Hardware**: Memory **4096–6144 MB**, Processors **1 × 4 cores**, Display → tick **Accelerate 3D
   graphics** (graphics memory 2–4 GB). Remove the printer and floppy if listed.
4. After Finish: **VM → Settings → Options → Advanced → Firmware type UEFI** (Secure Boot may stay on). If the status
   bar later shows a turtle, also tick **Disable side channel mitigations for Hyper-V enabled hosts** there.
5. Power on and go through the setup. The virtual disk is empty, so choose it and click Next; nothing to confirm.
6. When it says MWX 7 is ready it restarts by itself into the logon screen. Click your picture.
7. Take a snapshot (**VM → Snapshot → Take Snapshot**, "Fresh install") so you can always go back in seconds.

From then on: **Settings → Updates → Check for updates**, then **Install now** and **Restart now**.

## On a real PC (later, when it's ready for daily use)
1. Back up what matters first.
2. Write the ISO to a USB stick (4 GB or larger, its contents are erased) with [Rufus](https://rufus.ie): pick the ISO,
   click **Start**, and choose **Write in DD Image mode** when asked.
3. Restart the PC, open its boot menu (often F12, F11, F8 or Esc right after power-on) and pick the USB stick. It works
   with Secure Boot on.
4. In the setup, the disk page says what is on every disk ("Windows, files", "Empty"). A disk with something on it
   offers **Use the free space** (keeps everything) or **Erase this disk**, which you must confirm by ticking what will
   be deleted. **Advanced** opens the full installer: next to Windows (it shrinks a partition), or with disk encryption.

What an installed MWX 7 has: your own administrator account (root is locked), btrfs with compression, swap in
compressed RAM, a firewall that lets nothing unasked in, daily automatic security updates, and MWX 7 updates signed with
the project's key.

Checksum: compare the `.sha256` file with `Get-FileHash .\mwx7-….iso` in PowerShell.
