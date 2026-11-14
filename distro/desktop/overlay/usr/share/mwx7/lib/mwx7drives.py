"""Removable drives and network mounts, shared by the shell (AutoPlay notice, "Safely remove hardware") and Explorer
(Computer view). Everything goes through Gio's volume monitor (gvfs + udisks2), so nothing here polls.

Windows-style drive letters: a drive keeps its letter while it stays plugged in. The two processes agree through a
small file in the runtime dir (gone at logout, like a Windows session's assignments)."""
import json
import os

from gi.repository import Gio, GLib

PHONE_SCHEMES = ('mtp', 'gphoto2', 'afc')
NET_SCHEMES = ('smb', 'sftp', 'ftp', 'dav', 'davs', 'nfs', 'afp', 'ssh')
LETTERS = os.path.join(GLib.get_user_runtime_dir(), 'mwx7-drive-letters.json')


def is_removable_drive(drive):
    return drive is not None and (drive.is_removable() or drive.can_eject() or drive.can_stop())


def kind(mount):
    """'removable' (USB stick, SD card, disc, phone), 'network' or None (the system's own disks, archives, ...)."""
    if mount.is_shadowed():
        return None
    vol = mount.get_volume()
    if vol is not None:
        return 'removable' if is_removable_drive(vol.get_drive()) else None
    scheme = mount.get_root().get_uri_scheme()
    if scheme in PHONE_SCHEMES:
        return 'removable'
    return 'network' if scheme in NET_SCHEMES else None


def volume_removable(volume):
    return is_removable_drive(volume.get_drive())


def mounts(what='removable'):
    return [m for m in Gio.VolumeMonitor.get().get_mounts() if kind(m) == what]


def key(mount):
    vol = mount.get_volume()
    return (vol and (vol.get_uuid() or vol.get_identifier('uuid'))) or mount.get_uuid() or mount.get_root().get_uri()


def letter(k, live=()):
    """The letter for the drive `k`, the lowest free one from E (A-D are for floppies and the system disk)."""
    try:
        with open(LETTERS) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    keep = {a: b for a, b in data.items() if a in live or a == k}
    if k not in keep:
        used = set(keep.values())
        keep[k] = next((c for c in 'EFGHIJKLMNOPQRSTUVWXYZ' if c not in used), '?')
    if keep != data:
        try:
            tmp = LETTERS + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(keep, f)
            os.replace(tmp, LETTERS)
        except OSError:
            pass
    return keep[k]


def label(mount, live=None):
    """"USB Drive (E:)" for a removable drive's mount; the bare name for anything else."""
    if kind(mount) != 'removable':
        return mount.get_name()
    live = live if live is not None else [key(m) for m in mounts()]
    return f'{mount.get_name()} ({letter(key(mount), live)}:)'


def process_names(pids):
    names = []
    for pid in pids or ():
        try:
            with open(f'/proc/{int(pid)}/comm') as f:
                n = f.read().strip()
        except (OSError, ValueError):
            continue
        if n and n not in names:
            names.append(n)
    return names


def eject(mount, done):
    """Unmounts and, where the hardware allows, powers it off (what the notice "safe to remove" is true for).
    done(ok, blockers): blockers lists the programs still using it when it was busy (needs lsof for gvfs to know)."""
    vol = mount.get_volume()
    drive = vol.get_drive() if vol else None
    op = Gio.MountOperation()
    blockers = []

    def busy(o, _msg, pids, _choices):
        blockers.extend(n for n in process_names(pids) if n not in blockers)
        o.reply(Gio.MountOperationResult.ABORTED)
    op.connect('show-processes', busy)
    op.connect('ask-question', lambda o, *_a: o.reply(Gio.MountOperationResult.ABORTED))

    def finish(obj, res, fin):
        try:
            getattr(obj, fin)(res)
        except GLib.Error:
            done(False, blockers)
            return
        done(True, [])
    none = Gio.MountUnmountFlags.NONE
    if drive is not None and drive.can_eject():
        drive.eject_with_operation(none, op, None, lambda o, r: finish(o, r, 'eject_with_operation_finish'))
    elif drive is not None and drive.can_stop():
        drive.stop(none, op, None, lambda o, r: finish(o, r, 'stop_finish'))
    else:
        mount.unmount_with_operation(none, op, None, lambda o, r: finish(o, r, 'unmount_with_operation_finish'))
