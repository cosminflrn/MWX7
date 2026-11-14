"""MWX 7 desktop layer: desktop icons and widgets as one layer-shell surface between the wallpaper and the windows.

GTK4 + gtk4-layer-shell, same patterns as the shell. The surface paints the still wallpaper itself and is opaque (one
full-screen layer instead of swaybg plus a transparent layer blended on top: less overdraw on slow virtual GPUs). swaybg
only runs as a fallback while this layer is not running. Every redraw here makes Wayfire recomposite the screen, so
widgets redraw rarely: the clock once a minute, the CPU/RAM gauge every 3 s without animating, the calendar when the date
changes.
"""
import glob
import json
import socket
import struct
import math
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

import cairo
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402
from gi.repository import Gtk4LayerShell as Layer  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7displays as displays  # noqa: E402
ICONS = '/usr/share/mwx7/icons'
APP = '/usr/share/mwx7/bin/mwx7-app'
SETTINGS = '/usr/share/mwx7/settings/mwx7-settings'
CONFIG = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'mwx7', 'desktop.json')
CACHE = os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'mwx7', 'desktop-weather.json')
FONT = 'Selawik, DejaVu Sans'

# (label, icon, command, fallback command when the launcher is missing). Order = column order, top to bottom.
ITEMS = [
    ('My Computer', 'computer', ['/usr/share/mwx7/bin/mwx7-app', 'explorer'], None),
    ('Internet', 'browser', ['google-chrome-stable', '--ozone-platform=wayland'], None),
    ('Notepad', 'notepad', [APP, 'notepad'], None),
    ('Calculator', 'calculator', [APP, 'calculator'], None),
    ('Space Pinball', 'pinball', [APP, 'pinball'], None),
    # shell.py's own About entry points at a PINNED slot that does not exist yet; Settings has an About page.
    ('About MWX 7', 'about', [APP, 'about'], [SETTINGS]),
]

# Same grid as the concept's desktop icons.
CELL_W, CELL_H, ORIGIN = 96, 92, 10
# View -> Large / Medium / Small icons: (icon px, cell width, cell height).
SIZES = {'large': (64, 112, 112), 'medium': (48, 96, 92), 'small': (32, 84, 72)}
# Widgets are squares that fill 2x2 icon cells and snap to a grid of whole 2x2 blocks: rows from ORIGIN down,
# columns counted from the right edge (GADGET_RIGHT in). Their drawing code works in a D x D design space that is scaled to the real side.
GADGET_RIGHT, D = ORIGIN, 184



def ensure_x11():
    """Apps that only speak X11 (VLC, Steam, Discord, Spotify, Zoom from Get Apps) need DISPLAY. Wayfire starts
    Xwayland after the shell and the desktop are already running, so they never got it: without this those apps
    silently failed to open. Picks up Wayfire's Xwayland socket (owned by this user) the first time it's needed."""
    if os.environ.get('DISPLAY'):
        return
    uid = os.getuid()
    for path in sorted(glob.glob('/tmp/.X11-unix/X*'), key=lambda p: int(p.rsplit('X', 1)[1] or 0)):
        try:
            if os.stat(path).st_uid == uid:
                os.environ['DISPLAY'] = ':' + path.rsplit('X', 1)[1]
                return
        except (OSError, ValueError):
            continue

def hand_to_shell(cmd):
    """The shell (dock) shows the bounce, stops double launches and reports a failed start; it exposes a 'launch' action
    on the session bus. False when it isn't there (or the call fails), so the caller starts the program itself."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        has_owner = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'NameHasOwner',
                                  GLib.Variant('(s)', ('org.mwx7.shell',)), GLib.VariantType('(b)'),
                                  Gio.DBusCallFlags.NONE, 500, None).unpack()[0]
        if not has_owner:
            return False
        Gio.DBusActionGroup.get(bus, 'org.mwx7.shell', '/org/mwx7/shell').activate_action('launch', GLib.Variant('as', list(cmd)))
        return True
    except GLib.Error:
        return False


def launch(cmd, fallback=None):
    ensure_x11()
    if fallback and not os.path.exists(cmd[0]):
        cmd = fallback
    if hand_to_shell(cmd):
        return
    try:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


WALL_FILE = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'mwx7', 'wallpaper')
WALLPAPERS = '/usr/share/mwx7/wallpapers'
DEFAULT_WALL = '/usr/share/mwx7/wallpaper.jpg'
# Fallbacks for the bar's and dock's heights until the compositor tells us (the surface covers the whole output).
BAR_FALLBACK, DOCK_FALLBACK = 28, 72
SCREEN_OFF = os.path.join(os.environ.get('XDG_RUNTIME_DIR') or '/tmp', 'mwx7-screen-off')  # kept by bin/mwx7-idle
LIVE = '/usr/share/mwx7/live'  # live wallpaper loops: <name>.mp4, chosen by desktop.json's "live_wallpaper"
# What the widget gallery lists, in the column's order: (id, title, one line about it)
GADGET_INFO = [('clock', 'Clock', 'Analog clock with the date.'), ('calendar', 'Calendar', 'This month, today marked.'),
               ('meter', 'CPU Meter', 'Processor and memory load.'), ('weather', 'Weather', 'Temperature for your city.')]


def wayfire(method, data=None):
    """One request to Wayfire (Show desktop, Overview); a missing answer is ignored."""
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(2)
        s.connect(os.environ.get('WAYFIRE_SOCKET', ''))
        body = json.dumps({'method': method, 'data': data or {}}).encode()
        s.sendall(struct.pack('<I', len(body)) + body)
        s.recv(4096)
        s.close()
    except OSError:
        pass


def wayfire_views():
    """Wayfire's window list (the same request the shell uses), or None when it cannot be asked."""
    return wayfire_list('window-rules/list-views')


def wayfire_list(method):
    """The JSON list a Wayfire IPC request answers with, or None when it cannot be asked."""
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(2)
        s.connect(os.environ.get('WAYFIRE_SOCKET', ''))
        body = json.dumps({'method': method, 'data': {}}).encode()
        s.sendall(struct.pack('<I', len(body)) + body)
        buf = b''
        while len(buf) < 4:
            chunk = s.recv(4096)
            if not chunk:
                return None
            buf += chunk
        n = struct.unpack('<I', buf[:4])[0]
        buf = buf[4:]
        while len(buf) < n:
            chunk = s.recv(65536)
            if not chunk:
                return None
            buf += chunk
        s.close()
        views = json.loads(buf[:n])
        return views if isinstance(views, list) else None
    except (OSError, ValueError, struct.error):
        return None


def desktop_dir():
    return GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP) or os.path.expanduser('~/Desktop')


def unique(folder, name):
    """'New folder', 'New folder (2)'... as on the web."""
    base, ext = (name, '') if '.' not in name else (name.rsplit('.', 1)[0], '.' + name.rsplit('.', 1)[1])
    path, n = os.path.join(folder, name), 2
    while os.path.lexists(path):
        path, n = os.path.join(folder, f'{base} ({n}){ext}'), n + 1
    return path


def load_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Write beside, then rename: a crash mid-write must not leave half a settings file.
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError:
        pass


# ---- drawing helpers ----------------------------------------------------------------------------------------------
def col(hexcolor, a=1.0):
    h = hexcolor.lstrip('#')
    return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a


def lin(x0, y0, x1, y1, stops):
    g = cairo.LinearGradient(x0, y0, x1, y1)
    for off, c in stops:
        g.add_color_stop_rgba(off, *c)
    return g


def rad(cx, cy, r, stops):
    g = cairo.RadialGradient(cx, cy, 0, cx, cy, r)
    for off, c in stops:
        g.add_color_stop_rgba(off, *c)
    return g


def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def text(cr, s, x, y, px, rgba, weight=Pango.Weight.NORMAL, align='left', spacing=0.0):
    """Draw s with its baseline at (x, y) in user space. px is a device size: Pango hints badly under a scaled matrix."""
    dx, dy = cr.user_to_device(x, y)
    cr.save()
    cr.identity_matrix()
    layout = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription()
    fd.set_family(FONT)
    fd.set_weight(weight)
    fd.set_absolute_size(px * Pango.SCALE)
    layout.set_font_description(fd)
    layout.set_text(s, -1)
    if spacing:
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
        layout.set_attributes(attrs)
    w, _h = layout.get_pixel_size()
    base = layout.get_baseline() / Pango.SCALE
    left = dx - {'left': 0, 'center': w / 2, 'right': w}[align]
    cr.move_to(left, dy - base)
    cr.set_source_rgba(*rgba)
    PangoCairo.show_layout(cr, layout)
    cr.restore()


def glass_tile(cr, w, h):
    """The concept's .gdg: rounded blue glass, dark 1px ring, white inner edge and a glossy top half."""
    rrect(cr, 0.5, 0.5, w - 1, h - 1, 12)
    cr.set_source_rgba(*col('#001440', 0.6))
    cr.set_line_width(1)
    cr.stroke_preserve()
    cr.set_source(lin(0, 0, 0, h, [(0, col('#3a68a8', 0.72)), (1, col('#102c5c', 0.78))]))
    cr.fill()
    rrect(cr, 1.5, 1.5, w - 3, h - 3, 11)
    cr.set_source_rgba(1, 1, 1, 0.4)
    cr.stroke()
    # Shine: top 46%, rounded at the top and arched at the bottom, like the concept's border-radius trick.
    sh = h * 0.46
    cr.new_path()
    cr.arc(12, 12, 11, math.pi, 3 * math.pi / 2)
    cr.arc(w - 12, 12, 11, 3 * math.pi / 2, 2 * math.pi)
    cr.line_to(w - 1, sh - 18)
    cr.curve_to(w - 1, sh - 6, w * 0.75, sh, w / 2, sh)
    cr.curve_to(w * 0.25, sh, 1, sh - 6, 1, sh - 18)
    cr.close_path()
    cr.set_source(lin(0, 0, 0, sh, [(0, col('#ffffff', 0.3)), (1, col('#ffffff', 0.04))]))
    cr.fill()


