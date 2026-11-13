"""Task Manager (native), Windows 7's tabs. Applications (the open windows; End Task closes one), Processes (sortable;
End Process / End Process Tree with SIGTERM, then SIGKILL after 3 s; other users' programs can be shown but not ended),
Performance (green-on-black history graphs: CPU total or per core, memory, disk, network), Startup (what starts at sign-in).

Timers: one 1 s timer, alive only while the window is mapped and not minimized (Wayfire's view-minimized event; Wayland
has no minimized state). The graphs sample only while the Performance tab is showing, so a hidden Task Manager costs 0."""
import json
import os
import pwd
import re
import signal
import socket
import struct
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, GLib, Gtk  # noqa: E402

APP_ID = 'org.mwx7.taskmgr'
HISTORY = 60
KILL_GRACE_MS = 3000
CSS = """
window.mwx7-taskmgr > box { background: #f0f4fa; }
.tm-tabs { padding: 6px 8px 0; }
.tm-list { background: #ffffff; border: 1px solid #a9b9cf; }
.tm-list row { padding: 2px 8px; }
.tm-list row:selected { background: linear-gradient(180deg, #dcebfc, #c1dcfc); color: #0b2440; }
.tm-head { padding: 0 8px; font-weight: 600; color: #1e3f66; background: linear-gradient(180deg, #ffffff, #e4ecf6);
  border: 1px solid #a9b9cf; border-bottom: none; }
.tm-head label { padding: 3px 0; }
.tm-headbtn { padding: 0; min-height: 0; border: none; box-shadow: none; background: none; font-weight: 600; color: #1e3f66; }
.tm-headbtn:hover { background: rgba(120, 160, 220, 0.25); }
.tm-empty, .tm-note { color: #6b7b92; }
.tm-off { color: #8a97a8; }
.tm-num { font-feature-settings: "tnum"; color: #1c2530; }
.tm-graph { background: #000000; border: 1px solid #4d5c70; }
.tm-cap { font-weight: 600; color: #1e3f66; margin-top: 6px; }
.tm-val { font-feature-settings: "tnum"; color: #33475f; margin-top: 6px; }
.tm-status { padding: 3px 10px; font-size: 11px; color: #33475f; border-top: 1px solid #c3d0e0; background: #e8eef6; }
"""

# Core MWX 7 components, by their wayfire.ini [autostart] key: without them there is no desktop, so Startup won't switch them off
# (background, polkit and webapps too: no wallpaper, no password prompts, Notepad and Paint can't open).
CORE_KEYS = {'shell', 'desktop', 'notifications', 'idle', 'portal', 'background', 'polkit', 'webapps'}
NICE_NAMES = {'shell': 'Desktop shell', 'desktop': 'Desktop icons', 'notifications': 'Notifications', 'idle': 'Screen lock and sleep',
              'portal': 'Desktop portal', 'background': 'Wallpaper', 'startup_sound': 'Startup sound', 'perf': 'Performance tuning',
              'nightlight': 'Night light', 'notes': 'Sticky Notes', 'polkit': 'Password prompts', 'updates': 'Update notifier',
              'bootnotice': 'Boot notice', 'webapps': 'Built-in web apps', 'welcome': 'Welcome tour', 'refresh': 'Refresh rate'}
OFF_MARK = '#mwx7-off# '  # a disabled wayfire.ini line stays in the file, as a comment Wayfire ignores


def ipc_socket_path():
    return os.environ.get('WAYFIRE_SOCKET') or '/tmp/wayfire-wayland-1.socket'


def read_frame(s):
    head = b''
    while len(head) < 4:
        part = s.recv(4 - len(head))
        if not part:
            raise OSError('closed')
        head += part
    n = struct.unpack('<I', head)[0]
    buf = b''
    while len(buf) < n:
        part = s.recv(n - len(buf))
        if not part:
            raise OSError('closed')
        buf += part
    return json.loads(buf)


def send_frame(s, method, data=None):
    body = json.dumps({'method': method, 'data': data or {}}).encode()
    s.sendall(struct.pack('<I', len(body)) + body)


def ipc(method, data=None):
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(2)
        s.connect(ipc_socket_path())
        send_frame(s, method, data)
        out = read_frame(s)
        s.close()
        return out
    except (OSError, ValueError, struct.error):
        return None


def cpu_times():
    """{'cpu': (total, idle), 'cpu0': ...} from one read of /proc/stat."""
    out = {}
    with open('/proc/stat') as f:
        for line in f:
            if not line.startswith('cpu'):
                break
            parts = line.split()
            v = [int(x) for x in parts[1:]]
            out[parts[0]] = (sum(v[:8]), v[3] + v[4])
    return out


