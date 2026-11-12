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

import gi
import pwd
import re

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as Layer  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = '/usr/share/mwx7/icons'
WF_INI = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'mwx7', 'wayfire.ini')

APP = '/usr/share/mwx7/bin/mwx7-app'  # MWX 7's own apps (the web concept's apps, each in its own window)
SETTINGS = '/usr/share/mwx7/settings/mwx7-settings'
# Pinned dock apps, as on MWX 7 on the web: (label, icon, command, app-ids that count as "this app is running").
PINNED = [
    ('My Computer', 'computer', ['thunar'], ('thunar',)),
    ('Internet', 'browser', ['google-chrome-stable', '--ozone-platform=wayland'], ('google-chrome',)),
    ('Media Player', 'mediaplayer', [APP, 'mediaplayer'], ('mwx7-mediaplayer', 'mediaplayer.html', 'mediaplayer_html')),
    ('Notepad', 'notepad', [APP, 'notepad'], ('mwx7-notepad', 'notepad.html', 'notepad_html')),
    ('Calculator', 'calculator', [APP, 'calculator'], ('mwx7-calculator', 'calculator.html', 'calculator_html')),
    ('Settings', 'settings', [SETTINGS], ('org.mwx7.settings', 'mwx7-settings')),
]
ABOUT = [APP, 'about']
# Start menu, right pane: (label, icon, command); None is a separator. The person's name heads it (their home folder).
PLACES = [
    ('Documents', 'folder-documents', 'DOCUMENTS'), ('Pictures', 'folder-pictures', 'PICTURES'),
    ('Music', 'folder-music', 'MUSIC'), None,
    ('Computer', 'computer', ['thunar', 'computer:///']), ('Settings', 'settings', [SETTINGS]), None,
    ('Search', 'search', 'SEARCH'), ('About MWX 7', 'about', ABOUT),
]
# Log Off ends the Wayfire session, which returns to the MWX 7 logon screen.
POWER_ACTIONS = [('Lock', 'system-lock-screen', ['/usr/share/mwx7/bin/mwx7-lock']),
                 ('Log Off', 'user', ['pkill', '-u', str(os.getuid()), '-x', 'wayfire']),
                 ('Restart', 'logoff', ['systemctl', 'reboot']), ('Shut Down', 'shutdown', ['systemctl', 'poweroff'])]

# Written by mwx7-update-notify when updates are waiting: "<count> <MWX 7 version or ->". Gone when there are none.
UPDATES_FILE = os.path.join(os.environ.get('XDG_RUNTIME_DIR') or '/tmp', 'mwx7-updates')


def pending_updates():
    try:
        count, version = open(UPDATES_FILE).read().split()[:2]
        return int(count), ('' if version == '-' else version)
    except (OSError, ValueError):
        return 0, ''


def power(cmd):
    """Restart and Shut Down offer to install waiting updates first (never on their own): the person chooses."""
    action = {'reboot': 'restart', 'poweroff': 'shut down'}.get(cmd[-1]) if cmd[:1] == ['systemctl'] else None
    count, version = pending_updates()
    if not action or not count:
        subprocess.Popen(cmd)
        return
    dlg = Gtk.Window(title='Updates', modal=True, resizable=False)
    dlg.add_css_class('mwx7-power')
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=18, margin_bottom=16, margin_start=20,
                  margin_end=20)
    what = f'MWX 7 {version}' if version else f'{count} updates'
    title = Gtk.Label(label=f'{what} ready to install', xalign=0)
    title.add_css_class('power-title')
    box.append(title)
    text = Gtk.Label(label=f'Install now and then {action}? The PC restarts to install them, which takes a few minutes; don\'t turn it off.',
                     xalign=0, wrap=True, max_width_chars=50)
    box.append(text)
    btns = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=6)
    cancel = Gtk.Button(label='Cancel')
    plain = Gtk.Button(label=action.capitalize())
    upd = Gtk.Button(label=f'Update and {action}')
    upd.add_css_class('suggested-action')
    for b in (cancel, plain, upd):
        btns.append(b)
    box.append(btns)
    dlg.set_child(box)
    cancel.connect('clicked', lambda *_: dlg.close())
    plain.connect('clicked', lambda *_: (dlg.close(), subprocess.Popen(cmd)))

    def update(*_):
        # The machine restarts into the update screen (systemd offline update) and installs there, outside this
        # session, so there is nothing to show here: the dialog just goes away. pkexec uses MWX 7's update rule.
        dlg.close()
        subprocess.Popen(['pkexec', '/usr/share/mwx7/bin/mwx7-update', 'offline', cmd[-1]], start_new_session=True)
    upd.connect('clicked', update)
    dlg.present()


class Ipc:
    """Wayfire IPC: 4-byte little-endian length, then a JSON body; one request at a time per socket."""

    def __init__(self, timeout=1.0):
        self.path = os.environ.get('WAYFIRE_SOCKET', '')
        self.lock = threading.Lock()
        self.sock = None
        self.timeout = timeout

    def _connect(self, timeout=-1):
        timeout = self.timeout if timeout == -1 else timeout
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Requests from the main thread must never wait long: a missing answer is better than a frozen bar.
        s.settimeout(timeout)
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
            except (OSError, ValueError):
                # Timed out or broken: drop the socket, since a late answer would be read as the next reply.
                if self.sock is not None:
                    self.sock.close()
                self.sock = None
                return None

    def watch(self, on_event):
        """Blocking loop on its own socket; reconnects if Wayfire restarts."""
        while True:
            try:
                s = self._connect(timeout=None)  # the event stream may be quiet for hours
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
    'chromium': 'browser', 'mwx7-settings': 'settings',
}
# Friendly names for apps whose package names mean nothing to a person.
DISPLAY_NAMES = {'thunar': 'Files', 'org.codeberg.dnkl.foot': 'Terminal', 'foot': 'Terminal'}
# Helpers and duplicates that make no sense as Start menu entries.
HIDDEN_APPS = ('chromium', 'footclient', 'foot-server', 'org.codeberg.dnkl.footclient', 'org.codeberg.dnkl.foot-server', 'thunar-settings', 'thunar-bulk-rename', 'xfce4-', 'nm-connection',
               'org.freedesktop.Xwayland', 'debian-', 'gcr-', 'polkit', 'agreety', 'vim', 'htop', 'python3')


