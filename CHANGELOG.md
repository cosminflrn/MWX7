# Changelog

Derived from the git history. Newest first.

## v1.9.0
- **"Updates available" notification**: a few minutes after you sign in (and every few hours), MWX 7 says when an
  update is waiting; click it to open Settings → Updates
- **What's new in Settings → Updates**: after an update, the Updates page lists what changed (the first update
  delivered through the new update channel)
- **Set up instead of install**: the ISO starts straight into the MWX 7 setup — language, keyboard and time zone, where
  MWX 7 goes, Wi-Fi, your name, picture and password. MWX 7 copies itself to the disk in the background while you fill
  that in (zstd compression unpacks on every core), then restarts into the logon screen
- **The disk page says what is on each disk** ("Windows, files", "Empty"). Nothing is erased unless you tick exactly
  what will be deleted; "Use the free space" keeps everything. "Advanced" opens the full installer (next to Windows,
  encryption)
- **No password, if you like**: tick it in the setup; the logon screen then has a Sign in button and Enter unlocks the
  lock screen. Settings → Account adds, changes or removes the password, changes the picture, and can skip the logon
  screen when the PC starts (off by default)
- **Updates without a new ISO**: Settings → Updates installs the newest MWX 7 (from the project's signed update
  channel) together with Debian's and Chrome's updates. Settings → Updates also previews the first-start setup
- Lighter: the old website (MWX 7 Classic) and its local web server are gone from the OS, and the live-only "Keep
  settings" is replaced by the setup

## v1.8.3
- **MWX 7 boot menu** on an installed system: the splash's deep blue with the orb, a frosted-glass list and a glossy
  selection, in Selawik. Entries read "MWX 7" and "Windows" instead of "MWX 7 GNU/Linux" and "Windows Boot Manager
  (on /dev/sda1)". It shows only when Windows is there to choose or Esc is held
- **Lock screen like the logon screen**: your wallpaper, account picture and name, "Locked", and the password ring
  where the logon screen has its field
- Safety: the boot menu names are patched into GRUB's scripts only if the result is still valid (otherwise the scripts
  stay as they were), and the build stops if any boot menu script is broken — a mistake there would fail installation

## v1.8.2
- **Files feels like Explorer**: Desktop, Documents, Downloads, Music, Pictures and Videos exist from the first login,
  are listed in the sidebar and open in icon view; the window is titled by the folder ("Documents", not "mwx - Thunar")