# ---- gadgets --------------------------------------------------------------------------------------------------------
class Gadget(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.k = 1.0  # real px per design unit; text() wants device px, so labels multiply their sizes by it
        self.set_content_width(D)
        self.set_content_height(D)
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.set_draw_func(self.on_draw)

    def set_side(self, side):
        if side != self.get_content_width():
            self.set_content_width(side)
            self.set_content_height(side)
            self.queue_draw()

    def on_draw(self, _area, cr, w, _h):
        self.k = w / D
        cr.scale(self.k, self.k)
        glass_tile(cr, D, D)
        self.paint(cr, D, D)

    def t(self, cr, s, x, y, px, rgba, weight=Pango.Weight.NORMAL, align='left', spacing=0.0):
        text(cr, s, x, y, px * self.k, rgba, weight, align, spacing)

    def paint(self, cr, w, h):
        raise NotImplementedError


class Clock(Gadget):
    def __init__(self):
        super().__init__()
        self.now = time.localtime()

    def tick(self):
        # Redraw once a minute, not every second: each redraw makes Wayfire recomposite the screen, and a ticking
        # second hand alone cost ~17% of a core in the compositor in the test VM (part of the lag).
        now = time.localtime()
        if (now.tm_hour, now.tm_min) != (self.now.tm_hour, self.now.tm_min):
            self.now = now
            self.queue_draw()

    def paint(self, cr, w, h):
        t = self.now
        cr.save()
        k = (w - 16) / 100
        cr.translate(8, 8)
        cr.scale(k, k)
        cr.arc(50, 50, 47, 0, 2 * math.pi)
        cr.set_source(lin(3, 3, 97, 97, [(0, col('#f6f9fd')), (0.45, col('#8fa2b8')), (0.55, col('#d3dde9')),
                                         (1, col('#53647a'))]))
        cr.fill()
        cr.arc(50, 50, 43.5, 0, 2 * math.pi)
        cr.set_source(rad(50, 39, 61, [(0, col('#ffffff')), (0.7, col('#e4edf8')), (1, col('#b7c8dd'))]))
        cr.fill_preserve()
        cr.set_source_rgba(*col('#52667f', 0.6))
        cr.set_line_width(0.6)
        cr.stroke()
        for i in range(60):
            big = i % 5 == 0
            cr.save()
            cr.translate(50, 50)
            cr.rotate(math.radians(i * 6))
            cr.move_to(0, -(42 if big else 40.5))
            cr.line_to(0, -(36.5 if big else 38.5))
            cr.set_source_rgba(*col('#2b3a4f'))
            cr.set_line_width(1.6 if big else 0.6)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.stroke()
            cr.restore()
        self.t(cr, 'MWX 7', 50, 33, 5.4 * k, col('#5b6c82'), align='center', spacing=1.2 * k)
        minutes = t.tm_min
        hours = (t.tm_hour % 12) + minutes / 60
        self.hand(cr, hours * 30, 56, 29, 26, 3.6)
        self.hand(cr, minutes * 6, 58, 17, 14, 2.8)
        cr.arc(50, 50, 2.6, 0, 2 * math.pi)
        cr.set_source_rgba(*col('#d6341f'))
        cr.fill()
        cr.arc(50, 50, 1.1, 0, 2 * math.pi)
        cr.set_source_rgba(*col('#f6d2cb'))
        cr.fill()
        cr.move_to(12, 38)
        cr.curve_to(16, 18, 32, 8, 50, 8)
        cr.curve_to(68, 8, 84, 18, 88, 38)
        cr.curve_to(74, 29, 64, 27, 50, 27)
        cr.curve_to(36, 27, 26, 29, 12, 38)
        cr.close_path()
        cr.set_source(lin(0, 8, 0, 38, [(0, col('#ffffff', 0.7 * 0.55)), (1, col('#ffffff', 0))]))
        cr.fill()
        cr.restore()

    @staticmethod
    def hand(cr, angle, tail, tip, shoulder, width):
        cr.save()
        cr.translate(50, 50)
        cr.rotate(math.radians(angle))
        cr.move_to(-width / 2, tail - 50)
        cr.line_to(-width / 4, tip - 50)
        cr.curve_to(-width / 8, shoulder - 50 - 6, width / 8, shoulder - 50 - 6, width / 4, tip - 50)
        cr.line_to(width / 2, tail - 50)
        cr.close_path()
        cr.set_source_rgba(*col('#1d2a3c'))
        cr.fill()
        cr.restore()


MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November',
          'December']
DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']


class Calendar(Gadget):
    def __init__(self):
        super().__init__()
        self.key = None
        self.date = time.localtime()

    def update(self):
        """Called every second with the clock, but redraws only when the date changed."""
        t = time.localtime()
        key = (t.tm_year, t.tm_mon, t.tm_mday)
        if key != self.key:
            self.key = key
            self.date = t
            self.queue_draw()

    def paint(self, cr, w, h):
        t = self.date
        x, y, pw, ph = 8, 8, w - 16, h - 16
        rrect(cr, x, y, pw, ph, 7)
        cr.save()
        cr.clip_preserve()
        cr.set_source(lin(0, y, 0, y + ph, [(0, col('#ffffff')), (1, col('#e9eff7'))]))
        cr.fill()
        cr.rectangle(x, y, pw, 34)
        cr.set_source(lin(0, y, 0, y + 34, [(0, col('#e0553d')), (1, col('#b32a17'))]))
        cr.fill()
        cr.move_to(x, y + 0.5)
        cr.line_to(x + pw, y + 0.5)
        cr.set_source_rgba(1, 1, 1, 0.4)
        cr.set_line_width(1)
        cr.stroke()
        cr.restore()
        rrect(cr, x - 0.5, y - 0.5, pw + 1, ph + 1, 7.5)
        cr.set_source_rgba(*col('#001440', 0.45))
        cr.stroke()
        cx = x + pw / 2
        self.t(cr, f'{MONTHS[t.tm_mon - 1]} {t.tm_year}', cx, y + 23, 16, col('#ffffff'), Pango.Weight.SEMIBOLD, 'center')
        self.t(cr, str(t.tm_mday), cx, y + 117, 84, col('#1b2a3e'), Pango.Weight.LIGHT, 'center')
        # time.struct_time counts Monday as 0; the concept's list starts on Sunday.
        self.t(cr, DAYS[(t.tm_wday + 1) % 7], cx, y + 151, 17, col('#5b6c82'), align='center')


A0, A1 = -125.0, 125.0


class Meter(Gadget):
    """CPU and RAM as two dials. The needles ease to a new value over 0.6 s: the only animation on the desktop."""
    def __init__(self):
        super().__init__()
        self.value = [0.0, 0.0]
        self.target = [0.0, 0.0]
        self.shown = [0, 0]
        self.anim = None
        self.cpu_prev = None

    def set_targets(self, cpu, ram):
        new = [max(0.0, min(100.0, cpu)), max(0.0, min(100.0, ram))]
        if all(abs(a - b) < 0.4 for a, b in zip(new, self.target)):
            return
        # Straight to the new value, no sweep: every animation frame repainted the whole full-screen desktop layer and
        # made Wayfire recomposite the screen (with the blur) at 60 fps for 0.6 s of every 2 s. With the desktop
        # paused, Wayfire went from ~69% to ~5% CPU in the test VM: that was the lag (13 Nov 2026).
        self.target = new
        self.value = list(new)
        self.queue_draw()

    def stop(self):
        if self.anim is not None:
            self.remove_tick_callback(self.anim)
            self.anim = None

    def step(self, _w, clock):
        now = clock.get_frame_time() / 1e6
        if self.t0 is None:
            self.t0 = now
        p = min(1.0, (now - self.t0) / 0.6)
        e = 1 - (1 - p) ** 3
        self.value = [a + (b - a) * e for a, b in zip(self.start, self.target)]
        self.queue_draw()
        if p >= 1.0:
            self.anim = None
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def paint(self, cr, w, h):
        # Two dials side by side under a small title: each 78 wide, scaled up from the 60-unit dial drawing.
        k = 78 / 60
        self.t(cr, 'SYSTEM', w / 2, 27, 11, col('#8fb2dc'), Pango.Weight.SEMIBOLD, 'center', spacing=1.4)
        for i, label in enumerate(('CPU', 'RAM')):
            x0 = 14 + i * 92
            cr.save()
            cr.translate(x0, 40)
            cr.scale(k, k)
            self.dial(cr, label, self.value[i], k * self.k)
            cr.restore()
            self.t(cr, f'{round(self.target[i])}%', x0 + 39, 150, 22, col('#d7e9ff'), Pango.Weight.LIGHT, 'center')

    @staticmethod
    def dial(cr, label, pct, k):
        cr.arc(30, 32, 28, 0, 2 * math.pi)
        cr.set_source(lin(2, 4, 58, 60, [(0, col('#f6f9fd')), (0.45, col('#8fa2b8')), (0.55, col('#d3dde9')),
                                         (1, col('#53647a'))]))
        cr.fill()
        cr.arc(30, 32, 26, 0, 2 * math.pi)
        cr.set_source(rad(30, 24, 42, [(0, col('#2b3f5c')), (1, col('#0a1424'))]))
        cr.fill()
        cr.arc(30, 32, 19, math.radians(A1 - 50 - 90), math.radians(A1 - 90))
        cr.set_source_rgba(*col('#ff6a4d', 0.75))
        cr.set_line_width(2)
        cr.stroke()
        for i in range(11):
            a = A0 + (A1 - A0) * i / 10
            big = i % 5 == 0
            cr.save()
            cr.translate(30, 32)
            cr.rotate(math.radians(a))
            cr.move_to(0, -(25 if big else 23.5))
            cr.line_to(0, -20.5)
            cr.set_source_rgba(*col('#9fc8f5', 0.95 if big else 0.55))
            cr.set_line_width(1.1 if big else 0.6)
            cr.stroke()
            cr.restore()
        text(cr, label, 30, 46, 6.5 * k, col('#bcd6f2'), align='center')
        cr.save()
        cr.translate(30, 32)
        cr.rotate(math.radians(A0 + (A1 - A0) * pct / 100))
        cr.move_to(0, 4)
        cr.line_to(0, -21.5)
        cr.set_source_rgba(*col('#ff7a52'))
        cr.set_line_width(1.1)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.stroke()
        cr.restore()
        cr.arc(30, 32, 2.4, 0, 2 * math.pi)
        cr.set_source_rgba(*col('#e8eef6'))
        cr.fill()
        cr.move_to(7, 24)
        cr.curve_to(10, 12, 19, 6, 30, 6)
        cr.curve_to(41, 6, 50, 12, 53, 24)
        cr.curve_to(44, 19, 38, 18, 30, 18)
        cr.curve_to(22, 18, 16, 19, 7, 24)
        cr.close_path()
        cr.set_source(lin(0, 6, 0, 24, [(0, col('#ffffff', 0.35)), (1, col('#ffffff', 0))]))
        cr.fill()

    def read(self):
        """CPU % since the previous call (from /proc/stat) and RAM % in use (from /proc/meminfo)."""
        cpu = 0.0
        try:
            with open('/proc/stat') as f:
                v = [int(x) for x in f.readline().split()[1:]]
            idle, total = v[3] + (v[4] if len(v) > 4 else 0), sum(v)
            if self.cpu_prev:
                dt = total - self.cpu_prev[1]
                cpu = 100.0 * (1 - (idle - self.cpu_prev[0]) / dt) if dt > 0 else 0.0
            self.cpu_prev = (idle, total)
        except (OSError, ValueError, IndexError):
            pass
        ram = 0.0
        try:
            mem = {}
            with open('/proc/meminfo') as f:
                for line in f:
                    key, _, rest = line.partition(':')
                    if key in ('MemTotal', 'MemAvailable'):
                        mem[key] = int(rest.split()[0])
                    if len(mem) == 2:
                        break
            if mem.get('MemTotal'):
                ram = 100.0 * (1 - mem['MemAvailable'] / mem['MemTotal'])
        except (OSError, ValueError, KeyError):
            pass
        return cpu, ram

    def update(self):
        self.set_targets(*self.read())


