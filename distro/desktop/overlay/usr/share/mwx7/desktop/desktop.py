"""MWX 7 desktop layer: desktop icons and gadgets as one layer-shell surface between the wallpaper and the windows.

GTK4 + gtk4-layer-shell, same patterns as the shell. The surface is transparent, so the wallpaper (swaybg, background
layer) shows through. Nothing here runs faster than once a second, except the short needle animation of the CPU/RAM
gauge, and only the gadget that changed is redrawn.
"""
import json
import math
import os
import subprocess
import threading
import time
import urllib.request

import cairo
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402
from gi.repository import Gtk4LayerShell as Layer  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = '/usr/share/mwx7/icons'
APP = '/usr/share/mwx7/bin/mwx7-app'
SETTINGS = '/usr/share/mwx7/settings/mwx7-settings'
CONFIG = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'mwx7', 'desktop.json')
CACHE = os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'mwx7', 'desktop-weather.json')
FONT = 'Selawik, DejaVu Sans'

# (label, icon, command, fallback command when the launcher is missing). Order = column order, top to bottom.
ITEMS = [
    ('My Computer', 'computer', ['thunar'], None),
    ('Internet', 'browser', ['google-chrome-stable', '--ozone-platform=wayland'], None),
    ('Notepad', 'notepad', [APP, 'notepad'], None),
    ('Calculator', 'calculator', [APP, 'calculator'], None),
    ('Space Pinball', 'pinball', [APP, 'pinball'], None),
    # shell.py's own About entry points at a PINNED slot that does not exist yet; Settings has an About page.
    ('About MWX 7', 'about', [APP, 'about'], [SETTINGS]),
]

# Same grid as the concept's desktop icons.
CELL_W, CELL_H, ORIGIN = 96, 92, 10
GADGET_W, GADGET_GAP, GADGET_TOP, GADGET_RIGHT = 148, 10, 10, 16


def launch(cmd, fallback=None):
    if fallback and not os.path.exists(cmd[0]):
        cmd = fallback
    try:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


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
    HEIGHT = 100

    def __init__(self):
        super().__init__()
        self.set_content_width(GADGET_W)
        self.set_content_height(self.HEIGHT)
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.set_draw_func(self.on_draw)

    def on_draw(self, _area, cr, w, h):
        glass_tile(cr, w, h)
        self.paint(cr, w, h)

    def paint(self, cr, w, h):
        raise NotImplementedError


class Clock(Gadget):
    HEIGHT = 148

    def __init__(self):
        super().__init__()
        self.now = time.localtime()

    def tick(self):
        self.now = time.localtime()
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
        text(cr, 'MWX 7', 50, 33, 5.4 * k, col('#5b6c82'), align='center', spacing=1.2 * k)
        minutes = t.tm_min + t.tm_sec / 60
        hours = (t.tm_hour % 12) + minutes / 60
        self.hand(cr, hours * 30, 56, 29, 26, 3.6)
        self.hand(cr, minutes * 6, 58, 17, 14, 2.8)
        # Second hand: one step per second, no animation loop. Redrawing the face once a second is cheap.
        cr.save()
        cr.translate(50, 50)
        cr.rotate(math.radians(t.tm_sec * 6))
        cr.move_to(0, 10)
        cr.line_to(0, -37)
        cr.set_source_rgba(*col('#d6341f'))
        cr.set_line_width(1)
        cr.stroke()
        cr.restore()
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
    HEIGHT = 112

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
        cr.rectangle(x, y, pw, 20)
        cr.set_source(lin(0, y, 0, y + 20, [(0, col('#e0553d')), (1, col('#b32a17'))]))
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
        text(cr, f'{MONTHS[t.tm_mon - 1]} {t.tm_year}', cx, y + 14, 11, col('#ffffff'), Pango.Weight.SEMIBOLD, 'center')
        text(cr, str(t.tm_mday), cx, y + 60, 42, col('#1b2a3e'), Pango.Weight.LIGHT, 'center')
        # time.struct_time counts Monday as 0; the concept's list starts on Sunday.
        text(cr, DAYS[(t.tm_wday + 1) % 7], cx, y + 80, 11, col('#5b6c82'), align='center')


