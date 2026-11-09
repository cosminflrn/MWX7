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
import pwd

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402
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


# MWX 7's own icons for apps it knows; everything else uses the app's icon from the system theme.
APP_ICONS = {
    'google-chrome': 'browser', 'thunar': 'computer', 'foot': 'text', 'org.codeberg.dnkl.foot': 'text',
    'mwx7-classic': 'about', 'chromium': 'browser', 'mwx7-settings': 'settings',
}
# Friendly names for apps whose package names mean nothing to a person.
DISPLAY_NAMES = {'thunar': 'Files', 'org.codeberg.dnkl.foot': 'Terminal', 'foot': 'Terminal'}
# Helpers and duplicates: Chromium only exists to run MWX 7 Classic, Chrome is the browser.
HIDDEN_APPS = ('chromium', 'footclient', 'foot-server', 'org.codeberg.dnkl.footclient', 'org.codeberg.dnkl.foot-server', 'thunar-settings', 'thunar-bulk-rename', 'xfce4-', 'nm-connection',
               'org.freedesktop.Xwayland', 'debian-', 'gcr-', 'polkit', 'agreety', 'vim', 'htop', 'python3')


def app_name(app):
    aid = (app.get_id() or '').removesuffix('.desktop').lower()
    return DISPLAY_NAMES.get(aid, app.get_display_name())


def user_display_name():
    p = pwd.getpwuid(os.getuid())
    full = (p.pw_gecos or '').split(',')[0].strip()
    return full or p.pw_name.capitalize()


def app_icon_widget(app, size):
    aid = (app.get_id() or '').removesuffix('.desktop').lower()
    for key, name in APP_ICONS.items():
        if aid.startswith(key):
            img = Gtk.Image.new_from_file(os.path.join(ICONS, name + '.png'))
            break
    else:
        icon = app.get_icon()
        img = Gtk.Image.new_from_gicon(icon) if icon else Gtk.Image.new_from_icon_name('application-x-executable')
    img.set_pixel_size(size)
    return img


