"""MWX 7 native shell: the status bar (top) and the dock (bottom) as real desktop surfaces.

GTK4 + gtk4-layer-shell, styled by style.css with MWX 7's glass. Window state (running apps, focus, minimize) comes
from Wayfire's IPC socket, so the dock reflects real windows of real programs.
"""
import json
import os
import socket
import struct
import subprocess
import threading
import time
import urllib.request

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as Layer  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = '/usr/share/mwx7/icons'

# Pinned dock apps: (label, icon, command, app-ids that count as "this app is running").
PINNED = [
    ('Google Chrome', 'browser', ['google-chrome-stable', '--ozone-platform=wayland'], ('google-chrome',)),
    ('Files', 'computer', ['thunar'], ('thunar',)),
    ('Terminal', 'text', ['foot'], ('foot',)),
    ('MWX 7 Classic', 'about', ['chromium', '--ozone-platform=wayland', '--app=http://127.0.0.1:8080/',
                                '--user-data-dir=/tmp/mwx7-classic'], ('chrome-127.0.0.1',)),
]


class Ipc:
    """Wayfire IPC: 4-byte little-endian length, then a JSON body; one request at a time per socket."""

    def __init__(self):
        self.path = os.environ.get('WAYFIRE_SOCKET', '')
        self.lock = threading.Lock()
        self.sock = None

    def _connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.path)
        return s

    @staticmethod
    def _send(s, method, data=None):
        body = json.dumps({'method': method, 'data': data or {}}).encode()
        s.sendall(struct.pack('<I', len(body)) + body)

    @staticmethod
    def _recv(s):
        head = b''
        while len(head) < 4:
            chunk = s.recv(4 - len(head))
            if not chunk:
                raise ConnectionError('wayfire closed the socket')
            head += chunk
        (n,) = struct.unpack('<I', head)
        body = b''
        while len(body) < n:
            chunk = s.recv(n - len(body))
            if not chunk:
                raise ConnectionError('wayfire closed the socket')
            body += chunk
        return json.loads(body)

    def call(self, method, data=None):
        with self.lock:
            try:
                if self.sock is None:
                    self.sock = self._connect()
                self._send(self.sock, method, data)
                return self._recv(self.sock)
            except OSError:
                self.sock = None
                return None

    def watch(self, on_event):
        """Blocking loop on its own socket; reconnects if Wayfire restarts."""
        while True:
            try:
                s = self._connect()
                self._send(s, 'window-rules/events/watch')
                self._recv(s)
                while True:
                    on_event(self._recv(s))
            except (OSError, ConnectionError, ValueError):
                time.sleep(1)


def apps_windows(views):
    return [v for v in views or [] if v.get('type') == 'toplevel' and v.get('mapped', True) and v.get('role') != 'desktop']


