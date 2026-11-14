"""My Computer (native): the concept's Explorer, Windows 7 style. Back/forward, the path as clickable parts, search
in the folder (recursive, streamed in from a background thread); Favorites, My Computer and the Trash on the left; large
icons (with image and video thumbnails, cached as the freedesktop spec says) or details; a preview pane; open, open with,
cut/copy/paste with a progress window and a conflicts dialog, rename, new folder, move to Trash, restore, properties,
Undo (Ctrl+Z), and the usual keys. My Computer itself shows the disk and the person's folders."""
import datetime
import hashlib
import lzma
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7drives as drives  # noqa: E402
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk  # noqa: E402
import gi  # noqa: E402

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf  # noqa: E402

COMPUTER = 'computer:'
NETWORK = 'network:///'  # the Network place; any other "scheme://" place is a server or share browsed through gvfs
GVFS = f'/run/user/{os.getuid()}/gvfs/'  # where gvfs-fuse shows mounted shares, so the rest of Explorer can use plain paths
BOOKMARKS = os.path.join(GLib.get_user_config_dir(), 'gtk-3.0', 'bookmarks')  # shared with Thunar and the file pickers


def is_uri(loc):
    return '://' in loc


def read_bookmarks():
    """[(uri, name)] of the network places saved with "Map network drive…" (local folder bookmarks are not ours)."""
    out = []
    try:
        with open(BOOKMARKS) as f:
            for line in f:
                uri, _s, name = line.strip().partition(' ')
                if uri and is_uri(uri) and not uri.startswith('file://'):
                    out.append((uri, name or uri))
    except OSError:
        pass
    return out


def write_bookmarks(extra, drop=None):
    """Adds (uri, name) to the bookmarks file, or removes the one for `drop`; other people's lines stay as they are."""
    try:
        with open(BOOKMARKS) as f:
            lines = [l.rstrip('\n') for l in f if l.strip()]
    except OSError:
        lines = []
    lines = [l for l in lines if l.split(' ')[0] != drop and not (extra and l.split(' ')[0] == extra[0])]
    if extra:
        lines.append(f'{extra[0]} {extra[1]}')
    os.makedirs(os.path.dirname(BOOKMARKS), exist_ok=True)
    with open(BOOKMARKS, 'w') as f:
        f.write('\n'.join(lines) + ('\n' if lines else ''))


def to_uri(text):
    """What was typed as a network place: \\\\server\\share or smb://server/share (or sftp://..., ftp://...) as a gvfs URI."""
    t = text.strip()
    if t.startswith('\\\\'):
        return 'smb://' + urllib.parse.quote(t[2:].replace('\\', '/'), safe='/')
    if is_uri(t):
        return t
    return None


def mount_title(path):
    """The name of the gvfs mount a /run/user/.../gvfs/<mount> path belongs to."""
    for m in Gio.VolumeMonitor.get().get_mounts():
        if m.get_root().get_path() == path:
            return m.get_name()
    return os.path.basename(path)
TRASH = os.path.join(GLib.get_user_data_dir(), 'Trash')
ICONS = mwx7ui.ICONS
SPECIAL = [(GLib.UserDirectory.DIRECTORY_DESKTOP, 'desktop'), (GLib.UserDirectory.DIRECTORY_DOCUMENTS, 'folder-documents'),
           (GLib.UserDirectory.DIRECTORY_DOWNLOAD, 'folder'), (GLib.UserDirectory.DIRECTORY_MUSIC, 'folder-music'),
           (GLib.UserDirectory.DIRECTORY_PICTURES, 'folder-pictures'), (GLib.UserDirectory.DIRECTORY_VIDEOS, 'folder')]
IMAGES = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
THUMB_DIR = os.path.join(GLib.get_user_cache_dir(), 'thumbnails', 'normal')  # freedesktop spec: 128 px PNGs named md5(uri)
THUMB_BOX = (96, 72)  # what a thumbnail may fill in the icon view
CHUNK = 1 << 20
CSS = """
window.mwx7-explorer > box { background: #ffffff; }
.ex-nav { padding: 6px 8px; background: linear-gradient(180deg, #e9f2fc, #d5e5f7); border-bottom: 1px solid #a9c1de; }
.ex-nav button.ex-round { min-width: 28px; min-height: 28px; padding: 0; border-radius: 999px; border: 1px solid #2b5a94;
  background: radial-gradient(circle at 50% 30%, #bfe0ff, #3d86d8 60%, #1d559c); color: #ffffff;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.6); }
.ex-nav button.ex-round:disabled { background: radial-gradient(circle at 50% 30%, #eef3f9, #b7c4d4); border-color: #94a3b8;
  color: #f4f6f9; }
.ex-crumbs { padding: 0 4px; min-height: 26px; border: 1px solid #8ea7c6; border-radius: 2px; background: #ffffff; }
.ex-crumbs button { padding: 2px 6px; min-height: 0; border: 1px solid transparent; border-radius: 2px; background: none;
  box-shadow: none; color: #1c3150; }
.ex-crumbs button:hover { border-color: #a8c6ec; background: linear-gradient(180deg, #f4f9ff, #dbeafc); }
.ex-search { min-height: 26px; }
.ex-cmd { padding: 3px 8px; border-bottom: 1px solid #c8d8ea;
  background: linear-gradient(180deg, #fbfdff 0%, #eef4fb 50%, #e1ebf7 51%, #eaf1fa 100%); }
.ex-cmd button { padding: 3px 9px; min-height: 0; border: 1px solid transparent; border-radius: 3px; background: none;
  box-shadow: none; color: #1c3150; }
.ex-cmd button:hover { border-color: #a8c6ec; background: linear-gradient(180deg, #f4f9ff, #dbeafc); }
.ex-side { background: linear-gradient(180deg, #f3f8fe, #e8f1fb); border-right: 1px solid #c8d8ea; }
.ex-side row { padding: 3px 10px; color: #1c3150; border-radius: 3px; }
.ex-side row:selected { background: linear-gradient(180deg, #e2efff, #c9e0fb); box-shadow: inset 0 0 0 1px #84acdd; color: #0b2440; }
.ex-side .ex-head { padding: 8px 10px 2px; font-weight: 700; color: #1e3f66; }
flowbox.ex-items flowboxchild { padding: 4px; border-radius: 3px; border: 1px solid transparent; }
flowbox.ex-items flowboxchild:hover { background: linear-gradient(180deg, #f2f8ff, #e2efff); border-color: #b8d6fb; }
flowbox.ex-items flowboxchild:selected { background: linear-gradient(180deg, #dcebfc, #c1dcfc); border-color: #7da2ce; }
.ex-name { color: #1c2530; }
.ex-meta { color: #6a7f99; font-size: 11px; }
.ex-details { padding: 6px 12px; border-top: 1px solid #c8d8ea; background: linear-gradient(180deg, #f3f8fe, #dfeaf7); }
.ex-details-title { font-weight: 600; color: #1c3150; }
.ex-drive-bar trough { min-height: 10px; background: #e3e8ef; border: 1px solid #9aa9bd; border-radius: 1px; }
.ex-drive-bar progress { min-height: 10px; background: linear-gradient(180deg, #5fb0ff, #2a7fd9); border-radius: 1px; }
.ex-cols button { padding: 2px 0; font-size: 11px; min-height: 0; border: none; border-right: 1px solid #dfe7f1; border-radius: 0;
  background: none; box-shadow: none; color: #4a5f7d; }
.ex-cols button:hover { background: linear-gradient(180deg, #f4f9ff, #dbeafc); }
.ex-preview { border-left: 1px solid #c8d8ea; background: #f7fafe; padding: 10px; }
.ex-preview textview, .ex-preview text { background: #ffffff; color: #1c2530; font-family: monospace; font-size: 11px; }
.ex-progress-title { font-size: 14px; color: #1c3150; }
.ex-progress-from { color: #1e3f66; font-weight: 600; }
.ex-cmd button.ex-on { border-color: #7da2ce; background: linear-gradient(180deg, #dcebfc, #c1dcfc); }
.ex-group { padding: 12px 14px 4px; font-weight: 600; color: #1e3f66; }
.ex-drive-btn { padding: 2px 8px; min-height: 0; font-size: 11px; }
"""


def kind_icon(path):
    """MWX 7's own icon for a file, by what it is (the concept's Explorer does the same)."""
    if path.lower().endswith('.zip'):
        return 'zipfolder'  # a zip opens like a folder here (Windows 7's “Compressed (zipped) folder”)
    ctype, _u = Gio.content_type_guess(path, None)
    mime = Gio.content_type_get_mime_type(ctype) or ''
    if mime.startswith('image/'):
        return 'image'
    if mime.startswith('audio/'):
        return 'audio'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('text/') or mime in ('application/json', 'application/xml', 'application/x-shellscript'):
        return 'text'
    if any(k in mime for k in ('zip', 'tar', 'compressed', 'x-7z', 'rar', 'xz', 'bzip', 'gzip', 'zstd', 'debian')):
        return 'archive'
    return 'file'


def mount_op(win):
    """A Gio.MountOperation that asks for a user name and password (and the questions gvfs has, such as an unknown
    server key) in MWX 7's own windows."""
    op = Gio.MountOperation()
    op.connect('ask-password', lambda o, msg, user, domain, flags: credentials(win, o, msg, user, domain, flags))

    def question(o, msg, choices):
        dlg = Gtk.AlertDialog(message=msg, buttons=list(choices), cancel_button=-1)

        def chosen(d, res):
            try:
                o.set_choice(d.choose_finish(res))
                o.reply(Gio.MountOperationResult.HANDLED)
            except GLib.Error:
                o.reply(Gio.MountOperationResult.ABORTED)
        dlg.choose(win, None, chosen)
    op.connect('ask-question', question)
    return op


def credentials(win, op, message, user, domain, flags):
    """Windows' "Enter network credentials" box: only the fields the share asks for, an anonymous choice when it
    allows one, and whether to remember the password for this session."""
    F = Gio.AskPasswordFlags
    w = mwx7ui.dialog(win, 'Enter Network Credentials', '16/properties')
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=14, margin_start=18, margin_end=18)
    col.append(Gtk.Label(label=message, xalign=0, wrap=True, max_width_chars=46, css_classes=['ex-progress-title']))
    entries = {}

    def field(key, text, initial, secret=False):
        col.append(Gtk.Label(label=text, xalign=0, css_classes=['ex-meta']))
        e = Gtk.PasswordEntry(show_peek_icon=True) if secret else Gtk.Entry(text=initial or '', width_chars=34)
        col.append(e)
        entries[key] = e
        return e
    if flags & F.NEED_USERNAME:
        field('user', 'User name', user)
    if flags & F.NEED_DOMAIN:
        field('domain', 'Domain', domain or 'WORKGROUP')
    if flags & F.NEED_PASSWORD:
        field('pass', 'Password', '', True)
    anon = Gtk.CheckButton(label='Connect anonymously (guest)') if flags & F.ANONYMOUS_SUPPORTED else None
    if anon:
        col.append(anon)
        anon.connect('toggled', lambda b: [e.set_sensitive(not b.get_active()) for e in entries.values()])
    save = Gtk.CheckButton(label='Remember my password until I log out') if flags & F.SAVING_SUPPORTED else None
    if save:
        col.append(save)
    row = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=6)
    cancel, ok = Gtk.Button(label='Cancel'), Gtk.Button(label='Connect')
    ok.add_css_class('suggested-action')
    row.append(cancel)
    row.append(ok)
    col.append(row)
    w.set_child(col)
    state = {'done': False}

    def finish(good):
        if state['done']:
            return
        state['done'] = True
        if good:
            if anon and anon.get_active():
                op.set_anonymous(True)
            else:
                if 'user' in entries:
                    op.set_username(entries['user'].get_text())
                if 'domain' in entries:
                    op.set_domain(entries['domain'].get_text())
                if 'pass' in entries:
                    op.set_password(entries['pass'].get_text())
            op.set_password_save(Gio.PasswordSave.FOR_SESSION if save and save.get_active() else Gio.PasswordSave.NEVER)
        op.reply(Gio.MountOperationResult.HANDLED if good else Gio.MountOperationResult.ABORTED)
        w.destroy()
    ok.connect('clicked', lambda *_: finish(True))
    cancel.connect('clicked', lambda *_: finish(False))
    w.connect('close-request', lambda *_: (finish(False), False)[1])
    for e in entries.values():
        e.connect('activate', lambda *_: finish(True))
    w.present()
    first = next(iter(entries.values()), None)
    if first:
        GLib.idle_add(lambda: (first.grab_focus(), False)[1])


def human(n):
    for unit in ('bytes', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.0f} {unit}' if unit == 'bytes' else f'{n:.1f} {unit}'
        n /= 1024
    return ''


def special_dirs():
    out = []
    for d, icon in SPECIAL:
        p = GLib.get_user_special_dir(d)
        if p and os.path.isdir(p) and p != os.path.expanduser('~') and p not in [x[0] for x in out]:
            out.append((p, icon))
    return out