# WMO weather codes from Open-Meteo -> (text, icon kind).
def describe(code):
    if code == 0:
        return 'Clear sky', 'clear'
    if code == 1:
        return 'Mainly clear', 'partly'
    if code == 2:
        return 'Partly cloudy', 'partly'
    if code == 3:
        return 'Overcast', 'cloud'
    if code in (45, 48):
        return 'Fog', 'fog'
    if code in (51, 53, 55, 56, 57):
        return 'Drizzle', 'rain'
    if code in (61, 63, 65, 66, 67):
        return 'Rain', 'rain'
    if code in (71, 73, 75, 77, 85, 86):
        return 'Snow', 'snow'
    if code in (80, 81, 82):
        return 'Showers', 'rain'
    if code in (95, 96, 99):
        return 'Thunderstorm', 'storm'
    return 'Unknown', 'cloud'


class Weather(Gadget):
    def __init__(self, city, lat, lon):
        super().__init__()
        self.city, self.lat, self.lon = city, lat, lon
        self.temp = None
        self.code = None
        self.stamp = ''
        self.online = False
        self.busy = False
        cached = load_json(CACHE)
        if isinstance(cached.get('temp'), (int, float)) and isinstance(cached.get('code'), int):
            self.temp, self.code, self.stamp = round(cached['temp']), cached['code'], str(cached.get('at', ''))

    def refresh(self):
        """Fetch off the main thread; returns True so a GLib timeout keeps calling it."""
        if not self.busy:
            self.busy = True
            threading.Thread(target=self.fetch, daemon=True).start()
        return True

    def fetch(self):
        url = (f'https://api.open-meteo.com/v1/forecast?latitude={self.lat}&longitude={self.lon}'
               '&current=temperature_2m,weather_code')
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                cur = json.load(r)['current']
            res = (round(cur['temperature_2m']), int(cur['weather_code']))
        except Exception:  # offline, DNS, bad JSON: all the same to the tile, it keeps the last value
            res = None
        GLib.idle_add(self.done, res)

    def done(self, res):
        self.busy = False
        if res:
            self.temp, self.code = res
            self.stamp = time.strftime('%H:%M')
            self.online = True
            save_json(CACHE, {'temp': self.temp, 'code': self.code, 'at': self.stamp})
        else:
            self.online = False
            # Try again in 5 minutes instead of waiting out the half hour.
            GLib.timeout_add_seconds(300, lambda: self.refresh() and False)
        self.queue_draw()
        return False

    def paint(self, cr, w, h):
        kind = describe(self.code)[1] if self.code is not None else 'cloud'
        # Icon and temperature on top, city and condition below, the update note last.
        cr.save()
        cr.translate(14, 12)
        cr.scale(1.35, 1.35)
        self.icon(cr, kind)
        cr.restore()
        self.t(cr, f'{self.temp}°' if self.temp is not None else '–°', w - 16, 76, 46, col('#eaf3ff'),
               Pango.Weight.LIGHT, 'right')
        self.t(cr, self.city, 16, 123, 20 if len(self.city) <= 12 else 15, col('#eaf3ff'), Pango.Weight.SEMIBOLD)
        self.t(cr, describe(self.code)[0] if self.code is not None else '–', 16, 146, 15, col('#cfe3fb'))
        note = ('Updated ' + self.stamp) if self.online else (('Offline · ' + self.stamp) if self.stamp else 'Offline')
        self.t(cr, note.upper(), 16, 168, 10.5, col('#8fb2dc'), spacing=0.4)

    @staticmethod
    def sun(cr, cx, cy, s):
        cr.save()
        cr.translate(cx, cy)
        cr.scale(s, s)
        cr.set_source_rgba(*col('#ffb629', 0.95))
        cr.set_line_width(2)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for a in range(0, 360, 45):
            cr.save()
            cr.rotate(math.radians(a))
            cr.move_to(0, -13)
            cr.line_to(0, -9.5)
            cr.stroke()
            cr.restore()
        cr.arc(0, 0, 9, 0, 2 * math.pi)
        cr.set_source(rad(-1.8, -2.7, 13.5, [(0, col('#fff3a6')), (0.6, col('#ffc233')), (1, col('#e58a0c'))]))
        cr.fill_preserve()
        cr.set_source_rgba(*col('#b9650a', 0.45))
        cr.set_line_width(0.6)
        cr.stroke()
        cr.restore()

    @staticmethod
    def cloud(cr, dx=0.0, dy=0.0):
        """One union shape (three puffs on a base): outline stroked first, then filled, so only the outer edge shows."""
        cr.save()
        cr.translate(dx, dy)

        def shape():
            cr.new_path()
            cr.arc(20, 33, 5.5, 0, 2 * math.pi)
            cr.new_sub_path()
            cr.arc(29.5, 29.5, 6.8, 0, 2 * math.pi)
            cr.new_sub_path()
            cr.arc(38.5, 33.5, 6, 0, 2 * math.pi)
            rrect(cr, 13, 33, 32, 7.5, 3.75)
        shape()
        cr.set_source_rgba(*col('#6f87a6', 0.7))
        cr.set_line_width(1.4)
        cr.stroke()
        shape()
        cr.set_fill_rule(cairo.FILL_RULE_WINDING)
        cr.set_source(lin(0, 22.7, 0, 40.5, [(0, col('#ffffff')), (1, col('#c9d6e6'))]))
        cr.fill()
        cr.restore()

    def icon(self, cr, kind):
        if kind == 'clear':
            self.sun(cr, 32, 24, 1.35)
            return
        if kind == 'partly':
            self.sun(cr, 22, 19, 1)
            self.cloud(cr)
            return
        # Everything else: a cloud lifted a little to make room for what falls from it.
        self.cloud(cr, 3, -6)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if kind == 'rain':
            cr.set_source_rgba(*col('#7fc1ff'))
            cr.set_line_width(1.8)
            for x in (22, 31, 40):
                cr.move_to(x + 2, 38)
                cr.line_to(x, 44)
                cr.stroke()
        elif kind == 'snow':
            cr.set_source_rgba(*col('#ffffff'))
            for x, y in ((22, 40), (31, 44), (40, 40)):
                cr.arc(x, y, 1.6, 0, 2 * math.pi)
                cr.fill()
        elif kind == 'fog':
            cr.set_source_rgba(*col('#cfe3fb', 0.9))
            cr.set_line_width(1.8)
            for y, x0, x1 in ((38.5, 18, 46), (43, 22, 50)):
                cr.move_to(x0, y)
                cr.line_to(x1, y)
                cr.stroke()
        elif kind == 'storm':
            cr.move_to(32, 34)
            cr.line_to(26, 42)
            cr.line_to(31, 42)
            cr.line_to(28, 48)
            cr.line_to(38, 39)
            cr.line_to(33, 39)
            cr.line_to(36, 34)
            cr.close_path()
            cr.set_source_rgba(*col('#ffc233'))
            cr.fill()


# ---- the desktop surface -------------------------------------------------------------------------------------------
class DesktopIcon(Gtk.Box):
    def __init__(self, label, icon, on_select, on_open, px=48, width=94):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.add_css_class('desk-icon')
        self.set_size_request(width - 2, -1)
        img = icon if isinstance(icon, Gtk.Image) else Gtk.Image.new_from_file(os.path.join(ICONS, icon + '.png'))
        img.set_pixel_size(px)
        self.append(img)
        lab = Gtk.Label(label=label, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.CENTER,
                        max_width_chars=11)
        self.append(lab)
        # The left button (select, double-click to open, drag to move) is handled by the desktop around the icons:
        # measuring a drag on the widget that moves made it jitter.
        self.on_select, self.on_open, self.last_click = on_select, on_open, 0
        self.key = label
        # Right-click selects too, then bubbles up to the desktop's menu.
        r = Gtk.GestureClick()
        r.set_button(3)
        r.connect('pressed', lambda *_a: (setattr(self, 'right_at', GLib.get_monotonic_time()), on_select(self)))
        self.add_controller(r)

    def released(self, moved):
        now = GLib.get_monotonic_time()
        if not moved and now - self.last_click < 450_000:
            self.last_click = 0
            self.on_open()
        else:
            self.last_click = 0 if moved else now