def meminfo():
    m = {}
    with open('/proc/meminfo') as f:
        for line in f:
            k, v = line.split(':', 1)
            m[k] = int(v.split()[0])
    return m['MemTotal'], m['MemTotal'] - m.get('MemAvailable', m['MemFree'])


def disk_bytes():
    """(read, written) bytes since boot over the real disks (not loop, RAM, device-mapper or partitions)."""
    try:
        names = {n for n in os.listdir('/sys/block') if not re.match(r'(loop|ram|zram|dm-|md|sr|fd)', n)}
        r = w = 0
        with open('/proc/diskstats') as f:
            for line in f:
                p = line.split()
                if len(p) > 9 and p[2] in names:
                    r += int(p[5]) * 512
                    w += int(p[9]) * 512
        return r, w
    except (OSError, ValueError):
        return 0, 0


def net_bytes():
    """(received, sent) bytes since boot over every interface but loopback."""
    rx = tx = 0
    try:
        with open('/proc/net/dev') as f:
            for line in list(f)[2:]:
                name, data = line.split(':', 1)
                if name.strip() == 'lo':
                    continue
                p = data.split()
                rx += int(p[0])
                tx += int(p[8])
    except (OSError, ValueError, IndexError):
        pass
    return rx, tx


def rate(b):
    for unit in ('B/s', 'KB/s', 'MB/s'):
        if b < 1000:
            return f'{b:.0f} {unit}' if unit == 'B/s' else f'{b:.1f} {unit}'
        b /= 1024
    return f'{b:.1f} GB/s'


class Graph:
    """Windows 7's history graph: a black field, a dark green grid that slides left as samples arrive, bright green lines
    over a faint fill. The series are lists that the caller shifts in place."""

    def __init__(self, series, colors, fixed=None, height=84, show_scale=False):
        self.series, self.colors, self.fixed, self.show_scale = series, colors, fixed, show_scale
        self.phase = 0
        self.area = Gtk.DrawingArea(content_height=height, hexpand=True)
        self.area.add_css_class('tm-graph')
        self.area.set_draw_func(self.draw)

    def scale(self):
        if self.fixed:
            return self.fixed
        peak = max(max(s) for s in self.series)
        for e in range(5, 12):
            for k in (1, 2, 5):
                if peak <= k * 10 ** e:
                    return k * 10 ** e
        return 10 ** 12

    def draw(self, _a, cr, w, h):
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        cr.set_source_rgb(0, 0.38, 0.14)
        cr.set_line_width(1)
        step = 12
        off = (self.phase * w / (HISTORY - 1)) % step
        x = -off
        while x < w:
            cr.move_to(round(x) + 0.5, 0)
            cr.line_to(round(x) + 0.5, h)
            x += step
        for y in range(0, h, step):
            cr.move_to(0, y + 0.5)
            cr.line_to(w, y + 0.5)
        cr.stroke()
        top = self.scale()
        for hist, (r, g, b) in zip(self.series, self.colors):
            pts = [(w * i / (HISTORY - 1), h - 1.5 - (h - 3) * max(0, min(top, v)) / top) for i, v in enumerate(hist)]
            cr.move_to(0, h)
            for px, py in pts:
                cr.line_to(px, py)
            cr.line_to(w, h)
            cr.close_path()
            cr.set_source_rgba(r, g, b, 0.22)
            cr.fill()
            cr.set_source_rgb(r, g, b)
            cr.set_line_width(1.5)
            for i, (px, py) in enumerate(pts):
                (cr.move_to if i == 0 else cr.line_to)(px, py)
            cr.stroke()
        if self.show_scale:
            cr.set_source_rgb(0.55, 0.95, 0.6)
            cr.set_font_size(10)
            cr.move_to(5, 12)
            cr.show_text(rate(top))


def push(hist, v):
    hist.pop(0)
    hist.append(v)


# ---- startup entries ----------------------------------------------------------------------------------------------
def user_ini():
    return os.path.join(GLib.get_user_config_dir(), 'mwx7', 'wayfire.ini')


def autostart_section(text):
    return re.search(r'^\[autostart\]\s*$(.*?)(?=^\[|\Z)', text, re.M | re.S)


def get_key(kf, key):
    try:
        return kf.get_string('Desktop Entry', key)
    except GLib.Error:
        return ''


