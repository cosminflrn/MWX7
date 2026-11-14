"""Previous versions of files (Windows 7's "Restore previous versions"), shared by Explorer, Settings and the root script
bin/mwx7-snapshots. /home is its own btrfs subvolume (@home, oobe/install.py SUBVOLS); every hour a read-only snapshot of it is
taken into /home/.mwx7-snapshots/<YYYY-MM-DD_HHMMSS>. A snapshot keeps every file's owner and mode, so the normal user can read
(without pkexec) exactly the files they could read before and nobody else's private ones.
Everything here only reads; the root script does the writing."""
import datetime
import os
import stat
import subprocess

HOME = os.environ.get('MWX7_VERSIONS_HOME', '/home')
SNAPDIR = os.path.join(HOME, '.mwx7-snapshots')
OFF_FLAG = '/var/lib/mwx7/snapshots-off'   # exists: the person turned "Keep previous versions" off
STAMP = '%Y-%m-%d_%H%M%S'


def parse(name):
    """The time in one of our snapshot names, or None for anything else (so nothing else is ever touched)."""
    try:
        return datetime.datetime.strptime(name, STAMP) if len(name) == 17 else None
    except ValueError:
        return None


def keep_set(names, hourly=24, daily=7, weekly=4):
    """Which snapshot names to keep: the newest one of each of the last `hourly` hours, `daily` days and `weekly` ISO weeks
    that have a snapshot. Everything else that parses as ours may be deleted."""
    stamps = sorted(((parse(n), n) for n in names if parse(n)), reverse=True)
    keep = set()
    for count, key in ((hourly, lambda d: (d.date(), d.hour)), (daily, lambda d: d.date()), (weekly, lambda d: d.isocalendar()[:2])):
        seen = []
        for d, n in stamps:
            k = key(d)
            if k in seen:
                continue
            if len(seen) >= count:
                break
            seen.append(k)
            keep.add(n)
    return keep


def on_btrfs_home():
    """True when /home is its own btrfs subvolume (@home): the only layout this feature supports; otherwise it stays hidden."""
    try:
        r = subprocess.run(['findmnt', '-no', 'FSTYPE,SOURCE', '-T', HOME], capture_output=True, text=True, timeout=5)
        fs, _, src = r.stdout.strip().partition(' ')
        return fs == 'btrfs' and src.strip().endswith('[/@home]')
    except (OSError, subprocess.TimeoutExpired):
        return False


def enabled():
    return not os.path.exists(OFF_FLAG)


def snapshots(snapdir=None):
    """[(name, datetime)] newest first, for the snapshots that exist and can be listed."""
    try:
        names = os.listdir(snapdir or SNAPDIR)
    except OSError:
        return []
    return sorted(((n, parse(n)) for n in names if parse(n)), key=lambda t: t[1], reverse=True)


def _key(st):
    if stat.S_ISDIR(st.st_mode):
        return ('d', int(st.st_mtime))
    return ('f', int(st.st_mtime), st.st_size)


def versions_of(path, snapdir=None, home=None):
    """The earlier versions of `path` (a file or folder under /home), newest first, each a dict: snap (name), when, path (inside
    the snapshot), size, mtime, isdir. Only versions that differ (by modification time and size) from the current one and from
    the next newer version are listed, so an unchanged file shows nothing."""
    snapdir, home = snapdir or SNAPDIR, (home or HOME).rstrip('/')
    path = os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path.rstrip('/')))
    if not path.startswith(home + '/'):
        return []
    rel = path[len(home) + 1:]
    if rel.split('/')[0] == os.path.basename(snapdir):
        return []
    try:
        last = _key(os.lstat(path))
    except OSError:
        last = None
    found = []
    for name, when in snapshots(snapdir):
        p = os.path.join(snapdir, name, rel)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        k = _key(st)
        if k == last:
            continue
        last = k
        found.append({'snap': name, 'when': when, 'path': p, 'size': st.st_size, 'mtime': st.st_mtime,
                      'isdir': stat.S_ISDIR(st.st_mode)})
    return found