class WallOnly(Gtk.Window):
    """The desktop of a screen that is not the primary one: just the wallpaper, painted for this screen's own size (icons
    and widgets live on the primary screen). One layer surface per output, closed by the compositor when it goes away."""

    def __init__(self, app, monitor):
        super().__init__(application=app)
        self.app, self.monitor, self.size, self.key, self.gen = app, monitor, (0, 0), None, 0
        self.add_css_class('desktop-layer')
        self.add_css_class('opaque')  # opaque region: the compositor skips what is beneath
        Layer.init_for_window(self)
        Layer.set_monitor(self, monitor)
        Layer.set_layer(self, Layer.Layer.BOTTOM)
        Layer.set_namespace(self, 'mwx7-desktop-wall')
        for e in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
            Layer.set_anchor(self, e, True)
        Layer.set_exclusive_zone(self, -1)
        Layer.set_keyboard_mode(self, Layer.KeyboardMode.NONE)
        self.pic = Gtk.Picture(content_fit=Gtk.ContentFit.FILL, can_shrink=True, can_target=False, focusable=False,
                               hexpand=True, vexpand=True)
        self.set_child(self.pic)
        self.connect('realize', lambda win: win.get_surface().connect('layout', lambda _s, w, h: self.resized(w, h)))

    def resized(self, w, h):
        if (w, h) != self.size and w > 0 and h > 0:
            self.size = (w, h)
            self.reload()

    def reload(self):
        """Scale the current wallpaper to this screen (off the main thread); no-op when picture and size are unchanged."""
        w, h = self.size
        path = self.app.wall_path()
        try:
            key = (path, os.stat(path).st_mtime_ns, w, h)
        except OSError:
            return
        if key == self.key or w <= 0:
            return
        self.key = key
        self.gen += 1
        gen = self.gen

        def work():
            try:
                out = self.app.scale_wall(path, key[:2], w, h)
                GLib.idle_add(self.done, gen, out)
            except GLib.Error:
                GLib.idle_add(self.failed, gen)
        threading.Thread(target=work, daemon=True).start()

    def failed(self, gen):
        if gen == self.gen:
            self.key = None
        return False

    def done(self, gen, pix):
        if gen == self.gen:
            self.pic.set_paintable(Gdk.Texture.new_for_pixbuf(pix))
        return False


