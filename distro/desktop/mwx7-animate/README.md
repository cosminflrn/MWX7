# mwx7-animate

MWX 7 window animations for Wayfire 0.9: Debian's `animate` plugin (MIT, © Iliya Bozhinov and Wayfire contributors,
see `LICENSE.wayfire`) without the fire effect and with the **MWX 7 genie**:
- minimize pours the window into its dock icon, restore pours it back out (`genie.hpp`): the window is drawn as 64 thin
  strips whose ends follow two S-curves from the window's edges to the icon, then it slides down through that funnel
- a click while it is still moving turns it around from where it is
- the dock tells the plugin where each window's icon is over IPC: `mwx7/set-minimize-hint {id, x, y, width, height}`
- `[mwx7-animate] genie_duration` (ms, default 380) in wayfire.ini; set it to a few seconds to check frames

Reads the stock `[animate]` options for open/close. Load it as `mwx7-animate` instead of `animate`.
Built inside the ISO's chroot against `wayfire-dev` by `distro/desktop/setup.sh`.