class StartMenu(Gtk.Popover):
    """The MWX 7 Start menu: account tile, every installed app, search, power. Opens above the dock orb."""

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.add_css_class('startmenu')
        self.set_has_arrow(False)
        self.set_position(Gtk.PositionType.TOP)
        self.set_offset(0, -8)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # Account tile.
        head = Gtk.Box(spacing=10)
        head.add_css_class('sm-head')
        # Scale the photo up front: a Gtk.Picture asks for its full natural size and ignores size requests.
        try:
            buf = GdkPixbuf.Pixbuf.new_from_file_at_scale('/usr/share/mwx7/avatars/03-guitar.jpg', 48, 48, False)
            pic = Gtk.Image.new_from_paintable(Gdk.Texture.new_for_pixbuf(buf))
        except GLib.Error:
            pic = Gtk.Image.new_from_icon_name('avatar-default')
        pic.set_pixel_size(48)
        frame = Gtk.Frame()
        frame.set_valign(Gtk.Align.CENTER)
        frame.add_css_class('sm-avatar')
        frame.set_child(pic)
        head.append(frame)
        name = Gtk.Label(label=user_display_name(), xalign=0)
        name.add_css_class('sm-user')
        head.append(name)
        root.append(head)
        # App list.
        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class('sm-list')
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(True)
        self.listbox.connect('row-activated', self.on_row)
        self.listbox.set_filter_func(self.filter_row)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(360)
        scroll.set_max_content_height(360)
        scroll.set_child(self.listbox)
        root.append(scroll)
        # Search + power.
        foot = Gtk.Box(spacing=8)
        foot.add_css_class('sm-foot')
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text('Search programs and files')
        self.search.set_hexpand(True)
        self.search.connect('search-changed', lambda *_: self.listbox.invalidate_filter())
        self.search.connect('activate', self.on_enter)
        foot.append(self.search)
        for label, icon, cmd in (('Restart', 'logoff', ['systemctl', 'reboot']),
                                 ('Shut Down', 'shutdown', ['systemctl', 'poweroff'])):
            b = Gtk.Button()
            b.add_css_class('sm-power')
            b.set_tooltip_text(label)
            img = Gtk.Image.new_from_file(os.path.join(ICONS, icon + '.png'))
            img.set_pixel_size(22)
            b.set_child(img)
            b.connect('clicked', lambda *_, c=cmd: subprocess.Popen(c))
            foot.append(b)
        root.append(foot)
        self.set_child(root)
        self.connect('show', self.on_show)
        self.monitor = Gio.AppInfoMonitor.get()
        self.monitor.connect('changed', lambda *_: self.fill())
        self.fill()

    def fill(self):
        while (row := self.listbox.get_row_at_index(0)) is not None:
            self.listbox.remove(row)
        apps = [a for a in Gio.AppInfo.get_all() if a.should_show()
                and not (a.get_id() or '').lower().startswith(HIDDEN_APPS)]
        apps.sort(key=lambda a: app_name(a).lower())
        for app in apps:
            row = Gtk.ListBoxRow()
            row.app = app
            row.terms = ' '.join(filter(None, [app_name(app), app.get_display_name(), app.get_description() or '',
                                               ' '.join(getattr(app, 'get_keywords', lambda: [])() or [])])).lower()
            box = Gtk.Box(spacing=10)
            box.append(app_icon_widget(app, 32))
            box.append(Gtk.Label(label=app_name(app), xalign=0))
            row.set_child(box)
            self.listbox.append(row)
        return False

    def filter_row(self, row):
        q = self.search.get_text().strip().lower()
        return not q or all(w in row.terms for w in q.split())

    def first_visible(self):
        i = 0
        while (row := self.listbox.get_row_at_index(i)) is not None:
            if row.get_child_visible() and self.filter_row(row):
                return row
            i += 1
        return None

    def on_enter(self, *_):
        row = self.first_visible()
        if row:
            self.on_row(self.listbox, row)

    def on_row(self, _lb, row):
        self.popdown()
        try:
            row.app.launch([], None)
        except GLib.Error:
            pass

    def on_show(self, *_):
        self.search.set_text('')
        self.listbox.invalidate_filter()
        GLib.idle_add(self.search.grab_focus)


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
        threading.Thread(target=self.ipc.watch, args=(lambda ev: GLib.idle_add(self.on_ipc_event),), daemon=True).start()
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
        orb.set_popover(self.build_system_menu())
        left.append(orb)
        self.title = Gtk.Label(label='MWX 7')
        self.title.add_css_class('app-title')
        left.append(self.title)
        right = Gtk.Box(spacing=10)
        # Network: an icon whose tooltip names the connection (NetworkManager, polled; cheap and robust).
        self.net = Gtk.Image.new_from_icon_name('network-offline-symbolic')
        net_btn = Gtk.Button()
        net_btn.add_css_class('flat-ico')
        net_btn.set_child(self.net)
        # NetworkManager's own editor for now (Wi-Fi passwords, VPN); MWX 7 Settings will take this over.
        net_btn.connect('clicked', lambda *_: self.launch(['nm-connection-editor']))
        self.net_btn = net_btn
        right.append(net_btn)
        # Volume: click for a slider; scrolling over it also works.
        self.vol_btn = Gtk.MenuButton()
        self.vol_btn.add_css_class('tray-btn')
        self.vol_img = Gtk.Image.new_from_icon_name('audio-volume-medium-symbolic')
        self.vol_btn.set_child(self.vol_img)
        pop = Gtk.Popover()
        pop.add_css_class('start')
        self.vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, 0, 100, 1)
        self.vol_scale.set_inverted(True)
        self.vol_scale.set_size_request(-1, 140)
        self.vol_scale.set_draw_value(True)
        self.vol_scale.connect('value-changed', self.on_volume)
        self.vol_mute = Gtk.ToggleButton(label='Mute')
        self.vol_mute.connect('toggled', self.on_mute)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.append(self.vol_scale)
        vbox.append(self.vol_mute)
        pop.set_child(vbox)
        self.vol_btn.set_popover(pop)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', lambda _c, _dx, dy: (self.vol_scale.set_value(self.vol_scale.get_value() - dy * 5), True)[1])
        self.vol_btn.add_controller(scroll)
        right.append(self.vol_btn)
        self.vol_updating = False
        GLib.timeout_add_seconds(2, self.poll_status)
        GLib.idle_add(self.poll_status)
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

    def build_system_menu(self):
        pop = Gtk.Popover()
        pop.add_css_class('start')
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.append(self.menu_row('Settings', 'settings',
                                 lambda *_: (pop.popdown(), self.launch(['/usr/share/mwx7/settings/mwx7-settings']))))
        col.append(self.menu_row('About MWX 7', 'about', lambda *_: (pop.popdown(), self.launch(PINNED[3][2]))))
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
        # The search box in the Start menu needs the keyboard; on demand means only while it has focus.
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.ON_DEMAND)
        self.dock_box = Gtk.Box(spacing=6)
        self.dock_box.add_css_class('dock-shelf')
        self.dock_items = []
        start = Gtk.MenuButton()
        start.add_css_class('dock-orb')
        start.set_tooltip_text('Start')
        orb_big = Gtk.Image.new_from_file(os.path.join(ICONS, 'orb.png'))
        orb_big.set_pixel_size(52)
        start.set_child(orb_big)
        start.set_popover(StartMenu(self))
        self.dock_box.append(start)
        sep = Gtk.Box()
        sep.add_css_class('dock-sep')
        self.dock_box.append(sep)
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
            right_click = Gtk.GestureClick(button=3)
            # Capture phase: the button's own click handling would otherwise swallow the secondary button.
            right_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            right_click.connect('pressed', lambda *_a, btn=b, l=label, c=cmd, i=ids: self.dock_menu(btn, l, c, i))
            b.add_controller(right_click)
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

    def dock_menu(self, button, label, cmd, ids):
        # Right-click on a dock icon: open another window, or close the app's windows.
        pop = Gtk.Popover()
        pop.add_css_class('start')
        pop.set_parent(button)
        pop.set_position(Gtk.PositionType.TOP)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        head = Gtk.Label(label=label, xalign=0)
        head.add_css_class('menu-head')
        col.append(head)

        def item(text, fn):
            b = Gtk.Button(label=text)
            b.add_css_class('menu-row')
            b.get_child().set_xalign(0)
            b.connect('clicked', lambda *_: (pop.popdown(), fn()))
            col.append(b)

        item('New window', lambda: self.launch(cmd))
        wins = self.windows_of(ids)
        if wins:
            item('Close window' if len(wins) == 1 else f'Close all {len(wins)} windows',
                 lambda: [self.ipc.call('window-rules/close-view', {'id': w['id']}) for w in wins])
        pop.set_child(col)
        pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def on_ipc_event(self):
        # Wayfire sends focus/close events a moment before its view list reflects them, so look again shortly after;
        # coalesce bursts of events into one follow-up.
        self.refresh()
        if not getattr(self, 'refresh_pending', False):
            self.refresh_pending = True

            def later():
                self.refresh_pending = False
                self.refresh()
                return False
            GLib.timeout_add(150, later)
        return False

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

    # ---- volume and network ----------------------------------------------------------------------------------------
    @staticmethod
    def capture(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout
        except (OSError, subprocess.TimeoutExpired):
            return ''

    def poll_status(self):
        # wpctl: "Volume: 0.40" or "Volume: 0.40 [MUTED]"
        out = self.capture(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@']).split()
        if len(out) >= 2:
            try:
                level = round(float(out[1]) * 100)
            except ValueError:
                level = 0
            muted = '[MUTED]' in out
            name = 'muted' if muted or level == 0 else 'low' if level < 34 else 'medium' if level < 67 else 'high'
            self.vol_img.set_from_icon_name(f'audio-volume-{name}-symbolic')
            self.vol_btn.set_tooltip_text(f'Volume {level}%' + (' (muted)' if muted else ''))
            if not self.vol_btn.get_popover().get_visible():
                self.vol_updating = True
                self.vol_scale.set_value(level)
                self.vol_mute.set_active(muted)
                self.vol_updating = False
        else:
            self.vol_img.set_from_icon_name('audio-volume-muted-symbolic')
            self.vol_btn.set_tooltip_text('No sound device')
        # nmcli: TYPE:STATE:CONNECTION per device
        icon, tip = 'network-offline-symbolic', 'Not connected'
        for line in self.capture(['nmcli', '-t', '-f', 'TYPE,STATE,CONNECTION', 'device']).splitlines():
            parts = line.split(':')
            if len(parts) >= 3 and parts[1] == 'connected':
                if parts[0] == 'wifi':
                    icon, tip = 'network-wireless-signal-excellent-symbolic', f'Wi-Fi: {parts[2]}'
                    break
                if parts[0] == 'ethernet':
                    icon, tip = 'network-wired-symbolic', f'Connected: {parts[2]}'
        self.net.set_from_icon_name(icon)
        self.net_btn.set_tooltip_text(tip + ' (click for network settings)')
        return True

    def on_volume(self, scale):
        if not self.vol_updating:
            subprocess.Popen(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', f'{int(scale.get_value())}%'])

    def on_mute(self, btn):
        if not self.vol_updating:
            subprocess.Popen(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '1' if btn.get_active() else '0'])

    def tick_clock(self):
        # Same format as MWX 7 on the web: "Mon, Nov 9 09:51:37".
        t = time.localtime()
        self.clock.set_label(time.strftime('%a, %b ', t) + str(t.tm_mday) + time.strftime(' %H:%M:%S', t))
        return True


if __name__ == '__main__':
    Shell().run(None)