def startup_entries():
    """[{'id', 'name', 'cmd', 'where', 'enabled', 'core', 'own'}]: wayfire.ini's [autostart], then ~/.config/autostart,
    then the system's /etc/xdg/autostart (shown, never changed)."""
    out = []
    try:
        text = open(user_ini()).read()
    except OSError:
        text = ''
    m = autostart_section(text)
    for line in (m.group(1).splitlines() if m else []):
        k = re.match(r'^\s*(' + re.escape(OFF_MARK) + r')?([A-Za-z0-9_]+)\s*=\s*(.*)$', line)
        if not k or k.group(2) == 'autostart_wf_shell':
            continue
        key = k.group(2)
        out.append({'id': ('ini', key), 'name': NICE_NAMES.get(key, key), 'cmd': k.group(3).strip(), 'where': 'MWX 7 session',
                    'enabled': not k.group(1), 'core': key in CORE_KEYS, 'own': True})
    mine = os.path.join(GLib.get_user_config_dir(), 'autostart')
    seen = set()
    for folder, own in ((mine, True), ('/etc/xdg/autostart', False)):
        try:
            files = sorted(f for f in os.listdir(folder) if f.endswith('.desktop'))
        except OSError:
            continue
        for fn in files:
            if fn in seen:
                continue
            seen.add(fn)
            path = os.path.join(folder, fn)
            kf = GLib.KeyFile()
            try:
                kf.load_from_file(path, GLib.KeyFileFlags.NONE)
                hidden = get_key(kf, 'Hidden') == 'true' or get_key(kf, 'X-GNOME-Autostart-enabled') == 'false'
            except GLib.Error:
                continue
            if not own and hidden:
                continue
            out.append({'id': ('desktop', path), 'name': get_key(kf, 'Name') or fn[:-8], 'cmd': get_key(kf, 'Exec'),
                        'where': 'Your account' if own else 'System', 'enabled': not hidden, 'core': False, 'own': own})
    return out


def write_in_place(path, text):
    """Wayfire reloads wayfire.ini on an in-place modification, never on a rename over it; one write(), never shorter than
    the file was (a #PAD comment fills the rest), as Settings does."""
    text = re.sub(r'\n#PAD *\n?\Z', '\n', text)
    data = text.encode()
    old = os.path.getsize(path)
    if len(data) < old:
        data += b'#PAD' + b' ' * max(0, old - len(data) - 4)
    fd = os.open(path, os.O_WRONLY)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def set_startup(entry, enable):
    """Enable or disable one of the person's own entries. Raises OSError/ValueError when it can't."""
    if not entry['own'] or entry['core']:
        raise ValueError('not changeable')
    kind, ref = entry['id']
    if kind == 'ini':
        text = open(user_ini()).read()
        m = autostart_section(text)
        if not m:
            raise ValueError('no [autostart] section')
        pat = re.compile(r'^(' + re.escape(OFF_MARK) + r')?(' + re.escape(ref) + r'\s*=.*)$', re.M)
        body, n = pat.subn(lambda k: k.group(2) if enable else OFF_MARK + k.group(2), m.group(1), count=1)
        if not n:
            raise ValueError('entry is gone')
        write_in_place(user_ini(), text[:m.start(1)] + body + text[m.end(1):])
        return
    lines = open(ref).read().split('\n')
    lines = [ln for ln in lines if not re.match(r'\s*(Hidden|X-GNOME-Autostart-enabled)\s*=', ln)]
    if not enable:
        i = next((i for i, ln in enumerate(lines) if ln.strip() == '[Desktop Entry]'), None)
        if i is None:
            raise ValueError('not a desktop entry')
        lines.insert(i + 1, 'Hidden=true')
    tmp = ref + '.tmp'
    with open(tmp, 'w') as f:
        f.write('\n'.join(lines))
    os.replace(tmp, ref)