def is_media(path):
    return path.lower().endswith(IMAGES) or kind_icon(path) == 'video'


def make_thumb(path):
    """A pixbuf for an image or a video, from (or into) the shared thumbnail cache. Runs in a worker thread."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    uri = Gio.File.new_for_path(path).get_uri()
    cached = os.path.join(THUMB_DIR, hashlib.md5(uri.encode()).hexdigest() + '.png')
    pb = None
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file(cached)
        if pb.get_option('tEXt::Thumb::MTime') != str(int(st.st_mtime)):
            pb = None
    except GLib.Error:
        pass
    if pb is None:
        try:
            if path.lower().endswith(IMAGES):
                if st.st_size > 120 << 20:
                    return None
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 128, 128, True)
            else:
                pb = video_frame(path)
        except GLib.Error:
            pb = None
        if pb is None:
            return None
        try:
            os.makedirs(THUMB_DIR, mode=0o700, exist_ok=True)
            tmp = cached + f'.{os.getpid()}.tmp'
            pb.savev(tmp, 'png', ['tEXt::Thumb::URI', 'tEXt::Thumb::MTime'], [uri, str(int(st.st_mtime))])
            os.chmod(tmp, 0o600)
            os.replace(tmp, cached)
        except (GLib.Error, OSError):
            pass
    w, h = pb.get_width(), pb.get_height()
    k = min(THUMB_BOX[0] / w, THUMB_BOX[1] / h, 1)
    return pb.scale_simple(max(1, int(w * k)), max(1, int(h * k)), GdkPixbuf.InterpType.BILINEAR) if k < 1 else pb


def video_frame(path):
    """A frame of a video as a 128 px pixbuf: ffmpegthumbnailer if installed, else GStreamer's own command line."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 't.png')
        if shutil.which('ffmpegthumbnailer'):
            cmd = ['ffmpegthumbnailer', '-i', path, '-o', out, '-s', '128', '-t', '10%']
        elif shutil.which('gst-launch-1.0'):
            cmd = ['gst-launch-1.0', '-q', 'uridecodebin', 'uri=' + Gio.File.new_for_path(path).get_uri(), '!', 'videoconvert',
                   '!', 'videoscale', '!', 'video/x-raw,width=128', '!', 'pngenc', 'snapshot=true', '!', 'filesink',
                   'location=' + out]
        else:
            return None
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            return GdkPixbuf.Pixbuf.new_from_file(out)
        except (OSError, subprocess.SubprocessError, GLib.Error):
            return None


def tree_size(path):
    if os.path.islink(path) or not os.path.isdir(path):
        try:
            return os.lstat(path).st_size
        except OSError:
            return 0
    total = 0
    for r, _d, fs in os.walk(path):
        for f in fs:
            try:
                total += os.lstat(os.path.join(r, f)).st_size
            except OSError:
                pass
    return total


def unique_in(folder, name):
    base, ext = os.path.splitext(name)
    cand, i = name, 2
    while os.path.lexists(os.path.join(folder, cand)):
        cand = f'{base} ({i}){ext}'
        i += 1
    return os.path.join(folder, cand)


def remove_any(p):
    shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)


# ---- archives: made and unpacked with Python's own zipfile and tarfile ------------------------------------------------
TAR_EXTS = ('.tar.gz', '.tgz', '.tar.xz', '.txz', '.tar.bz2', '.tbz2', '.tar')
ARCHIVE_ERRORS = (zipfile.BadZipFile, tarfile.TarError, EOFError, RuntimeError, NotImplementedError, zlib.error,
                  lzma.LZMAError)  # RuntimeError: zipfile's way of saying “password required”


def archive_kind(path):
    """'zip' or 'tar' for a file Extract All can unpack, else None."""
    n = path.lower()
    return 'zip' if n.endswith('.zip') else 'tar' if n.endswith(TAR_EXTS) else None


def archive_stem(name):
    low = name.lower()
    for ext in ('.zip',) + TAR_EXTS:
        if low.endswith(ext) and len(name) > len(ext):
            return name[:-len(ext)]
    return name


def zsplit(loc):
    """A .zip browsed like a folder is the place \"/path/a.zip!/inner/folder\": returns (zip file, inner folder) or None."""
    i = loc.lower().find('.zip!/')
    if i < 0 or not os.path.isfile(loc[:i + 4]):
        return None
    return loc[:i + 4], loc[i + 6:].strip('/')


def safe_path(root, name):
    """Where archive member `name` lands under `root`, or None if it would land outside it: absolute paths, drive letters,
    “..” (zip-slip), or a folder on the way that is a symlink leading out. Never trust names from an archive."""
    norm = name.replace('\\', '/')
    parts = [p for p in norm.split('/') if p not in ('', '.')]
    if not parts or norm.startswith('/') or '..' in parts or re.match(r'[A-Za-z]:', parts[0]) or '\0' in name:
        return None
    path = os.path.join(root, *parts)
    base = os.path.realpath(root)
    if os.path.commonpath([os.path.realpath(os.path.dirname(path)), base]) != base:
        return None
    return path


def trashed_name_of(orig):
    """After Gio trashed `orig`: the name it got in the Trash (the newest .trashinfo that points back at it)."""
    info_dir, best = os.path.join(TRASH, 'info'), (0, None)
    try:
        for n in os.listdir(info_dir):
            fp = os.path.join(info_dir, n)
            for line in open(fp, errors='replace'):
                if line.startswith('Path=') and urllib.parse.unquote(line[5:].strip()) == orig:
                    best = max(best, (os.path.getmtime(fp), n[:-len('.trashinfo')]))
    except OSError:
        pass
    return best[1]


class Cancelled(Exception):
    pass


class Job:
    """Copy, move, trash or delete in a worker thread, with what a progress window needs (bytes, speed, time left) and a
    conflicts question that blocks the worker until the person answers. kind: copy | move | trash | delete, and for
    archives extract (srcs=[archive], dest=folder, members=names to take or None for all) | compress (srcs=items,
    dest=the .zip to make)."""

    def __init__(self, kind, srcs, dest=None, members=None):
        self.kind, self.srcs, self.dest, self.members = kind, list(srcs), dest, members
        self.then = None                    # called on the main thread when the job finished without error or Cancel
        self.skipped = 0                    # archive members refused because they would land outside the destination
        self.total = self.done = 0          # bytes for copy/move, items for trash/delete
        self.items_left, self.name = len(self.srcs), ''
        self.cancel = threading.Event()
        self.finished = False
        self.error = None
        self.results = []                   # [(src, dst)] for Undo
        self.ask = None                     # set by the UI: ask(src, dst, answer) -> answer('replace'|'skip'|'keep', all?)
        self.apply_all = None
        self.t0 = time.monotonic()
        self.same_dev = False

    def start(self, on_done):
        def run():
            try:
                self.run()
            except Cancelled:
                pass
            except (OSError, GLib.Error) as e:
                self.error = str(e)
            except ARCHIVE_ERRORS as e:
                self.error = str(e) or type(e).__name__
            self.finished = True
            GLib.idle_add(on_done, self)
        threading.Thread(target=run, daemon=True).start()

    def check(self):
        if self.cancel.is_set():
            raise Cancelled()

    def run(self):
        if self.kind == 'extract':
            return self.extract()
        if self.kind == 'compress':
            return self.compress()
        if self.kind in ('copy', 'move'):
            self.total = sum(tree_size(s) for s in self.srcs) or 1
            try:
                self.same_dev = os.stat(self.dest).st_dev == os.stat(os.path.dirname(self.srcs[0].rstrip('/'))).st_dev
            except OSError:
                pass
        else:
            self.total = len(self.srcs)
        for src in self.srcs:
            self.check()
            self.name = os.path.basename(src.rstrip('/'))
            if self.kind == 'trash':
                Gio.File.new_for_path(src).trash(None)
                self.results.append((src, trashed_name_of(src)))
                self.done += 1
            elif self.kind == 'delete':
                remove_any(src)
                info = os.path.join(TRASH, 'info', os.path.basename(src) + '.trashinfo')
                if os.path.dirname(src) == os.path.join(TRASH, 'files') and os.path.exists(info):
                    os.remove(info)
                self.done += 1
            else:
                dst = os.path.join(self.dest, os.path.basename(src.rstrip('/')))
                if self.kind == 'copy' and os.path.dirname(src.rstrip('/')) == self.dest.rstrip('/'):
                    dst = unique_in(self.dest, os.path.basename(src))  # pasted into its own folder: "name (2)"
                final = self.xfer(src, dst, self.kind == 'move')
                if final:
                    self.results.append((src, final))
            self.items_left -= 1

    # ---- archives ---------------------------------------------------------------------------------------------------
    def claim(self, name, path, is_dir):
        """Makes room for an extracted item at `path`: asks about a name that is taken. Returns the path to write, or None
        to skip it."""
        if os.path.lexists(path):
            if is_dir and os.path.isdir(path) and not os.path.islink(path):
                return path  # folders merge
            choice = self.conflict('', path)
            if choice == 'skip':
                return None
            if choice == 'keep':
                return unique_in(os.path.dirname(path), os.path.basename(path))
            remove_any(path)  # also for a symlink: it is removed, never followed
        return path

    def extract(self):
        src = self.srcs[0]
        self.name = os.path.basename(src)
        created = not os.path.exists(self.dest)
        os.makedirs(self.dest, exist_ok=True)
        try:
            self.extract_zip(src) if archive_kind(src) == 'zip' else self.extract_tar(src)
        except BaseException:
            if created:  # a cancelled or failed extraction leaves no half-filled folder we made ourselves
                shutil.rmtree(self.dest, ignore_errors=True)
            raise

    def extract_zip(self, src):
        with zipfile.ZipFile(src) as zf:
            infos = [i for i in zf.infolist() if self.members is None or i.filename in self.members]
            self.total = sum(i.file_size for i in infos) or 1
            self.items_left = len(infos)
            for zi in infos:
                self.check()
                self.name = os.path.basename(zi.filename.rstrip('/')) or zi.filename
                mode = zi.external_attr >> 16
                try:
                    mtime = time.mktime(zi.date_time + (0, 0, -1))
                except (OverflowError, ValueError):
                    mtime = None
                kind = 'dir' if zi.is_dir() else 'link' if stat.S_ISLNK(mode) else 'file'
                self.put(zi.filename, kind, mode, mtime, lambda zi=zi: zf.open(zi), zi.file_size)
                self.items_left -= 1

    def extract_tar(self, src):
        # Streamed ("r|*"): one pass, whatever the compression; progress is how much of the file has been read.
        self.total, self.items_left = os.path.getsize(src) or 1, -1
        with open(src, 'rb') as raw, tarfile.open(fileobj=raw, mode='r|*') as tf:
            for ti in tf:
                self.check()
                self.done = raw.tell()
                self.name = os.path.basename(ti.name.rstrip('/')) or ti.name
                kind = ('dir' if ti.isdir() else 'link' if ti.issym() else 'hard' if ti.islnk() else
                        'file' if ti.isfile() else None)
                if kind is None:  # devices, fifos: nothing an Explorer should create
                    self.skipped += 1
                    continue
                self.put(ti.name, kind, ti.mode, ti.mtime, lambda ti=ti: tf.extractfile(ti), ti.size,
                         target=ti.linkname, raw=raw)
            self.done = self.total

    def put(self, name, kind, mode, mtime, opener, size, target='', raw=None):
        """Writes one archive member under self.dest, if its name is safe."""
        if name.strip('/.') == '':
            return
        path = safe_path(self.dest, name)
        if path is None:
            self.skipped += 1
            return
        if kind == 'dir':
            if self.claim(name, path, True):
                os.makedirs(path, exist_ok=True)
            return
        if kind in ('link', 'hard'):
            if kind == 'link' and not target:
                target = opener().read().decode(errors='replace')  # zip: the link's target is its content
            self.link(name, path, kind, target)
            if raw is None:
                self.done += size
            return
        path = self.claim(name, path, False)
        if path is None:
            if raw is None:
                self.done += size
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # O_EXCL | O_NOFOLLOW: the file is new, and never written through a symlink.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb') as fo, opener() as fi:
                while chunk := fi.read(CHUNK):
                    fo.write(chunk)
                    if raw is None:
                        self.done += len(chunk)
                    else:
                        self.done = raw.tell()
                    self.check()
        except BaseException:
            try:
                os.remove(path)
            except OSError:
                pass
            raise
        os.chmod(path, 0o755 if mode & 0o111 else 0o644)  # no setuid/setgid/sticky from an archive
        if mtime:
            try:
                os.utime(path, (mtime, mtime))
            except OSError:
                pass

    def link(self, name, path, kind, target):
        """Symlinks and hard links are made only when they stay inside the destination folder."""
        base = os.path.realpath(self.dest)
        if kind == 'hard':
            origin = safe_path(self.dest, target)
            if not origin or not os.path.isfile(origin) or os.path.islink(origin):
                self.skipped += 1
                return
            path = self.claim(name, path, False)
            if path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                shutil.copyfile(origin, path)  # a copy, not a second name for the same data
            return
        inside = (target and '\0' not in target and not os.path.isabs(target) and os.path.commonpath(
            [os.path.realpath(os.path.join(os.path.dirname(path), target)), base]) == base)
        if not inside:
            self.skipped += 1
            return
        path = self.claim(name, path, False)
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            os.symlink(target, path)

    def compress(self):
        """Packs the items into the .zip at self.dest (written as a hidden .part file first, so a Cancel or an error leaves
        no broken archive behind)."""
        entries, stack = [], [(s.rstrip('/'), os.path.basename(s.rstrip('/'))) for s in self.srcs]
        part = os.path.join(os.path.dirname(self.dest), '.' + os.path.basename(self.dest) + '.part')
        while stack:
            path, arc = stack.pop(0)
            self.check()
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                entries.append((path, arc, 'link', 0))
            elif stat.S_ISDIR(st.st_mode):
                entries.append((path, arc + '/', 'dir', 0))
                stack[0:0] = [(os.path.join(path, n), arc + '/' + n) for n in sorted(os.listdir(path))]
            elif stat.S_ISREG(st.st_mode):
                entries.append((path, arc, 'file', st.st_size))
        self.total = sum(e[3] for e in entries) or 1
        self.items_left = len(entries)
        try:
            with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for path, arc, kind, size in entries:
                    self.check()
                    self.name = os.path.basename(arc.rstrip('/'))
                    zi = zipfile.ZipInfo.from_file(path, arc, strict_timestamps=False)  # pre-1980 dates are clamped
                    if kind == 'link':
                        zi.external_attr = (stat.S_IFLNK | 0o777) << 16
                        zf.writestr(zi, os.readlink(path))
                    elif kind == 'dir':
                        zf.writestr(zi, b'')
                    else:
                        zi.compress_type = zipfile.ZIP_DEFLATED
                        with open(path, 'rb') as fi, zf.open(zi, 'w', force_zip64=size > zipfile.ZIP64_LIMIT) as fo:
                            while chunk := fi.read(CHUNK):
                                fo.write(chunk)
                                self.done += len(chunk)
                                self.check()
                    self.items_left -= 1
            if os.path.lexists(self.dest):  # taken while we worked
                self.dest = unique_in(os.path.dirname(self.dest), os.path.basename(self.dest))
            os.replace(part, self.dest)
        except BaseException:
            try:
                os.remove(part)
            except OSError:
                pass
            raise

    def conflict(self, src, dst):
        if self.apply_all:
            return self.apply_all
        ev, box = threading.Event(), []

        def answer(choice, all_):
            box.append(choice)
            self.apply_all = choice if all_ else None
            ev.set()
        GLib.idle_add(lambda: (self.ask(src, dst, answer), False)[1])
        while not ev.wait(0.2):
            self.check()
        self.check()
        return box[0]

    def xfer(self, src, dst, move):
        """Copies or moves one thing to `dst`; returns where it ended up, or None if it was skipped."""
        self.check()
        if os.path.lexists(dst) and not (os.path.isdir(src) and os.path.isdir(dst) and not os.path.islink(src)):
            choice = self.conflict(src, dst)
            if choice == 'skip':
                self.done += tree_size(src)
                return None
            if choice == 'keep':
                dst = unique_in(os.path.dirname(dst), os.path.basename(dst))
            else:
                remove_any(dst)
        if os.path.isdir(src) and not os.path.islink(src):
            if os.path.isdir(dst):  # merge into the folder that is already there
                for n in os.listdir(src):
                    self.xfer(os.path.join(src, n), os.path.join(dst, n), move)
                if move:
                    try:
                        os.rmdir(src)
                    except OSError:
                        pass
                return dst
            if move and self.same_dev:
                os.rename(src, dst)
                self.done += tree_size(dst)
                return dst
            os.mkdir(dst)
            for n in os.listdir(src):
                self.xfer(os.path.join(src, n), os.path.join(dst, n), move)
            shutil.copystat(src, dst, follow_symlinks=False)
            if move:
                try:
                    os.rmdir(src)
                except OSError:
                    pass
            return dst
        self.name = os.path.basename(src)
        if move and self.same_dev:
            size = os.lstat(src).st_size
            os.rename(src, dst)
            self.done += size
            return dst
        if os.path.islink(src):
            os.symlink(os.readlink(src), dst)
        else:
            try:
                with open(src, 'rb') as fi, open(dst, 'wb') as fo:
                    while chunk := fi.read(CHUNK):
                        fo.write(chunk)
                        self.done += len(chunk)
                        self.check()
                shutil.copystat(src, dst)
            except Cancelled:
                try:
                    os.remove(dst)
                except OSError:
                    pass
                raise
        if move:
            os.remove(src)
        return dst