def icon_image(name):
    """An MWX 7 icon when we drew one, otherwise the icon of that name from the system theme."""
    path = os.path.join(ICONS, name + '.png')
    return Gtk.Image.new_from_file(path) if os.path.exists(path) else Gtk.Image.new_from_icon_name(name)


def app_name(app):
    aid = (app.get_id() or '').removesuffix('.desktop').lower()
    return DISPLAY_NAMES.get(aid, app.get_display_name())


def app_for_id(aid):
    """The menu entry of a window's app id: by desktop file or window class, and MWX 7's web apps by their page
    (Chrome names their windows after it: chrome-..._notepad.html-...)."""
    if not aid:
        return None
    m = re.search(r'([a-z0-9-]+)[._]html', aid)
    want = {f'mwx7-{m.group(1)}'} if m else set()
    for a in Gio.AppInfo.get_all():
        did = (a.get_id() or '').removesuffix('.desktop').lower()
        if aid in (did, (a.get_startup_wm_class() or '').lower()) or did in want:
            return a
    return None


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
    """The MWX 7 Start menu, as on the web (Windows 7's): the account on the glass, programs and search on the white
    left pane, places on the dark glass right pane, Log off and Shut down underneath. Opens above the dock orb."""

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.add_css_class('startmenu')
        self.set_has_arrow(False)
        self.set_position(Gtk.PositionType.TOP)
        self.set_offset(0, -6)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # Account tile on the glass.
        head = Gtk.Box(spacing=12)
        head.add_css_class('sm-head')
        # Scale the photo up front: a Gtk.Picture asks for its full natural size and ignores size requests.
        try:
            own = f'/var/lib/AccountsService/icons/{pwd.getpwuid(os.getuid()).pw_name}'
            path = own if os.path.exists(own) else '/usr/share/mwx7/avatars/03-guitar.jpg'
            buf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 48, 48, False)
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
        body = Gtk.Box()
        body.add_css_class('sm-body')
        # Left: every installed app, and search.
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.add_css_class('sm-left')
        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class('sm-list')
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(True)
        self.listbox.connect('row-activated', self.on_row)
        self.listbox.set_filter_func(self.filter_row)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(372)
        scroll.set_max_content_height(372)
        scroll.set_vexpand(True)
        scroll.set_child(self.listbox)
        left.append(scroll)
        self.search = Gtk.SearchEntry()
        self.search.add_css_class('sm-search')
        self.search.set_placeholder_text('Search programs and files')
        self.search.connect('search-changed', lambda *_: self.listbox.invalidate_filter())
        self.search.connect('activate', self.on_enter)
        left.append(self.search)
        body.append(left)
        # Right: the person's folders and the system's places.
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        right.add_css_class('sm-right')
        right.append(self.place_row(user_display_name(), None, ['thunar', GLib.get_home_dir()], avatar=True))
        dirs = {'DOCUMENTS': GLib.UserDirectory.DIRECTORY_DOCUMENTS, 'PICTURES': GLib.UserDirectory.DIRECTORY_PICTURES,
                'MUSIC': GLib.UserDirectory.DIRECTORY_MUSIC}
        for entry in PLACES:
            if entry is None:
                sep = Gtk.Box()
                sep.add_css_class('sm-sep')
                right.append(sep)
                continue
            label, icon, cmd = entry
            if isinstance(cmd, str) and cmd in dirs:
                cmd = ['thunar', GLib.get_user_special_dir(dirs[cmd]) or GLib.get_home_dir()]
            right.append(self.place_row(label, icon, cmd))
        body.append(right)
        root.append(body)
        # Log off and Shut down (with the other power choices behind the arrow), bottom right as on Windows 7.
        foot = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        foot.add_css_class('sm-foot')
        logoff = self.power_button('Log off', 'logoff', ['pkill', '-u', str(os.getuid()), '-x', 'wayfire'])
        foot.append(logoff)
        shut = Gtk.Box()
        shut.add_css_class('sm-split')
        shut.append(self.power_button('Shut down', 'shutdown', ['systemctl', 'poweroff']))
        more = Gtk.MenuButton()
        more.add_css_class('sm-more')
        more.set_icon_name('pan-end-symbolic')
        more_pop = Gtk.Popover()
        more_pop.add_css_class('start')
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for label, icon, cmd in POWER_ACTIONS:
            col.append(shell.menu_row(label, icon, lambda *_a, c=cmd: (more_pop.popdown(), self.popdown(), power(c))))
        more_pop.set_child(col)
        more.set_popover(more_pop)
        shut.append(more)
        foot.append(shut)
        root.append(foot)
        self.set_child(root)
        self.connect('show', self.on_show)
        self.monitor = Gio.AppInfoMonitor.get()
        self.monitor.connect('changed', lambda *_: self.fill())
        self.fill()

    def place_row(self, label, icon, cmd, avatar=False):
        b = Gtk.Button()
        b.add_css_class('sm-place')
        row = Gtk.Box(spacing=10)
        if avatar:
            img = Gtk.Box()
            img.set_size_request(0, 22)
        else:
            img = icon_image(icon)
            img.set_pixel_size(22)
        row.append(img)
        row.append(Gtk.Label(label=label, xalign=0))
        b.set_child(row)

        def go(*_):
            if cmd == 'SEARCH':
                self.search.grab_focus()
                return
            self.popdown()
            self.shell.launch(cmd)
        b.connect('clicked', go)
        return b

    def power_button(self, label, icon, cmd):
        b = Gtk.Button()
        b.add_css_class('sm-power')
        row = Gtk.Box(spacing=6)
        img = icon_image(icon)
        img.set_pixel_size(18)
        row.append(img)
        row.append(Gtk.Label(label=label))
        b.set_child(row)
        b.connect('clicked', lambda *_: (self.popdown(), power(cmd)))
        return b

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
        if getattr(self, 'bar', None):  # a second start of the shell only activates this one: never a second bar
            return
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(HERE, 'style.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        # The bar and dock glass take the window colour chosen in Settings, and follow it when it changes.
        self.tint = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.tint, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.apply_tint()
        self.tint_monitor = Gio.File.new_for_path(WF_INI).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.tint_monitor.connect('changed', lambda *_a: GLib.timeout_add(150, lambda: self.apply_tint() and False))
        self.bar = self.build_bar()
        self.dock = self.build_dock()
        self.bar.present()
        self.dock.present()
        GLib.timeout_add(200, self.tick_clock)
        threading.Thread(target=self.ipc.watch, args=(lambda ev: GLib.idle_add(self.on_ipc_event),), daemon=True).start()
        self.refresh()
        # For screenshots of the Start menu in automated checks (no pointer there): MWX7_SHELL_OPEN=start.
        what = os.environ.get('MWX7_SHELL_OPEN')
        if what == 'search':
            GLib.timeout_add(1500, lambda: self.open_search() and False)
        if what in ('start', 'calendar', 'system'):
            btn = {'start': lambda: self.start_button, 'calendar': lambda: self.clock_btn,
                   'system': lambda: self.orb_button}[what]()
            GLib.timeout_add(1500, lambda: btn.popup() and False)

    def apply_tint(self):
        """The bar, the dock and the Start menu's glass take the window colour and intensity chosen in Settings, the
        same recipe as the frames (tint over Wayfire's blur, top sheen, diagonal light streaks)."""
        rgb, a = (30, 100, 220), 0.08
        try:
            m = re.search(r'^active_color\s*=\s*\\?#([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?', open(WF_INI).read(), re.M)
            if m:
                rgb = tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
                a = int(m.group(2), 16) / 255 if m.group(2) else 0.46
        except OSError:
            pass
        r, g, b = rgb
        streaks = ('linear-gradient(118deg, rgba(255,255,255,0) 22%, rgba(255,255,255,0.1) 22.5%, rgba(255,255,255,0.1) 24%, '
                   'rgba(255,255,255,0) 25%, rgba(255,255,255,0) 46%, rgba(255,255,255,0.07) 46.5%, '
                   'rgba(255,255,255,0.07) 50%, rgba(255,255,255,0) 51%, rgba(255,255,255,0) 70%, '
                   'rgba(255,255,255,0.05) 70.5%, rgba(255,255,255,0.05) 71.5%, rgba(255,255,255,0) 72%)')
        sheen = 'linear-gradient(to bottom, rgba(255,255,255,0.3), rgba(255,255,255,0.06) 34px, rgba(255,255,255,0) 70px)'
        tint = f'linear-gradient(to bottom, rgba({r},{g},{b},{a:.3f}), rgba({r},{g},{b},{a * 0.86:.3f}))'
        # The Start menu's glass is a little denser than the frames so its text stays readable over any wallpaper.
        menu = f'linear-gradient(rgba({r},{g},{b},{max(a, 0.3):.3f}), rgba({r},{g},{b},{max(a, 0.3) * 0.9:.3f}))'
        self.tint.load_from_data(
            (f'window.bar .bar-plate {{ background: {streaks}, {sheen}, {tint}; }}\n'
             f'.dock-shelf {{ background: {streaks}, {sheen}, {tint}; }}\n'
             f'popover.startmenu > contents {{ background: {streaks}, {sheen}, {menu}, '
             f'linear-gradient(rgba(20,40,70,0.35), rgba(20,40,70,0.35)); }}\n').encode())
        return False

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
        # Its menus (orb, app name, clock) need focus while open, or GTK closes them before a click lands.
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.ON_DEMAND)
        box = Gtk.CenterBox()
        left = Gtk.Box(spacing=8)
        orb = Gtk.MenuButton()
        orb.add_css_class('orb')
        orb_img = Gtk.Image.new_from_file(os.path.join(ICONS, 'orb.png'))
        orb_img.set_pixel_size(22)
        orb.set_child(orb_img)
        orb.set_popover(self.build_system_menu())
        self.orb_button = orb
        left.append(orb)
        # The focused app's name, a menu as on the web: Minimize, Full Screen, Close (Personalize and About on the desktop).
        self.title = Gtk.Label(label='Desktop')
        self.title.add_css_class('app-title')
        app_btn = Gtk.MenuButton()
        app_btn.add_css_class('app-btn')
        app_btn.set_child(self.title)
        self.app_pop = Gtk.Popover()
        self.app_pop.add_css_class('sysmenu')
        self.app_pop.set_has_arrow(False)
        self.app_pop.connect('show', lambda *_: self.fill_app_menu())
        app_btn.set_popover(self.app_pop)
        left.append(app_btn)
        right = Gtk.Box(spacing=10)
        # Updates waiting: a quiet icon (no pop-ups); click for Settings -> Updates. Shut Down and Restart also offer them.
        self.upd_btn = Gtk.Button(visible=False)
        self.upd_btn.add_css_class('flat-ico')
        self.upd_btn.set_child(Gtk.Image.new_from_icon_name('software-update-available-symbolic'))
        self.upd_btn.connect('clicked', lambda *_: self.launch(['/usr/share/mwx7/settings/mwx7-settings', '--updates']))
        right.append(self.upd_btn)
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
        # Search (the Start menu's search box) and all windows side by side, as in the web concept's menu bar.
        find = Gtk.Button()
        find.add_css_class('flat-ico')
        find.set_tooltip_text('Search')
        find.set_child(self.tray_icon('search'))
        find.connect('clicked', lambda *_: self.open_search())
        right.append(find)
        views_btn = Gtk.Button()
        views_btn.add_css_class('flat-ico')
        views_btn.set_tooltip_text('All windows')
        views_btn.set_child(Gtk.Image.new_from_icon_name('view-grid-symbolic'))
        views_btn.connect('clicked', lambda *_: self.act('scale/toggle'))
        right.append(views_btn)
        show_desktop = Gtk.Button()
        show_desktop.add_css_class('flat-ico')
        show_desktop.set_child(Gtk.Image.new_from_file(os.path.join(ICONS, '16', 'desktop.png')) if os.path.exists(
            os.path.join(ICONS, '16', 'desktop.png')) else Gtk.Image.new_from_icon_name('user-desktop'))
        show_desktop.set_tooltip_text('Show desktop')
        show_desktop.connect('clicked', lambda *_: self.act('wm-actions/toggle_showdesktop'))
        right.append(show_desktop)
        # The clock opens the web concept's calendar flyout: the time large, the date, the month, Today.
        self.clock = Gtk.Label()
        self.clock.add_css_class('clock')
        clock_btn = Gtk.MenuButton()
        clock_btn.add_css_class('clock-btn')
        clock_btn.set_child(self.clock)
        clock_btn.set_popover(self.build_calendar())
        self.clock_btn = clock_btn
        right.append(clock_btn)
        box.set_start_widget(left)
        box.set_end_widget(right)
        box.set_hexpand(True)
        # A plain Box carries the glass: it paints its CSS background reliably on every GTK theme.
        plate = Gtk.Box()
        plate.add_css_class('bar-plate')
        plate.append(box)
        w.set_child(plate)
        return w

    @staticmethod
    def tray_icon(name):
        img = icon_image(name)
        img.set_pixel_size(16)
        return img

    def open_search(self):
        """The web concept's search: a glass box near the top of the screen over a lightly dimmed desktop; apps and
        documents as you type, Enter or a click opens, Escape or a click outside closes."""
        if getattr(self, 'search_win', None):
            self.search_win.present()
            return
        w = Gtk.Window(application=self)
        w.add_css_class('search-overlay')
        Layer.init_for_window(w)
        Layer.set_layer(w, Layer.Layer.OVERLAY)
        Layer.set_namespace(w, 'mwx7-search')
        for e in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
            Layer.set_anchor(w, e, True)
        Layer.set_exclusive_zone(w, -1)
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.EXCLUSIVE)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER, valign=Gtk.Align.START)
        box.add_css_class('sp-box')
        bar = Gtk.Box(spacing=10)
        bar.add_css_class('sp-bar')
        bar.append(icon_image('search'))
        bar.get_first_child().set_pixel_size(22)
        entry = Gtk.Text(hexpand=True)
        entry.add_css_class('sp-input')
        entry.set_placeholder_text('Search apps and documents')
        bar.append(entry)
        box.append(bar)
        results = Gtk.ListBox()
        results.add_css_class('sp-results')
        results.set_selection_mode(Gtk.SelectionMode.BROWSE)
        results.set_activate_on_single_click(True)
        results.set_visible(False)
        box.append(results)
        w.set_child(box)
        self.search_win = w
        docs = []

        def scan():
            # Documents are indexed once per search, off the main thread; three levels deep is where people keep files.
            home = GLib.get_home_dir()
            for top in ('Desktop', 'Documents', 'Downloads', 'Music', 'Pictures', 'Videos'):
                base = os.path.join(home, top)
                for root, dirs, files in os.walk(base):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    if root[len(base):].count(os.sep) >= 3:
                        dirs[:] = []
                    for f in files:
                        if not f.startswith('.'):
                            docs.append(os.path.join(root, f))
                    if len(docs) > 4000:
                        return
        threading.Thread(target=scan, daemon=True).start()

        def close(*_):
            if self.search_win:
                self.search_win.destroy()
                self.search_win = None

        def score(q, name):
            n = name.lower()
            if n.startswith(q):
                return 4
            if any(word.startswith(q) for word in re.split(r'[\s._-]+', n)):
                return 3
            return 2 if q in n else 0

        def row(icon, title, sub, run):
            r = Gtk.ListBoxRow()
            r.run = run
            b = Gtk.Box(spacing=10)
            b.add_css_class('sp-row')
            icon.set_pixel_size(24)
            b.append(icon)
            t = Gtk.Label(label=title, xalign=0)
            t.add_css_class('sp-row-title')
            b.append(t)
            st = Gtk.Label(label=sub, xalign=0, hexpand=True, ellipsize=3)
            st.add_css_class('sp-row-sub')
            b.append(st)
            r.set_child(b)
            return r

        def group(title):
            r = Gtk.ListBoxRow(selectable=False, activatable=False)
            lab = Gtk.Label(label=title, xalign=0)
            lab.add_css_class('sp-group')
            r.set_child(lab)
            return r

        def update(*_):
            while (child := results.get_row_at_index(0)) is not None:
                results.remove(child)
            q = entry.get_text().strip().lower()
            if not q:
                results.set_visible(False)
                return
            apps = sorted(((score(q, app_name(a)), app_name(a), a) for a in Gio.AppInfo.get_all()
                           if a.should_show() and not (a.get_id() or '').lower().startswith(HIDDEN_APPS)),
                          key=lambda t: (-t[0], t[1].lower()))
            apps = [t for t in apps if t[0]][:6]
            found = sorted(((score(q, os.path.basename(d)), d) for d in list(docs)), key=lambda t: -t[0])
            found = [t for t in found if t[0]][:8]
            first = None
            if apps:
                results.append(group('Applications'))
                for _sc, name, a in apps:
                    r = row(app_icon_widget(a, 24), name, a.get_description() or '', lambda a=a: a.launch([], None))
                    results.append(r)
                    first = first or r
            if found:
                results.append(group('Documents'))
                for _sc, d in found:
                    f = Gio.File.new_for_path(d)
                    try:
                        gicon = f.query_info('standard::icon', Gio.FileQueryInfoFlags.NONE, None).get_icon()
                        img = Gtk.Image.new_from_gicon(gicon)
                    except GLib.Error:
                        img = Gtk.Image.new_from_icon_name('text-x-generic')
                    r = row(img, os.path.basename(d), os.path.dirname(d).replace(GLib.get_home_dir(), '~'),
                            lambda u=f.get_uri(): Gio.AppInfo.launch_default_for_uri(u, None))
                    results.append(r)
                    first = first or r
            if first is None:
                empty = Gtk.ListBoxRow(selectable=False, activatable=False)
                lab = Gtk.Label(label=f'No results for “{entry.get_text().strip()}”')
                lab.add_css_class('sp-empty')
                empty.set_child(lab)
                results.append(empty)
            else:
                results.select_row(first)
            results.set_visible(True)

        def go(row_):
            if row_ is not None and getattr(row_, 'run', None):
                close()
                try:
                    row_.run()
                except GLib.Error:
                    pass
        entry.connect('changed', update)
        entry.connect('activate', lambda *_: go(results.get_selected_row()))
        results.connect('row-activated', lambda _l, r: go(r))
        keys = Gtk.EventControllerKey()

        def key(_c, keyval, _code, _state):
            if keyval == Gdk.KEY_Escape:
                close()
                return True
            if keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
                rows, i = [], 0
                while (r := results.get_row_at_index(i)) is not None:
                    if getattr(r, 'run', None):
                        rows.append(r)
                    i += 1
                if rows:
                    cur = results.get_selected_row()
                    k = rows.index(cur) if cur in rows else -1
                    k = min(len(rows) - 1, k + 1) if keyval == Gdk.KEY_Down else max(0, k - 1)
                    results.select_row(rows[k])
                return True
            return False
        keys.connect('key-pressed', key)
        w.add_controller(keys)
        outside = Gtk.GestureClick()
        outside.connect('pressed', lambda g, _n, x, y: close() if not box.contains(*w.translate_coordinates(box, x, y) or (0, 0)) else None)
        w.add_controller(outside)
        w.present()
        entry.grab_focus()
        if os.environ.get('MWX7_SHELL_QUERY'):  # automated checks: a query typed in advance
            GLib.timeout_add(1500, lambda: entry.set_text(os.environ['MWX7_SHELL_QUERY']) and False)

    def build_calendar(self):
        pop = Gtk.Popover()
        pop.add_css_class('calflyout')
        pop.set_has_arrow(False)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        head.add_css_class('cal-head')
        big = Gtk.Label(xalign=0)
        big.add_css_class('cal-time')
        date = Gtk.Label(xalign=0)
        date.add_css_class('cal-date')
        head.append(big)
        head.append(date)
        col.append(head)
        cal = Gtk.Calendar()
        cal.add_css_class('cal-month')
        col.append(cal)
        foot = Gtk.Box()
        foot.add_css_class('cal-foot')
        today = Gtk.Button(label='Today')
        today.add_css_class('cal-link')
        today.connect('clicked', lambda *_: cal.select_day(GLib.DateTime.new_now_local()))
        foot.append(today)
        spacer = Gtk.Box(hexpand=True)
        foot.append(spacer)
        change = Gtk.Button(label='Change date and time settings…')
        change.add_css_class('cal-link')
        change.connect('clicked', lambda *_: (pop.popdown(), self.launch([SETTINGS, '--page', 'datetime'])))
        foot.append(change)
        col.append(foot)
        pop.set_child(col)

        def tick():
            if not pop.get_visible():
                return False
            t = time.localtime()
            big.set_label(time.strftime('%H:%M:%S', t))
            date.set_label(time.strftime('%A, %B ', t) + str(t.tm_mday) + time.strftime(', %Y', t))
            return True

        def shown(*_):
            cal.select_day(GLib.DateTime.new_now_local())
            tick()
            GLib.timeout_add(500, tick)
        pop.connect('show', shown)
        return pop

    def build_system_menu(self):
        """The orb in the bar: the web concept's (macOS-like) system menu, text only."""
        pop = Gtk.Popover()
        pop.add_css_class('sysmenu')
        pop.set_has_arrow(False)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def item(label, fn):
            b = Gtk.Button(label=label)
            b.add_css_class('sys-item')
            b.get_child().set_xalign(0)
            b.connect('clicked', lambda *_: (pop.popdown(), fn()))
            col.append(b)

        def sep():
            s = Gtk.Box()
            s.add_css_class('sys-sep')
            col.append(s)
        item('About MWX 7', lambda: self.launch(ABOUT))
        sep()
        item('Settings…', lambda: self.launch([SETTINGS]))
        item('Search', self.open_search)
        item('Overview', lambda: self.act('scale/toggle'))
        sep()
        item('Lock', lambda: power(POWER_ACTIONS[0][2]))
        item('Log Off…', lambda: power(POWER_ACTIONS[1][2]))
        item('Restart…', lambda: power(POWER_ACTIONS[2][2]))
        item('Shut Down…', lambda: power(POWER_ACTIONS[3][2]))
        pop.set_child(col)
        return pop

    def menu_row(self, label, icon, on_click):
        b = Gtk.Button()
        b.add_css_class('menu-row')
        row = Gtk.Box(spacing=10)
        img = icon_image(icon)
        img.set_pixel_size(32)
        row.append(img)
        row.append(Gtk.Label(label=label, xalign=0))
        b.set_child(row)
        b.connect('clicked', on_click)
        return b

    def build_dock(self):
        # Flush with the bottom edge like MWX 7 on the web: the same glass as the window frames, top corners rounded.
        w = self.layer_window('dock', (Layer.Edge.BOTTOM,), 0)
        # The search box in the Start menu needs the keyboard; on demand means only while it has focus.
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.ON_DEMAND)
        shelf = Gtk.Box(spacing=5)
        shelf.add_css_class('dock-shelf')
        self.dock_items = []
        start = Gtk.MenuButton()
        start.add_css_class('dock-orb')
        start.set_tooltip_text('Start')
        orb_big = Gtk.Image.new_from_file(os.path.join(ICONS, 'orb.png'))
        orb_big.set_pixel_size(56)
        start.set_child(orb_big)
        self.start_menu = StartMenu(self)
        start.set_popover(self.start_menu)
        self.start_button = start
        shelf.append(start)
        shelf.append(self.dock_sep())
        # Pinned apps, then apps that run without being pinned (while they have a window).
        self.dock_box = Gtk.Box(spacing=5)
        shelf.append(self.dock_box)
        for label, icon, cmd, ids in PINNED:
            img = Gtk.Image.new_from_file(os.path.join(ICONS, icon + '.png'))
            self.add_dock_item(label, img, lambda c=cmd: self.launch(c), ids)
        self.dock_running = {}
        shelf.append(self.dock_sep())
        trash = Gtk.Button()
        trash.add_css_class('dock-item')
        trash.set_tooltip_text('Trash')
        self.trash_img = Gtk.Image()
        self.trash_img.set_pixel_size(48)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        v.append(self.trash_img)
        dot = Gtk.Box()
        dot.add_css_class('run-dot')
        v.append(dot)
        trash.set_child(v)
        trash.connect('clicked', lambda *_: self.launch(['thunar', 'trash:///']))
        self.hover_zoom(trash, self.trash_img)
        shelf.append(trash)
        self.update_trash()
        # Full or empty, as on the web: watched rather than polled.
        try:
            tdir = Gio.File.new_for_path(os.path.join(GLib.get_user_data_dir(), 'Trash', 'files'))
            tdir.make_directory_with_parents(None)
        except GLib.Error:
            pass
        self.trash_mon = tdir.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.trash_mon.connect('changed', lambda *_: GLib.timeout_add(200, lambda: self.update_trash() and False))
        w.set_child(shelf)
        return w

    def update_trash(self):
        d = os.path.join(GLib.get_user_data_dir(), 'Trash', 'files')
        try:
            full = bool(os.listdir(d))
        except OSError:
            full = False
        self.trash_img.set_from_file(os.path.join(ICONS, 'trash-full.png' if full else 'trash-empty.png'))
        return False

    @staticmethod
    def dock_sep():
        sep = Gtk.Box()
        sep.add_css_class('dock-sep')
        return sep

    @staticmethod
    def hover_zoom(button, img):
        """The pointed-at icon grows a little, like the web dock's magnification (inside the shelf: the glass behind
        the dock is blurred as one rectangle, so nothing may stick out of it)."""
        motion = Gtk.EventControllerMotion()
        motion.connect('enter', lambda *_: img.set_pixel_size(56))
        motion.connect('leave', lambda *_: img.set_pixel_size(48))
        button.add_controller(motion)

    def add_dock_item(self, label, img, launch, ids):
        b = Gtk.Button()
        b.add_css_class('dock-item')
        b.set_tooltip_text(label)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.END)
        img.set_pixel_size(48)
        dot = Gtk.Box()
        dot.add_css_class('run-dot')
        dot.set_halign(Gtk.Align.CENTER)
        v.append(img)
        v.append(dot)
        b.set_child(v)
        b.connect('clicked', lambda *_: self.dock_click(launch, ids))
        self.hover_zoom(b, img)
        self.peek_on_hover(b, label, ids)
        right_click = Gtk.GestureClick(button=3)
        # Capture phase: the button's own click handling would otherwise swallow the secondary button.
        right_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        right_click.connect('pressed', lambda *_a: self.dock_menu(b, label, launch, ids))
        b.add_controller(right_click)
        self.dock_box.append(b)
        self.dock_items.append((b, ids))
        return b

    def sync_running_apps(self):
        """Give every running app without a pinned icon its own dock icon, and take it away when its last window closes."""
        pinned = tuple(i for _b, ids in self.dock_items[:len(PINNED)] for i in ids)
        # Dialogs (windows with a parent) belong to their app's icon, not one of their own.
        open_ids = {(v.get('app-id') or '').lower() for v in apps_windows(self.views) if v.get('parent', -1) in (-1, None)}
        open_ids = {a for a in open_ids if a and not any(p in a for p in pinned)}
        for aid in list(self.dock_running):
            if aid not in open_ids:
                b = self.dock_running.pop(aid)
                self.dock_items = [(x, ids) for x, ids in self.dock_items if x is not b]
                self.dock_box.remove(b)
                # A window never shrinks by itself in GTK 4; ask for the smallest size so the dock fits its icons again.
                self.dock.set_default_size(1, 1)
        for aid in sorted(open_ids - set(self.dock_running)):
            app = app_for_id(aid)
            if app:
                label, img, launch = app_name(app), app_icon_widget(app, 48), lambda a=app: a.launch([], None)
            else:
                # A window whose app has no menu entry (a helper dialog): still reachable, just no way to start another.
                label, img, launch = aid, Gtk.Image.new_from_icon_name('application-x-executable'), None
            self.dock_running[aid] = self.add_dock_item(label, img, launch, (aid,))

    # ---- behaviour ------------------------------------------------------------------------------------------------
    @staticmethod
    def launch(cmd):
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def windows_of(self, ids):
        # Substrings: Chrome names app windows after their page (chrome-..._notepad.html-...).
        return [v for v in apps_windows(self.views) if any(i in (v.get('app-id') or '').lower() for i in ids)]

    def dock_click(self, launch, ids):
        wins = self.windows_of(ids)
        if not wins:
            if launch:
                launch()
            return
        w = wins[0]
        if w.get('activated') and not w.get('minimized'):
            self.act('wm-actions/set-minimized', {'view_id': w['id'], 'state': True})
        else:
            if w.get('minimized'):
                self.act('wm-actions/set-minimized', {'view_id': w['id'], 'state': False})
            self.act('window-rules/focus-view', {'id': w['id']})

    def peek_on_hover(self, button, label, ids):
        """Aero Peek, as on the web: resting the pointer on a running app's dock icon lists its windows above it
        (pick one to bring it forward). Shown after a short pause so passing over the dock opens nothing."""
        state = {'timer': 0, 'pop': None}

        def close():
            if state['timer']:
                GLib.source_remove(state['timer'])
                state['timer'] = 0
            if state['pop']:
                state['pop'].popdown()

        def show():
            state['timer'] = 0
            wins = self.windows_of(ids)
            if not wins:
                return False
            pop = Gtk.Popover()
            pop.add_css_class('peek')
            pop.set_has_arrow(False)
            pop.set_autohide(False)
            pop.set_parent(button)
            pop.set_position(Gtk.PositionType.TOP)
            pop.set_offset(0, -6)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            head = Gtk.Label(label=label, xalign=0)
            head.add_css_class('peek-head')
            col.append(head)
            for w in wins:
                b = Gtk.Button()
                b.add_css_class('peek-item')
                row = Gtk.Box(spacing=8)
                t = Gtk.Label(label=(w.get('title') or label)[:60], xalign=0, hexpand=True)
                t.set_ellipsize(3)  # end
                row.append(t)
                if w.get('minimized'):
                    m = Gtk.Label(label='minimized')
                    m.add_css_class('peek-min')
                    row.append(m)
                b.set_child(row)

                def pick(_b, v=w):
                    close()
                    if v.get('minimized'):
                        self.act('wm-actions/set-minimized', {'view_id': v['id'], 'state': False})
                    self.act('window-rules/focus-view', {'id': v['id']})
                b.connect('clicked', pick)
                col.append(b)
            hover = Gtk.EventControllerMotion()
            hover.connect('enter', lambda *_: state['timer'] and (GLib.source_remove(state['timer']),
                                                                  state.update(timer=0)))
            hover.connect('leave', lambda *_: leave())
            col.add_controller(hover)
            pop.set_child(col)
            pop.connect('closed', lambda p: (GLib.idle_add(p.unparent), state.update(pop=None)))
            state['pop'] = pop
            # The list already names the app: no tooltip on top of it while it is open.
            button.set_has_tooltip(False)
            pop.connect('closed', lambda *_: button.set_has_tooltip(True))
            pop.popup()
            return False

        def enter(*_):
            if state['pop'] is None and not state['timer']:
                state['timer'] = GLib.timeout_add(450, show)

        def leave(*_):
            # A moment to move from the icon onto the list without it closing.
            if state['timer']:
                GLib.source_remove(state['timer'])
            state['timer'] = GLib.timeout_add(350, lambda: (close(), False)[1])
        motion = Gtk.EventControllerMotion()
        motion.connect('enter', enter)
        motion.connect('leave', leave)
        button.add_controller(motion)
        button.connect('clicked', lambda *_: close())

    def dock_menu(self, button, label, launch, ids):
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

        if launch:
            item('New window', launch)
        wins = self.windows_of(ids)
        if wins:
            item('Close window' if len(wins) == 1 else f'Close all {len(wins)} windows',
                 lambda: [self.act('window-rules/close-view', {'id': w['id']}) for w in wins])
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
        """Asks Wayfire for its windows off the main thread (a busy or slow machine can take seconds to answer, and
        with the old 1 s limit on the main thread the dock and the bar simply never learned about any window), then
        updates the dock and the bar on the main thread. One request at a time; a request during one runs once after."""
        if getattr(self, 'refreshing', False):
            self.refresh_again = True
            return False
        self.refreshing, self.refresh_again = True, False
        if not hasattr(self, 'list_ipc'):
            self.list_ipc = Ipc(timeout=8.0)

        def work():
            views = self.list_ipc.call('window-rules/list-views')
            GLib.idle_add(self.apply_views, views)
        threading.Thread(target=work, daemon=True).start()
        return False

    def apply_views(self, views):
        self.refreshing = False
        if self.refresh_again:
            GLib.idle_add(self.refresh)
        if not isinstance(views, list):
            return False  # no answer this time: keep showing what was last known
        self.views = views
        self.sync_running_apps()
        for b, ids in self.dock_items:
            if self.windows_of(ids):
                b.add_css_class('running')
            else:
                b.remove_css_class('running')
        self.send_minimize_hints()
        self.send_icons()
        focused = next((v for v in apps_windows(self.views) if v.get('activated') and not v.get('minimized')), None)
        self.focused_view = focused
        self.title.set_label(self.app_label(focused) if focused else 'Desktop')
        return False

    def fill_app_menu(self):
        pop, v = self.app_pop, getattr(self, 'focused_view', None)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def item(label, fn):
            b = Gtk.Button(label=label)
            b.add_css_class('sys-item')
            b.get_child().set_xalign(0)
            b.connect('clicked', lambda *_: (pop.popdown(), fn()))
            col.append(b)

        def sep():
            line = Gtk.Box()
            line.add_css_class('sys-sep')
            col.append(line)
        if v:
            name, vid = self.app_label(v), v['id']
            item('Minimize', lambda: self.act('wm-actions/set-minimized', {'view_id': vid, 'state': True}))
            item('Exit Full Screen' if v.get('maximized') or v.get('tiled-edges') == 15 else 'Full Screen',
                 lambda: self.act('mwx7/toggle-maximize', {'id': vid}))
            sep()
            item(f'Close {name}', lambda: self.act('window-rules/close-view', {'id': vid}))
        else:
            item('Personalize…', lambda: self.launch([SETTINGS, '--page', 'themes']))
            item('About MWX 7', lambda: self.launch(ABOUT))
        pop.set_child(col)

    def app_label(self, view):
        """The focused app's name, as the web concept's menu bar shows it (\"My Computer\", \"Notepad\")."""
        aid = (view.get('app-id') or '').lower()
        for label, _icon, _cmd, ids in PINNED:
            if any(i in aid for i in ids):
                return label
        app = app_for_id(aid)
        return app_name(app) if app else (view.get('title') or aid)[:40]

    def act(self, method, data=None):
        """Tells Wayfire to do something (focus, minimize, close, overview...) from a worker thread, in order, with
        time to answer: on a busy PC a one-second limit on the main thread silently dropped dock clicks."""
        if not hasattr(self, 'act_ipc'):
            import queue
            self.act_ipc, self.act_queue = Ipc(timeout=8.0), queue.Queue()

            def worker():
                while True:
                    m, d = self.act_queue.get()
                    self.act_ipc.call(m, d)
            threading.Thread(target=worker, daemon=True).start()
        self.act_queue.put((method, data))

    def icon_path(self, aid):
        """A PNG for a window's title bar: MWX 7's own picture for its apps, else the app's menu icon if it is a PNG
        (the frames draw PNGs only)."""
        for _label, icon, _cmd, ids in PINNED:
            if any(i in aid for i in ids):
                return os.path.join(ICONS, icon + '.png')
        for key, name in APP_ICONS.items():
            if aid.startswith(key):
                return os.path.join(ICONS, name + '.png')
        app = app_for_id(aid)
        gicon = app.get_icon() if app else None
        if gicon is None:
            return ''
        if isinstance(gicon, Gio.FileIcon):
            path = gicon.get_file().get_path() or ''
        else:
            found = Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).lookup_by_gicon(
                gicon, 32, 1, Gtk.TextDirection.NONE, 0)
            f = found.get_file() if found else None
            path = (f.get_path() if f else '') or ''
        return path if path.endswith('.png') else ''

    def send_icons(self):
        """Each window's app icon to its frame (once per window)."""
        sent = getattr(self, 'icons_sent', {})
        live = {}
        for v in apps_windows(self.views):
            vid = v.get('id')
            if vid in sent:
                live[vid] = sent[vid]
                continue
            path = self.icon_path((v.get('app-id') or '').lower())
            if path:
                self.act('mwx7/set-icon', {'id': vid, 'path': path})
            live[vid] = path
        self.icons_sent = live

    def send_minimize_hints(self):
        """Tell the compositor where each window's dock icon is, so minimize pours the window into it (genie)."""
        dock = next((v for v in self.views if v.get('app-id') == 'mwx7-dock'), None)
        geo = (dock or {}).get('geometry') or (dock or {}).get('bbox')
        if not geo:
            return
        sent = getattr(self, 'hints', {})
        live = {}
        for v in apps_windows(self.views):
            app = (v.get('app-id') or '').lower()
            # Windows without a dock icon pour into the Start orb.
            button = next((b for b, ids in self.dock_items if app.startswith(ids)), self.dock_box.get_first_child())
            ok, r = button.compute_bounds(self.dock)
            if not ok or r.get_width() < 1:
                continue
            hint = (int(geo['x'] + r.get_x() + r.get_width() / 2 - 24), int(geo['y'] + r.get_y() + 4), 48, 48)
            live[v['id']] = hint
            if sent.get(v['id']) != hint:
                self.act('mwx7/set-minimize-hint', {'id': v['id'], 'x': hint[0], 'y': hint[1], 'width': 48, 'height': 48})
        self.hints = live

    # ---- volume and network ----------------------------------------------------------------------------------------
    @staticmethod
    def capture(cmd):
        """Output of a command, '' if it fails, None if it did not answer in time."""
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except subprocess.TimeoutExpired:
            return None
        except OSError:
            return ''

    def poll_status(self):
        """Ask for volume and network in a worker thread; the answer is applied on the main thread.
        Running wpctl/nmcli on the main thread froze the clock, the title and every click for seconds whenever the
        system was busy (found with Chrome loading in a VM, 10 Nov 2026). At most one check runs at a time."""
        if getattr(self, 'status_busy', False):
            return True
        self.status_busy = True

        def work():
            vol = self.capture(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
            net = self.capture(['nmcli', '-t', '-f', 'TYPE,STATE,CONNECTION', 'device'])
            GLib.idle_add(self.apply_status, vol, net)
        threading.Thread(target=work, daemon=True).start()
        return True

    def apply_status(self, vol, net):
        self.status_busy = False
        count, version = pending_updates()
        self.upd_btn.set_visible(count > 0)
        if count:
            self.upd_btn.set_tooltip_text(f'MWX 7 {version} is ready to install' if version else
                                          f'{count} updates are ready to install')
        # None means the tool did not answer in time (a busy system): keep showing what was last known rather than
        # flashing "muted" / "not connected".
        if vol is None and net is None:
            return False
        # wpctl: "Volume: 0.40" or "Volume: 0.40 [MUTED]"
        out = (vol or '').split()
        if vol is None:
            pass
        elif len(out) >= 2:
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
        if net is None:
            return False
        icon, tip = 'network-offline-symbolic', 'Not connected'
        for line in net.splitlines():
            parts = line.split(':')
            if len(parts) >= 3 and parts[1] == 'connected':
                if parts[0] == 'wifi':
                    icon, tip = 'network-wireless-signal-excellent-symbolic', f'Wi-Fi: {parts[2]}'
                    break
                if parts[0] == 'ethernet':
                    icon, tip = 'network-wired-symbolic', f'Connected: {parts[2]}'
        self.net.set_from_icon_name(icon)
        self.net_btn.set_tooltip_text(tip + ' (click for network settings)')
        return False

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