class TaskManager:
    def __init__(self):
        self.uid = os.getuid()
        self.ticks = os.sysconf('SC_CLK_TCK')
        self.page = os.sysconf('SC_PAGE_SIZE')
        self.ncpu = os.cpu_count() or 1
        self.prev_cpu = {}
        self.prev_proc = {}
        self.prev_io = None
        self.procs = []
        self.users = {}
        self.sort_key, self.sort_desc = 'cpu', True
        self.show_all = False
        self.timer = 0
        self.minimized = False
        self.mapped = False
        self.watch_sock = None
        self.zeros = lambda: [0.0] * HISTORY
        self.hist = {'cpu': self.zeros(), 'mem': self.zeros(), 'read': self.zeros(), 'write': self.zeros(), 'down': self.zeros(),
                     'up': self.zeros()}
        self.core_hist = [self.zeros() for _ in range(self.ncpu)]

    # ---- window ---------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-taskmgr')
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stack = Gtk.Stack(vexpand=True, margin_start=8, margin_end=8, margin_bottom=8)
        sw = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.START)
        sw.add_css_class('tm-tabs')
        root.append(sw)
        root.append(self.stack)
        self.build_apps()
        self.build_procs()
        self.build_perf()
        self.build_startup()
        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class('tm-status')
        root.append(self.status)
        tab = os.environ.get('MWX7_TM_TAB')  # for screenshots
        if tab:
            self.stack.set_visible_child_name(tab)
        self.stack.connect('notify::visible-child', lambda *_: self.page_changed())
        win.connect('map', lambda *_: self.set_mapped(True))
        win.connect('unmap', lambda *_: self.set_mapped(False))
        win.connect('realize', lambda *_: self.on_realize())
        win.connect('close-request', lambda *_: self.shutdown())
        self.start_watch()
        return root

    def on_realize(self):
        # Compositors that do report a minimized toplevel state are honoured too.
        surf = self.win.get_surface()
        if surf is not None and hasattr(surf, 'get_state'):
            surf.connect('notify::state', lambda s, _p: self.set_minimized(bool(s.get_state() & Gdk.ToplevelState.MINIMIZED)))

    def start_watch(self):
        """Wayfire tells us when our own window is minimized or restored; nothing polls for it."""
        try:
            s = socket.socket(socket.AF_UNIX)
            s.settimeout(2)
            s.connect(ipc_socket_path())
            send_frame(s, 'window-rules/events/watch', {'events': ['view-minimized']})
            read_frame(s)
        except (OSError, ValueError, struct.error):
            return
        self.watch_sock = s
        GLib.io_add_watch(s.fileno(), GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.on_event)

    def on_event(self, _fd, cond):
        try:
            if cond & GLib.IO_IN:
                ev = read_frame(self.watch_sock)
                view = ev.get('view') or {}
                if ev.get('event') == 'view-minimized' and view.get('app-id') == APP_ID:
                    self.set_minimized(bool(ev.get('state', view.get('minimized'))))
                return True
        except (OSError, ValueError, struct.error):
            pass
        self.watch_sock = None
        return False

    def shutdown(self):
        self.set_mapped(False)
        return False

    def set_mapped(self, v):
        self.mapped = v
        self.sync_timer()

    def set_minimized(self, v):
        self.minimized = v
        self.sync_timer()

    def sync_timer(self):
        run = self.mapped and not self.minimized
        if run and not self.timer:
            self.rebase()
            self.tick()
            self.timer = GLib.timeout_add_seconds(1, self.tick)
        elif not run and self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def page_changed(self):
        self.rebase()
        if self.timer:
            self.tick()

    def rebase(self):
        """Counters are deltas; after a pause the first reading only sets the baseline, so no spike lands on a graph."""
        self.prev_cpu = cpu_times()
        self.prev_proc = {}
        self.prev_io = None

    # ---- tabs: building -------------------------------------------------------------------------------------------
    def build_apps(self):
        apps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8)
        head = Gtk.Box()
        head.add_css_class('tm-head')
        head.append(Gtk.Label(label='Task', xalign=0, hexpand=True))
        head.append(Gtk.Label(label='Status', width_chars=12, xalign=0))
        apps.append(head)
        self.app_list = Gtk.ListBox()
        self.app_list.add_css_class('tm-list')
        # Shown by GTK itself whenever the list has no rows, so it needs no bookkeeping in the refresh code.
        none = Gtk.Label(label='No applications are open.\nPrograms you start will show up here.',
                         justify=Gtk.Justification.CENTER, margin_top=60)
        none.add_css_class('tm-empty')
        self.app_list.set_placeholder(none)
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.app_list)
        apps.append(sc)
        row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        b = Gtk.Button(label='End Task')
        b.connect('clicked', lambda *_: self.end_task())
        sw2 = Gtk.Button(label='Switch To')
        sw2.connect('clicked', lambda *_: self.switch_to())
        row.append(b)
        row.append(sw2)
        apps.append(row)
        self.stack.add_titled(apps, 'apps', 'Applications')

    COLS = (('name', 'Image Name', 0, 0), ('user', 'User', 12, 0), ('pid', 'PID', 7, 1), ('cpu', 'CPU', 6, 1), ('mem', 'Memory', 11, 1))

    def build_procs(self):
        procs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8)
        head = Gtk.Box()
        head.add_css_class('tm-head')
        self.head_btns = {}
        for key, text, w, x in self.COLS:
            lab = Gtk.Label(label=text, xalign=x, hexpand=not w)
            if w:
                lab.set_width_chars(w)
            if key == 'user':
                self.user_head = lab
                lab.set_visible(False)
                head.append(lab)
                continue
            b = Gtk.Button(hexpand=not w)
            b.add_css_class('tm-headbtn')
            b.set_child(lab)
            b.connect('clicked', lambda _b, k=key: self.sort_by(k))
            self.head_btns[key] = lab
            head.append(b)
        procs.append(head)
        self.proc_list = Gtk.ListBox()
        self.proc_list.add_css_class('tm-list')
        self.proc_list.connect('row-selected', lambda *_: self.proc_buttons())
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.proc_list)
        procs.append(sc)
        row = Gtk.Box(spacing=6)
        self.all_users = Gtk.CheckButton(label='Show processes from all users')
        self.all_users.connect('toggled', self.on_all_users)
        row.append(self.all_users)
        row.append(Gtk.Box(hexpand=True))
        self.end_btn = Gtk.Button(label='End Process')
        self.end_btn.connect('clicked', lambda *_: self.end_process(tree=False))
        self.tree_btn = Gtk.Button(label='End Process Tree')
        self.tree_btn.connect('clicked', lambda *_: self.end_process(tree=True))
        row.append(self.end_btn)
        row.append(self.tree_btn)
        procs.append(row)
        self.stack.add_titled(procs, 'procs', 'Processes')
        self.mark_sort()
        self.proc_buttons()

    def build_perf(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=4, margin_end=6)

        def section(title, with_toggle=False):
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=title, xalign=0, css_classes=['tm-cap']))
            val = Gtk.Label(xalign=0, hexpand=True, css_classes=['tm-val'])
            row.append(val)
            if with_toggle:
                chk = Gtk.CheckButton(label='One graph per CPU', margin_top=4)
                row.append(chk)
                box.append(row)
                return val, chk
            box.append(row)
            return val, None

        green, lime = (0.25, 1.0, 0.35), (0.85, 1.0, 0.3)
        self.cpu_val, self.core_chk = section('CPU Usage History', True)
        self.cpu_graph = Graph([self.hist['cpu']], [green], fixed=100)
        self.core_graphs = [Graph([h], [green], fixed=100, height=44) for h in self.core_hist]
        grid = Gtk.Grid(column_spacing=4, row_spacing=4, column_homogeneous=True)
        cols = 1 if self.ncpu == 1 else 2 if self.ncpu <= 4 else 4
        for i, g in enumerate(self.core_graphs):
            grid.attach(g.area, i % cols, i // cols, 1, 1)
        self.cpu_stack = Gtk.Stack()
        self.cpu_stack.add_named(self.cpu_graph.area, 'total')
        self.cpu_stack.add_named(grid, 'cores')
        self.core_chk.connect('toggled', lambda c: self.cpu_stack.set_visible_child_name('cores' if c.get_active() else 'total'))
        box.append(self.cpu_stack)
        self.mem_val, _ = section('Physical Memory Usage History')
        self.mem_graph = Graph([self.hist['mem']], [(0.25, 1.0, 0.35)], fixed=100)
        box.append(self.mem_graph.area)
        self.disk_val, _ = section('Disk Activity History')
        self.disk_graph = Graph([self.hist['read'], self.hist['write']], [green, lime], show_scale=True)
        box.append(self.disk_graph.area)
        self.net_val, _ = section('Network Usage History')
        self.net_graph = Graph([self.hist['down'], self.hist['up']], [green, lime], show_scale=True)
        box.append(self.net_graph.area)
        self.perf_text = Gtk.Label(xalign=0, css_classes=['tm-num'], margin_top=6)
        box.append(self.perf_text)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_child(box)
        self.stack.add_titled(sc, 'perf', 'Performance')
        self.graphs = [self.cpu_graph, self.mem_graph, self.disk_graph, self.net_graph] + self.core_graphs

    def build_startup(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8)
        head = Gtk.Box()
        head.add_css_class('tm-head')
        head.append(Gtk.Label(label='Program', xalign=0, width_chars=22))
        head.append(Gtk.Label(label='Command', xalign=0, hexpand=True))
        head.append(Gtk.Label(label='Status', xalign=0, width_chars=10))
        box.append(head)
        self.start_list = Gtk.ListBox()
        self.start_list.add_css_class('tm-list')
        self.start_list.connect('row-selected', lambda *_: self.start_buttons())
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.start_list)
        box.append(sc)
        row = Gtk.Box(spacing=6)
        self.start_note = Gtk.Label(xalign=0, hexpand=True, wrap=True, css_classes=['tm-note'])
        row.append(self.start_note)
        self.enable_btn = Gtk.Button(label='Enable')
        self.enable_btn.connect('clicked', lambda *_: self.toggle_startup(True))
        self.disable_btn = Gtk.Button(label='Disable')
        self.disable_btn.connect('clicked', lambda *_: self.toggle_startup(False))
        row.append(self.enable_btn)
        row.append(self.disable_btn)
        box.append(row)
        self.stack.add_titled(box, 'startup', 'Startup')
        self.fill_startup()

    # ---- the tick -------------------------------------------------------------------------------------------------
    def tick(self):
        now = cpu_times()
        tot, idle = now['cpu']
        ptot, pidle = self.prev_cpu.get('cpu', (tot, idle))
        dt = max(1, tot - ptot)
        cpu = 100 * (1 - (idle - pidle) / dt)
        mt, mu = meminfo()
        page = self.stack.get_visible_child_name()
        nprocs = None
        if page == 'procs':
            self.procs = self.processes(dt)
            nprocs = len(self.procs)
            self.fill_procs()
        elif page == 'apps':
            self.fill_apps()
        elif page == 'perf':
            self.sample_perf(now, cpu, mt, mu)
        self.prev_cpu = now
        if nprocs is None:
            nprocs = sum(1 for p in os.listdir('/proc') if p.isdigit())
        self.status.set_label(f'Processes: {nprocs}    CPU Usage: {cpu:.0f}%    Physical Memory: {100 * mu / mt:.0f}%')
        return True

    def sample_perf(self, now, cpu, mt, mu):
        io = (disk_bytes(), net_bytes(), now)
        if self.prev_io is not None:
            # The very first reading after a pause is only a baseline.
            (r0, w0), (rx0, tx0), prev = self.prev_io
            (r1, w1), (rx1, tx1), _ = io
            push(self.hist['cpu'], cpu)
            for i, h in enumerate(self.core_hist):
                t, idl = now.get(f'cpu{i}', (0, 0))
                pt, pidl = prev.get(f'cpu{i}', (t, idl))
                push(h, 100 * (1 - (idl - pidl) / max(1, t - pt)))
            push(self.hist['mem'], 100 * mu / mt)
            push(self.hist['read'], max(0, r1 - r0))
            push(self.hist['write'], max(0, w1 - w0))
            push(self.hist['down'], max(0, rx1 - rx0))
            push(self.hist['up'], max(0, tx1 - tx0))
            for g in self.graphs:
                g.phase += 1
                g.area.queue_draw()
            self.cpu_val.set_label(f'{cpu:.0f}%')
            self.mem_val.set_label(f'{mu / 1048576:.1f} GB of {mt / 1048576:.1f} GB')
            self.disk_val.set_label(f'Read {rate(self.hist["read"][-1])}   Write {rate(self.hist["write"][-1])}')
            self.net_val.set_label(f'Down {rate(self.hist["down"][-1])}   Up {rate(self.hist["up"][-1])}')
        self.prev_io = io
        self.perf_text.set_label(f'{self.ncpu} threads    Up time {self.uptime()}')

    @staticmethod
    def uptime():
        s = int(float(open('/proc/uptime').read().split()[0]))
        return f'{s // 86400}d {s % 86400 // 3600:02d}:{s % 3600 // 60:02d}' if s >= 86400 else f'{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}'

    def user_name(self, uid):
        if uid not in self.users:
            try:
                self.users[uid] = pwd.getpwuid(uid).pw_name
            except KeyError:
                self.users[uid] = str(uid)
        return self.users[uid]

    def processes(self, dt_total):
        """[(pid, name, cpu, rss, uid, ppid, start)] for every user; the list is filtered when it is drawn."""
        out, now = [], {}
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                st = os.stat(f'/proc/{pid}')
                with open(f'/proc/{pid}/stat') as f:
                    raw = f.read()
                name = raw[raw.index('(') + 1:raw.rindex(')')]
                fields = raw[raw.rindex(')') + 2:].split()
                used = int(fields[11]) + int(fields[12])
                rss = int(fields[21]) * self.page
                ppid, start = int(fields[1]), int(fields[19])
            except (OSError, ValueError, IndexError):
                continue
            now[pid] = used
            cpu = 100 * self.ncpu * (used - self.prev_proc.get(pid, used)) / dt_total
            try:
                cmd = open(f'/proc/{pid}/cmdline', 'rb').read().split(b'\0')
                if name in ('python3', 'sh') and len(cmd) > 1 and cmd[1]:
                    name = os.path.basename(cmd[1].decode(errors='replace'))
            except OSError:
                pass
            out.append((int(pid), name, cpu, rss, st.st_uid, ppid, start))
        self.prev_proc = now
        return out

    # ---- tabs: filling --------------------------------------------------------------------------------------------
    def keep_selection(self, lst):
        r = lst.get_selected_row()
        return getattr(r, 'key', None) if r else None

    def fill_apps(self):
        views = ipc('window-rules/list-views') or []
        keep = self.keep_selection(self.app_list)
        while (r := self.app_list.get_row_at_index(0)) is not None:
            self.app_list.remove(r)
        for v in views:
            if v.get('role') != 'toplevel' or not v.get('mapped', True) or v.get('app-id') == APP_ID:
                continue
            row = Gtk.ListBoxRow()
            row.key = v['id']
            box = Gtk.Box(spacing=8)
            box.append(Gtk.Label(label=v.get('title') or v.get('app-id') or '?', xalign=0, hexpand=True, ellipsize=3))
            box.append(Gtk.Label(label='Minimized' if v.get('minimized') else 'Running', width_chars=12, xalign=0))
            row.set_child(box)
            self.app_list.append(row)
            if row.key == keep:
                self.app_list.select_row(row)

    def sort_by(self, key):
        self.sort_desc = not self.sort_desc if key == self.sort_key else key != 'name'
        self.sort_key = key
        self.mark_sort()
        self.fill_procs()

    def mark_sort(self):
        for key, lab in self.head_btns.items():
            text = next(t for k, t, *_ in self.COLS if k == key)
            lab.set_label(text + (' ▼' if self.sort_desc else ' ▲') if key == self.sort_key else text)

    def on_all_users(self, chk):
        self.show_all = chk.get_active()
        self.user_head.set_visible(self.show_all)
        self.fill_procs()

    def fill_procs(self):
        keep = self.keep_selection(self.proc_list)
        idx = {'name': 1, 'pid': 0, 'cpu': 2, 'mem': 3}[self.sort_key]
        rows = [p for p in self.procs if self.show_all or p[4] == self.uid]
        rows.sort(key=lambda p: (p[1].lower(), p[0]) if self.sort_key == 'name' else (p[idx], p[3]), reverse=self.sort_desc)
        self.proc_list.unselect_all()
        while (r := self.proc_list.get_row_at_index(0)) is not None:
            self.proc_list.remove(r)
        for pid, name, cpu, rss, uid, _pp, _st in rows:
            row = Gtk.ListBoxRow()
            row.key = pid
            box = Gtk.Box()
            box.append(Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3))
            cells = [(str(pid), 7), (f'{cpu:.0f}', 6), (f'{rss // 1024:,} K', 11)]
            if self.show_all:
                cells.insert(0, (self.user_name(uid), 12))
            for text, w in cells:
                lab = Gtk.Label(label=text, xalign=0 if text == cells[0][0] and self.show_all else 1, width_chars=w, ellipsize=3)
                lab.add_css_class('tm-num')
                if uid != self.uid:
                    lab.add_css_class('tm-off')
                box.append(lab)
            row.set_child(box)
            self.proc_list.append(row)
            if pid == keep:
                self.proc_list.select_row(row)
        self.proc_buttons()

    def selected_proc(self):
        r = self.proc_list.get_selected_row()
        return next((p for p in self.procs if r and p[0] == r.key), None)

    def tree_of(self, pid):
        """The process and everything below it, from the last reading."""
        kids = {}
        for p in self.procs:
            kids.setdefault(p[5], []).append(p)
        out, todo = [], [p for p in self.procs if p[0] == pid]
        while todo:
            p = todo.pop()
            out.append(p)
            todo += kids.get(p[0], [])
        return out

    def proc_buttons(self):
        p = self.selected_proc() if hasattr(self, 'end_btn') else None
        me = os.getpid()
        own = bool(p) and p[4] == self.uid and p[0] != me
        tree = self.tree_of(p[0]) if p else []
        self.end_btn.set_sensitive(own)
        self.tree_btn.set_sensitive(own and all(t[0] != me for t in tree))
        tip = "This belongs to another user; ending it needs administrator rights, which Task Manager doesn't ask for." if (
            p and p[4] != self.uid) else ''
        self.end_btn.set_tooltip_text(tip)
        self.tree_btn.set_tooltip_text(tip)

    def fill_startup(self):
        keep = self.keep_selection(self.start_list)
        while (r := self.start_list.get_row_at_index(0)) is not None:
            self.start_list.remove(r)
        for e in startup_entries():
            row = Gtk.ListBoxRow()
            row.key, row.entry = e['id'], e
            box = Gtk.Box(spacing=8)
            box.append(Gtk.Label(label=e['name'], xalign=0, width_chars=22, ellipsize=3))
            cmd = Gtk.Label(label=e['cmd'], xalign=0, hexpand=True, ellipsize=3)
            cmd.set_tooltip_text(f"{e['cmd']}\n({e['where']})")
            cmd.add_css_class('tm-num')
            box.append(cmd)
            status = 'Required' if e['core'] else 'Enabled' if e['enabled'] else 'Disabled'
            if not e['own'] and not e['core']:
                status = 'System'
            lab = Gtk.Label(label=status, xalign=0, width_chars=10)
            if not e['enabled'] or not e['own']:
                lab.add_css_class('tm-off')
            box.append(lab)
            row.set_child(box)
            self.start_list.append(row)
            if row.key == keep:
                self.start_list.select_row(row)
        self.start_buttons()

    def start_buttons(self):
        r = self.start_list.get_selected_row()
        e = getattr(r, 'entry', None)
        ok = bool(e) and e['own'] and not e['core']
        self.enable_btn.set_sensitive(ok and not e['enabled'])
        self.disable_btn.set_sensitive(ok and e['enabled'])
        if e and e['core']:
            note = 'This is part of MWX 7 itself and always starts.'
        elif e and not e['own']:
            note = 'Installed for everyone on this PC; only an administrator can change it.'
        else:
            note = 'Changes apply the next time you sign in.'
        self.start_note.set_label(note)

    def toggle_startup(self, enable):
        r = self.start_list.get_selected_row()
        e = getattr(r, 'entry', None)
        if not e:
            return
        try:
            set_startup(e, enable)
        except (OSError, ValueError) as err:
            self.start_note.set_label(f'Could not change it: {err}')
            return
        self.fill_startup()

    # ---- graphs: see Graph ----------------------------------------------------------------------------------------

    # ---- actions --------------------------------------------------------------------------------------------------
    def end_task(self):
        r = self.app_list.get_selected_row()
        if r:
            ipc('window-rules/close-view', {'id': r.key})

    def switch_to(self):
        r = self.app_list.get_selected_row()
        if r:
            ipc('wm-actions/set-minimized', {'view_id': r.key, 'state': False})
            ipc('window-rules/focus-view', {'id': r.key})

    def end_process(self, tree):
        p = self.selected_proc()
        if not p or p[4] != self.uid:
            return
        # Only the person's own programs; anything below one that belongs to somebody else is left alone.
        victims = [t for t in (self.tree_of(p[0]) if tree else [p]) if t[4] == self.uid and t[0] != os.getpid()]
        what = f'{p[1]} and the {len(victims) - 1} program(s) it started' if tree and len(victims) > 1 else p[1]
        detail = ('It is asked to quit first; if it is still running after 3 seconds it is stopped by force. '
                  'Unsaved work in it will be lost.')
        if any(v[1] in ('wayfire', 'mwx7-shell') for v in victims):
            detail = 'This is part of your desktop session: ending it will sign you out.\n' + detail
        dlg = Gtk.AlertDialog(message=f'End {what}?', detail=detail,
                              buttons=['End Process Tree' if tree else 'End Process', 'Cancel'], default_button=1, cancel_button=1)

        def done(d, res):
            try:
                if d.choose_finish(res) == 0:
                    self.terminate([(v[0], v[6]) for v in victims])
            except GLib.Error:
                pass
        dlg.choose(self.win, None, done)

    def terminate(self, targets):
        """SIGTERM now, SIGKILL for what is still the same process 3 s later (the start time guards against a reused PID)."""
        for pid, _start in targets:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

        def force():
            for pid, start in targets:
                try:
                    with open(f'/proc/{pid}/stat') as f:
                        raw = f.read()
                    if int(raw[raw.rindex(')') + 2:].split()[19]) == start and raw[raw.rindex(')') + 2] != 'Z':
                        os.kill(pid, signal.SIGKILL)
                except (OSError, ValueError, IndexError):
                    pass
            return False
        GLib.timeout_add(KILL_GRACE_MS, force)


if __name__ == '__main__':
    tm = TaskManager()
    mwx7ui.App(APP_ID, 'Task Manager', 'taskmgr', (580, 640), CSS, tm.build).run_main()