- **Sharper text**: Selawik everywhere an app asks for the system font (Chrome's pages too), with light hinting and
  greyscale smoothing for crisp letters on ordinary monitors
- Settings → Display: highest refresh rate first for each resolution (144 Hz monitors), and a hint to enlarge text
  on screens with small pixels

## v1.8.1 "No lag"
- **Status bar no longer freezes** while the PC is busy: the volume and network checks ran on the bar's own thread, so
  when one of them was slow (Chrome starting, for example) the clock, the window title and every click on the bar and
  dock stopped for seconds. They run in the background now; a check that doesn't answer keeps the last state instead
  of flashing "muted" or "not connected"
- **Smaller download** (about 240 MB less): MWX 7 Classic opens as a Google Chrome app window, so the separate Chromium
  is gone, and a heavy password-prompt helper (with map and image libraries) is replaced by a 47 kB one
- **Faster start**: the boot menu stays hidden (hold Esc or Shift to see it) and a library-cache rebuild that ran on
  every live boot is skipped

## v1.8.0 "Keep settings"
- **MWX 7 remembers everything without installing**: Settings → **Keep settings** turns an empty disk (in VMware the
  VM's own virtual disk) into MWX 7's memory: wallpaper, settings, Chrome sign-in, files and Wi-Fi networks survive
  restarts. A newer MWX 7 ISO started with the same disk keeps all of it, because only your home folder and Wi-Fi are
  kept and the system itself always comes fresh from the ISO. Only completely blank disks are offered or accepted.
  A notification points to it when such a disk is there.
- New MWX 7 defaults now reach a kept or installed system: an older copy of the window manager settings is rebuilt
  from the new release, keeping what you chose in Settings (window colour, keyboard, mouse, display)
- Dock: dialogs no longer get an icon of their own; the dock shrinks back when an app closes
- Notifications: click to do what they offer, right-click to dismiss
- CI: one job per workflow and no flaky Snipping Tool test (no more failure emails caused by GitHub hiccups)

## v1.7.1
- Try the logon and lock screens without installing: the live session's password is now **mwx7** (the logon screen
  says so), and **Lock** and **Log Off** are in the menus there too. The installer removes this user.

## v1.7.0 "Installer"
- **Install MWX 7** to a disk: the drive icon in the dock (live session only) starts an MWX 7-branded installer
  (Calamares). Erase a disk or partition by hand, optional **full-disk encryption**, your own account. Works offline.
- **MWX 7 logon screen** on an installed system: your picture, name and password on the wallpaper, Restart and Shut
  Down in the corner; "log in automatically" is a choice in the installer. **Log Off** appears in the menus.
- **Lock screen** (installed system): Super+L or **Lock** in the menus, and automatically after 10 idle minutes and
  before sleep; your wallpaper with a ring that fills as you type the password
- An installed MWX 7 is set up to be safe by default: root locked (sudo with your password), a firewall that lets
  nothing unasked in, daily automatic security updates (Debian and Chrome), btrfs with compression and separate
  system / home subvolumes, swap in compressed RAM.
- The system calls itself **MWX 7** (boot menu, About, `/etc/os-release`); English and Romanian locales are built in
- Tested in QEMU: install → boot → logon → desktop on UEFI (plain and encrypted) and on BIOS

## v1.6.0 "Genie"
- **Genie minimize** on MWX 7 OS: a window pours into its dock icon and pours back out when you click the icon, like
  MWX 7 on the web (our own Wayfire plugin `distro/desktop/mwx7-animate`; a click mid-way turns it around)
- **Running apps appear in the dock**: any open app that is not pinned (Settings, for example) gets its icon with the
  running dot while it has a window, so a minimized window can always be brought back
- The status bar shows "MWX 7" instead of a minimized window's title

## v1.5.0
- **MWX 7 boot splash**: the glossy orb and "MWX 7" on deep blue with a pulsing progress glow while the system starts,
  instead of console text (Plymouth theme, shown even though the serial console stays on for the CI tests)
- **MWX 7 Settings** app (Start menu, or the top-left orb): wallpaper picker with the MWX 7 photos, window frame colour,
  display resolution and scale, keyboard layouts and repeat, mouse speed / natural scrolling / left-handed, date & time
  zone, and About. Changes apply live and are kept in your own config
- Wallpaper now comes from your settings instead of being fixed

## v1.4.1
- Google Chrome uses the MWX 7 window frame and traffic lights like every other app (no welcome or default-browser
  prompts; Google's own terms dialog still appears on the first start)
- Dock: **right-click** an icon for New window / Close window
- Network icon opens network settings (Wi-Fi passwords, VPN)
- The status bar title follows focus reliably when windows close

## v1.4.0 "Aero frames"
- **MWX 7 window frames** for every app: our own Wayfire plugin (`distro/desktop/mwx7-decor`, a fork of Wayfire's MIT
  decoration plugin) draws light-blue Aero glass with a soft gloss and a bright top edge, the title on the left with a
  white caption glow, and glossy **traffic lights** on the right (green maximize, yellow minimize, red close) that turn
  grey on unfocused windows and show their symbol under the pointer
- Built from source inside the ISO build against Debian's Wayfire; the compiler is removed again afterwards

## v1.3.0
- **Start menu** on the dock orb, like MWX 7 on the web: account picture and name, every installed app with MWX 7
  icons where we have them, type-to-search (Enter opens the first match), Restart and Shut Down
- Top-left orb is now a small system menu (About, Restart, Shut Down)
- Status bar: **network** (wired / Wi-Fi with the connection name) and **volume** (click for a slider and Mute, or scroll)
- **Notifications** as MWX 7 glass cards at the top right
- **MWX 7 look for apps**: Selawik is the system font, and GTK 3 apps (Files, file dialogs) get an MWX 7 theme with
  Aero command bars, Windows 7 selection blue, glossy buttons and menus

## v1.2.3
- Clock shows Bucharest time (was UTC)
- VM integration: VMware tools, SPICE agent and QEMU guest agent (each only runs on its own hypervisor)
- Chrome: no "restore tabs" bar or default-browser prompt on every start of the live system

## v1.2.2
- One download: `mwx7-<version>.iso` is the real MWX 7 desktop. The separate web-kiosk ISO is gone (MWX 7 Classic is
  still there as an app in the dock)
- CI boot-tests the desktop on legacy BIOS, UEFI and UEFI with Secure Boot

## v1.2.1
- Desktop preview: the status bar and dock now appear in VMware and VirtualBox with 3D acceleration (GTK 4's GPU
  renderer misdraws there; the shell now draws on the CPU and other GTK apps use the older GL renderer in VMs)
- The shell restarts itself if it ever crashes and logs to /run/user/1000/mwx7-shell.log; Wayfire logs to
  /run/user/1000/wayfire.log instead of flashing its first log line on screen

## v1.2.0 "Desktop preview"
- New second ISO, **MWX 7 Desktop (preview)**: a real Linux desktop instead of the web version full screen. Wayfire
  compositor with glass blur, the native MWX 7 status bar (orb, active app, Show desktop, clock with seconds) and dock
  (running indicators, click to open / focus / minimize), Google Chrome from Google's own repository, Files (Thunar),
  Terminal, and MWX 7 Classic as an app window
- CI builds and boot-tests both ISOs; the desktop one passes once the native shell has started

## v1.1.1
- Live ISO: shows "Starting MWX 7 ..." while booting and a readable message on screen if the display cannot start,
  instead of a blank console with a stray live-boot warning (what a VirtualBox tester saw)
- Restarts Chromium automatically if it comes up with a blank page on a cold first start
- Graphics firmware for Intel, AMD and NVIDIA (plus Intel/Realtek network firmware), so real PCs get a picture
- Moved to Debian 13: kernel 6.12, current Mesa and Chromium
- CI boot tests pass only once MWX 7 has actually loaded, on BIOS, UEFI and UEFI with Secure Boot

## v1.1.0 "Live"
- MWX 7 live ISO: boots straight into MWX 7 from a VM or USB stick without installing anything; UEFI with Secure Boot,
  UEFI and legacy BIOS. Built and boot-tested by CI on every version tag and attached to the GitHub release
- Windows 11 how-to for VirtualBox, Hyper-V and Rufus (distro/RELEASE_NOTES.md)

## v1.0.1
- Snipping Tool redesigned: Windows 7 command bar, New menu with Rectangular, Window and Full-screen snips, glossy icon
- Media Player playlist shows distinct titles (Variatio 1, 2, …) and a different cover colour per track
- Space Pinball opens without a hitch: the hall reverb is built once, when the browser is idle
- Code released under the MIT License
- Linux distro: build works without udev or a vfat kernel module, standalone GRUB boot loader that finds the disk by label

## v1.0.0
- Apps load on demand: faster first boot, each app's code fetched the first time it opens
- My Computer: drag ghost for files, Properties dialog; Internet: favorites, history, clear blocked-site panel
- Media Player: more CC0 tracks, album art, mini player controls in the dock menu
- Snipping Tool, recent files in dock menus, Themes in Settings
- Traffic lights no longer miss a click right after leaving full screen
- Linux distro groundwork (distro/: Debian live-image scripts, not yet tested on hardware)

## v0.9 (0.9.0 to 0.9.29)
- Genie minimize rebuilt off-page: interruptible, frozen glass baked once, one shadow, funnel shape, no flicker
- Performance: no idle animation loops, compositor-driven window dragging, wallpaper always playing, 1080p Meadow default (1440p on large screens)
- Welcome tour with piano music, power-on photo scene with CRT zoom into the BIOS
- New apps and games: Photo Viewer, Task Manager, Sticky Notes, Mines, Solitaire; game tutorials
- Notepad uses the OS Save / Don't Save dialog; calendar follows the 24-hour setting
- End-to-end test suite (boot, every app, genie, drag, Notepad save, clean reload) gates CI and deploys

## v0.8
- Shell v8: correctly sized genie clone, peek fades for minimized windows, lights only when focused, toasts top-right
- BIOS VGA font, new Settings (clock, dock, desktop), Windows 7 style scrollbars and icons

## v0.7 "Crystal" (0.7.1, 0.7.2)
- Glossy Crystal Clear icons, unified tintable glass, flush dock, show desktop
- Internet browser and Media Player; VGA/CRT look for Commander and BIOS
- Exact-state genie with shadow and scroll; Computer details view

## v0.6 "Luna"
- XP glass, full-screen morph, smooth dock, genie, Tango icons, mouse-only input
- Keyboard shortcuts and Terminal removed; Search and Overview naming

## v0.5 "Paint"
- Paint with a Windows 7 style ribbon; Mission Control overview

## v0.4 "Explorer"
- Explorer file manager, Aero switcher, calendar flyout

## v0.3 "Aero"
- Real media: wallpaper videos, avatars, icons, Selawik font; wallpaper engine
- Shell v3: real genie, first-run setup, session-only storage, sampled sounds; MWX Commander

## v0.2 "Fidelity"
- Premium look, boot sequence, sounds, genie
- Virtual file system v2 (IndexedDB), Terminal, Space Pinball

## v0.1 "Genesis"
- Foundation: scaffold, deploy pipeline, window manager, menu bar, dock, Start menu, Spotlight, notifications
- Notepad, Calculator, Settings, About