class Shell(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.mwx7.shell')
        self.ipc = Ipc()
        self.views = []

    def do_activate(self):
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(HERE, 'style.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.bar = self.build_bar()
        self.dock = self.build_dock()
        self.bar.present()
        self.dock.present()
        GLib.timeout_add(200, self.tick_clock)
        threading.Thread(target=self.ipc.watch, args=(lambda ev: GLib.idle_add(self.refresh),), daemon=True).start()
        self.refresh()
        threading.Thread(target=self.announce, daemon=True).start()

    @staticmethod
    def announce():
        # Tells the boot test (and anyone watching the system log) that the desktop is up.
        for _ in range(30):
            try:
                urllib.request.urlopen('http://127.0.0.1:8080/__mwx7-shell-ready', timeout=2)
            except Exception as e:  # a 404 still proves the request reached the server
                if getattr(e, 'code', None) == 404:
                    return
            time.sleep(2)

    # ---- layer surfaces -------------------------------------------------------------------------------------------
    def layer_window(self, name, edges, height):
        w = Gtk.ApplicationWindow(application=self)
        w.add_css_class(name)
        Layer.init_for_window(w)
        Layer.set_layer(w, Layer.Layer.TOP)
        Layer.set_namespace(w, 'mwx7-' + name)
        for e in edges:
            Layer.set_anchor(w, e, True)
        Layer.auto_exclusive_zone_enable(w)
        # Only size the axis the surface spans; -1 here reaches the compositor as an invalid huge width.
        if height:
            w.set_default_size(0, height)
        return w

    def build_bar(self):
        w = self.layer_window('bar', (Layer.Edge.TOP, Layer.Edge.LEFT, Layer.Edge.RIGHT), 28)
        box = Gtk.CenterBox()
        left = Gtk.Box(spacing=8)
        orb = Gtk.MenuButton()
        orb.add_css_class('orb')
        orb_img = Gtk.Image.new_from_file(os.path.join(ICONS, 'orb.png'))
        orb_img.set_pixel_size(22)
        orb.set_child(orb_img)
        orb.set_popover(self.build_start())
        left.append(orb)
        self.title = Gtk.Label(label='MWX 7')
        self.title.add_css_class('app-title')
        left.append(self.title)
        right = Gtk.Box(spacing=10)
        show_desktop = Gtk.Button()
        show_desktop.add_css_class('flat-ico')
        show_desktop.set_child(Gtk.Image.new_from_file(os.path.join(ICONS, '16', 'desktop.png')) if os.path.exists(
            os.path.join(ICONS, '16', 'desktop.png')) else Gtk.Image.new_from_icon_name('user-desktop'))
        show_desktop.set_tooltip_text('Show desktop')
        show_desktop.connect('clicked', lambda *_: self.ipc.call('wm-actions/toggle_showdesktop'))
        right.append(show_desktop)
        self.clock = Gtk.Label()
        self.clock.add_css_class('clock')
        right.append(self.clock)
        box.set_start_widget(left)
        box.set_end_widget(right)
        box.set_hexpand(True)
        # A plain Box carries the glass: it paints its CSS background reliably on every GTK theme.
        plate = Gtk.Box()
        plate.add_css_class('bar-plate')
        plate.append(box)
        w.set_child(plate)
        return w

    def build_start(self):
        pop = Gtk.Popover()
        pop.add_css_class('start')
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for label, icon, cmd, _ in PINNED:
            col.append(self.menu_row(label, icon, lambda *_, c=cmd: (pop.popdown(), self.launch(c))))
        col.append(Gtk.Separator())
        col.append(self.menu_row('Restart', 'logoff', lambda *_: subprocess.Popen(['systemctl', 'reboot'])))
        col.append(self.menu_row('Shut Down', 'shutdown', lambda *_: subprocess.Popen(['systemctl', 'poweroff'])))
        pop.set_child(col)
        return pop

    def menu_row(self, label, icon, on_click):
        b = Gtk.Button()
        b.add_css_class('menu-row')
        row = Gtk.Box(spacing=10)
        img = Gtk.Image.new_from_file(os.path.join(ICONS, icon + '.png'))
        img.set_pixel_size(32)
        row.append(img)
        row.append(Gtk.Label(label=label, xalign=0))
        b.set_child(row)
        b.connect('clicked', on_click)
        return b

    def build_dock(self):
        w = self.layer_window('dock', (Layer.Edge.BOTTOM,), 0)
        Layer.set_margin(w, Layer.Edge.BOTTOM, 6)
        self.dock_box = Gtk.Box(spacing=6)
        self.dock_box.add_css_class('dock-shelf')
        self.dock_items = []
        for label, icon, cmd, ids in PINNED:
            b = Gtk.Button()
            b.add_css_class('dock-item')
            b.set_tooltip_text(label)
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            img = Gtk.Image.new_from_file(os.path.join(ICONS, icon + '.png'))
            img.set_pixel_size(48)
            dot = Gtk.Box()
            dot.add_css_class('run-dot')
            dot.set_halign(Gtk.Align.CENTER)
            v.append(img)
            v.append(dot)
            b.set_child(v)
            b.connect('clicked', lambda *_, c=cmd, i=ids: self.dock_click(c, i))
            self.dock_box.append(b)
            self.dock_items.append((b, ids))
        w.set_child(self.dock_box)
        return w

    # ---- behaviour ------------------------------------------------------------------------------------------------
    @staticmethod
    def launch(cmd):
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def windows_of(self, ids):
        return [v for v in apps_windows(self.views) if (v.get('app-id') or '').lower().startswith(ids)]

    def dock_click(self, cmd, ids):
        wins = self.windows_of(ids)
        if not wins:
            self.launch(cmd)
            return
        w = wins[0]
        if w.get('activated') and not w.get('minimized'):
            self.ipc.call('wm-actions/set-minimized', {'view_id': w['id'], 'state': True})
        else:
            if w.get('minimized'):
                self.ipc.call('wm-actions/set-minimized', {'view_id': w['id'], 'state': False})
            self.ipc.call('window-rules/focus-view', {'id': w['id']})

    def refresh(self):
        views = self.ipc.call('window-rules/list-views')
        self.views = views if isinstance(views, list) else []
        for b, ids in self.dock_items:
            if self.windows_of(ids):
                b.add_css_class('running')
            else:
                b.remove_css_class('running')
        focused = next((v for v in apps_windows(self.views) if v.get('activated')), None)
        self.title.set_label(focused.get('title', '')[:60] if focused else 'MWX 7')
        return False

    def tick_clock(self):
        # Same format as MWX 7 on the web: "Mon, Nov 9 09:51:37".
        t = time.localtime()
        self.clock.set_label(time.strftime('%a, %b ', t) + str(t.tm_mday) + time.strftime(' %H:%M:%S', t))
        return True


if __name__ == '__main__':
    Shell().run(None)