class Explorer:
    def __init__(self):
        self.loc, self.back, self.fwd = COMPUTER, [], []
        self.clip, self.clip_cut = [], False
        self.view = 'icons'
        self.undo_stack = []
        self.zmeta = {}                     # members of the zip being browsed: path -> (is_dir, mtime, size)
        self.searching, self.search_gen, self.search_cancel = False, 0, threading.Event()
        self.thumbs = ThreadPoolExecutor(max_workers=2)
        self.preview_gen = 0
        # Details view: each column's header and cells share a width.
        self.col_groups = [Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL) for _ in range(3)]

    # ---- layout ---------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-explorer')
        app.on_open = lambda files: self.go(files[0].get_path() or files[0].get_uri())
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        nav = Gtk.Box(spacing=6)
        nav.add_css_class('ex-nav')
        self.back_btn = self.round('go-previous-symbolic', 'Back', lambda: self.history(-1))
        self.fwd_btn = self.round('go-next-symbolic', 'Forward', lambda: self.history(1))
        nav.append(self.back_btn)
        nav.append(self.fwd_btn)
        self.crumbs = Gtk.Box(hexpand=True)
        self.crumbs.add_css_class('ex-crumbs')
        # Clicking the empty part of the address bar turns it into a box to type a place in, as in Explorer.
        self.addr = Gtk.Entry(hexpand=True)
        self.addr.add_css_class('ex-search')
        self.addr.connect('activate', lambda e: self.typed_place(e.get_text()))
        focus = Gtk.EventControllerFocus()
        focus.connect('leave', lambda *_: self.addr_stack.set_visible_child(self.crumbs))
        self.addr.add_controller(focus)
        self.addr_stack = Gtk.Stack(hexpand=True)
        self.addr_stack.add_child(self.crumbs)
        self.addr_stack.add_child(self.addr)
        bg = Gtk.GestureClick()
        bg.connect('released', lambda *_: self.edit_place())
        self.crumbs.add_controller(bg)
        nav.append(self.addr_stack)
        self.search = Gtk.SearchEntry(placeholder_text='Search', width_chars=22)
        self.search.add_css_class('ex-search')
        self.search.connect('search-changed', lambda e: self.search_changed(e.get_text()))
        self.search.connect('stop-search', lambda *_: self.stop_search(True))
        nav.append(self.search)
        root.append(nav)
        cmd = Gtk.Box(spacing=2)
        cmd.add_css_class('ex-cmd')
        org = Gtk.MenuButton(label='Organize')
        menu = Gio.Menu()
        for label, name, fn in (('Cut', 'cut', lambda: self.copy(True)), ('Copy', 'copy', lambda: self.copy(False)),
                                ('Paste', 'paste', self.paste), ('Select all', 'selectall', lambda: self.flow.select_all()),
                                ('Undo', 'undo', self.undo), ('Rename', 'rename', self.rename), ('Delete', 'delete', self.delete),
                                ('Properties', 'props', self.properties)):
            a = Gio.SimpleAction.new(name, None)
            a.connect('activate', lambda *_a, f=fn: f())
            app.add_action(a)
            menu.append(label, 'app.' + name)
        org.set_menu_model(menu)
        cmd.append(org)
        self.newdir_btn = Gtk.Button(label='New folder')
        self.newdir_btn.connect('clicked', lambda *_: self.new_folder())
        cmd.append(self.newdir_btn)
        self.map_btn = Gtk.Button(label='Map network drive…')
        self.map_btn.connect('clicked', lambda *_: self.map_drive())
        cmd.append(self.map_btn)
        self.empty_btn = Gtk.Button(label='Empty the Trash')
        self.empty_btn.connect('clicked', lambda *_: self.empty_trash())
        cmd.append(self.empty_btn)
        self.restore_btn = Gtk.Button(label='Restore')
        self.restore_btn.connect('clicked', lambda *_: self.restore())
        cmd.append(self.restore_btn)
        spacer = Gtk.Box(hexpand=True)
        cmd.append(spacer)
        self.preview_btn = Gtk.Button(label='Preview pane')
        self.preview_btn.connect('clicked', lambda *_: self.toggle_preview())
        cmd.append(self.preview_btn)
        self.view_btn = Gtk.Button(label='Details')
        self.view_btn.connect('clicked', lambda *_: self.toggle_view())
        cmd.append(self.view_btn)
        root.append(cmd)

        body = Gtk.Paned(vexpand=True, shrink_start_child=False, position=190)
        side = Gtk.ScrolledWindow()
        side.add_css_class('ex-side')
        self.side = Gtk.ListBox()
        self.side.connect('row-activated', lambda _l, r: getattr(r, 'path', None) and self.go(r.path))
        side.set_child(self.side)
        body.set_start_child(side)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.MULTIPLE, activate_on_single_click=False,
                                homogeneous=True, valign=Gtk.Align.START, row_spacing=2, column_spacing=2,
                                max_children_per_line=40, margin_top=6, margin_start=6, margin_end=6)
        self.flow.add_css_class('ex-items')
        self.drop_on(self.flow, lambda: self.loc if self.loc not in (COMPUTER,) else COMPUTER)
        self.flow.connect('child-activated', lambda _f, c: self.open_item(c.item))
        self.flow.connect('selected-children-changed', lambda *_: self.details())
        click = Gtk.GestureClick(button=3)
        click.connect('pressed', self.context_menu)
        self.flow.add_controller(click)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content.append(self.flow)
        self.sc = Gtk.ScrolledWindow(hexpand=True)
        self.sc.set_child(self.content)
        self.sc.get_vadjustment().connect('value-changed', lambda *_: self.schedule_thumbs())
        # The preview pane sits to the right of the items, as in Windows 7; hidden until its button is pressed.
        self.preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, visible=False, hexpand=False)
        self.preview.add_css_class('ex-preview')
        self.preview.set_size_request(260, -1)
        self.preview_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        self.preview.append(self.preview_body)
        right = Gtk.Box()
        right.append(self.sc)
        right.append(self.preview)
        body.set_end_child(right)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key_pressed)
        win.add_controller(keys)
        root.append(body)
        self.detail = Gtk.Box(spacing=12)
        self.detail.add_css_class('ex-details')
        self.detail_icon = Gtk.Image(pixel_size=48)
        dcol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.detail_title = Gtk.Label(xalign=0)
        self.detail_title.add_css_class('ex-details-title')
        self.detail_text = Gtk.Label(xalign=0)
        self.detail_text.add_css_class('ex-meta')
        dcol.append(self.detail_title)
        dcol.append(self.detail_text)
        self.detail.append(self.detail_icon)
        self.detail.append(dcol)
        root.append(self.detail)

        self.monitor = None
        start = (app.files[0].get_path() or app.files[0].get_uri()) if app.files else (sys.argv[1] if len(sys.argv) > 1 and (os.path.isdir(sys.argv[1]) or sys.argv[1] == NETWORK) else COMPUTER)
        self.fill_side()
        # Drives and shares come and go: the volume monitor tells us (no polling).
        self.vmon = Gio.VolumeMonitor.get()
        for sig in ('mount-added', 'mount-removed', 'mount-changed', 'volume-added', 'volume-removed'):
            self.vmon.connect(sig, lambda *_a: GLib.idle_add(lambda: (self.drives_changed(), False)[1]))
        self.go(start, remember=False)
        # The items, not the search box, get the keys (GTK would focus the first widget it finds once the window shows).
        win.connect('map', lambda *_: GLib.timeout_add(100, lambda: (self.focus_items(), False)[1]))
        return root

    def round(self, icon, tip, fn):
        b = Gtk.Button(icon_name=icon, tooltip_text=tip, focusable=False, valign=Gtk.Align.CENTER)
        b.add_css_class('ex-round')
        b.connect('clicked', lambda *_: fn())
        return b

    def side_row(self, label, icon, path):
        row = Gtk.ListBoxRow()
        row.path = path
        self.drop_on(row, lambda: path)
        box = Gtk.Box(spacing=8)
        box.append(mwx7ui.icon(icon, 16))
        box.append(Gtk.Label(label=label, xalign=0))
        row.set_child(box)
        return row

    def side_head(self, label):
        row = Gtk.ListBoxRow(selectable=False, activatable=False)
        l = Gtk.Label(label=label, xalign=0)
        l.add_css_class('ex-head')
        row.set_child(l)
        return row

    def fill_side(self):
        self.side.append(self.side_head('Favorites'))
        for p, icon in special_dirs():
            self.side.append(self.side_row(os.path.basename(p), icon, p))
        self.side.append(self.side_head('My Computer'))
        self.side.append(self.side_row('Local Disk', 'drive', '/'))
        live = [drives.key(m) for m in drives.mounts()]
        for m in drives.mounts():  # USB sticks, cards and phones appear here as they are plugged in
            path = m.get_root().get_path()
            if path:
                self.side.append(self.side_row(drives.label(m, live), 'drive', path))
        self.side.append(self.side_row(GLib.get_real_name() or GLib.get_user_name(), 'user', os.path.expanduser('~')))
        self.side.append(self.side_head('Network'))
        self.side.append(self.side_row('Network', 'computer', NETWORK))
        for uri, name in read_bookmarks():
            self.side.append(self.side_row(name, 'folder', uri))
        self.side.append(self.side_head(''))
        self.side.append(self.side_row('Trash', 'trash-empty', TRASH))

    def drives_changed(self):
        """The volume monitor says a drive or share came or went (a signal, not polling): refresh the places on screen."""
        while (r := self.side.get_first_child()) is not None:
            self.side.remove(r)
        self.fill_side()
        gone = self.loc.startswith(('/run/media/', '/media/', GVFS)) and not os.path.isdir(self.loc)
        if gone:
            self.go(COMPUTER)
        elif self.loc == COMPUTER or self.loc == NETWORK:
            self.fill()
        else:
            self.sync_side()

    def sync_side(self):
        i = 0
        while (r := self.side.get_row_at_index(i)) is not None:
            if getattr(r, 'path', None) == self.loc:
                self.side.select_row(r)
                return
            i += 1

    # ---- navigation -----------------------------------------------------------------------------------------------
    def go(self, path, remember=True):
        if path.rstrip('/') == TRASH:
            path = TRASH
            for sub in ('files', 'info'):
                os.makedirs(os.path.join(TRASH, sub), exist_ok=True)
        if path != COMPUTER and not is_uri(path) and not os.path.isdir(path) and zsplit(path) is None:
            return
        if remember and path != self.loc:
            self.back.append(self.loc)
            self.fwd.clear()
        self.loc = path
        if path not in (COMPUTER, TRASH) and not is_uri(path) and zsplit(path) is None:
            mwx7ui.remember(path)
        self.stop_search(True, refill=False)
        self.watch()
        self.fill()

    def history(self, d):
        src, dst = (self.back, self.fwd) if d < 0 else (self.fwd, self.back)
        if src:
            dst.append(self.loc)
            self.loc = src.pop()
            self.stop_search(True, refill=False)
            self.watch()
            self.fill()

    def watch(self):
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        folder = os.path.join(TRASH, 'files') if self.loc == TRASH else self.loc
        if folder != COMPUTER and os.path.isdir(folder):
            self.monitor = Gio.File.new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.monitor.connect('changed', lambda *_: self.later_fill())

    def later_fill(self):
        if not getattr(self, 'fill_pending', False) and not self.searching:
            self.fill_pending = True
            GLib.timeout_add(250, lambda: (setattr(self, 'fill_pending', False), self.fill(), False)[2])

    def edit_place(self):
        if self.addr_stack.get_visible_child() is self.addr:
            return
        self.addr.set_text(os.path.expanduser('~') if self.loc == COMPUTER else self.loc)
        self.addr_stack.set_visible_child(self.addr)
        GLib.idle_add(lambda: (self.addr.grab_focus(), self.addr.select_region(0, -1), False)[2])

    def typed_place(self, text):
        path = os.path.expanduser(text.strip())
        self.addr_stack.set_visible_child(self.crumbs)
        if text.strip().lower() in ('my computer', 'computer'):
            self.go(COMPUTER)
        elif text.strip().lower() == 'network':
            self.go(NETWORK)
        elif to_uri(text):
            self.open_net(to_uri(text))
        elif os.path.isdir(path) or zsplit(path) is not None:
            self.go(os.path.abspath(path))
        elif os.path.isfile(path):
            self.open_item(path)
        else:
            self.alert(f'MWX 7 can\u2019t find \u201c{text.strip()}\u201d.', 'Check the spelling and try again.')

    def title_of(self, path):
        if path == COMPUTER:
            return 'My Computer'
        if path == TRASH:
            return 'Trash'
        if path == NETWORK:
            return 'Network'
        z = zsplit(path)
        if z:
            return os.path.basename(z[1]) or os.path.basename(z[0])
        if is_uri(path):
            u = urllib.parse.urlparse(path)
            return urllib.parse.unquote(u.path.rstrip('/').rpartition('/')[2] or u.hostname or path)
        if path.startswith(GVFS) and path.rstrip('/').count('/') == GVFS.count('/'):
            return mount_title(path.rstrip('/'))
        if path == '/':
            return 'Local Disk'
        if path == os.path.expanduser('~'):
            return GLib.get_real_name() or GLib.get_user_name()
        return os.path.basename(path.rstrip('/')) or path

    def fill_crumbs(self):
        while (c := self.crumbs.get_first_child()) is not None:
            self.crumbs.remove(c)
        parts = [COMPUTER]
        if self.loc == TRASH:
            parts = [TRASH]
        elif is_uri(self.loc):
            u = urllib.parse.urlparse(self.loc)
            parts = [NETWORK]
            if self.loc != NETWORK:
                acc = f'{u.scheme}://{u.netloc}'
                parts.append(acc + '/')
                for part in [x for x in u.path.split('/') if x]:
                    acc += '/' + part
                    parts.append(acc + '/')
        elif self.loc.startswith(GVFS):
            root = GVFS + self.loc[len(GVFS):].split('/')[0]
            parts = [NETWORK, root]
            rest = os.path.relpath(self.loc, root)
            if rest != '.':
                acc = root
                for part in rest.split(os.sep):
                    acc = os.path.join(acc, part)
                    parts.append(acc)
        elif self.loc != COMPUTER:
            z = self.zip_loc()
            where = z[0] if z else self.loc  # a zip is shown as a folder inside the folder it lies in
            home = os.path.expanduser('~')
            base = home if where.startswith(home) else '/'
            parts.append(base)
            rest = os.path.relpath(where, base)
            if rest != '.':
                acc = base
                for part in rest.split(os.sep):
                    acc = os.path.join(acc, part)
                    parts.append(acc)
            if z:
                acc = z[0] + '!'
                parts[-1] = z[0] + '!/'
                for part in [x for x in z[1].split('/') if x]:
                    acc += '/' + part
                    parts.append(acc)
        for i, p in enumerate(parts):
            if i:
                self.crumbs.append(Gtk.Label(label='›'))
            b = Gtk.Button(label=self.title_of(p), focusable=False)
            b.connect('clicked', lambda _b, p=p: self.go(p))
            self.crumbs.append(b)

    # ---- items ----------------------------------------------------------------------------------------------------
    def items(self):
        """[(path, name, is_dir, icon_widget_factory, meta)] for the current place."""
        if self.loc == COMPUTER or is_uri(self.loc):
            return []
        z = self.zip_loc()
        folder = os.path.join(TRASH, 'files') if self.loc == TRASH else self.loc
        if z:
            out = self.zip_items(*z)
        else:
            try:
                names = os.listdir(folder)
            except OSError:
                return []
            out = []
            for n in names:
                if n.startswith('.') and self.loc != TRASH:
                    continue
                p = os.path.join(folder, n)
                out.append((p, n, os.path.isdir(p)))
        col, desc = getattr(self, 'sort', ('name', False))

        def key(t):
            p, n, d = t
            st = self.stat_of(p)
            v = {'name': n.lower(), 'date': st[0] if st else 0, 'size': (st[1] if st and not d else -1),
                 'type': ('' if d else os.path.splitext(n)[1].lower(), n.lower())}[col]
            return v
        out.sort(key=key, reverse=desc)
        out.sort(key=lambda t: not t[2])  # folders first, whatever the order
        return out

    def zip_loc(self):
        return zsplit(self.loc)

    def zip_items(self, zp, inner):
        """The members of the zip that sit directly in `inner`, as [(virtual path, name, is_dir)]; self.zmeta keeps what
        the details view shows (a zip has no files on disk to stat)."""
        self.zmeta, seen = {}, {}
        prefix = inner + '/' if inner else ''
        try:
            with zipfile.ZipFile(zp) as zf:
                infos = zf.infolist()
        except (OSError, *ARCHIVE_ERRORS):
            return []
        for zi in infos:
            if not zi.filename.startswith(prefix) or zi.filename == prefix:
                continue
            first, sep, _rest = zi.filename[len(prefix):].partition('/')
            if not first:
                continue
            is_dir = bool(sep) or zi.is_dir()
            if first not in seen or is_dir:
                try:
                    mtime = time.mktime(zi.date_time + (0, 0, -1))
                except (OverflowError, ValueError):
                    mtime = 0
                seen[first] = (is_dir, mtime, 0 if is_dir else zi.file_size)
        out = []
        for name, (is_dir, mtime, size) in seen.items():
            vp = f'{zp}!/{prefix}{name}'
            self.zmeta[vp] = (is_dir, mtime, size)
            out.append((vp, name, is_dir))
        return out

    def stat_of(self, p):
        """(mtime, size) of an item, from the zip's index for one inside a zip."""
        m = getattr(self, 'zmeta', {}).get(p) if self.zip_loc() else None
        if m:
            return m[1], m[2]
        try:
            st = os.stat(p)
            return st.st_mtime, st.st_size
        except OSError:
            return None

    def is_dir_item(self, p):
        return self.zmeta[p][0] if self.zip_loc() and p in getattr(self, 'zmeta', {}) else os.path.isdir(p)

    def icon_for(self, path, is_dir, size):
        if is_dir:
            for p, icon in special_dirs():
                if p == path:
                    return mwx7ui.icon(icon, size)
            return mwx7ui.icon('folder', size)
        return mwx7ui.icon(kind_icon(path), size)

    def fill(self):
        if self.searching:  # a refresh (or a change in the folder) ends a search
            self.stop_search(True, refill=False)
        f = self.win.get_focus()
        had_focus = f is not None and (f is self.flow or f.is_ancestor(self.flow))  # rebuilding the cells would drop it
        self.fill_crumbs()
        self.app.set_title(self.title_of(self.loc))
        self.back_btn.set_sensitive(bool(self.back))
        self.fwd_btn.set_sensitive(bool(self.fwd))
        virtual = self.loc == COMPUTER or is_uri(self.loc)
        in_trash, real = self.loc == TRASH, self.loc not in (COMPUTER, TRASH) and not virtual and not self.zip_loc()
        self.newdir_btn.set_visible(real)
        self.map_btn.set_visible(virtual)
        self.empty_btn.set_visible(in_trash)
        self.restore_btn.set_visible(in_trash)
        self.view_btn.set_visible(not virtual)
        while (c := self.flow.get_first_child()) is not None:
            self.flow.remove(c)
        child = self.content.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            if child is not self.flow:
                self.content.remove(child)
            child = nxt
        i, mine = 0, None
        while (r := self.side.get_row_at_index(i)) is not None:
            if getattr(r, 'path', None) == self.loc:
                mine = r
                break
            i += 1
        if mine:
            self.side.select_row(mine)
        else:
            self.side.unselect_all()
        if self.loc == COMPUTER:
            self.fill_computer()
        elif is_uri(self.loc):
            self.fill_network()
        else:
            details = self.view == 'details'
            if details:
                self.content.prepend(self.columns())
            self.flow.set_max_children_per_line(1 if details else 40)
            self.flow.set_homogeneous(not details)
            for path, name, is_dir in self.items():
                self.flow.append(self.cell(path, name, is_dir, details))
        self.details()
        self.schedule_thumbs()
        if had_focus:
            self.focus_items()

    def columns(self):
        """Details view's column headers, as in Explorer: click one to sort by it, again to reverse."""
        col, desc = getattr(self, 'sort', ('name', False))
        row = Gtk.Box(spacing=8, margin_start=11, margin_end=11, margin_top=4)
        row.add_css_class('ex-cols')
        for key, label, w in (('name', 'Name', 0), ('date', 'Date modified', 16), ('type', 'Type', 18), ('size', 'Size', 9)):
            arrow = (' \u25be' if desc else ' \u25b4') if key == col else ''
            b = Gtk.Button(label=label + arrow, hexpand=not w)
            b.get_child().set_xalign(0)
            if w:
                b.get_child().set_width_chars(w)
                self.col_groups[('date', 'type', 'size').index(key)].add_widget(b)
            b.connect('clicked', lambda _b, k=key: (setattr(self, 'sort', (k, not desc if k == col else False)),
                                                    self.fill()))
            row.append(b)
        row.get_first_child().set_margin_start(24)  # over the names, past the icons
        return row

    def cell(self, path, name, is_dir, details):
        c = Gtk.FlowBoxChild()
        c.item = path
        self.dnd(c, path, is_dir)
        if details:
            row = Gtk.Box(spacing=8)
            row.append(self.icon_for(path, is_dir, 16))
            n = Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3)
            n.add_css_class('ex-name')
            row.append(n)
            st = self.stat_of(path)
            when = datetime.datetime.fromtimestamp(st[0]).strftime('%d/%m/%Y %H:%M') if st and st[0] else ''
            size = '' if is_dir or not st else human(st[1])
            kind = 'File folder' if is_dir else 'Compressed (zipped) folder' if archive_kind(path) == 'zip' else \
                Gio.content_type_get_description(Gio.content_type_guess(path, None)[0])
            for i, (text, w) in enumerate(((when, 16), (kind, 18), (size, 9))):
                l = Gtk.Label(label=text, xalign=0, width_chars=w, max_width_chars=w, ellipsize=3)
                l.add_css_class('ex-meta')
                self.col_groups[i].add_widget(l)
                row.append(l)
            c.set_child(row)
        else:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            box.set_size_request(96, -1)
            if not is_dir and is_media(path) and not self.zip_loc():
                # Lazy: the thumbnail is made only once the cell scrolls into view (load_visible).
                holder = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
                holder.set_size_request(*THUMB_BOX)
                img = self.icon_for(path, False, 48)
                img.set_hexpand(True)
                holder.append(img)
                c.thumb = (holder, img)
                c.thumb_state = 0
                box.append(holder)
            else:
                box.append(self.icon_for(path, is_dir, 48))
            l = Gtk.Label(label=name, wrap=True, wrap_mode=2, max_width_chars=12, lines=2, ellipsize=3,
                          justify=Gtk.Justification.CENTER)
            l.add_css_class('ex-name')
            box.append(l)
            c.set_child(box)
        return c

    def fill_computer(self):
        """My Computer: the disk with how full it is, then the person's folders."""
        def group(text):
            g = Gtk.Label(label=text, xalign=0)
            g.add_css_class('ex-group')
            return g
        self.content.prepend(group('Hard Disk Drives'))
        disk = Gtk.FlowBoxChild()
        disk.item = '/'
        row = Gtk.Box(spacing=10)
        row.append(mwx7ui.icon('drive', 48))
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, valign=Gtk.Align.CENTER)
        col.append(Gtk.Label(label='Local Disk', xalign=0, css_classes=['ex-name']))
        d = shutil.disk_usage('/')
        bar = Gtk.ProgressBar(fraction=(d.total - d.free) / d.total if d.total else 0)
        bar.add_css_class('ex-drive-bar')
        bar.set_size_request(180, -1)
        col.append(bar)
        col.append(Gtk.Label(label=f'{human(d.free)} free of {human(d.total)}', xalign=0, css_classes=['ex-meta']))
        row.append(col)
        disk.set_child(row)
        self.flow.set_max_children_per_line(40)
        self.flow.set_homogeneous(False)
        self.flow.append(disk)
        folders = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=False,
                              max_children_per_line=40, margin_start=6, margin_end=6)
        folders.add_css_class('ex-items')
        folders.connect('child-activated', lambda _f, c: self.go(c.item))
        for p, _icon in special_dirs():
            folders.append(self.cell(p, os.path.basename(p), True, False))
        self.content.append(group('Your Folders'))
        self.content.append(folders)
        self.vols = {}
        live = [drives.key(m) for m in drives.mounts()]
        cells = []
        for m in drives.mounts():
            path = m.get_root().get_path()
            frac, sub = None, 'Device'
            if path:
                try:
                    d = shutil.disk_usage(path)
                    frac, sub = (d.total - d.free) / d.total if d.total else 0, f'{human(d.free)} free of {human(d.total)}'
                except OSError:
                    sub = ''
            cells.append(self.drive_cell('drive', drives.label(m, live), sub, frac, path or m.get_root().get_uri(),
                                         [('Eject', lambda m=m: self.eject(m))]))
        for v in Gio.VolumeMonitor.get().get_volumes():  # plugged in but not mounted (yet, or it could not be)
            if drives.volume_removable(v) and v.get_mount() is None:
                self.vols[v.get_name()] = v
                cells.append(self.drive_cell('drive', v.get_name(), 'Double-click to open it', None, 'vol:' + v.get_name()))
        if cells:
            self.shelf('Devices with Removable Storage', cells)
        marks = read_bookmarks()
        cells = [self.drive_cell('computer', 'Network', 'Computers and shares around you', None, NETWORK)]
        seen = set()
        for m in drives.mounts('network'):
            uri = m.get_root().get_uri()
            seen.add(uri.rstrip('/'))
            acts = [('Disconnect', lambda m=m: self.eject(m))]
            if uri.rstrip('/') in [u.rstrip('/') for u, _n in marks]:
                acts.append(('Remove', lambda uri=uri: self.forget(uri)))
            cells.append(self.drive_cell('drive', m.get_name(), 'Network location', None, m.get_root().get_path() or uri, acts))
        for uri, name in marks:
            if uri.rstrip('/') not in seen:
                cells.append(self.drive_cell('drive', name, 'Network location', None, uri,
                                             [('Remove', lambda uri=uri: self.forget(uri))]))
        self.shelf('Network Locations', cells)

    def drive_cell(self, icon, title, sub, frac, item, actions=()):
        """A drive as Windows 7 shows it in Computer: icon, name, a usage bar, the free space and a button or two."""
        c = Gtk.FlowBoxChild()
        c.item = item
        row = Gtk.Box(spacing=10)
        row.append(mwx7ui.icon(icon, 48))
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, valign=Gtk.Align.CENTER)
        col.append(Gtk.Label(label=title, xalign=0, css_classes=['ex-name']))
        if frac is not None:
            bar = Gtk.ProgressBar(fraction=frac)
            bar.add_css_class('ex-drive-bar')
            bar.set_size_request(180, -1)
            col.append(bar)
        col.append(Gtk.Label(label=sub, xalign=0, css_classes=['ex-meta']))
        row.append(col)
        for text, fn in actions:
            b = Gtk.Button(label=text, valign=Gtk.Align.CENTER, focusable=False)
            b.add_css_class('ex-drive-btn')
            b.connect('clicked', lambda *_a, fn=fn: fn())
            row.append(b)
        c.set_child(row)
        return c

    def shelf(self, title, cells):
        g = Gtk.Label(label=title, xalign=0)
        g.add_css_class('ex-group')
        self.content.append(g)
        fb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=False, homogeneous=False,
                         max_children_per_line=40, margin_start=6, margin_end=6)
        fb.add_css_class('ex-items')
        fb.connect('child-activated', lambda _f, c: self.open_item(c.item))
        for c in cells:
            fb.append(c)
        self.content.append(fb)

    def eject(self, mount):
        name = drives.label(mount)
        removable = drives.kind(mount) == 'removable'
        root = mount.get_root().get_path()
        if root and self.loc.startswith(root):  # leave it first, as Windows does: nothing of ours holds it open
            self.go(COMPUTER)

        def done(ok, blockers):
            if ok:
                if removable:
                    self.alert('Safe to Remove Hardware', f'{name} can now be safely removed from the computer.')
            elif blockers:
                self.alert(f'Problem ejecting {name}', f'{", ".join(blockers[:3])} is still using it. Close it, then try again.')
            else:
                self.alert(f'Problem ejecting {name}', 'A program is still using it. Close any windows showing its files, then try again.')
        drives.eject(mount, done)

    def open_volume(self, name):
        v = self.vols.get(name)
        if v is None:
            return

        def done(vol, res):
            try:
                vol.mount_finish(res)
            except GLib.Error as e:
                if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.FAILED_HANDLED):
                    self.alert(f'MWX 7 couldn’t open {name}.', e.message)
                return
            m = vol.get_mount()
            if m and m.get_root().get_path():
                self.go(m.get_root().get_path())
        v.mount(Gio.MountMountFlags.NONE, mount_op(self.win), None, done)

    # ---- network: shares and servers through gvfs ---------------------------------------------------------------------
    def forget(self, uri):
        write_bookmarks(None, drop=uri)
        self.drives_changed()

    def open_net(self, uri):
        """A mounted share is an ordinary folder (gvfs-fuse); servers, the Network place and shares not yet mounted are
        browsed through Gio, which asks for the password when the share needs one."""
        p = Gio.File.new_for_uri(uri).get_path()
        self.go(p if p and os.path.isdir(p) else uri)

    def mount_uri(self, uri, cb):
        """cb(ok, message): message is empty when it worked or when the person cancelled the password box."""
        def done(src, res):
            try:
                src.mount_enclosing_volume_finish(res)
            except GLib.Error as e:
                if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.ALREADY_MOUNTED):
                    cb(True, '')
                else:
                    cb(False, '' if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.FAILED_HANDLED) else e.message)
                return
            cb(True, '')
        Gio.File.new_for_uri(uri).mount_enclosing_volume(Gio.MountMountFlags.NONE, mount_op(self.win), None, done)

    def fill_network(self):
        """The Network place, or a server: what Gio lists there (computers found on the network, or a server's shares)."""
        self.net_gen = getattr(self, 'net_gen', 0) + 1
        gen, uri = self.net_gen, self.loc
        status = Gtk.Label(label='Searching for network locations…', xalign=0, margin_start=14, margin_top=12,
                           wrap=True, max_width_chars=70, css_classes=['ex-meta'])
        self.content.append(status)
        attrs = 'standard::name,standard::display-name,standard::type,standard::target-uri'
        src = Gio.File.new_for_uri(uri)

        def listed(f, res, tried=False):
            if gen != self.net_gen or self.loc != uri:
                return
            try:
                en = f.enumerate_children_finish(res)
            except GLib.Error as e:
                if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_MOUNTED) and not tried:
                    status.set_label('Connecting…')
                    self.mount_uri(uri, lambda ok, msg: mounted(ok, msg))
                elif e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_SUPPORTED):
                    status.set_label('Network places are not available on this system (the gvfs network backends are missing).')
                else:
                    status.set_label(e.message)
                return
            en.next_files_async(500, GLib.PRIORITY_DEFAULT, None, lambda en_, r: got(en_, r))

        def mounted(ok, msg):
            if gen != self.net_gen or self.loc != uri:
                return
            if not ok:
                status.set_label(f'MWX 7 couldn’t connect. {msg}' if msg else 'Not connected. Go back, or try again with a password.')
                return
            p = Gio.File.new_for_uri(uri).get_path()
            if p and os.path.isdir(p) and urllib.parse.urlparse(uri).path.strip('/'):
                self.go(p)  # a share's contents are ordinary files now
            else:
                src.enumerate_children_async(attrs, 0, GLib.PRIORITY_DEFAULT, None, lambda f, r: listed(f, r, True))

        def got(en, res):
            if gen != self.net_gen or self.loc != uri:
                return
            try:
                infos = en.next_files_finish(res)
            except GLib.Error as e:
                status.set_label(e.message)
                return
            self.content.remove(status)
            for info in infos:
                name = info.get_display_name()
                dest = info.get_attribute_string('standard::target-uri') or src.get_child(info.get_name()).get_uri()
                share = info.get_file_type() == Gio.FileType.MOUNTABLE
                icon = 'computer' if uri == NETWORK else 'drive' if share else 'folder'
                c = Gtk.FlowBoxChild()
                c.item = dest
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
                box.append(mwx7ui.icon(icon, 48))
                box.append(Gtk.Label(label=name, wrap=True, wrap_mode=2, max_width_chars=14, lines=2, ellipsize=3,
                                     justify=Gtk.Justification.CENTER, css_classes=['ex-name']))
                c.set_child(box)
                self.flow.append(c)
            if not infos:
                note = ('No computers were found on the network. Use “Map network drive…” to connect to one by name, '
                        'for example \\\\server\\share.') if uri == NETWORK else 'Nothing is shared here.'
                self.content.append(Gtk.Label(label=note, xalign=0, margin_start=14, margin_top=12, wrap=True,
                                              max_width_chars=70, css_classes=['ex-meta']))
        src.enumerate_children_async(attrs, 0, GLib.PRIORITY_DEFAULT, None, listed)

    def map_drive(self):
        """Windows' "Map Network Drive": a share by name, connected now and kept in the sidebar and in Computer."""
        d = mwx7ui.dialog(self.win, 'Map Network Drive', '16/properties')
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=14, margin_start=18, margin_end=18)
        col.append(Gtk.Label(label='What network folder would you like to connect to?', xalign=0,
                             css_classes=['ex-progress-title']))
        e = Gtk.Entry(width_chars=44, placeholder_text='\\\\server\\share')
        col.append(e)
        col.append(Gtk.Label(label='For example  \\\\server\\share,  smb://server/share  or  sftp://server/folder', xalign=0,
                             css_classes=['ex-meta']))
        status = Gtk.Label(label='', xalign=0, wrap=True, max_width_chars=50, css_classes=['ex-meta'])
        col.append(status)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=6)
        cancel, ok = Gtk.Button(label='Cancel'), Gtk.Button(label='Finish')
        ok.add_css_class('suggested-action')
        row.append(cancel)
        row.append(ok)
        col.append(row)
        d.set_child(col)

        def finish(*_):
            text = e.get_text().strip()
            uri = to_uri(text) or ('smb://' + text.replace('\\', '/') if '/' in text else None)
            if not uri:
                status.set_label('Type the folder as \\\\server\\share or as an address such as smb://server/share.')
                return
            status.set_label('Connecting…')
            ok.set_sensitive(False)

            def connected(good, msg):
                if not good:
                    ok.set_sensitive(True)
                    status.set_label(f'MWX 7 couldn’t connect. {msg}' if msg else 'Not connected.')
                    return
                u = urllib.parse.urlparse(uri)
                share = urllib.parse.unquote(u.path.rstrip('/').rpartition('/')[2])
                write_bookmarks((uri, f'{share} on {u.hostname}' if share else (u.hostname or uri)))
                d.close()
                self.drives_changed()
                self.open_net(uri)
            self.mount_uri(uri, connected)
        ok.connect('clicked', finish)
        e.connect('activate', finish)
        cancel.connect('clicked', lambda *_: d.close())
        d.present()
        GLib.idle_add(lambda: (e.grab_focus(), False)[1])

    # ---- drag and drop: drag items onto a folder (or a place on the left) to move them there, as in Explorer ----
    def dnd(self, widget, path, is_dir):
        if self.loc == TRASH or self.zip_loc():
            return
        src = Gtk.DragSource(actions=Gdk.DragAction.MOVE | Gdk.DragAction.COPY)

        def prepare(_s, _x, _y):
            paths = self.selected() if path in self.selected() else [path]
            files = [Gio.File.new_for_path(p) for p in paths]
            return Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list(files))
        src.connect('prepare', prepare)
        widget.add_controller(src)
        if is_dir:
            self.drop_on(widget, lambda: path)

    def drop_on(self, widget, where):
        tgt = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.MOVE | Gdk.DragAction.COPY)

        def drop(_t, value, _x, _y):
            dest = where()
            if dest == COMPUTER or is_uri(dest):
                return False
            files = [f.get_path() for f in value.get_files() if f.get_path()]
            self.move_into(files, dest)
            return True
        tgt.connect('drop', drop)
        widget.add_controller(tgt)

    def move_into(self, files, dest):
        if self.zip_loc():
            return
        files = [src for src in files if os.path.exists(src) and os.path.dirname(src.rstrip('/')) != dest.rstrip('/')
                 and not dest.startswith(src.rstrip('/') + '/') and src != dest]
        if files:
            self.run_job(Job('trash' if dest == TRASH else 'move', files, dest))

    # ---- actions --------------------------------------------------------------------------------------------------
    def selected(self):
        # Network places and unmounted drives have no path of their own: they are opened, never cut, renamed or deleted.
        return [c.item for c in self.flow.get_selected_children() if c.item.startswith('/')]

    def open_item(self, path):
        if self.loc == TRASH:
            return
        if path.startswith('vol:'):
            self.open_volume(path[4:])
            return
        if is_uri(path):
            self.open_net(path)
            return
        z = zsplit(path)
        if z:  # inside a zip: folders open as folders, a file is unpacked to a temp folder and opened from there
            if self.zmeta.get(path, (False,))[0]:
                self.go(path)
            else:
                self.open_from_zip(*z, path)
            return
        if os.path.isdir(path):
            self.go(path)
            return
        if archive_kind(path) == 'zip' and zipfile.is_zipfile(path):
            self.go(path + '!/')
            return
        try:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None)
        except GLib.Error as e:
            Gtk.AlertDialog(message=f'MWX 7 has no app to open {os.path.basename(path)}.', detail=e.message).show(self.win)

    def details(self):
        sel = self.selected()
        self.update_preview(sel)
        if len(sel) == 1:
            p = sel[0]
            is_dir = self.is_dir_item(p)
            self.detail_icon.set_from_paintable(None)
            img = self.icon_for(p, is_dir, 48)
            if img.get_paintable():
                self.detail_icon.set_from_paintable(img.get_paintable())
            elif img.get_gicon():
                self.detail_icon.set_from_gicon(img.get_gicon())
            self.detail_title.set_label(os.path.basename(p) or p)
            st = self.stat_of(p)
            if st:
                when = datetime.datetime.fromtimestamp(st[0]).strftime('%d %B %Y, %H:%M')
                self.detail_text.set_label(('File folder' if is_dir else human(st[1])) + f'  ·  Modified {when}')
            else:
                self.detail_text.set_label('')
        elif self.searching and not sel:
            n, c = 0, self.flow.get_first_child()
            while c is not None:
                n, c = n + 1, c.get_next_sibling()
            self.detail_title.set_label(f'Search results for “{self.search.get_text().strip()}”')
            self.detail_text.set_label(f'{n} items found  ·  Esc to stop')
        else:
            n = len(sel) if sel else len(self.items()) if self.loc != COMPUTER and not is_uri(self.loc) else 0
            here = 'computer' if self.loc == COMPUTER or is_uri(self.loc) else 'trash-empty' if self.loc == TRASH else \
                'zipfolder' if self.zip_loc() else 'folder'
            self.detail_icon.set_from_file(os.path.join(ICONS, here + '.png'))
            self.detail_title.set_label(f'{n} items selected' if sel else self.title_of(self.loc))
            self.detail_text.set_label('' if sel else (f'{n} items' if self.loc != COMPUTER and not is_uri(self.loc) else ''))

    def toggle_view(self):
        self.view = 'icons' if self.view == 'details' else 'details'
        self.view_btn.set_label('Large icons' if self.view == 'details' else 'Details')
        self.fill()

    def copy(self, cut):
        if self.zip_loc() or self.loc == COMPUTER or is_uri(self.loc):
            return
        self.clip, self.clip_cut = self.selected(), cut

    def unique(self, folder, name):
        base, ext = os.path.splitext(name)
        cand, i = name, 2
        while os.path.exists(os.path.join(folder, cand)):
            cand = f'{base} ({i}){ext}'
            i += 1
        return os.path.join(folder, cand)

    def paste(self):
        if self.zip_loc() or self.loc in (COMPUTER, TRASH) or is_uri(self.loc) or not self.clip:
            return
        files = [s for s in self.clip if os.path.exists(s) and not self.loc.startswith(s.rstrip('/') + '/')]
        if self.clip_cut:
            files = [s for s in files if os.path.dirname(s.rstrip('/')) != self.loc.rstrip('/')]
        if files:
            self.run_job(Job('move' if self.clip_cut else 'copy', files, self.loc))
        if self.clip_cut:
            self.clip = []

    def new_folder(self):
        if self.zip_loc() or self.loc in (COMPUTER, TRASH) or is_uri(self.loc):
            return
        try:
            os.mkdir(self.unique(self.loc, 'New folder'))
        except OSError as e:
            self.alert('The folder could not be made.', str(e))
        self.fill()

    def ask(self, title, initial, done):
        d = mwx7ui.dialog(self.win, title, '16/rename')
        box = Gtk.Box(spacing=8, margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        e = Gtk.Entry(text=initial, width_chars=32)
        ok = Gtk.Button(label='OK')
        ok.add_css_class('suggested-action')
        box.append(e)
        box.append(ok)
        d.set_child(box)

        def go(*_):
            d.close()
            done(e.get_text().strip())
        ok.connect('clicked', go)
        e.connect('activate', go)
        d.present()
        stem = os.path.splitext(initial)[0]
        GLib.idle_add(lambda: (e.grab_focus(), e.select_region(0, len(stem)), False)[2])

    def rename(self):
        sel = self.selected()
        if len(sel) != 1 or self.loc in (TRASH, COMPUTER) or is_uri(self.loc) or self.zip_loc():
            return
        src = sel[0]

        def done(name):
            if not name or '/' in name or name == os.path.basename(src):
                return
            dst = os.path.join(os.path.dirname(src), name)
            if os.path.exists(dst):
                self.alert('There is already an item with that name.', name)
                return
            try:
                os.rename(src, dst)
                self.undo_stack.append(('rename', [(src, dst)]))
            except OSError as e:
                self.alert('This could not be renamed.', str(e))
            self.fill()
        self.ask('Rename', os.path.basename(src), done)

    def delete(self):
        sel = self.selected()
        if self.zip_loc() or not sel or self.loc == COMPUTER or is_uri(self.loc):
            return
        if self.loc == TRASH:
            msg, detail, btn = 'Delete permanently?', f'{len(sel)} item(s) will be gone for good.', 'Delete'
        else:
            msg, detail, btn = 'Move to the Trash?', ', '.join(os.path.basename(p) for p in sel[:3]) + (
                '…' if len(sel) > 3 else ''), 'Move to Trash'
        dlg = Gtk.AlertDialog(message=msg, detail=detail, buttons=[btn, 'Cancel'], default_button=1, cancel_button=1)

        def done(d, res):
            try:
                if d.choose_finish(res) != 0:
                    return
            except GLib.Error:
                return
            self.run_job(Job('delete' if self.loc == TRASH else 'trash', sel))
        dlg.choose(self.win, None, done)

    def restore_one(self, p):
        """Puts one thing from the Trash back where it came from (under a new name if that is taken)."""
        info = os.path.join(TRASH, 'info', os.path.basename(p) + '.trashinfo')
        orig = next(urllib.parse.unquote(line.split('=', 1)[1].strip()) for line in open(info)
                    if line.startswith('Path='))
        os.makedirs(os.path.dirname(orig), exist_ok=True)
        dst = self.unique(os.path.dirname(orig), os.path.basename(orig))
        shutil.move(p, dst)
        os.remove(info)
        return orig, dst

    def restore(self):
        for p in self.selected():
            try:
                orig, dst = self.restore_one(p)
                self.undo_stack.append(('restore', [(orig, dst)]))
            except (OSError, StopIteration) as e:
                self.alert('This could not be restored.', str(e))
        self.fill()

    def undo(self):
        """Ctrl+Z: takes back the last move, rename or move to the Trash (and a restore from it)."""
        if not self.undo_stack:
            return
        kind, pairs = self.undo_stack.pop()
        try:
            for a, b in reversed(pairs):
                if kind == 'trash':  # a = where it was, b = its name in the Trash
                    p = os.path.join(TRASH, 'files', b or '')
                    if not b or not os.path.lexists(p):
                        raise OSError('It is no longer in the Trash.')
                    self.restore_one(p)
                elif kind == 'restore':  # a = where it was in the Trash's eyes, b = where it went
                    Gio.File.new_for_path(b).trash(None)
                else:  # move / rename: b is where it went, a where it was
                    if os.path.lexists(a):
                        raise OSError(f'“{os.path.basename(a)}” already exists in its old place.')
                    os.makedirs(os.path.dirname(a), exist_ok=True)
                    shutil.move(b, a)
        except (OSError, GLib.Error, StopIteration) as e:
            self.alert('This could not be undone.', str(e))
        self.fill()

    def empty_trash(self):
        dlg = Gtk.AlertDialog(message='Empty the Trash?', detail='Everything in it will be gone for good.',
                              buttons=['Empty the Trash', 'Cancel'], default_button=1, cancel_button=1)

        def done(d, res):
            try:
                if d.choose_finish(res) != 0:
                    return
            except GLib.Error:
                return
            for sub in ('files', 'info'):
                folder = os.path.join(TRASH, sub)
                for n in os.listdir(folder) if os.path.isdir(folder) else []:
                    p = os.path.join(folder, n)
                    try:
                        shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
                    except OSError:
                        pass
            self.fill()
        dlg.choose(self.win, None, done)

    def properties(self):
        sel = self.selected() or ([self.loc] if self.loc not in (COMPUTER, TRASH) and not is_uri(self.loc) else [])
        if len(sel) != 1 or self.zip_loc():
            return
        p = sel[0]
        try:
            st = os.stat(p)
        except OSError:
            return
        size = st.st_size
        if os.path.isdir(p):
            size = 0
            for r, _d, fs in os.walk(p):
                for f in fs:
                    try:
                        size += os.lstat(os.path.join(r, f)).st_size
                    except OSError:
                        pass
        when = lambda t: datetime.datetime.fromtimestamp(t).strftime('%d %B %Y, %H:%M')  # noqa: E731
        is_dir = os.path.isdir(p)
        kind = 'File folder' if is_dir else Gio.content_type_get_description(Gio.content_type_guess(p, None)[0])
        # Windows 7's Properties window: the item on top, then type and place, size, dates.
        w = mwx7ui.dialog(self.win, f'{os.path.basename(p) or p} Properties', '16/properties')
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=14,
                      margin_start=18, margin_end=18)
        head = Gtk.Box(spacing=14)
        head.append(self.icon_for(p, is_dir, 48))
        head.append(Gtk.Label(label=os.path.basename(p) or p, xalign=0, wrap=True, max_width_chars=34))
        col.append(head)

        def block(rows):
            col.append(Gtk.Separator())
            g = Gtk.Grid(column_spacing=18, row_spacing=6)
            for i, (k, v) in enumerate(rows):
                g.attach(Gtk.Label(label=k + ':', xalign=0, css_classes=['ex-meta']), 0, i, 1, 1)
                g.attach(Gtk.Label(label=v, xalign=0, selectable=True, wrap=True, max_width_chars=40), 1, i, 1, 1)
            col.append(g)
        block([('Type', kind), ('Location', os.path.dirname(p) or '/')])
        size_rows = [('Size', f'{human(size)} ({size:,} bytes)')]
        if is_dir:
            files = dirs = 0
            for _r, ds, fs in os.walk(p):
                files += len(fs)
                dirs += len(ds)
            size_rows.append(('Contains', f'{files:,} Files, {dirs:,} Folders'))
        block(size_rows)
        block([('Created', when(st.st_ctime)), ('Modified', when(st.st_mtime)), ('Accessed', when(st.st_atime))])
        ok = Gtk.Button(label='OK', halign=Gtk.Align.END, margin_top=4)
        ok.connect('clicked', lambda *_: w.close())
        col.append(ok)
        w.set_child(col)
        w.present()
        ok.grab_focus()  # not the first selectable value, which GTK would show selected

    # ---- keyboard ---------------------------------------------------------------------------------------------------
    def key_pressed(self, _c, keyval, _code, state):
        K, M = Gdk, Gdk.ModifierType
        ctrl, alt, shift = bool(state & M.CONTROL_MASK), bool(state & M.ALT_MASK), bool(state & M.SHIFT_MASK)
        key = K.keyval_to_lower(keyval)
        focus = self.win.get_focus()
        typing = isinstance(focus, Gtk.Editable)
        if keyval == K.KEY_Escape and (self.searching or self.search.get_text()):
            self.stop_search(True)
            self.focus_items()
            return True
        if ctrl and key == K.KEY_f:
            self.search.grab_focus()
            return True
        if typing:  # the address and search boxes keep their own editing keys
            return False
        in_flow = focus is not None and (focus is self.flow or focus.is_ancestor(self.flow))
        if ctrl and not alt:
            fn = {K.KEY_c: lambda: self.copy(False), K.KEY_x: lambda: self.copy(True), K.KEY_v: self.paste,
                  K.KEY_a: lambda: self.flow.select_all(), K.KEY_z: self.undo}.get(key)
            if key == K.KEY_n and shift:
                fn = self.new_folder
            if fn:
                fn()
                return True
            return False
        if alt:
            fn = {K.KEY_Up: self.go_up, K.KEY_Left: lambda: self.history(-1), K.KEY_Right: lambda: self.history(1)}.get(keyval)
            if fn:
                fn()
                return True
            return False
        if keyval == K.KEY_Delete or keyval == K.KEY_KP_Delete:
            self.delete()
        elif keyval == K.KEY_F2:
            self.rename()
        elif keyval == K.KEY_F5:
            self.fill()
        elif keyval == K.KEY_BackSpace:
            self.history(-1)
        elif keyval in (K.KEY_Return, K.KEY_KP_Enter) and in_flow:
            sel = self.selected()
            if len(sel) == 1 or any(os.path.isdir(p) for p in sel):
                self.open_item(sel[0]) if sel else None
            else:
                for p in sel:
                    self.open_item(p)
        else:
            return False
        return True

    def focus_items(self):
        """Focus goes to an item (the FlowBox itself can't take it), so the keys act on the files, not the search box."""
        sel = self.flow.get_selected_children()
        c = sel[0] if sel else self.flow.get_first_child()
        self.win.set_focus(c)

    def go_up(self):
        if self.loc == COMPUTER or self.loc == NETWORK:
            return
        if is_uri(self.loc):
            u = urllib.parse.urlparse(self.loc)
            parent = u.path.rstrip('/').rpartition('/')[0]
            self.go(f'{u.scheme}://{u.netloc}{parent}/' if parent else NETWORK)
            return
        if self.loc.startswith(GVFS) and self.loc.rstrip('/').count('/') == GVFS.count('/'):
            self.go(NETWORK)
            return
        z = self.zip_loc()
        if z and z[1]:
            self.go(f'{z[0]}!/{z[1].rpartition("/")[0]}')
            return
        self.go(COMPUTER if self.loc in (TRASH, '/') else os.path.dirname((z[0] if z else self.loc).rstrip('/')) or '/')

    # ---- search: the folder and everything under it, found by a background thread and streamed into the view --------
    def search_changed(self, text):
        if getattr(self, 'quiet', False):
            return
        if getattr(self, 'search_timer', 0):
            GLib.source_remove(self.search_timer)
            self.search_timer = 0
        text = text.strip()
        if self.loc == COMPUTER or is_uri(self.loc) or self.zip_loc():  # nothing to search through here
            return
        if not text:
            self.stop_search(False)
            return

        def go():
            self.search_timer = 0
            self.start_search(text)
            return False
        self.search_timer = GLib.timeout_add(250, go)

    def stop_search(self, clear_text, refill=True):
        self.search_cancel.set()
        self.search_gen += 1
        if getattr(self, 'search_timer', 0):
            GLib.source_remove(self.search_timer)
            self.search_timer = 0
        was, self.searching = self.searching, False
        if clear_text and self.search.get_text():
            self.quiet = True
            self.search.set_text('')
            self.quiet = False
        if was and refill:
            self.fill()

    def clear_view(self):
        while (c := self.flow.get_first_child()) is not None:
            self.flow.remove(c)
        child = self.content.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            if child is not self.flow:
                self.content.remove(child)
            child = nxt

    def start_search(self, text):
        self.search_cancel.set()
        ev = self.search_cancel = threading.Event()
        self.search_gen += 1
        gen = self.search_gen
        self.searching = True
        home = os.path.expanduser('~')
        base = home if self.loc == COMPUTER else os.path.join(TRASH, 'files') if self.loc == TRASH else self.loc
        self.clear_view()
        details = self.view == 'details' and self.loc != COMPUTER
        if details:
            self.content.prepend(self.columns())
        self.flow.set_max_children_per_line(1 if details else 40)
        self.flow.set_homogeneous(not details)
        self.flow.unselect_all()
        out, found = [], [0]
        needle = text.lower()

        def work():
            for root, dirs, files in os.walk(base):
                if ev.is_set():
                    return
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for n, is_dir in [(d, True) for d in dirs] + [(f, False) for f in files]:
                    if needle in n.lower() and not n.startswith('.'):
                        out.append((os.path.join(root, n), n, is_dir))
                        if len(out) > 20000:
                            break
            out.append(None)  # the end

        threading.Thread(target=work, daemon=True).start()

        def status(done):
            n = found[0]
            self.detail_icon.set_from_file(os.path.join(ICONS, 'folder.png'))
            self.detail_title.set_label(f'Search results for “{text}”')
            self.detail_text.set_label((f'{n} items found' if done else f'Searching… {n} found') +
                                       '  ·  Esc to stop')

        def drain():
            if gen != self.search_gen or ev.is_set():
                return False
            batch = out[:150]
            del out[:len(batch)]
            done = False
            for it in batch:
                if it is None:
                    done = True
                    break
                cell = self.cell(it[0], it[1], it[2], details)
                cell.set_tooltip_text(os.path.dirname(it[0]))
                self.flow.append(cell)
                found[0] += 1
            if not self.selected():
                status(done)
            self.schedule_thumbs()
            return not done
        status(False)
        GLib.timeout_add(120, drain)

    # ---- thumbnails: made in two worker threads, and only for the cells that are on screen --------------------------
    def schedule_thumbs(self):
        if getattr(self, 'thumb_timer', 0):
            return
        self.thumb_timer = GLib.timeout_add(100, self.load_visible)

    def load_visible(self):
        self.thumb_timer = 0
        h = self.sc.get_height()
        if h <= 0:
            return True  # not laid out yet
        c = self.flow.get_first_child()
        while c is not None:
            if getattr(c, 'thumb_state', 1) == 0:
                ok, b = c.compute_bounds(self.sc)
                if ok and b.get_y() + b.get_height() > -120 and b.get_y() < h + 120:
                    c.thumb_state = 1
                    fut = self.thumbs.submit(make_thumb, c.item)
                    fut.add_done_callback(lambda f, c=c: GLib.idle_add(self.thumb_done, c, f))
            c = c.get_next_sibling()
        return False

    def thumb_done(self, cell, fut):
        try:
            pb = fut.result()
        except Exception:  # noqa: BLE001 - a bad file must not break the others
            pb = None
        if pb is not None and cell.get_parent() is not None:
            img = cell.thumb[1]
            img.set_pixel_size(-1)
            img.set_from_paintable(Gdk.Texture.new_for_pixbuf(pb))
        return False

    # ---- preview pane -----------------------------------------------------------------------------------------------
    def toggle_preview(self):
        on = not self.preview.get_visible()
        self.preview.set_visible(on)
        (self.preview_btn.add_css_class if on else self.preview_btn.remove_css_class)('ex-on')
        self.update_preview(self.selected())

    def update_preview(self, sel):
        if not self.preview.get_visible():
            return
        self.preview_gen += 1
        gen = self.preview_gen
        while (c := self.preview_body.get_first_child()) is not None:
            self.preview_body.remove(c)
        if len(sel) != 1 or self.zip_loc():
            self.preview_body.append(Gtk.Label(label='Select a file to preview it.' if not sel or self.zip_loc() else f'{len(sel)} items selected',
                                               vexpand=True, css_classes=['ex-meta']))
            return
        p = sel[0]
        is_dir = os.path.isdir(p)
        slot = Gtk.Box(vexpand=True)
        self.preview_body.append(slot)
        name = Gtk.Label(label=os.path.basename(p), wrap=True, wrap_mode=2, max_width_chars=28, css_classes=['ex-details-title'])
        self.preview_body.append(name)

        def plain(text):
            slot.append(Gtk.Box(vexpand=True))
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True, valign=Gtk.Align.CENTER)
            col.append(self.icon_for(p, is_dir, 64))
            col.append(Gtk.Label(label=text, css_classes=['ex-meta']))
            slot.append(col)

        def load():
            kind = None
            try:
                if p.lower().endswith(IMAGES) and os.path.getsize(p) < 80 << 20:
                    kind, data = 'image', GdkPixbuf.Pixbuf.new_from_file_at_scale(p, 236, 360, True)
                elif not is_dir and kind_icon(p) == 'text':
                    with open(p, 'rb') as f:
                        raw = f.read(8000)
                    if b'\0' not in raw:
                        kind, data = 'text', raw.decode('utf-8', 'replace')
            except (OSError, GLib.Error):
                pass
            GLib.idle_add(show, kind, data if kind else None)

        def show(kind, data):
            if gen != self.preview_gen:
                return False
            if kind == 'image':
                pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(data))
                pic.set_can_shrink(True)
                pic.set_content_fit(Gtk.ContentFit.CONTAIN)
                pic.set_halign(Gtk.Align.CENTER)
                slot.append(pic)
            elif kind == 'text':
                tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR, hexpand=True,
                                  left_margin=6, right_margin=6, top_margin=4)
                tv.get_buffer().set_text(data)
                scr = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
                scr.set_child(tv)
                slot.append(scr)
            else:
                plain('Folder' if is_dir else 'No preview available.')
            return False
        threading.Thread(target=load, daemon=True).start()

    # ---- open with ----------------------------------------------------------------------------------------------------
    def apps_for(self, paths):
        self.with_apps = []
        if not paths:
            return []
        p = paths[0]
        ctype = 'inode/directory' if os.path.isdir(p) else Gio.content_type_guess(p, None)[0]
        seen = set()
        for a in Gio.AppInfo.get_all_for_type(ctype):
            if a.should_show() and a.get_id() not in seen:
                seen.add(a.get_id())
                self.with_apps.append(a)
        self.with_apps = self.with_apps[:12]
        return self.with_apps

    def open_with(self, i):
        sel = self.selected()
        if sel and i < len(self.with_apps):
            try:
                self.with_apps[i].launch([Gio.File.new_for_path(p) for p in sel], None)
            except GLib.Error as e:
                self.alert(f'{self.with_apps[i].get_name()} could not open this.', e.message)

    def ctx_action(self, name):
        if name.startswith('with'):
            return self.open_with(int(name[4:]))
        {'open': lambda: [self.open_item(p) for p in self.selected()[:1]], 'cut': lambda: self.copy(True),
         'copy': lambda: self.copy(False), 'rename': self.rename, 'delete': self.delete, 'props': self.properties,
         'paste': self.paste, 'newdir': self.new_folder, 'refresh': self.fill, 'restore': self.restore,
         'empty': self.empty_trash, 'undo': self.undo, 'zip': self.compress_selection, 'extract': self.extract_selected,
         'extractall': self.extract_here}[name]()

    # ---- copy, move, delete with a progress window ----------------------------------------------------------------
    def run_job(self, job):
        state = {'win': None, 'timer': 0, 'speed': 0.0, 'last': (time.monotonic(), 0)}
        job.ask = lambda src, dst, answer: self.conflict_dialog(job, src, dst, answer)
        verb = {'copy': 'Copying', 'move': 'Moving', 'trash': 'Moving to the Trash', 'delete': 'Deleting',
                'extract': 'Extracting', 'compress': 'Compressing'}[job.kind]

        def finished(j):
            if state['timer']:
                GLib.source_remove(state['timer'])
            if state['win']:
                state['win'].destroy()
            if j.error:
                self.alert('This could not be finished.', j.error)
            elif j.skipped:
                self.alert(f'{j.skipped} items were not extracted.', 'Their names would have put them outside the destination '
                           'folder, or they are not ordinary files, folders or links.')
            if j.kind in ('move', 'trash') and j.results:
                self.undo_stack.append((j.kind, j.results))
                del self.undo_stack[:-30]
            self.fill()
            if j.then and not j.error and not j.cancel.is_set():
                j.then(j)
            return False

        def tick():
            w = state['win']
            if job.finished or w is None:
                return not job.finished
            now = time.monotonic()
            t, d = state['last']
            if now - t >= 0.5:
                inst = (job.done - d) / (now - t)
                state['speed'] = inst if not state['speed'] else state['speed'] * 0.6 + inst * 0.4
                state['last'] = (now, job.done)
            frac = min(1.0, job.done / job.total) if job.total else 0
            w.bar.set_fraction(frac)
            w.title_label.set_label(f'{frac * 100:.0f}% complete' if job.total else 'Working…')
            w.name.set_label(f'Name: {job.name}')
            by_bytes = job.kind in ('copy', 'move', 'extract', 'compress')
            speed = state['speed']
            left = (job.total - job.done) / speed if speed > 0 else None
            w.time.set_label('Time remaining: ' + ('Calculating…' if left is None or now - job.t0 < 1.5 else
                                                  'Less than a second' if left < 1 else
                                                  f'About {left:.0f} seconds' if left < 90 else f'About {left / 60:.0f} minutes'))
            left_bytes = f' ({human(job.total - job.done)})' if by_bytes else ''
            w.items.set_label(f'Items remaining: {job.items_left}{left_bytes}' if job.items_left >= 0 else '')
            w.speed.set_label(f'Speed: {human(speed)}/s' if by_bytes and speed else 'Speed:')
            return True

        def show():
            state['timer'] = 0
            if job.finished:
                return False
            n = len(job.srcs)
            what = f'{n} items' if n > 1 else f'“{os.path.basename(job.srcs[0].rstrip("/"))}”'
            w = state['win'] = mwx7ui.dialog(self.win, f'{verb} {what}', '16/properties')
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=14, margin_bottom=14,
                          margin_start=18, margin_end=18)
            col.set_size_request(420, -1)
            w.title_label = Gtk.Label(label='', xalign=0, css_classes=['ex-progress-title'])
            col.append(w.title_label)
            frm = f'{verb} {what}'
            if job.dest and job.kind != 'extract':
                frm += f' from {self.title_of(os.path.dirname(job.srcs[0].rstrip("/")))} to {self.title_of(job.dest)}'
            elif job.dest:
                frm += f' to {job.dest}'
            col.append(Gtk.Label(label=frm, xalign=0, wrap=True, max_width_chars=50, css_classes=['ex-progress-from']))
            w.bar = Gtk.ProgressBar(margin_top=6, margin_bottom=6)
            w.bar.add_css_class('ex-drive-bar')
            col.append(w.bar)
            for attr in ('name', 'time', 'items', 'speed'):
                setattr(w, attr, Gtk.Label(label='', xalign=0, css_classes=['ex-meta']))
                col.append(getattr(w, attr))
            cancel = Gtk.Button(label='Cancel', halign=Gtk.Align.END, margin_top=6)
            cancel.connect('clicked', lambda *_: job.cancel.set())
            col.append(cancel)
            w.set_child(col)
            w.connect('close-request', lambda *_: (job.cancel.set(), False)[1])
            w.present()
            tick()
            state['timer'] = GLib.timeout_add(200, tick)
            return False
        job.start(finished)
        # Quick jobs finish before this fires, so they never flash a window.
        state['timer'] = GLib.timeout_add(500, show)

    def conflict_dialog(self, job, src, dst, answer):
        """Windows 7's 'Copy File' question: Replace / Skip / Keep both, optionally for every other conflict."""
        w = mwx7ui.dialog(self.win, 'Replace or Skip Files' if job.kind in ('copy', 'extract') else 'Move File', '16/properties')
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=14, margin_start=18,
                      margin_end=18)
        name = os.path.basename(dst)
        col.append(Gtk.Label(label=f'The destination already has an item named “{name}”', xalign=0, wrap=True,
                             max_width_chars=48, css_classes=['ex-progress-title']))
        done = {'v': False}

        def info(label, p):
            try:
                st = os.stat(p)
                when = datetime.datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M')
                return f'{label}: {"Folder" if os.path.isdir(p) else human(st.st_size)}, modified {when}'
            except OSError:
                return label

        col.append(Gtk.Label(label=info('Existing', dst), xalign=0, css_classes=['ex-meta']))
        col.append(Gtk.Label(label=info('Incoming', src), xalign=0, css_classes=['ex-meta']))
        every = Gtk.CheckButton(label='Do this for all conflicts', margin_top=4)
        col.append(every)

        def pick(choice):
            if done['v']:
                return
            done['v'] = True
            answer(choice, every.get_active())
            w.destroy()
        for label, choice in (('Replace the item in the destination', 'replace'), ('Don’t copy this item', 'skip'),
                              ('Copy, but keep both items', 'keep')):
            b = Gtk.Button(label=label, halign=Gtk.Align.FILL)
            b.get_child().set_xalign(0)
            b.connect('clicked', lambda _b, c=choice: pick(c))
            col.append(b)

        def closed(*_):
            if not done['v']:
                job.cancel.set()
                pick('skip')
            return False
        w.connect('close-request', closed)
        w.set_child(col)
        w.present()

    # ---- compressed folders -------------------------------------------------------------------------------------------
    def compress_selection(self):
        """Send to > Compressed (zipped) folder: NAME.zip next to the items, named after the first one, in a worker."""
        sel = self.selected()
        if not sel or self.zip_loc() or self.loc in (COMPUTER, TRASH):
            return
        first = os.path.basename(sel[0].rstrip('/'))
        name = first if os.path.isdir(sel[0]) else os.path.splitext(first)[0] or first
        dest = unique_in(self.loc, name + '.zip')  # "NAME (2).zip" when the name is taken
        self.run_job(Job('compress', sel, dest))

    def extract_selected(self):
        sel = self.selected()
        if len(sel) == 1 and archive_kind(sel[0]) and os.path.isfile(sel[0]):
            self.extract_dialog(sel[0])

    def extract_here(self):
        z = self.zip_loc()
        if z:
            self.extract_dialog(z[0])

    def extract_dialog(self, archive):
        """Windows 7's Extract Compressed (Zipped) Folders: where to, and whether to show the files afterwards."""
        w = mwx7ui.dialog(self.win, 'Extract Compressed (Zipped) Folders', '16/properties')
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=14, margin_start=18,
                      margin_end=18)
        col.set_size_request(460, -1)
        col.append(Gtk.Label(label='Select a Destination and Extract Files', xalign=0, css_classes=['ex-progress-title']))
        col.append(Gtk.Label(label='Files will be extracted to this folder:', xalign=0, margin_top=6))
        row = Gtk.Box(spacing=8)
        entry = Gtk.Entry(text=os.path.join(os.path.dirname(archive), archive_stem(os.path.basename(archive))), hexpand=True)
        browse = Gtk.Button(label='Browse…')
        row.append(entry)
        row.append(browse)
        col.append(row)
        show = Gtk.CheckButton(label='Show extracted files when complete', active=True, margin_top=4)
        col.append(show)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=10)
        ok = Gtk.Button(label='Extract', css_classes=['suggested-action'])
        cancel = Gtk.Button(label='Cancel')
        buttons.append(ok)
        buttons.append(cancel)
        col.append(buttons)

        def pick(*_):
            dlg = Gtk.FileDialog(title='Select a destination', modal=True)
            dlg.set_initial_folder(Gio.File.new_for_path(os.path.dirname(entry.get_text()) or os.path.expanduser('~')))

            def chosen(d, res):
                try:
                    entry.set_text(d.select_folder_finish(res).get_path())
                except GLib.Error:
                    pass
            dlg.select_folder(w, None, chosen)

        def go(*_):
            dest = os.path.abspath(os.path.expanduser(entry.get_text().strip()))
            if not entry.get_text().strip():
                return
            if os.path.exists(dest) and not os.path.isdir(dest):
                self.alert('That destination is a file, not a folder.', dest)
                return
            w.close()
            job = Job('extract', [archive], dest)
            if show.get_active():
                job.then = lambda _j: self.go(dest)
            self.run_job(job)
        browse.connect('clicked', pick)
        ok.connect('clicked', go)
        entry.connect('activate', go)
        cancel.connect('clicked', lambda *_: w.close())
        w.set_child(col)
        w.present()
        GLib.idle_add(lambda: (entry.grab_focus(), False)[1])

    def open_from_zip(self, zp, inner, vpath):
        """A file in a zip is unpacked to a temp folder (with the progress window, so a big one can be cancelled) and
        opened from there. Temp folders of earlier days are swept away first."""
        tmp_root = tempfile.gettempdir()
        for n in os.listdir(tmp_root):
            d = os.path.join(tmp_root, n)
            try:
                if n.startswith('mwx7-zip-') and os.stat(d).st_uid == os.getuid() and time.time() - os.stat(d).st_mtime > 86400:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass
        dest = tempfile.mkdtemp(prefix='mwx7-zip-')
        job = Job('extract', [zp], dest, members={inner})
        target = safe_path(dest, inner)

        def launch(_j):
            if target and os.path.isfile(target):
                self.open_item(target)
        job.then = launch
        self.run_job(job)

    def alert(self, msg, detail=''):
        Gtk.AlertDialog(message=msg, detail=detail).show(self.win)

    def context_menu(self, gesture, _n, x, y):
        child = self.flow.get_child_at_pos(x, y)
        if child and not child.is_selected():
            self.flow.unselect_all()
            self.flow.select_child(child)
        elif not child:
            self.flow.unselect_all()
        menu = Gio.Menu()
        z = self.zip_loc()
        if child:
            if self.loc == TRASH:
                menu.append('Restore', 'win.ctx::restore')
                menu.append('Delete permanently', 'win.ctx::delete')
            elif z:  # a zip is read-only here: open things, or take everything out
                menu.append('Open', 'win.ctx::open')
                menu.append('Extract All…', 'win.ctx::extractall')
            else:
                menu.append('Open', 'win.ctx::open')
                apps = self.apps_for(self.selected()[:1])
                if apps:
                    sub = Gio.Menu()
                    for i, a in enumerate(apps):
                        sub.append(a.get_name(), f'win.ctx::with{i}')
                    menu.append_submenu('Open with…', sub)
                sel = self.selected()
                if len(sel) == 1 and archive_kind(sel[0]) and os.path.isfile(sel[0]):
                    menu.append('Extract All…', 'win.ctx::extract')
                send = Gio.Menu()  # Windows 7's Send to; only the zip so far
                send.append('Compressed (zipped) folder', 'win.ctx::zip')
                menu.append_submenu('Send to', send)
                menu.append('Cut', 'win.ctx::cut')
                menu.append('Copy', 'win.ctx::copy')
                menu.append('Rename', 'win.ctx::rename')
                menu.append('Move to Trash', 'win.ctx::delete')
                menu.append('Properties', 'win.ctx::props')
        elif z:
            menu.append('Extract All…', 'win.ctx::extractall')
            menu.append('Refresh', 'win.ctx::refresh')
        elif self.loc not in (COMPUTER, TRASH) and not is_uri(self.loc):
            menu.append('Paste', 'win.ctx::paste')
            menu.append('New folder', 'win.ctx::newdir')
            menu.append('Refresh', 'win.ctx::refresh')
            menu.append('Properties', 'win.ctx::props')
        elif self.loc == TRASH:
            menu.append('Empty the Trash', 'win.ctx::empty')
        if not self.win.lookup_action('ctx'):
            act = Gio.SimpleAction.new('ctx', GLib.VariantType.new('s'))
            act.connect('activate', lambda _a, v: self.ctx_action(v.get_string()))
            self.win.add_action(act)
        pop = Gtk.PopoverMenu(menu_model=menu, has_arrow=False)
        pop.set_parent(self.flow)
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = int(x), int(y), 1, 1
        pop.set_pointing_to(r)
        pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
        pop.popup()


if __name__ == '__main__':
    ex = Explorer()
    mwx7ui.App('org.mwx7.explorer', 'My Computer', 'computer', (900, 600), CSS, ex.build).run_main()