A0, A1 = -125.0, 125.0


class Meter(Gadget):
    """CPU and RAM as two dials. The needles ease to a new value over 0.6 s: the only animation on the desktop."""
    HEIGHT = 106

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
        self.target = new
        self.start = list(self.value)
        self.t0 = None
        if self.anim is None:
            self.anim = self.add_tick_callback(self.step)

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
        k = (w - 14) / 2 / 60
        for i, label in enumerate(('CPU', 'RAM')):
            cr.save()
            cr.translate(6 + i * (60 * k + 2), 8)
            cr.scale(k, k)
            self.dial(cr, label, self.value[i], k)
            cr.restore()
            text(cr, f'{round(self.target[i])}%', 6 + i * (60 * k + 2) + 30 * k, 8 + 60 * k + 10, 11, col('#d7e9ff'),
                 align='center')

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
    HEIGHT = 108

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
        cr.save()
        cr.translate(12, 10)
        cr.scale(62 / 64, 62 / 64)
        self.icon(cr, kind)
        cr.restore()
        text(cr, f'{self.temp}°' if self.temp is not None else '–°', w - 12, 43, 30, col('#eaf3ff'),
             Pango.Weight.LIGHT, 'right')
        text(cr, self.city, 12, 72, 13, col('#eaf3ff'), Pango.Weight.SEMIBOLD)
        text(cr, describe(self.code)[0] if self.code is not None else '–', 12, 87, 11.5, col('#cfe3fb'))
        note = ('Updated ' + self.stamp) if self.online else (('Offline · ' + self.stamp) if self.stamp else 'Offline')
        text(cr, note.upper(), 12, 100, 9.5, col('#8fb2dc'), spacing=0.4)

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
    def __init__(self, label, icon, on_select, on_open):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.add_css_class('desk-icon')
        self.set_size_request(94, -1)
        img = Gtk.Image.new_from_file(os.path.join(ICONS, icon + '.png'))
        img.set_pixel_size(48)
        self.append(img)
        lab = Gtk.Label(label=label, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.CENTER,
                        max_width_chars=11)
        self.append(lab)
        g = Gtk.GestureClick()
        g.set_button(1)
        g.connect('pressed', lambda gest, n, _x, _y: self.pressed(gest, n, on_select, on_open))
        self.add_controller(g)
        # Right-click selects too, then bubbles up to the desktop's menu.
        r = Gtk.GestureClick()
        r.set_button(3)
        r.connect('pressed', lambda *_a: on_select(self))
        self.add_controller(r)

    def pressed(self, gest, n_press, on_select, on_open):
        # Claimed so the desktop's "click on empty space deselects" handler does not also fire.
        gest.set_state(Gtk.EventSequenceState.CLAIMED)
        on_select(self)
        if n_press == 2:
            on_open()