class Desktop(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.mwx7.desktop')
        self.win = None
        self.rows = 0
        self.selected = None
        self.timers = []
        self.cfg = load_json(CONFIG)
        self.gadgets_on = self.cfg.get('gadgets', True) is not False
        self.cells = {}
        self.height = 0
        self.set_sizes()

    def set_sizes(self):
        self.icon_px, self.cell_w, self.cell_h = SIZES.get(self.cfg.get('icon_size'), SIZES['medium'])

    def do_activate(self):
        if self.win:  # a second start only activates the first: never a second desktop layer
            return
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(HERE, 'desktop.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.win = self.build()
        self.win.present()
        self.sync_timer = 0
        Gdk.Display.get_default().get_monitors().connect('items-changed', lambda *_a: self.sync_later())
        self.disp_mon = Gio.File.new_for_path(displays.CONF).monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.disp_mon.connect('changed', lambda *_a: self.sync_later())
        self.sync_outputs()
        if self.gadgets_on:
            self.start_timers()

    def build(self):
        w = Gtk.ApplicationWindow(application=self)
        w.add_css_class('desktop-layer')
        self.win = w  # update_background (called from set_live below) needs it before do_activate stores the result
        Layer.init_for_window(w)
        mon = displays.pick_primary(displays.monitors(Gdk.Display.get_default()))
        if mon is not None:
            Layer.set_monitor(w, mon)  # icons and widgets live on the primary screen only
        # BOTTOM sits above the live wallpaper (background layer) and below every window. Exclusive zone -1 makes the
        # surface ignore the bar's and dock's reserved strips and cover the whole output, so the wallpaper it paints
        # also shows behind them; icons and widgets are inset by those strips instead (see set_insets).
        Layer.set_layer(w, Layer.Layer.BOTTOM)
        Layer.set_namespace(w, 'mwx7-desktop')
        for e in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
            Layer.set_anchor(w, e, True)
        Layer.set_exclusive_zone(w, -1)
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.NONE)

        self.root = Gtk.Overlay()
        self.fixed = Gtk.Fixed()
        # The live wallpaper is not drawn here: this surface only covers the area between bar and dock. It gets its own
        # full-screen surface on the background layer (see set_live); this one stays transparent over it.
        self.live_pic = None
        self.live_still = None  # the clip's thumbnail under the video, so the layer is never empty before the first frame
        self.live_media = None
        self.live_win = None
        self.live_name = ''
        self.live_paused = False
        self.live_ready = False  # the live layer is on screen: only then does this one turn transparent (no black gap)
        self.live_gen = 0
        self.live_timer = 0
        self.live_soft = None
        self.live_dpms = None  # watches the flag mwx7-idle keeps while the outputs are off
        self.gallery = None
        # The still wallpaper: a texture already scaled to the surface size (see load_wall), shown 1:1 so no draw scales it.
        self.wall_pic = Gtk.Picture(content_fit=Gtk.ContentFit.FILL, can_shrink=True, can_target=False, focusable=False,
                                    hexpand=True, vexpand=True)
        self.wall_key = None  # (path, mtime) of the picture that is shown or being prepared
        self.wall_src = None  # (key, decoded pixbuf): decoded once per picture, not per size
        self.wall_lock = threading.Lock()
        self.others = {}  # connector -> WallOnly, one per screen that is not the primary
        self.wall_size = (0, 0)
        self.wall_gen = 0
        self.wall_ready = False
        self.surf_size = (0, 0)
        self.insets = (BAR_FALLBACK, DOCK_FALLBACK)
        self.root.set_child(self.wall_pic)
        # Icons and widgets live in the area between bar and dock, as before; the margins are that inset.
        self.stage = Gtk.Box(margin_top=self.insets[0], margin_bottom=self.insets[1])
        self.fixed.set_hexpand(True)
        self.fixed.set_vexpand(True)
        self.stage.append(self.fixed)
        self.root.add_overlay(self.stage)
        self.icons = []
        self.put_fixed_icons()
        # The files and folders in the Desktop folder follow MWX 7's own icons, as on the web; watched, not polled.
        os.makedirs(desktop_dir(), exist_ok=True)
        self.desk_mon = Gio.File.new_for_path(desktop_dir()).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.desk_mon.connect('changed', lambda *_a: self.files_later())
        self.files_timer = 0
        self.load_files()

        city = str(self.cfg.get('city') or 'Bucharest')
        lat, lon = self.num('lat', 44.43), self.num('lon', 26.10)
        self.clock, self.cal, self.meter = Clock(), Calendar(), Meter()
        self.weather = Weather(city, lat, lon)
        # Gadgets sit on the same surface as the icons and snap to a grid when dropped; each keeps its place.
        self.gadgets = [('clock', self.clock), ('calendar', self.cal), ('meter', self.meter), ('weather', self.weather)]
        for name, g in self.gadgets:
            g.set_visible(self.gadget_shown(name))
            self.fixed.put(g, 0, 0)
            g.gadget_name = name
        self.show_icons(self.cfg.get('icons', True) is not False)
        # Settings -> Desktop writes the same file: follow it (icons, gadgets, weather city) without a restart.
        self.cfg_mon = Gio.File.new_for_path(CONFIG).monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.cfg_mon.connect('changed', lambda *_a: GLib.timeout_add(200, self.reload_config))
        self.set_live(str(self.cfg.get('live_wallpaper') or ''))
        # Settings and "Next Wallpaper" write this file: follow it, as swaybg restarts used to.
        os.makedirs(os.path.dirname(WALL_FILE), exist_ok=True)
        self.wall_mon = Gio.File.new_for_path(WALL_FILE).monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.wall_timer = 0
        self.wall_mon.connect('changed', lambda *_a: self.wall_later())
        self.measure_insets()
        for secs in (1, 3, 8):  # the shell may start after this layer; the dock also changes size with Settings
            GLib.timeout_add_seconds(secs, lambda: self.measure_insets() and False)

        # For screenshots in automated checks (no pointer there): MWX7_DESKTOP_OPEN=menu.
        if os.environ.get('MWX7_DESKTOP_OPEN') == 'menu':
            GLib.timeout_add(2000, lambda: self.menu(500, 300) and False)
        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect('pressed', self.desktop_click)
        self.root.add_controller(click)
        # Files dragged from My Computer onto the desktop move into the Desktop folder.
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.MOVE | Gdk.DragAction.COPY)

        def dropped(_t, value, _x, _y):
            for f in value.get_files():
                src = f.get_path()
                if src and os.path.exists(src) and os.path.dirname(src) != desktop_dir():
                    try:
                        shutil.move(src, unique(desktop_dir(), os.path.basename(src)))
                    except OSError:
                        pass
            return True
        drop.connect('drop', dropped)
        self.fixed.add_controller(drop)
        # One gesture on the desktop surface for the left button: on an icon it selects (double-click opens) and
        # drags it; on a gadget it drags it; on empty space it draws the rubber band. Offsets are measured on the
        # desktop, which never moves, so dragged things follow the pointer exactly.
        press = Gtk.GestureDrag(button=1)
        press.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        press.connect('drag-begin', self.press_begin)
        press.connect('drag-update', self.press_update)
        press.connect('drag-end', self.press_end)
        self.fixed.add_controller(press)
        w.set_child(self.root)
        # Rows depend on the output height, which only arrives with the compositor's configure.
        w.connect('realize', lambda win: win.get_surface().connect('layout', lambda _s, wd, h: self.layout(wd, h)))
        return w

    # -- screens
    def sync_later(self):
        # Plugging a screen in is a burst of events: one pass after they settle.
        if self.sync_timer:
            GLib.source_remove(self.sync_timer)
        self.sync_timer = GLib.timeout_add(400, self.sync_outputs)

    def sync_outputs(self):
        """The desktop (icons, widgets) goes on the primary screen; every other screen gets a wallpaper-only surface.
        Runs at start and on every hotplug or change of the main display."""
        self.sync_timer = 0
        try:
            mons = displays.monitors(Gdk.Display.get_default())
            main = displays.pick_primary(mons)
            if main is None:
                return False
            if self.win is not None:
                cur = Layer.get_monitor(self.win)
                if cur is None or cur not in mons or displays.connector(cur) != displays.connector(main) \
                        or not self.win.get_visible():
                    Layer.set_monitor(self.win, main)  # remaps; also revives the layer when its screen was unplugged
                    self.win.present()
                    self.wall_size = (0, 0)  # the new output's size arrives with its configure; wallpaper redone then
                if self.live_win is not None:
                    lcur = Layer.get_monitor(self.live_win)
                    if lcur is None or lcur not in mons or displays.connector(lcur) != displays.connector(main) \
                            or not self.live_win.get_visible():
                        Layer.set_monitor(self.live_win, main)  # the video follows the primary screen
                        self.live_win.present()
            want = {displays.connector(m) or str(i): m for i, m in enumerate(mons) if m is not main}
            for name in [n for n in self.others if n not in want or self.others[n].monitor not in mons]:
                self.others.pop(name).destroy()
            for name, m in want.items():
                if name not in self.others:
                    o = WallOnly(self, m)
                    self.others[name] = o
                    o.present()
        except Exception as e:  # never let a hotplug event take the desktop down
            print('sync_outputs:', e, file=sys.stderr)
        return False

    # -- still wallpaper
    def wall_path(self):
        try:
            p = open(WALL_FILE).read().strip()
        except OSError:
            p = ''
        return p if p and os.access(p, os.R_OK) else DEFAULT_WALL

    def wall_later(self):
        # A write is several change events (truncate, write, rename): one reload after they settle.
        if self.wall_timer:
            GLib.source_remove(self.wall_timer)
        self.wall_timer = GLib.timeout_add(150, self.wall_reload)

    def wall_reload(self):
        self.wall_timer = 0
        self.load_wall()
        for o in list(self.others.values()):
            o.reload()
        return False

    def load_wall(self):
        """Prepares the picture for the current surface size off the main thread: decoded once per picture, then scaled and
        cropped once per size ("fill", like swaybg -m fill) into a texture the size of the surface."""
        w, h = self.surf_size
        if w <= 0 or h <= 0:
            return
        path = self.wall_path()
        try:
            key = (path, os.stat(path).st_mtime_ns)
        except OSError:
            return
        if key == self.wall_key and (w, h) == self.wall_size:
            return
        self.wall_key, self.wall_size = key, (w, h)
        self.wall_gen += 1
        gen = self.wall_gen

        def work():
            try:
                pix = self.decode_wall(path, key)
                GLib.idle_add(self.wall_done, gen, key, pix, self.fit_wall(pix, w, h))
            except GLib.Error:
                GLib.idle_add(self.wall_failed, gen)
        threading.Thread(target=work, daemon=True).start()

    def decode_wall(self, path, key):
        """The decoded picture, shared by every screen (decoded once per picture, not per screen)."""
        with self.wall_lock:
            src = self.wall_src
            if not (src and src[0] == key):
                src = (key, GdkPixbuf.Pixbuf.new_from_file(path))
                self.wall_src = src
            return src[1]

    @staticmethod
    def fit_wall(pix, w, h):
        """Scaled and cropped to exactly w x h ("fill", like swaybg -m fill)."""
        k = max(w / pix.get_width(), h / pix.get_height())
        sw, sh = max(w, math.ceil(pix.get_width() * k)), max(h, math.ceil(pix.get_height() * k))
        big = pix.scale_simple(sw, sh, GdkPixbuf.InterpType.BILINEAR)
        out = big.new_subpixbuf((sw - w) // 2, (sh - h) // 2, w, h)
        if out.get_has_alpha():  # a transparent PNG would make the whole surface non-opaque: flatten it on black
            flat = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h)
            flat.fill(0x000000ff)
            out.composite(flat, 0, 0, w, h, 0, 0, 1, 1, GdkPixbuf.InterpType.NEAREST, 255)
            out = flat
        return out.copy()

    def scale_wall(self, path, key, w, h):
        return self.fit_wall(self.decode_wall(path, key), w, h)  # for the other screens' WallOnly (worker thread)

    def wall_failed(self, gen):
        if gen == self.wall_gen:
            self.wall_key = None  # swaybg (or the previous picture) stays; try again on the next change
        return False

    def wall_done(self, gen, key, src, scaled):
        if gen != self.wall_gen:  # a newer picture or size was asked for meanwhile
            return False
        with self.wall_lock:
            self.wall_src = (key, src)
        self.wall_pic.set_paintable(Gdk.Texture.new_for_pixbuf(scaled))
        self.wall_ready = True
        self.update_background()
        return False

    def update_background(self):
        """Opaque desktop (CSS .opaque makes GTK send the opaque region, so the compositor skips what is beneath) while a
        still wallpaper is shown; transparent over the video layer while the live wallpaper plays."""
        still = self.wall_ready and not (self.live_win and self.live_ready)
        self.wall_pic.set_visible(bool(still))
        if still:
            self.win.add_css_class('opaque')
            self.retire_swaybg()
        else:
            self.win.remove_css_class('opaque')

    def retire_swaybg(self):
        """swaybg only covers for this layer; once our first opaque frame is out it is a full-screen surface drawn for
        nothing. Stopped after a few frames (and at most 1.5 s later), so the screen never shows a gap."""
        if getattr(self, 'swaybg_gone', False):
            return
        self.swaybg_gone = True
        done = [False]

        def kill(*_a):
            if not done[0]:
                done[0] = True
                subprocess.run(['pkill', '-u', str(os.getuid()), '-x', 'swaybg'])
            return False
        frames = [0]

        def tick(_w, _clock):
            frames[0] += 1
            if frames[0] >= 3:
                kill()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        self.win.add_tick_callback(tick)
        GLib.timeout_add(1500, kill)

    # -- bar and dock strips
    def measure_insets(self):
        """The surface covers the whole output now, so ask Wayfire how tall the bar and the dock really are."""
        def work():
            bar = dock = None
            for v in wayfire_views() or []:
                geo = v.get('geometry') if isinstance(v, dict) and isinstance(v.get('geometry'), dict) else None
                if not geo:
                    continue
                if v.get('app-id') == 'mwx7-bar':
                    bar = max(0, int(geo.get('y', 0)) + int(geo.get('height', 0)))
                elif v.get('app-id') == 'mwx7-dock' and self.surf_size[1]:
                    dock = max(0, self.surf_size[1] - int(geo.get('y', 0)))
            GLib.idle_add(self.set_insets, bar, dock)
        threading.Thread(target=work, daemon=True).start()
        return True

    def set_insets(self, bar, dock):
        top, bottom = bar if bar is not None else self.insets[0], dock if dock is not None else self.insets[1]
        if (top, bottom) != self.insets:
            self.insets = (top, bottom)
            self.stage.set_margin_top(top)
            self.stage.set_margin_bottom(bottom)
            self.relayout(self.surf_size[1] - top - bottom, force=True)
        return False

    def num(self, key, default):
        v = self.cfg.get(key)
        return float(v) if isinstance(v, (int, float)) else default

    # -- icons
    def put_fixed_icons(self):
        for label, icon, cmd, fallback in ITEMS:
            item = DesktopIcon(label, icon, self.select, lambda c=cmd, f=fallback: launch(c, f), self.icon_px, self.cell_w)
            self.draggable(item, 'item:' + icon)
            self.icons.append(item)
            self.fixed.put(item, ORIGIN, ORIGIN)
        self.fixed_count = len(self.icons)

    def rebuild_icons(self):
        """After View or Sort by: every icon again at the new size / in the new order."""
        self.selected = None
        for item in self.icons:
            self.fixed.remove(item)
        self.icons = []
        self.put_fixed_icons()
        self.load_files()

    def set_view(self, key, value):
        self.cfg[key] = value
        if key == 'sort':
            self.cfg.pop('positions', None)  # sorting lines the icons up again, as Windows does
        save_json(CONFIG, self.cfg)
        self.set_sizes()
        self.rebuild_icons()

    def layout(self, width, height):
        # Called on every layout: move things only when the size really changed, or moving them asks for another
        # layout, forever.
        self.surf_size = (width, height)
        self.load_wall()  # no-op unless the output size changed
        self.relayout(height - sum(self.insets))
        if width != getattr(self, 'width', 0):
            self.width = width
            self.place_gadgets()

    def show_icons(self, on):
        for item in self.icons:
            item.set_visible(on)
        self.icons_on = on

    def widget_side(self):
        """Side of a widget: it snaps to a two-by-two cell block but fills only about three quarters of it, centred; the
        full block read as too big next to the icons."""
        return round(2 * min(self.cell_w, self.cell_h) * 0.74)

    def widget_x(self, c):
        """Left edge of a widget in slot column c (0 = rightmost). A slot is one widget block (2x2 icon cells), so columns are
        exactly one block apart; centred in its block when the cells aren't square."""
        return self.width - GADGET_RIGHT - (2 * c + 2) * self.cell_w + (2 * self.cell_w - self.widget_side()) // 2

    def widget_y(self, r):
        return ORIGIN + r * 2 * self.cell_h + (2 * self.cell_h - self.widget_side()) // 2

    def widget_saved(self, c, r):
        """gadgets_at keeps the distance from the right edge to the widget's left edge and the top y, as older versions did."""
        return [GADGET_RIGHT + (2 * c + 2) * self.cell_w, self.widget_y(r)]

    def widget_slots(self):
        """(columns, rows) of widget slots that fit: whole blocks from the right edge and from the top."""
        cols = max(1, (self.width - GADGET_RIGHT) // (2 * self.cell_w))
        rows = max(1, (getattr(self, 'height', 600) - ORIGIN) // (2 * self.cell_h))
        return cols, rows

    def widget_want(self, name):
        """The (slot column from the right edge, slot row from the top) a widget asks for. Saved positions are rounded to the
        nearest block: older versions snapped to single icon cells, which let columns sit half a widget apart (a staircase).
        Without one, the default is a compact block at the top right, filled column by column (two rows high, or one on a
        screen with room for just one), so the first two widgets stack in the rightmost column and the next two beside them."""
        at = self.cfg.get('gadgets_at') if isinstance(self.cfg.get('gadgets_at'), dict) else {}
        pos = at.get(name)
        if isinstance(pos, list) and len(pos) == 2 and all(isinstance(v, (int, float)) for v in pos):
            c = max(0, round((pos[0] - GADGET_RIGHT) / self.cell_w) - 2)
            r = max(0, round((pos[1] - ORIGIN) / self.cell_h))
            return (c + 1) // 2, (r + 1) // 2  # half a block rounds away from the edge/top, so near-ties don't pile onto one slot
        per_col = min(2, self.widget_slots()[1])
        idx = 0
        for n, _g in self.gadgets:
            if n == name:
                break
            if self.gadget_shown(n):
                idx += 1
        return idx // per_col, idx % per_col

    def widget_cells(self, first=None, want=None):
        """Snap every shown widget to a block slot with no overlap. `first` (with its wanted slot `want`) is placed before
        the rest, so a dropped widget gets its spot and the others keep theirs; a taken slot moves to the nearest free one."""
        cols, rows = self.widget_slots()
        taken, out = set(), {}
        order = [n for n, _g in self.gadgets if self.gadget_shown(n)]
        order.sort(key=lambda n: n != first)
        for n in order:
            c0, r0 = want if n == first and want else self.widget_want(n)
            c0, r0 = max(0, min(cols - 1, c0)), max(0, min(rows - 1, r0))
            best = None
            for c in range(cols):
                for r in range(rows):
                    if (c, r) in taken:
                        continue
                    d = (c - c0) ** 2 + (r - r0) ** 2
                    if best is None or d < best[0]:
                        best = (d, c, r)
            c, r = (best[1], best[2]) if best else (c0, r0)
            taken.add((c, r))
            out[n] = (c, r)
        return out

    def place_gadgets(self):
        if not getattr(self, 'width', 0):
            return
        side = self.widget_side()
        at = self.cfg.get('gadgets_at') if isinstance(self.cfg.get('gadgets_at'), dict) else {}
        norm = dict(at)
        for name, (c, r) in self.widget_cells().items():
            g = dict(self.gadgets)[name]
            g.set_side(side)
            self.fixed.move(g, self.widget_x(c), self.widget_y(r))
            norm[name] = self.widget_saved(c, r)
        if norm != at:  # normalize what an older version (or another screen size) saved, once
            self.cfg['gadgets_at'] = norm
            save_json(CONFIG, self.cfg)

    def gadget_drop(self, name, g, x, y):
        want = (round((self.width - GADGET_RIGHT - x + (2 * self.cell_w - self.widget_side()) // 2) / (2 * self.cell_w)) - 1,
                round((y - ORIGIN) / (2 * self.cell_h)))
        c, r = self.widget_cells(name, want)[name]
        at = self.cfg.get('gadgets_at') if isinstance(self.cfg.get('gadgets_at'), dict) else {}
        at[name] = self.widget_saved(c, r)
        self.cfg['gadgets_at'] = at
        save_json(CONFIG, self.cfg)
        self.place_gadgets()

    def relayout(self, height, force=False):
        self.height = height
        rows = max(1, (height - ORIGIN) // self.cell_h)
        if rows == self.rows and not force:
            return
        self.rows = rows
        # Icons the person moved keep their cell; the rest fill the free cells column by column, like Windows.
        saved = self.cfg.get('positions') if isinstance(self.cfg.get('positions'), dict) else {}
        taken, place = set(), {}
        for item in self.icons:
            pos = saved.get(item.key)
            if isinstance(pos, list) and len(pos) == 2 and 0 <= pos[1] < rows and tuple(pos) not in taken:
                place[item] = tuple(pos)
                taken.add(tuple(pos))
        cell = 0
        for item in self.icons:
            if item in place:
                continue
            while (cell // rows, cell % rows) in taken:
                cell += 1
            place[item] = (cell // rows, cell % rows)
            taken.add(place[item])
        self.cells = place
        for item, (c, r) in place.items():
            self.fixed.move(item, ORIGIN + c * self.cell_w, ORIGIN + r * self.cell_h)

    # -- moving icons by dragging them, as on Windows: they snap to the grid and keep their place
    def draggable(self, item, key):
        item.key = key
        item.set_visible(getattr(self, 'icons_on', True))

    def icon_drop(self, item, x, y):
        c, r = self.cells.get(item, (0, 0))
        nc = max(0, round((x - ORIGIN) / self.cell_w))
        nr = max(0, min(self.rows - 1, round((y - ORIGIN) / self.cell_h)))
        positions = self.cfg.get('positions') if isinstance(self.cfg.get('positions'), dict) else {}
        # Dropping on another icon swaps the two.
        for other, cell in self.cells.items():
            if other is not item and cell == (nc, nr):
                positions[other.key] = [c, r]
        positions[item.key] = [nc, nr]
        self.cfg['positions'] = positions
        save_json(CONFIG, self.cfg)
        self.relayout(self.height, force=True)

    def files_later(self):
        # A burst of changes (a copy of many files) reloads once.
        if not self.files_timer:
            self.files_timer = GLib.timeout_add(300, self.load_files)

    def load_files(self):
        self.files_timer = 0
        for item in self.icons[self.fixed_count:]:
            if item is self.selected:
                self.selected = None
            self.fixed.remove(item)
        del self.icons[self.fixed_count:]
        try:
            names = sorted((n for n in os.listdir(desktop_dir()) if not n.startswith('.')), key=str.lower)
            order = self.cfg.get('sort')
            if order == 'date':
                names.sort(key=lambda n: -os.path.getmtime(os.path.join(desktop_dir(), n)))
            elif order == 'type':
                names.sort(key=lambda n: (not os.path.isdir(os.path.join(desktop_dir(), n)),
                                          os.path.splitext(n)[1].lower(), n.lower()))
        except OSError:
            names = []
        for name in names[:60]:
            f = Gio.File.new_for_path(os.path.join(desktop_dir(), name))
            # MWX 7's own icons by kind, as My Computer shows them (the theme's generic ones looked foreign here).
            path = os.path.join(desktop_dir(), name)
            if os.path.isdir(path):
                kind = 'folder'
            else:
                mime = Gio.content_type_get_mime_type(Gio.content_type_guess(path, None)[0]) or ''
                kind = next((k for k, test in (('exe', name.lower().endswith(('.exe', '.msi'))),
                                               ('image', mime.startswith('image/')), ('audio', mime.startswith('audio/')),
                                               ('video', mime.startswith('video/')), ('text', mime.startswith('text/')),
                                               ('archive', any(z in mime for z in ('zip', 'tar', 'compressed', '7z'))))
                             if test), 'file')
            img = Gtk.Image.new_from_file(os.path.join(ICONS, kind + '.png'))
            label = name
            item = DesktopIcon(label, img, self.select,
                               lambda u=f.get_uri(): Gio.AppInfo.launch_default_for_uri(u, None), self.icon_px, self.cell_w)
            self.draggable(item, 'file:' + name)
            self.icons.append(item)
            self.fixed.put(item, ORIGIN, ORIGIN)
        if getattr(self, 'height', 0):
            self.relayout(self.height, force=True)
        return False

    def next_wallpaper(self):
        try:
            walls = sorted(os.path.join(WALLPAPERS, f) for f in os.listdir(WALLPAPERS)
                           if f.lower().endswith(('.jpg', '.png')))
        except OSError:
            walls = []
        try:
            cur = open(WALL_FILE).read().strip()
        except OSError:
            cur = ''
        if not walls:
            return
        nxt = walls[(walls.index(cur) + 1) % len(walls)] if cur in walls else walls[0]
        os.makedirs(os.path.dirname(WALL_FILE), exist_ok=True)
        with open(WALL_FILE, 'w') as f:
            f.write(nxt + '\n')
        if self.cfg.get('live_wallpaper'):  # a still picture replaces the live one, as in Settings
            self.cfg['live_wallpaper'] = ''
            save_json(CONFIG, self.cfg)
            self.set_live('')
        # The wallpaper file monitor (wall_mon) shows it; the old picture stays until the new one is ready.

    def trash(self, path):
        try:
            Gio.File.new_for_path(path).trash(None)
        except GLib.Error:
            pass

    def rename(self, path):
        """A small box with the name selected (without its extension), as Windows renames on the desktop."""
        w = Gtk.Window(title='Rename', resizable=False)
        box = Gtk.Box(spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        e = Gtk.Entry(text=os.path.basename(path), width_chars=30)
        ok = Gtk.Button(label='Rename')
        ok.add_css_class('suggested-action')
        box.append(e)
        box.append(ok)
        w.set_child(box)

        def go(*_a):
            name = e.get_text().strip()
            w.close()
            if name and '/' not in name and name != os.path.basename(path):
                dest = os.path.join(os.path.dirname(path), name)
                if not os.path.exists(dest):
                    try:
                        os.rename(path, dest)
                        pos = self.cfg.get('positions')
                        if isinstance(pos, dict) and ('file:' + os.path.basename(path)) in pos:
                            pos['file:' + name] = pos.pop('file:' + os.path.basename(path))
                            save_json(CONFIG, self.cfg)
                    except OSError:
                        pass
        ok.connect('clicked', go)
        e.connect('activate', go)
        w.present()
        stem = os.path.splitext(os.path.basename(path))[0] if os.path.isfile(path) else os.path.basename(path)
        GLib.idle_add(lambda: (e.grab_focus(), e.select_region(0, len(stem)), False)[2])

    def new_item(self, folder):
        path = unique(desktop_dir(), 'New folder' if folder else 'New Text Document.txt')
        try:
            os.mkdir(path) if folder else open(path, 'x').close()
        except OSError:
            pass

    def select(self, item):
        for other in getattr(self, 'band_sel', ()):
            other.remove_css_class('selected')
        self.band_sel = set()
        if self.selected is item:
            return
        if self.selected:
            self.selected.remove_css_class('selected')
        self.selected = item
        if item:
            item.add_css_class('selected')

    # -- rubber-band selection, as on the web (Windows 7): drag on empty space, the icons it touches get selected
    def hit(self, x, y):
        """The icon or gadget under a desktop point, if any."""
        for w in list(self.icons) + [g for _n, g in getattr(self, 'gadgets', [])]:
            if not w.get_visible():
                continue
            ok, b = w.compute_bounds(self.fixed)
            if ok and b.get_x() <= x <= b.get_x() + b.get_width() and b.get_y() <= y <= b.get_y() + b.get_height():
                return w
        return None

    def press_begin(self, _g, x, y):
        self.grab = self.hit(x, y)
        self.grab_moved = False
        if self.grab is None:
            self.band_begin(None, x, y)
            return
        ok, b = self.grab.compute_bounds(self.fixed)
        self.grab_from = (b.get_x(), b.get_y()) if ok else (x, y)
        if isinstance(self.grab, DesktopIcon):
            self.select(self.grab)

    def press_update(self, _g, dx, dy):
        if self.grab is None:
            self.band_update(None, dx, dy)
            return
        if not self.grab_moved and abs(dx) < 5 and abs(dy) < 5:
            return
        self.grab_moved = True
        self.fixed.move(self.grab, self.grab_from[0] + dx, self.grab_from[1] + dy)

    def press_end(self, _g, dx, dy):
        w, self.grab = self.grab, None
        if w is None:
            self.band_end()
            return
        x, y = self.grab_from[0] + dx, self.grab_from[1] + dy
        if isinstance(w, DesktopIcon):
            w.released(self.grab_moved)
            if self.grab_moved:
                self.icon_drop(w, x, y)
        elif self.grab_moved:
            self.gadget_drop(w.gadget_name, w, x, y)

    def band_begin(self, _g, x, y):
        self.select(None)
        self.band_start = (x, y)
        self.band = Gtk.Box()
        self.band.add_css_class('rubber-band')
        self.fixed.put(self.band, x, y)

    def band_update(self, _g, dx, dy):
        if not getattr(self, 'band', None):
            return
        x0, y0 = self.band_start
        x, y, w, h = min(x0, x0 + dx), min(y0, y0 + dy), abs(dx), abs(dy)
        self.fixed.move(self.band, x, y)
        self.band.set_size_request(int(w), int(h))
        hit = set()
        for item in self.icons:
            ok, b = item.compute_bounds(self.fixed)
            if ok and b.get_x() < x + w and b.get_x() + b.get_width() > x and b.get_y() < y + h \
                    and b.get_y() + b.get_height() > y:
                hit.add(item)
        for item in self.band_sel - hit:
            item.remove_css_class('selected')
        for item in hit - self.band_sel:
            item.add_css_class('selected')
        self.band_sel = hit

    def band_end(self, *_a):
        if getattr(self, 'band', None):
            self.fixed.remove(self.band)
            self.band = None

    def desktop_click(self, gest, _n, x, y):
        button = gest.get_current_button()
        if button == 1:
            pass  # the desktop's own gesture selects or clears (press_begin)
        elif button == 3:
            self.menu(x, y)

    def menu(self, x, y):
        """The web concept's desktop menu: glass card, 16 px icons, the same items in the same order."""
        it = self.selected
        on_file = it is not None and str(getattr(it, 'key', '')).startswith('file:') and \
            GLib.get_monotonic_time() - getattr(it, 'right_at', 0) < 800_000
        pop = Gtk.Popover()
        pop.add_css_class('desk-menu')
        pop.set_parent(self.root)
        pop.set_has_arrow(False)
        pop.set_halign(Gtk.Align.START)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        pop.set_pointing_to(rect)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def row(label, icon, fn):
            b = Gtk.Button()
            b.add_css_class('menu-row')
            r = Gtk.Box(spacing=8)
            path = os.path.join(ICONS, '16', icon + '.png')
            img = Gtk.Image.new_from_file(path) if os.path.exists(path) else Gtk.Image()
            img.set_pixel_size(16)
            r.append(img)
            r.append(Gtk.Label(label=label, xalign=0))
            b.set_child(r)
            b.connect('clicked', lambda *_a: (pop.popdown(), fn()))
            box.append(b)

        def sep():
            line = Gtk.Box()
            line.add_css_class('menu-sep')
            box.append(line)

        def sub(label, choices, current, key):
            """A row that opens its choices beside it, the current one ticked (Windows 7's View / Sort by)."""
            b = Gtk.Button()
            b.add_css_class('menu-row')
            r = Gtk.Box(spacing=8)
            r.append(Gtk.Box(width_request=16))
            r.append(Gtk.Label(label=label, xalign=0, hexpand=True))
            r.append(Gtk.Label(label='\u25b6'))
            b.set_child(r)
            inner = Gtk.Popover()
            inner.add_css_class('desk-menu')
            inner.set_has_arrow(False)
            inner.set_position(Gtk.PositionType.RIGHT)
            inner.set_parent(b)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            for value, text in choices:
                c = Gtk.Button()
                c.add_css_class('menu-row')
                cr = Gtk.Box(spacing=8)
                cr.append(Gtk.Label(label='\u2713' if value == current else '', width_chars=2))
                cr.append(Gtk.Label(label=text, xalign=0))
                c.set_child(cr)
                c.connect('clicked', lambda *_a, v=value: (inner.popdown(), pop.popdown(), self.set_view(key, v)))
                col.append(c)
            inner.set_child(col)
            b.connect('clicked', lambda *_a: inner.popup())
            box.append(b)
        over = self.hit(x, y)
        if isinstance(over, Gadget) and not on_file:
            row('Close widget', 'delete', lambda n=over.gadget_name: self.set_gadget(n, False))
            row('Widgets\u2026', 'gadgets', self.show_gallery)
            pop.set_child(box)
            pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
            pop.popup()
            return
        if on_file:
            # A file or folder on the desktop: its own menu, as in Explorer.
            path = os.path.join(desktop_dir(), it.key[5:])
            row('Open', 'open', lambda: Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None))
            sep()
            row('Rename', 'rename', lambda: self.rename(path))
            row('Move to Trash', 'delete', lambda: self.trash(path))
            pop.set_child(box)
            pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
            pop.popup()
            return
        sub('View', [('large', 'Large icons'), ('medium', 'Medium icons'), ('small', 'Small icons')],
            self.cfg.get('icon_size', 'medium'), 'icon_size')
        sub('Sort by', [('name', 'Name'), ('date', 'Date modified'), ('type', 'Item type')],
            self.cfg.get('sort', 'name'), 'sort')
        row('Refresh', 'refresh', self.rebuild_icons)
        sep()
        row('Next Wallpaper', 'wallpaper', self.next_wallpaper)
        row('Personalize…', 'settings', lambda: launch([SETTINGS, '--page', 'wallpapers']))
        sep()
        row('New Folder', 'new-folder', lambda: self.new_item(True))
        row('New Text Document', 'new-file', lambda: self.new_item(False))
        row('Widgets\u2026', 'gadgets', self.show_gallery)
        row('Hide Widgets' if self.gadgets_on else 'Show Widgets', 'gadgets', self.toggle_gadgets)
        sep()
        row('Show Desktop', 'desktop', lambda: wayfire('wm-actions/toggle_showdesktop'))
        row('Overview', 'maximize', lambda: wayfire('scale/toggle'))
        row('About MWX 7', 'info', lambda: launch([APP, 'about'], [SETTINGS]))
        pop.set_child(box)
        # A popover keeps its parent alive; unparent once it closes or every right-click would leak one.
        pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    # -- gadgets
    def reload_config(self):
        cfg = load_json(CONFIG)
        if not isinstance(cfg, dict) or cfg == self.cfg:
            return False
        relook = (cfg.get('icon_size'), cfg.get('sort')) != (self.cfg.get('icon_size'), self.cfg.get('sort'))
        self.cfg = cfg
        if relook:
            self.set_sizes()
            self.rebuild_icons()
        self.show_icons(cfg.get('icons', True) is not False)
        self.gadgets_on = cfg.get('gadgets', True) is not False
        self.apply_gadgets()
        GLib.timeout_add(600, lambda: self.measure_insets() and False)  # a new dock size changes its strip
        if self.live_name != str(cfg.get('live_wallpaper') or ''):
            self.set_live(str(cfg.get('live_wallpaper') or ''))
        lat, lon = self.num('lat', 44.43), self.num('lon', 26.10)
        if (lat, lon) != (self.weather.lat, self.weather.lon):
            self.weather.city = str(cfg.get('city') or 'Bucharest')
            self.weather.lat, self.weather.lon = lat, lon
            self.weather.temp = None
            self.weather.queue_draw()
            self.weather.refresh()
        return False

    def toggle_gadgets(self):
        self.gadgets_on = not self.gadgets_on
        self.cfg['gadgets'] = self.gadgets_on
        save_json(CONFIG, self.cfg)
        self.apply_gadgets()

    def gadget_shown(self, name):
        hidden = self.cfg.get('gadgets_hidden')
        return self.gadgets_on and not (isinstance(hidden, list) and name in hidden)

    def apply_gadgets(self):
        """Show the gadgets the config wants; the timers run only while at least one is on screen."""
        for n, g in self.gadgets:
            g.set_visible(self.gadget_shown(n))
        self.place_gadgets()
        if any(self.gadget_shown(n) for n, _g in self.gadgets):
            self.start_timers()
        else:
            self.stop_timers()
        if self.gallery:
            self.gallery.refresh()

    def set_gadget(self, name, on):
        hidden = [n for n in (self.cfg.get('gadgets_hidden') if isinstance(self.cfg.get('gadgets_hidden'), list) else [])
                  if n != name]
        if not on:
            hidden.append(name)
        self.cfg['gadgets_hidden'] = hidden
        if on and not self.gadgets_on:  # adding one while all are hidden brings the gadgets back
            self.gadgets_on = True
            self.cfg['gadgets'] = True
        save_json(CONFIG, self.cfg)
        self.apply_gadgets()

    def show_gallery(self):
        if self.gallery:
            self.gallery.present()
            return
        win = Gtk.Window(title='Widgets', resizable=False, default_width=380)
        win.set_application(self)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12, margin_bottom=12, margin_start=12,
                      margin_end=12)
        buttons = {}
        for name, title, blurb in GADGET_INFO:
            r = Gtk.Box(spacing=10)
            lab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            lab.append(Gtk.Label(label=title, xalign=0, css_classes=['heading']))
            lab.append(Gtk.Label(label=blurb, xalign=0, css_classes=['dim-label']))
            b = Gtk.Button(valign=Gtk.Align.CENTER, width_request=80)
            b.connect('clicked', lambda _b, n=name: self.set_gadget(n, not self.gadget_shown(n)))
            r.append(lab)
            r.append(b)
            box.append(r)
            buttons[name] = b

        def refresh():
            for n, b in buttons.items():
                b.set_label('Remove' if self.gadget_shown(n) else 'Add')
        win.refresh = refresh
        refresh()
        win.set_child(box)
        win.connect('close-request', lambda *_a: setattr(self, 'gallery', None) or False)
        self.gallery = win
        win.present()

    # -- live wallpaper
    @staticmethod
    def software_gl():
        """True when OpenGL is drawn by the CPU (llvmpipe/softpipe): a looping video then costs far too much."""
        try:
            import ctypes
            import ctypes.util
            ctx = Gdk.Display.get_default().create_gl_context()
            ctx.realize()
            ctx.make_current()
            lib = ctypes.CDLL(ctypes.util.find_library('GLESv2') or ctypes.util.find_library('GL') or 'libGL.so.1')
            lib.glGetString.restype = ctypes.c_char_p
            name = (lib.glGetString(0x1F01) or b'').decode(errors='replace').lower()  # GL_RENDERER
            Gdk.GLContext.clear_current()
        except Exception:
            return False
        return any(w in name for w in ('llvmpipe', 'softpipe', 'software'))

    def stop_swaybg(self):
        """swaybg is a background-layer surface too; two of them on one layer have no defined order, so it stops once the
        video layer is on screen (never before: it is what covers the screen until then)."""
        if self.live_win and self.live_ready:
            subprocess.run(['pkill', '-u', str(os.getuid()), '-x', 'swaybg'])
        return False

    def live_drop_media(self):
        """Releases the pipeline for real (clear() closes the stream: decoder, buffers, textures), not only pauses it."""
        if self.live_media:
            m, self.live_media = self.live_media, None
            if self.live_pic:
                self.live_pic.set_paintable(None)
            m.pause()
            m.clear()

    def live_close(self):
        if self.live_win:
            self.live_win.destroy()
        self.live_win = self.live_pic = self.live_still = None
        self.live_ready = False

    def live_open(self):
        w = Gtk.Window(application=self)
        w.add_css_class('live-layer')
        Layer.init_for_window(w)
        mon = displays.pick_primary(displays.monitors(Gdk.Display.get_default()))
        if mon is not None:
            Layer.set_monitor(w, mon)  # the video plays on the primary screen; the others show the still picture
        Layer.set_layer(w, Layer.Layer.BACKGROUND)
        Layer.set_namespace(w, 'mwx7-live')
        for e in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
            Layer.set_anchor(w, e, True)
        Layer.set_exclusive_zone(w, -1)  # -1: ignore the bar's and dock's strips, cover the whole output
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.NONE)
        self.live_still = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True, can_target=False, focusable=False,
                                      hexpand=True, vexpand=True)
        self.live_pic = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True, can_target=False, focusable=False,
                                    hexpand=True, vexpand=True)
        box = Gtk.Overlay()
        box.set_child(self.live_still)
        box.add_overlay(self.live_pic)
        w.set_child(box)
        self.live_win = w
        self.live_ready = False
        gen = self.live_gen

        def shown(*_a):
            # The compositor needs a moment to show a new layer surface; the desktop layer stays opaque until then, so the
            # screen never shows black, and swaybg only goes after.
            def ready():
                if gen == self.live_gen and self.live_win is w:
                    self.live_ready = True
                    self.update_background()
                    self.stop_swaybg()
                return False
            GLib.timeout_add(400, ready)
        w.connect('map', shown)
        w.present()

    def set_live(self, name):
        """Play LIVE/<name>.mp4 looped and muted on a full-screen background layer surface of its own; '' (or a missing
        file, or software rendering) goes back to the still wallpaper."""
        path = os.path.join(LIVE, os.path.basename(name) + '.mp4') if name else ''
        self.live_gen += 1  # forgets any "ready" timer of an earlier call
        if self.live_timer:
            GLib.source_remove(self.live_timer)
            self.live_timer = 0
        self.live_drop_media()
        self.live_name = name
        was_live = self.live_win is not None
        playable = bool(name) and os.path.isfile(path)
        if playable and self.live_soft is None:
            self.live_soft = self.software_gl()
        if not playable or self.live_soft:
            self.live_close()
            if was_live:  # bring the still wallpaper back (painted by this layer, which turns opaque again)
                self.load_wall()
                self.update_background()
            return
        if not self.live_win:
            self.live_open()
        # The still of the same name is the clip's first frame (it is also its Settings thumbnail): shown until the video
        # has a frame of its own, so there is no flash.
        still = os.path.join(WALLPAPERS, os.path.basename(name) + '.jpg')
        if os.path.isfile(still):
            self.live_still.set_filename(still)
            self.live_still.set_visible(True)
        media = Gtk.MediaFile.new_for_filename(path)
        media.set_loop(True)  # the stream seeks back to 0 itself: no new pipeline per round
        media.set_muted(True)
        self.live_media = media
        hid = []

        def frame(m):
            if m.is_prepared() and self.live_media is m and self.live_still:
                self.live_still.set_visible(False)
                self.live_still.set_paintable(None)
                if hid:
                    m.disconnect(hid.pop())
        hid.append(media.connect('invalidate-contents', frame))
        self.live_pic.set_paintable(media)
        self.live_paused = False
        media.play()
        self.update_background()  # (no change until the layer is on screen)
        # A video nobody can see is wasted power: look every 2 s for a covering window, the lock screen or a dark screen;
        # the flag mwx7-idle keeps for DPMS also wakes it at once.
        self.live_timer = GLib.timeout_add_seconds(2, self.live_check)
        if self.live_dpms is None:
            self.live_dpms = Gio.File.new_for_path(SCREEN_OFF).monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.live_dpms.connect('changed', lambda *_a: self.live_check() and False)
        self.live_check()

    def live_check(self):
        if not self.live_media:
            return False
        area = getattr(self, 'width', 0) * getattr(self, 'height', 0)
        main = displays.connector(displays.pick_primary(displays.monitors(Gdk.Display.get_default())))
        dark = os.path.exists(SCREEN_OFF)  # DPMS: mwx7-idle keeps this flag while the outputs are off

        def work():
            def running(*args):
                return subprocess.run(['pgrep', '-u', str(os.getuid())] + list(args), capture_output=True).returncode == 0
            covered = dark or running('-x', 'swaylock') or running('-f', '[m]wx7-lockscreen')
            if not covered:
                views = wayfire_views()
                # Only windows on the screen that plays the video count (a maximized one on the other screen hides nothing).
                oid = None
                for o in (wayfire_list('window-rules/list-outputs') or []) if main else []:
                    if isinstance(o, dict) and o.get('name') == main:
                        oid = o.get('id')

                def big(v):  # a window over ~80% of the desktop area hides the video as well as a maximized one does
                    g = v.get('geometry') if isinstance(v.get('geometry'), dict) else {}
                    return area > 0 and g.get('width', 0) * g.get('height', 0) >= 0.8 * area
                covered = any(
                    isinstance(v, dict) and v.get('mapped', True) and not v.get('minimized')
                    and v.get('role', 'toplevel') == 'toplevel' and (oid is None or v.get('output-id', oid) == oid)
                    and (v.get('fullscreen') or v.get('maximized') or v.get('tiled-edges') == 15 or big(v)) for v in (views or []))
            GLib.idle_add(self.live_apply, covered)
        threading.Thread(target=work, daemon=True).start()
        return True

    def live_apply(self, covered):
        """PAUSED, not just hidden: a paused GStreamer pipeline decodes nothing and the layer is not redrawn."""
        if self.live_media and covered != self.live_paused:
            self.live_paused = covered
            self.live_media.pause() if covered else self.live_media.play()
        return False

    def start_timers(self):
        if self.timers:
            return
        self.tick()
        self.meter.update()
        self.weather.refresh()
        # Whole-second timers let GLib batch wakeups with other programs'. Hidden gadgets cost nothing: all stopped.
        self.timers = [GLib.timeout_add_seconds(1, self.tick), GLib.timeout_add_seconds(3, self.meter_tick),
                       GLib.timeout_add_seconds(1800, self.weather.refresh)]

    def stop_timers(self):
        for t in self.timers:
            GLib.source_remove(t)
        self.timers = []
        self.meter.stop()

    def tick(self):
        self.clock.tick()
        self.cal.update()
        return True

    def meter_tick(self):
        self.meter.update()
        return True


if __name__ == '__main__':
    Desktop().run(None)