class Desktop(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.mwx7.desktop')
        self.win = None
        self.rows = 0
        self.selected = None
        self.timers = []
        self.cfg = load_json(CONFIG)
        self.gadgets_on = self.cfg.get('gadgets', True) is not False

    def do_activate(self):
        if self.win:  # a second start only activates the first: never a second desktop layer
            return
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(HERE, 'desktop.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.win = self.build()
        self.win.present()
        if self.gadgets_on:
            self.start_timers()

    def build(self):
        w = Gtk.ApplicationWindow(application=self)
        w.add_css_class('desktop-layer')
        Layer.init_for_window(w)
        # BOTTOM sits above the wallpaper (background) and below every window. Exclusive zone 0 keeps the bar's and
        # dock's reserved strips free, so the surface covers exactly the usable area.
        Layer.set_layer(w, Layer.Layer.BOTTOM)
        Layer.set_namespace(w, 'mwx7-desktop')
        for e in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
            Layer.set_anchor(w, e, True)
        Layer.set_exclusive_zone(w, 0)
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.NONE)

        self.root = Gtk.Overlay()
        self.fixed = Gtk.Fixed()
        self.root.set_child(self.fixed)
        self.icons = []
        for label, icon, cmd, fallback in ITEMS:
            item = DesktopIcon(label, icon, self.select, lambda c=cmd, f=fallback: launch(c, f))
            self.icons.append(item)
            self.fixed.put(item, ORIGIN, ORIGIN)

        city = str(self.cfg.get('city') or 'Bucharest')
        lat, lon = self.num('lat', 44.43), self.num('lon', 26.10)
        self.clock, self.cal, self.meter = Clock(), Calendar(), Meter()
        self.weather = Weather(city, lat, lon)
        self.gadget_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=GADGET_GAP, halign=Gtk.Align.END,
                                  valign=Gtk.Align.START, margin_top=GADGET_TOP, margin_end=GADGET_RIGHT)
        for g in (self.clock, self.cal, self.meter, self.weather):
            self.gadget_col.append(g)
        self.gadget_col.set_visible(self.gadgets_on)
        # halign END / valign START: the column takes only the space of its tiles, the desktop gets the rest.
        self.root.add_overlay(self.gadget_col)

        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect('pressed', self.desktop_click)
        self.root.add_controller(click)
        w.set_child(self.root)
        # Rows depend on the output height, which only arrives with the compositor's configure.
        w.connect('realize', lambda win: win.get_surface().connect('layout', lambda _s, _w, h: self.relayout(h)))
        return w

    def num(self, key, default):
        v = self.cfg.get(key)
        return float(v) if isinstance(v, (int, float)) else default

    # -- icons
    def relayout(self, height):
        rows = max(1, (height - ORIGIN) // CELL_H)
        if rows == self.rows:
            return
        self.rows = rows
        # Column-major like Windows: fill a column top to bottom, then the next one.
        for i, item in enumerate(self.icons):
            self.fixed.move(item, ORIGIN + (i // rows) * CELL_W, ORIGIN + (i % rows) * CELL_H)

    def select(self, item):
        if self.selected is item:
            return
        if self.selected:
            self.selected.remove_css_class('selected')
        self.selected = item
        if item:
            item.add_css_class('selected')

    def desktop_click(self, gest, _n, x, y):
        button = gest.get_current_button()
        if button == 1:
            self.select(None)
        elif button == 3:
            self.menu(x, y)

    def menu(self, x, y):
        pop = Gtk.Popover()
        pop.add_css_class('desk-menu')
        pop.set_parent(self.root)
        pop.set_has_arrow(False)
        pop.set_halign(Gtk.Align.START)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        pop.set_pointing_to(rect)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def row(label, fn):
            b = Gtk.Button()
            b.add_css_class('menu-row')
            lab = Gtk.Label(label=label, xalign=0)
            b.set_child(lab)
            b.connect('clicked', lambda *_a: (pop.popdown(), fn()))
            box.append(b)

        row('Change wallpaper…', lambda: launch([SETTINGS]))
        row('Hide gadgets' if self.gadgets_on else 'Show gadgets', self.toggle_gadgets)
        pop.set_child(box)
        # A popover keeps its parent alive; unparent once it closes or every right-click would leak one.
        pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    # -- gadgets
    def toggle_gadgets(self):
        self.gadgets_on = not self.gadgets_on
        self.cfg['gadgets'] = self.gadgets_on
        save_json(CONFIG, self.cfg)
        self.gadget_col.set_visible(self.gadgets_on)
        if self.gadgets_on:
            self.start_timers()
        else:
            self.stop_timers()

    def start_timers(self):
        if self.timers:
            return
        self.tick()
        self.meter.update()
        self.weather.refresh()
        # Whole-second timers let GLib batch wakeups with other programs'. Hidden gadgets cost nothing: all stopped.
        self.timers = [GLib.timeout_add_seconds(1, self.tick), GLib.timeout_add_seconds(2, self.meter_tick),
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
