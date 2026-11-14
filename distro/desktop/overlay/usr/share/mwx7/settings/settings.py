"""MWX 7 Settings: the system settings as an MWX 7 app (GTK 4).

Most settings live in the user's Wayfire config (~/.config/mwx7/wayfire.ini), which Wayfire reloads by itself, so
changes apply immediately. The wallpaper is painted by the desktop layer, which follows the wallpaper file (swaybg is only the fallback).
"""
import time
T0 = time.monotonic()  # MWX7_PERF=1 prints start-to-first-frame timings to stderr

import datetime
import glob
import grp
import json
import os
import pwd
import re
import shutil
import stat
import struct
import subprocess
import sys
import threading

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7displays as displays  # noqa: E402
import arrange  # noqa: E402
ICONS = '/usr/share/mwx7/icons'
CONF_DIR = os.path.join(GLib.get_user_config_dir(), 'mwx7')
WF_INI = os.path.join(CONF_DIR, 'wayfire.ini')
WALL_FILE = os.path.join(CONF_DIR, 'wallpaper')
WALLPAPERS = '/usr/share/mwx7/wallpapers'
LIVE = '/usr/share/mwx7/live'
ADMIN = '/usr/share/mwx7/bin/mwx7-admin'
UPDATE = '/usr/share/mwx7/bin/mwx7-update'
BACKUP = '/usr/share/mwx7/bin/mwx7-backup'
BACKUP_STATE = '/var/lib/mwx7/backup.json'
GREETD = '/etc/greetd/config.toml'
USER = pwd.getpwuid(os.getuid()).pw_name

# Window colours, as Windows 7's "Window Color and Appearance" (and MWX 7 on the web): the glass's tint; the intensity
# slider sets how strongly it is tinted (0 = nearly clear glass over the blurred desktop).
COLORS = [
    ('Sky', '#1e64dc'), ('Twilight', '#4a4f8f'), ('Sea', '#1d9aa5'), ('Leaf', '#3f9a3f'),
    ('Lime', '#9ac93a'), ('Sun', '#e8c52b'), ('Pumpkin', '#e8812a'), ('Ruby', '#c42b3a'),
    ('Fuchsia', '#c23a9a'), ('Blush', '#ee9fb4'), ('Violet', '#7d4cc4'), ('Lavender', '#a99bd6'),
    ('Taupe', '#8a7f73'), ('Chocolate', '#6b4630'), ('Slate', '#5f6b78'), ('Frost', '#b9d3e8'),
]


def glass_alpha(intensity):
    return 0.08 + max(0, min(100, intensity)) / 100 * 0.7


def glass_now():
    """(#rrggbb, intensity 0-100) from the frames' colour in wayfire.ini."""
    v = ini_get('decoration', 'active_color', '#1E64DC14').lstrip('\\').lstrip('#')
    try:
        a = int(v[6:8], 16) / 255 if len(v) >= 8 else 1.0
        return '#' + v[:6].lower(), round(max(0.0, min(1.0, (a - 0.08) / 0.7)) * 100)
    except ValueError:
        return '#1e64dc', 0


# ---- Wayfire config editing: keep the file as written (comments, \\# escapes) and change single keys --------------
def ini_get(section, key, default=''):
    try:
        text = open(WF_INI).read()
    except OSError:
        return default
    m = re.search(r'^\[' + re.escape(section) + r'\]\s*$(.*?)(?=^\[|\Z)', text, re.M | re.S)
    if not m:
        return default
    k = re.search(r'^' + re.escape(key) + r'\s*=\s*(.*)$', m.group(1), re.M)
    return k.group(1).strip() if k else default


def ini_set(section, key, value):
    text = open(WF_INI).read()
    m = re.search(r'^\[' + re.escape(section) + r'\]\s*$(.*?)(?=^\[|\Z)', text, re.M | re.S)
    line = f'{key} = {value}'
    if not m:
        text = text.rstrip('\n') + f'\n\n[{section}]\n{line}\n'
    else:
        body = m.group(1)
        if re.search(r'^' + re.escape(key) + r'\s*=.*$', body, re.M):
            body = re.sub(r'^' + re.escape(key) + r'\s*=.*$', lambda _m: line, body, count=1, flags=re.M)
        else:
            body = '\n' + line + body if body.startswith('\n') else '\n' + line + '\n' + body
        text = text[:m.start(1)] + body + text[m.end(1):]
    # Wayfire reloads its config when the file is modified in place (inotify IN_MODIFY); a new file renamed over it
    # is never noticed, which is why changes (window colour) did not apply. One write() of the whole file, never
    # shorter than before (a padding comment fills the rest), so Wayfire can't read a truncated or half-written file.
    ini_write(text)


def ini_unset(section, key):
    """Remove a key (no-op when absent)."""
    try:
        text = open(WF_INI).read()
    except OSError:
        return
    m = re.search(r'^\[' + re.escape(section) + r'\]\s*$(.*?)(?=^\[|\Z)', text, re.M | re.S)
    if not m or not re.search(r'^' + re.escape(key) + r'\s*=', m.group(1), re.M):
        return
    body = re.sub(r'^' + re.escape(key) + r'\s*=.*\n?', '', m.group(1), count=1, flags=re.M)
    ini_write(text[:m.start(1)] + body + text[m.end(1):])


def ini_write(text):
    text = re.sub(r'\n#PAD *\n?\Z', '\n', text)
    data = text.encode()
    old = os.path.getsize(WF_INI)
    if len(data) < old:
        data += b'#PAD' + b' ' * max(0, old - len(data) - 4)
    fd = os.open(WF_INI, os.O_WRONLY)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def titlebar_css(selector, rgb, alpha, active=True):
    """Settings' own title bar (GTK 4 draws it) as the same glass as the frames: tint, sheen and streaks over the blur
    Wayfire puts behind it."""
    r, g, b = (int(rgb[i:i + 2], 16) for i in (1, 3, 5))
    a = alpha if active else alpha * 0.5
    veil = '' if active else ', linear-gradient(rgba(150, 165, 190, 0.22), rgba(150, 165, 190, 0.22))'
    sheen = 0.30 if active else 0.22
    return (f'{selector} {{ background: linear-gradient(118deg, rgba(255,255,255,0) 22%, rgba(255,255,255,0.1) 22.5%, '
            f'rgba(255,255,255,0.1) 24%, rgba(255,255,255,0) 25%, rgba(255,255,255,0) 46%, rgba(255,255,255,0.07) 46.5%, '
            f'rgba(255,255,255,0.07) 50%, rgba(255,255,255,0) 51%), linear-gradient(to bottom, rgba(255,255,255,{sheen}), '
            f'rgba(255,255,255,0.06)), linear-gradient(rgba({r},{g},{b},{a:.3f}), rgba({r},{g},{b},{a * 0.86:.3f})){veil}; }}\n')


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def perf(what):
    if os.environ.get('MWX7_PERF'):
        print(f'[settings perf] {(time.monotonic() - T0) * 1000:7.1f} ms  {what}', file=sys.stderr, flush=True)


# Slow read-only probes (lspci, wpctl status, wlr-randr) are cached for a short while and warmed in a background thread, so a
# page that needs one does not wait for the process to start. drop_cache() after anything that changes what they report.
_cache = {}
_cache_lock = threading.Lock()


def run_cached(cmd, ttl=30):
    key = tuple(cmd)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    out = run(cmd)
    with _cache_lock:
        _cache[key] = (time.monotonic(), out)
    return out


def drop_cache():
    with _cache_lock:
        _cache.clear()


def prewarm():
    """Fill the probe cache off the main thread (only tools that exist), once the first frame is up."""
    def work():
        for cmd, ttl in ((['lspci'], 3600),):
            if shutil.which(cmd[0]):
                run_cached(cmd, ttl)
    threading.Thread(target=work, daemon=True).start()


# ---- UI helpers ---------------------------------------------------------------------------------------------------
def heading(text):
    l = Gtk.Label(label=text, xalign=0)
    l.add_css_class('page-title')
    return l


def section(text):
    l = Gtk.Label(label=text, xalign=0)
    l.add_css_class('section')
    return l


def note(text):
    l = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=85)
    l.add_css_class('note')
    return l


def page(title=None, sub=None):
    """A page: its title (the same words as the sidebar entry) and one short line under it."""
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    b.add_css_class('page')
    if title:
        b.append(heading(title))
    if sub:
        b.append(note(sub))
    return b


def field(label, widget, width=20):
    """A label and its control on one row; the labels share a width so the controls line up down the page."""
    r = Gtk.Box(spacing=12)
    r.append(Gtk.Label(label=label, xalign=0, width_chars=width, css_classes=['key']))
    widget.set_halign(Gtk.Align.START)
    r.append(widget)
    return r


def thumb(path, w, h):
    try:
        buf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, False)
        img = Gtk.Image.new_from_paintable(Gdk.Texture.new_for_pixbuf(buf))
    except GLib.Error:
        img = Gtk.Image.new_from_icon_name('image-missing')
    img.set_size_request(w, h)
    img.set_pixel_size(max(w, h))
    return img


class Settings(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.mwx7.settings')
        GLib.set_prgname('org.mwx7.settings')  # the window's app id without a session bus too (frames, dock, bar)

    def do_activate(self):
        if self.get_windows():
            self.get_windows()[0].present()
            return
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(HERE, 'settings.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        w = Gtk.ApplicationWindow(application=self, title='Settings')
        w.set_default_size(820, 560)
        w.add_css_class('mwx7-settings')
        w.set_titlebar(self.titlebar(w, 'Settings'))
        # GTK 4 draws this window's title bar itself, so it follows the chosen window colour here (Wayfire tints the rest).
        self.tint = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.tint,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.apply_tint()
        root = Gtk.Box()
        nav = Gtk.ListBox()
        nav.add_css_class('nav')
        nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120)
        self.stack.set_hexpand(True)
        self.sound_live = lambda on: None  # the Sound page replaces this when it is first built
        pages = [
            ('wallpapers', 'Wallpapers', 'image', self.page_wallpapers),
            ('wincolor', 'Window Color', 'paint', self.page_wincolor),
            ('desktop', 'Desktop', 'desktop', self.page_desktop),
            ('dock', 'Dock', 'computer', self.page_dock),
            ('display', 'Display', 'computer', self.page_display),
            ('sound', 'Sound', 'audio', self.page_sound),
            ('keyboard', 'Keyboard', 'text', self.page_keyboard),
            ('mouse', 'Mouse', 'settings', self.page_mouse),
            ('access', 'Ease of Access', 'settings', self.page_access),
            ('language', 'Language & region', 'text', self.page_language),
            ('network', 'Network', 'computer', self.page_network),
            ('bluetooth', 'Bluetooth', 'bluetooth', self.page_bluetooth),
            ('printers', 'Printers', 'printer', self.page_printers),
            ('account', 'User account', 'user', self.page_account),
            ('defaults', 'Default apps', 'settings', self.page_defaults),
            ('datetime', 'Date & time', 'about', self.page_datetime),
            ('power', 'Power', 'shutdown', self.page_power),
            ('storage', 'Storage', 'drive', self.page_storage),
            ('security', 'Security', 'settings', self.page_security),
            ('updates', 'Updates', 'updates', self.page_updates),
            ('backup', 'Backup', 'backup', self.page_backup),
            ('about', 'About', 'about', self.page_about),
        ]
        # Pages are built when first shown (an empty scroller stands in until then): Settings opens at once and a page's
        # probes and scans (Storage, Security, Display ...) run only when somebody looks at it.
        scrolls = {}
        builders = {}

        def ensure_built(pid):
            build = builders.pop(pid, None)
            if build is None:
                return
            t = time.monotonic()
            try:
                scrolls[pid].set_child(build())
            except Exception as e:  # one broken page must not take Settings down
                print(f'settings: page {pid} failed: {e!r}', file=sys.stderr)
                scrolls[pid].set_child(Gtk.Label(label='This page could not be loaded.', margin_top=20))
            perf(f'built {pid} in {(time.monotonic() - t) * 1000:.1f} ms')
            if pid in ('wallpapers', 'wincolor'):
                self.sync_personalize()  # mark the current theme and wallpaper

        def select(_l, r):
            if r:
                ensure_built(r.pid)
                self.stack.set_visible_child_name(r.pid)
        for pid, label, icon, build in pages:
            row = Gtk.ListBoxRow()
            row.pid = pid
            box = Gtk.Box(spacing=10)
            img = Gtk.Image.new_from_file(os.path.join(ICONS, icon + '.png'))
            img.set_pixel_size(24)
            box.append(img)
            box.append(Gtk.Label(label=label, xalign=0))
            row.set_child(box)
            nav.append(row)
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolls[pid] = scroll
            builders[pid] = build
            self.stack.add_named(scroll, pid)
        nav.connect('row-selected', select)
        # "--updates" (the update notification) opens straight at Updates; "--page <id>" at any page (the bar's clock
        # opens Date & time, the desktop's menu Personalize).
        want = 'updates' if '--updates' in sys.argv else (sys.argv[sys.argv.index('--page') + 1]
                                                         if '--page' in sys.argv[:-1] else '')
        want = {'personalize': 'wallpapers'}.get(want, want)  # the desktop menu's old "Personalize" page id
        start = next((i for i, pg in enumerate(pages) if pg[0] == want), 0)
        nav.select_row(nav.get_row_at_index(start))
        root.append(nav)
        root.append(self.stack)
        # The Sound page polls (input meter, apps list): only while it is on screen and this window is in front.
        def sound_sync(*_a):
            self.sound_live(self.stack.get_visible_child_name() == 'sound' and w.is_active())
        self.stack.connect('notify::visible-child-name', sound_sync)
        w.connect('notify::is-active', sound_sync)
        w.connect('close-request', lambda *_a: self.sound_live(False) and False)
        w.set_child(root)
        perf('window built')
        if os.environ.get('MWX7_PERF'):
            # First frame = the surface's first paint; MWX7_PERF=quit then exits (for timing runs).
            hid = [0]

            def painted(clock):
                perf('first frame')
                clock.disconnect(hid[0])
                prewarm()
                if os.environ['MWX7_PERF'] == 'quit':
                    self.quit()
            w.connect('realize', lambda win: hid.__setitem__(
                0, win.get_surface().get_frame_clock().connect('after-paint', painted)))
        else:
            GLib.idle_add(lambda: prewarm() and False)
        w.present()

    @staticmethod
    def titlebar(win, title, icon_name='settings'):
        # MWX 7's frames (mwx7-decor) draw the title bar: the same Aero glass, icon, title, buttons and window menu as
        # every other window. GTK draws none of its own then (it sees the compositor prefers server-side frames).
        # MWX7_CSD=1 brings back the GTK-drawn bar below, for a compositor without MWX 7's frames.
        if os.environ.get('MWX7_CSD') != '1':
            return None
        bar = Gtk.HeaderBar()
        bar.add_css_class('mwx7-titlebar')
        bar.set_show_title_buttons(False)
        icon = Gtk.Image.new_from_file(os.path.join(ICONS, icon_name + '.png'))
        icon.set_pixel_size(16)
        icon.set_margin_end(6)
        bar.pack_start(icon)
        label = Gtk.Label(label=title)
        label.add_css_class('mwx7-title')
        bar.pack_start(label)
        bar.set_title_widget(Gtk.Box())
        for cls, tip, fn in (('light-close', 'Close', win.close), ('light-min', 'Minimize', win.minimize),
                             ('light-max', 'Maximize', lambda: win.unmaximize() if win.is_maximized() else win.maximize())):
            b = Gtk.Button()
            b.add_css_class('light')
            b.add_css_class(cls)
            b.set_tooltip_text(tip)
            b.set_valign(Gtk.Align.CENTER)
            b.connect('clicked', lambda *_a, f=fn: f())
            bar.pack_end(b)
        # Full screen (maximized): as in the concept the title bar merges into the top bar, which shows the name and
        # the traffic lights then.
        win.connect('notify::maximized', lambda w, _p: bar.set_visible(not w.is_maximized()))
        # Right-click on the title bar: Windows 7's window menu.
        menu = Gio.Menu()
        for label, name in (('Restore', 'restore'), ('Minimize', 'minimize'), ('Maximize', 'maximize'), ('Close', 'close')):
            menu.append(label, 'wmenu.wm-' + name)
        acts = {'restore': lambda: win.unmaximize(), 'minimize': win.minimize, 'maximize': win.maximize,
                'close': win.close}
        # An action group of its own: dialogs are plain Gtk.Windows, which have no add_action.
        group = Gio.SimpleActionGroup()
        for name, fn in acts.items():
            a = Gio.SimpleAction.new('wm-' + name, None)
            a.connect('activate', lambda *_a, f=fn: f())
            group.add_action(a)
        win.insert_action_group('wmenu', group)
        pop = Gtk.PopoverMenu(menu_model=menu, has_arrow=False)
        pop.set_parent(bar)
        click = Gtk.GestureClick(button=3)
        # Capture phase: GTK's own title bar handling would otherwise take the right-click first.
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

        def on_right(g, _n, x, y):
            g.set_state(Gtk.EventSequenceState.CLAIMED)
            maxed = win.is_maximized()
            group.lookup_action('wm-restore').set_enabled(maxed)
            group.lookup_action('wm-maximize').set_enabled(not maxed)
            r = Gdk.Rectangle()
            r.x, r.y, r.width, r.height = int(x), int(y), 1, 1
            pop.set_pointing_to(r)
            pop.popup()
        click.connect('pressed', on_right)
        bar.add_controller(click)
        return bar

    # ---- Themes, Wallpapers, Window Color (the web Settings' three Personalization pages) ----------------------------
    # The web's four themes. Aurora and Dusk are drawn live on the web; here they are stills rendered from the concept's
    # own drawing code.
    THEMES = [('MWX 7', 'meadow.jpg', '#1e64dc', 0), ('Aurora', 'aurora.jpg', '#1b3f9e', 60),
              ('Sierra', 'sierra.jpg', '#5f6b78', 45), ('Dusk', 'dusk.jpg', '#7d4cc4', 55)]

    @staticmethod
    def tile(preview, name, strip=None):
        """A selectable tile as in the web Settings: thumbnail, optional colour strip under it, then the name."""
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        v.append(preview)
        if strip:
            bar = Gtk.Box()
            bar.set_size_request(150, 8)
            bar.set_halign(Gtk.Align.CENTER)
            bar.add_css_class('theme-strip')
            prov = Gtk.CssProvider()
            prov.load_from_data(f'box {{ background: {strip}; }}'.encode())
            bar.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            v.append(bar)
        v.append(Gtk.Label(label=name))
        return v

    def sync_personalize(self):
        """Re-select the tiles that match the current wallpaper and colour: a theme click changes both pages' state."""
        # The default wallpaper (/usr/share/mwx7/wallpaper.jpg) is the meadow picture.
        name = lambda p: 'meadow.jpg' if os.path.basename(p) == 'wallpaper.jpg' else os.path.basename(p)
        wall = name(self.current_wallpaper())
        rgb, level = glass_now()
        for flow, match in ((getattr(self, 'wall_flow', None), lambda c: name(c.path) == wall),
                            (getattr(self, 'theme_flow', None),
                             lambda c: name(c.path) == wall and (c.rgb.lower(), c.level) == (rgb, level))):
            if not flow:
                continue
            flow.unselect_all()
            child = flow.get_child_at_index(0)
            while child:
                if match(child):
                    flow.select_child(child)
                child = child.get_next_sibling()

    def page_themes(self):
        p = page()
        p.append(heading('Change the visuals and sounds on your computer'))
        p.append(note('Click a theme to set the desktop background and window color together.'))
        flow = Gtk.FlowBox(max_children_per_line=4, selection_mode=Gtk.SelectionMode.SINGLE, column_spacing=10,
                           row_spacing=10, homogeneous=True, valign=Gtk.Align.START)
        flow.add_css_class('walls')
        for name, f, rgb, level in self.THEMES:
            path = os.path.join(WALLPAPERS, f)
            if not os.path.exists(path):
                continue
            child = Gtk.FlowBoxChild()
            child.path, child.rgb, child.level = path, rgb, level
            child.set_child(self.tile(thumb(path, 150, 94), name, rgb))
            flow.append(child)

        def chosen(_f, c):
            self.set_wallpaper(c.path)
            self.set_glass(c.rgb, c.level)
            self.sync_personalize()
        flow.connect('child-activated', chosen)
        self.theme_flow = flow
        p.append(flow)
        return p

    def page_wallpapers(self):
        p = page('Wallpapers', 'Click a picture to use it as your desktop background.')
        flow = Gtk.FlowBox(max_children_per_line=4, selection_mode=Gtk.SelectionMode.SINGLE, column_spacing=10,
                           row_spacing=10, homogeneous=True, valign=Gtk.Align.START)
        flow.add_css_class('walls')
        for f in sorted(f for f in os.listdir(WALLPAPERS) if f.lower().endswith(('.jpg', '.png'))):
            path = os.path.join(WALLPAPERS, f)
            child = Gtk.FlowBoxChild()
            child.path = path
            child.set_child(self.tile(thumb(path, 150, 94), os.path.splitext(f)[0].replace('-', ' ').capitalize()))
            flow.append(child)

        def chosen(_f, c):
            self.set_wallpaper(c.path)
            self.sync_personalize()
        flow.connect('child-activated', chosen)
        self.wall_flow = flow
        p.append(flow)
        # Live wallpapers: a looped, muted video the desktop layer plays behind the icons. Off unless one is clicked.
        live = [f[:-4] for f in sorted(os.listdir(LIVE)) if f.endswith('.mp4')] if os.path.isdir(LIVE) else []
        if live:
            p.append(section('Live wallpapers'))
            soft = self.acceleration().startswith('Off')  # the desktop will not play a video drawn by the CPU
            p.append(note('A moving background. Click it again to turn it off.' +
                          (' Needs 3D acceleration, which is off on this PC.' if soft else '')))
            lf = Gtk.FlowBox(max_children_per_line=4, selection_mode=Gtk.SelectionMode.SINGLE, column_spacing=10,
                             row_spacing=10, homogeneous=True, valign=Gtk.Align.START)
            lf.add_css_class('walls')
            lf.set_sensitive(not soft)
            for n in live:
                child = Gtk.FlowBoxChild()
                child.live = n
                still = os.path.join(WALLPAPERS, n + '.jpg')  # the still of the same name is its thumbnail
                child.set_child(self.tile(thumb(still, 150, 94), n.capitalize() + ' (live)'))
                lf.append(child)
            cur = self.live_choice()
            c = lf.get_first_child()
            while c:
                if getattr(c, 'live', None) == cur:
                    lf.select_child(c)
                c = c.get_next_sibling()

            def chose_live(_f, c):
                if self.live_choice() == c.live:  # a second click turns it off
                    lf.unselect_all()
                    self.set_live('')
                else:
                    self.set_live(c.live)
            lf.connect('child-activated', chose_live)
            self.live_flow = lf
            p.append(lf)
        return p

    @staticmethod
    def live_choice():
        try:
            return str(json.load(open(os.path.join(CONF_DIR, 'desktop.json'))).get('live_wallpaper') or '')
        except (OSError, ValueError, AttributeError):
            return ''

    @staticmethod
    def set_live(name):
        """The desktop layer watches desktop.json and starts or stops the video; a still wallpaper clears this."""
        path = os.path.join(CONF_DIR, 'desktop.json')
        try:
            cfg = json.load(open(path))
        except (OSError, ValueError):
            cfg = {}
        cfg['live_wallpaper'] = name
        os.makedirs(CONF_DIR, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(cfg, f)
        os.replace(tmp, path)

    def page_wincolor(self):
        p = page('Window Color', 'The tint of the glass on window frames, the status bar and the dock.')
        p.append(section('Color'))
        flow = Gtk.FlowBox(max_children_per_line=8, min_children_per_line=8, selection_mode=Gtk.SelectionMode.NONE,
                           column_spacing=6, row_spacing=6, halign=Gtk.Align.START)
        cur, intensity = glass_now()
        self.swatches = []
        for name, hexc in COLORS:
            b = Gtk.Button()
            b.add_css_class('swatch')
            b.set_tooltip_text(name)
            sw = Gtk.Box()
            sw.set_size_request(36, 36)
            prov = Gtk.CssProvider()
            prov.load_from_data(f'box {{ background: {hexc}; border-radius: 4px; }}'.encode())
            sw.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            b.set_child(sw)
            if hexc == cur:
                b.add_css_class('chosen')
            b.connect('clicked', lambda _b, h=hexc: (self.set_glass(h, None), self.sync_personalize()))
            self.swatches.append((hexc, b))
            flow.append(b)
        p.append(flow)
        self.intensity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.intensity.set_value(intensity)
        self.intensity.set_size_request(320, -1)
        self.intensity.set_halign(Gtk.Align.START)
        self.intensity.set_draw_value(False)
        # Applied when the slider is let go (and after a short pause while dragging), not on every pixel of travel.
        self.intensity_timer = 0

        def moved(*_):
            if self.intensity_timer:
                GLib.source_remove(self.intensity_timer)
            self.intensity_timer = GLib.timeout_add(250, lambda: (setattr(self, 'intensity_timer', 0),
                                                                  self.set_glass(None, self.intensity.get_value()),
                                                                  self.sync_personalize())
                                                    and False)
        self.intensity.connect('value-changed', moved)
        p.append(section('Intensity'))
        p.append(self.intensity)
        p.append(note('Left is clear glass, right is a strong tint.'))
        return p

    @staticmethod
    def current_wallpaper():
        try:
            return open(WALL_FILE).read().strip()
        except OSError:
            return '/usr/share/mwx7/wallpaper.jpg'

    @staticmethod
    def set_wallpaper(path):
        if Settings.live_choice():
            Settings.set_live('')
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(WALL_FILE, 'w') as f:
            f.write(path + '\n')
        # The desktop layer paints the wallpaper itself and follows the file. swaybg is only the fallback when it is not running.
        if subprocess.run(['pgrep', '-u', str(os.getuid()), '-f', 'mwx7/desktop/desktop.py'], capture_output=True).returncode == 0:
            return
        # Start the new wallpaper before stopping the old one, so the desktop never flashes empty.
        old = run(['pgrep', '-u', str(os.getuid()), '-x', 'swaybg']).split()
        subprocess.Popen(['swaybg', '-i', path, '-m', 'fill'], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        GLib.timeout_add(700, lambda: [subprocess.run(['kill', pid]) for pid in old] and False)

    def apply_tint(self):
        rgb, intensity = glass_now()
        a = glass_alpha(intensity)
        self.tint.load_from_data((titlebar_css('headerbar.mwx7-titlebar', rgb, a) +
                                  titlebar_css('window.mwx7-settings:backdrop headerbar.mwx7-titlebar', rgb, a, False) +
                                  'window.mwx7-settings { background: transparent; }\n'
                                  'window.mwx7-settings > box { background: #ffffff; }\n').encode())

    def set_glass(self, rgb, intensity):
        cur, cur_i = glass_now()
        rgb = rgb or cur
        intensity = cur_i if intensity is None else intensity
        value = '\\' + rgb.upper() + f'{round(glass_alpha(intensity) * 255):02X}'
        ini_set('decoration', 'active_color', value)
        ini_set('decoration', 'inactive_color', value)
        self.apply_tint()
        for hexc, btn in getattr(self, 'swatches', []):
            (btn.add_css_class if hexc == rgb else btn.remove_css_class)('chosen')


    # ---- Display ----------------------------------------------------------------------------------------------------
    @staticmethod
    def read_outputs():
        """Screens as wlr-randr reports them: [{name, make, model, scale, physical_size, modes: [{width, height, refresh,
        preferred, current}]}]. `--json` where this wlr-randr has it, else its plain text."""
        fake = os.environ.get('MWX7_FAKE_OUTPUTS')  # a JSON file in wlr-randr --json's shape: for screenshots and checks
        if fake:
            try:
                return json.load(open(fake))
            except (OSError, ValueError):
                return []
        if not shutil.which('wlr-randr'):
            return []
        try:
            data = json.loads(run_cached(['wlr-randr', '--json'], 3) or '[]')
            if isinstance(data, list) and data:
                return data
        except ValueError:
            pass
        outs, cur = [], None
        for line in run_cached(['wlr-randr'], 3).splitlines():
            if line and not line[0].isspace():
                cur = {'name': line.split()[0], 'modes': [], 'scale': 1.0}
                outs.append(cur)
                continue
            if cur is None:
                continue
            t = line.strip()
            m = re.match(r'(\d+)x(\d+) px, ([\d.]+) Hz(?: \((.*)\))?', t)
            if m:
                flags = (m.group(4) or '').split(', ')
                cur['modes'].append({'width': int(m.group(1)), 'height': int(m.group(2)), 'refresh': float(m.group(3)),
                                     'preferred': 'preferred' in flags, 'current': 'current' in flags})
            elif t.startswith('Position:'):
                try:
                    px, py = t.split(':', 1)[1].strip().split(',')
                    cur['position'] = {'x': int(px), 'y': int(py)}
                except ValueError:
                    pass
            elif t.startswith('Enabled:'):
                cur['enabled'] = t.split(':', 1)[1].strip().lower() == 'yes'
            elif t.startswith('Transform:'):
                cur['transform'] = t.split(':', 1)[1].strip()
            elif t.startswith('Scale:'):
                try:
                    cur['scale'] = float(t.split(':', 1)[1])
                except ValueError:
                    pass
            elif t.startswith('Make:'):
                cur['make'] = t.split(':', 1)[1].strip()
            elif t.startswith('Model:'):
                cur['model'] = t.split(':', 1)[1].strip()
        return outs

    @staticmethod
    def randr(name, mode, scale):
        """Apply a mode and scale to one screen right now (wlr-randr); True when the compositor accepted it."""
        drop_cache()
        w, h, r = mode
        arg = f'{w}x{h}' + (f'@{r:.3f}Hz' if r else '')
        try:
            return subprocess.run(['wlr-randr', '--output', name, '--mode', arg, '--scale', f'{scale:g}'],
                                  capture_output=True, timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def keep_dialog(self, on_keep, on_revert):
        """"Keep these display settings?": like Windows, goes back by itself after 15 seconds so a screen that shows
        nothing usable never stays that way."""
        dlg = self.small_window('Display settings', 'settings')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=18, margin_bottom=16,
                      margin_start=20, margin_end=20)
        box.append(Gtk.Label(label='Keep these display settings?', xalign=0, css_classes=['section']))
        msg = Gtk.Label(xalign=0, wrap=True, max_width_chars=48)
        box.append(msg)
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=6)
        revert = Gtk.Button(label='Revert')
        keep = Gtk.Button(label='Keep changes', css_classes=['suggested-action'])
        btns.append(revert)
        btns.append(keep)
        box.append(btns)
        dlg.set_child(box)
        st = {'left': 15, 'done': False, 'timer': 0}

        def show():
            msg.set_label(f'Going back to the previous settings in {st["left"]} seconds.')

        def decide(keep_it):
            # Not tied to the window's destroy signal: every way out (buttons, timeout, close, Settings closing) ends here.
            if st['done']:
                return
            st['done'] = True
            if st['timer']:
                GLib.source_remove(st['timer'])
                st['timer'] = 0
            (on_keep if keep_it else on_revert)()
            dlg.destroy()

        def tick():
            st['left'] -= 1
            if st['left'] <= 0:
                st['timer'] = 0
                decide(False)
                return False
            show()
            return True
        keep.connect('clicked', lambda _b: decide(True))
        revert.connect('clicked', lambda _b: decide(False))
        dlg.connect('close-request', lambda _w: decide(False) and False)
        parent = self.get_active_window()
        if parent is not None:
            parent.connect('close-request', lambda _w: decide(False) and False)
        show()
        st['timer'] = GLib.timeout_add_seconds(1, tick)
        dlg.present()

    def output_controls(self, p, o):
        """Resolution, refresh rate and size pickers for one screen. A change applies at once, then waits for the
        15-second "Keep these settings?" answer; only a kept change is written to wayfire.ini."""
        name = o.get('name', '?')
        modes = [(m['width'], m['height'], float(m.get('refresh') or 0), bool(m.get('preferred')), bool(m.get('current')))
                 for m in o.get('modes', [])]
        p.append(section((f"{o.get('make') or ''} {o.get('model') or ''}".strip() + f' ({name})').strip()))
        if not modes:
            p.append(note('This screen reports no modes.'))
            return
        sizes = sorted({(m[0], m[1]) for m in modes}, reverse=True)
        pick = next((m for m in modes if m[4]), modes[0])
        scales = [1.0, 1.25, 1.5, 1.75, 2.0]
        try:
            scale0 = min(scales, key=lambda s: abs(s - float(o.get('scale', 1))))
        except (TypeError, ValueError):
            scale0 = 1.0
        st = {'mode': pick[:3], 'scale': scale0, 'busy': False}

        def rates(size):
            return sorted({m[2] for m in modes if (m[0], m[1]) == size}, reverse=True)

        def rate_label(r):
            return (f'{r:.2f}'.rstrip('0').rstrip('.') + ' Hz') if r else 'Default'
        size_dd = Gtk.DropDown.new_from_strings([f'{w} × {h}' + (' (recommended)' if any(
            m[3] for m in modes if (m[0], m[1]) == (w, h)) else '') for w, h in sizes])
        rate_dd = Gtk.DropDown.new_from_strings([rate_label(r) for r in rates(sizes[0])])
        scale_dd = Gtk.DropDown.new_from_strings([f'{round(s * 100)}%' for s in scales])

        def show(mode, scale):
            """Put the pickers on a mode without it counting as a change by the person."""
            st['busy'] = True
            size = (mode[0], mode[1])
            size_dd.set_selected(sizes.index(size) if size in sizes else 0)
            rs = rates(size)
            rate_dd.set_model(Gtk.StringList.new([rate_label(r) for r in rs]))
            rate_dd.set_selected(min(range(len(rs)), key=lambda i: abs(rs[i] - mode[2])))
            scale_dd.set_selected(scales.index(scale))
            st['busy'] = False
        show(st['mode'], st['scale'])
        status = note('')

        def changed(new_mode, new_scale):
            old_mode, old_scale = st['mode'], st['scale']
            if (new_mode, new_scale) == (old_mode, old_scale):
                return
            if not self.randr(name, new_mode, new_scale):
                status.set_label('The screen did not accept that setting.')
                show(old_mode, old_scale)
                return
            status.set_label('')

            drops = (size_dd, rate_dd, scale_dd)  # no second change while the question is open

            def keep():
                for d in drops:
                    d.set_sensitive(True)
                st['mode'], st['scale'] = new_mode, new_scale
                ini_set(f'output:{name}', 'mode', f'{new_mode[0]}x{new_mode[1]}@{int(round(new_mode[2] * 1000))}')
                ini_set(f'output:{name}', 'scale', f'{new_scale:g}')

            def back():
                for d in drops:
                    d.set_sensitive(True)
                self.randr(name, old_mode, old_scale)
                show(old_mode, old_scale)
            for d in drops:
                d.set_sensitive(False)
            self.keep_dialog(keep, back)

        def size_changed(d, _p):
            if st['busy']:
                return
            size = sizes[d.get_selected()]
            rs = rates(size)
            best = min(rs, key=lambda r: abs(r - st['mode'][2]))  # same refresh rate if the new size has it
            st['busy'] = True
            rate_dd.set_model(Gtk.StringList.new([rate_label(r) for r in rs]))
            rate_dd.set_selected(rs.index(best))
            st['busy'] = False
            changed((size[0], size[1], best), st['scale'])

        def rate_changed(d, _p):
            size = sizes[size_dd.get_selected()]
            rs = rates(size)
            if st['busy'] or d.get_selected() >= len(rs):
                return
            r = rs[d.get_selected()]
            changed((size[0], size[1], r), st['scale'])
        size_dd.connect('notify::selected', size_changed)
        rate_dd.connect('notify::selected', rate_changed)
        scale_dd.connect('notify::selected', lambda d, _p: st['busy'] or changed(st['mode'], scales[d.get_selected()]))
        p.append(field('Resolution', size_dd))
        p.append(field('Refresh rate', rate_dd))
        p.append(field('Size of text and apps', scale_dd))
        p.append(status)
        # A monitor with tiny text out of the box gets a hint (Wayfire starts every screen at 100%).
        mm_w = int((o.get('physical_size') or {}).get('width') or 0)
        if mm_w and st['mode'][0] / (mm_w / 25.4) > 140 and st['scale'] < 1.25:
            p.append(note('This screen has small pixels; 150% or 200% may be easier to read.'))

    def page_display(self):
        p = page('Display', 'Screen size, text size and night light.')
        outputs = self.read_outputs()
        if not outputs:
            p.append(note('No display information is available here (wlr-randr found no screen).'))
        if len(outputs) > 1:
            self.arrangement(p, outputs)
        for o in outputs:
            self.output_controls(p, o)
        self.animations_section(p)
        self.night_light(p)
        self.graphics_driver(p)
        return p

    @staticmethod
    def randr_pos(items):
        """Move screens right now: items is [(name, x, y)]. True when wlr-randr accepted it."""
        drop_cache()
        cmd = ['wlr-randr']
        for name, x, y in items:
            cmd += ['--output', name, '--pos', f'{x},{y}']
        try:
            return subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def identify(self, outputs):
        """Windows' "Identify": a big number on every screen for two seconds, the same numbers as in the arrangement."""
        mons = displays.monitors(Gdk.Display.get_default())
        for i, o in enumerate(outputs):
            mon = next((m for m in mons if displays.connector(m) == o.get('name')), None)
            if mon is None:
                continue
            w = Gtk.Window(title='MWX 7', decorated=False)
            w.add_css_class('identify')
            w.set_child(Gtk.Label(label=str(i + 1), css_classes=['identify-num']))
            w.fullscreen_on_monitor(mon)
            w.present()
            GLib.timeout_add(2000, lambda win=w: win.destroy() and False)

    def arrangement(self, p, outputs):
        """Drag the screens to where they sit on the desk; choose the main display; extend or duplicate. Positions
        apply at once through wlr-randr (with the 15-second "Keep these settings?" question) and are kept in wayfire.ini
        as [output:NAME] position = x,y, which Wayfire reads at every start."""
        p.append(section('Arrange your displays'))
        p.append(note('Drag the screens to match how they sit on your desk. The main display carries the bar, the dock and '
                      'the desktop icons.'))
        rects = []
        for o in outputs:
            w, h = arrange.logical_size(o)
            x, y = arrange.position_of(o)
            rects.append({'name': o.get('name', '?'), 'x': x, 'y': y, 'w': w, 'h': h})
        arrange.normalize(rects)
        names = [r['name'] for r in rects]
        mons = displays.monitors(Gdk.Display.get_default())
        main = displays.pick_primary(mons)
        main_name = displays.connector(main) if main is not None and displays.connector(main) in names else (
            displays.primary_name() if displays.primary_name() in names else names[0])
        start = {r['name']: (r['x'], r['y']) for r in rects}
        st = {'main': main_name, 'start': dict(start)}
        status = note('')
        apply_btn = Gtk.Button(label='Apply', sensitive=False)
        main_btn = Gtk.Button(label='Make this my main display')
        ident = Gtk.Button(label='Identify')

        def moved_names():
            return [r for r in rects if (r['x'], r['y']) != st['start'][r['name']]]

        def refresh(*_a):
            apply_btn.set_sensitive(bool(moved_names()))
            main_btn.set_sensitive(area.selected != st['main'])
            area.primary = st['main']
            area.queue_draw()
            status.set_label('')

        area = arrange.Arrange(rects, main_name, on_select=lambda _n: refresh(), on_moved=refresh)
        area.set_halign(Gtk.Align.FILL)
        p.append(area)
        row = Gtk.Box(spacing=8)
        row.append(ident)
        row.append(main_btn)
        row.append(apply_btn)
        p.append(row)
        p.append(status)

        def set_main(*_a):
            st['main'] = area.selected
            displays.set_primary(area.selected)  # the shell and the desktop layer follow this file live
            refresh()
        main_btn.connect('clicked', set_main)
        ident.connect('clicked', lambda *_a: self.identify(outputs))

        def do_apply(*_a):
            changed = moved_names()
            old = {r['name']: st['start'][r['name']] for r in changed}
            new = {r['name']: (r['x'], r['y']) for r in changed}
            if not self.randr_pos([(n, x, y) for n, (x, y) in new.items()]):
                status.set_label('The screens did not accept that arrangement.')
                for r in changed:
                    r['x'], r['y'] = old[r['name']]
                refresh()
                return
            apply_btn.set_sensitive(False)

            def keep():
                for n, (x, y) in new.items():
                    ini_set(f'output:{n}', 'position', f'{x},{y}')
                st['start'].update(new)
                refresh()

            def back():
                self.randr_pos([(n, x, y) for n, (x, y) in old.items()])
                for r in changed:
                    r['x'], r['y'] = old[r['name']]
                refresh()
            self.keep_dialog(keep, back)
        apply_btn.connect('clicked', do_apply)
        # Extend or duplicate: Wayfire's [output:NAME] mirror_from makes a screen show another one's picture.
        mirrored = any(ini_get(f'output:{n}', 'mirror_from') for n in names)
        ext = Gtk.CheckButton(label='Extend these displays')
        dup = Gtk.CheckButton(label='Duplicate these displays', group=ext)
        (dup if mirrored else ext).set_active(True)

        def mode_changed(*_a):
            for n in names:
                if dup.get_active() and n != st['main']:
                    ini_set(f'output:{n}', 'mirror_from', st['main'])
                else:
                    ini_unset(f'output:{n}', 'mirror_from')
            status.set_label('Duplicating the main display.' if dup.get_active() else 'Each screen shows its own desktop.')
        dup.connect('toggled', lambda *_a: mode_changed())
        p.append(field('Multiple displays', ext))
        p.append(field('', dup))
        p.append(note('Duplicate shows the main display on the other screens; it may need signing out and in again to apply.'))
        refresh()

    def night_light(self, p):
        """Night light: warmer colours from sunset to sunrise (where the weather widget's city is) or between hours of
        the person's choosing. The flag file's first line holds "custom HH:MM HH:MM" (start, end) for the latter;
        bin/mwx7-nightlight reads it."""
        p.append(section('Night light'))
        flag = os.path.join(CONF_DIR, 'nightlight')
        try:
            first = open(flag).readline().split()
        except OSError:
            first = []
        custom = len(first) == 3 and first[0] == 'custom'
        times = [f'{h:02d}:{m:02d}' for h in range(24) for m in (0, 30)]
        night = Gtk.CheckButton(label='Warmer colors at night')
        night.set_active(os.path.exists(flag))
        sun = Gtk.CheckButton(label='From sunset to sunrise')
        hours = Gtk.CheckButton(label='Custom hours', group=sun)
        (hours if custom else sun).set_active(True)
        start, end = Gtk.DropDown.new_from_strings(times), Gtk.DropDown.new_from_strings(times)
        start.set_selected(times.index(first[1]) if custom and first[1] in times else times.index('21:00'))
        end.set_selected(times.index(first[2]) if custom and first[2] in times else times.index('07:00'))
        when = Gtk.Box(spacing=8, margin_start=24)
        when.append(Gtk.Label(label='From'))
        when.append(start)
        when.append(Gtk.Label(label='to'))
        when.append(end)

        def apply(*_a):
            hours.set_sensitive(night.get_active())
            sun.set_sensitive(night.get_active())
            when.set_sensitive(night.get_active() and hours.get_active())
            if night.get_active():
                os.makedirs(CONF_DIR, exist_ok=True)
                with open(flag, 'w') as f:
                    if hours.get_active():
                        f.write(f'custom {times[start.get_selected()]} {times[end.get_selected()]}\n')
                subprocess.Popen(['/usr/share/mwx7/bin/mwx7-nightlight'], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                if os.path.exists(flag):
                    os.remove(flag)
                run(['pkill', '-u', str(os.getuid()), '-x', 'wlsunset'])
        apply_later = lambda *_a: apply()
        night.connect('toggled', apply_later)
        hours.connect('toggled', apply_later)
        start.connect('notify::selected', apply_later)
        end.connect('notify::selected', apply_later)
        hours.set_sensitive(night.get_active())
        sun.set_sensitive(night.get_active())
        when.set_sensitive(night.get_active() and custom)
        p.append(night)
        p.append(sun)
        p.append(hours)
        p.append(when)
        p.append(note('Sunset and sunrise follow the city set on the Desktop page.'))

    ANIM_LEVELS = [('full', 'Full (fades, zoom, genie, hover glow)'), ('reduced', 'Reduced (short fades only)'), ('off', 'Off')]

    def animations_section(self, p):
        """Window animations are redrawn every frame; a slow virtual GPU (VMware) lags with them. The plugins read the
        level live. A level chosen here is remembered so mwx7-perf never overrides it at the next sign-in."""
        p.append(section('Animations'))
        cur = ini_get('mwx7-animate', 'level', 'full')
        dd = Gtk.DropDown.new_from_strings([l for _k, l in self.ANIM_LEVELS])
        dd.set_selected(next((i for i, (k, _l) in enumerate(self.ANIM_LEVELS) if k == cur), 0))

        def chosen(d, _p):
            level = self.ANIM_LEVELS[d.get_selected()][0]
            os.makedirs(CONF_DIR, exist_ok=True)
            with open(os.path.join(CONF_DIR, 'animations.json'), 'w') as f:
                json.dump({'level': level}, f)
            try:
                os.unlink(os.path.join(CONF_DIR, 'perf-animations.json'))
            except OSError:
                pass
            ini_set('mwx7-animate', 'level', level)
        dd.connect('notify::selected', chosen)
        p.append(field('Window animations', dd))
        p.append(note('Reduced or Off helps in a virtual machine or on an older graphics card.'))

    def graphics_driver(self, p):
        """Only on a PC with an NVIDIA graphics card: its driver is not in MWX 7 by default (it is not free software)."""
        if not re.search(r'(VGA|3D|Display).*NVIDIA', run_cached(['lspci'], 3600)):
            return
        p.append(section('Graphics driver'))
        have = 'install ok installed' in run(['dpkg-query', '-W', '-f=${Status}', 'nvidia-driver'])
        status = Gtk.Label(xalign=0, wrap=True)
        status.add_css_class('note')
        btn = Gtk.Button(label='Remove the NVIDIA driver' if have else 'Use the NVIDIA driver')
        btn.set_halign(Gtk.Align.START)
        sb = 'enabled' in run(['mokutil', '--sb-state']).lower()
        status.set_label('The NVIDIA driver is installed.' if have else
                         'This PC has an NVIDIA graphics card. The driver that comes with MWX 7 works, but NVIDIA\u2019s own '
                         'driver is faster in games and 3D apps. It comes from Debian (non-free) and needs the internet.')

        def go(_b):
            install = not have
            btn.set_sensitive(False)
            status.set_label('Installing the NVIDIA driver\u2026 this takes a few minutes.' if install else
                             'Removing the NVIDIA driver\u2026')

            def done(ok, err):
                if ok:
                    msg = ('Done. Restart the PC to finish; Remove brings the old driver back.' if install else
                           'Removed. Restart the PC to go back to the standard driver.')
                    if install and sb:
                        # Secure Boot refuses unsigned drivers: the signing key is queued, and a blue screen appears at the
                        # restart. Without answering it the screen keeps working, on the standard driver.
                        msg += (' Secure Boot is on: at the restart a blue screen asks about a key. Choose Enroll MOK, '
                                'Continue, Yes, and type the password mwx7mwx7. Or switch Secure Boot off in the BIOS.')
                    status.set_label(msg)
                else:
                    status.set_label(f'That did not work: {err}')
                    btn.set_sensitive(True)
            self.admin(['nvidia', 'install' if install else 'remove'], done, timeout=1800)
        btn.connect('clicked', go)
        p.append(status)
        p.append(btn)
        p.append(note('A restart is required after installing or removing it.'))

    # ---- Bluetooth --------------------------------------------------------------------------------------------------
    BT_MAC = re.compile(r'[0-9A-F]{2}(:[0-9A-F]{2}){5}\Z')

    @staticmethod
    def btctl(args, timeout=20):
        try:
            r = subprocess.run(['bluetoothctl'] + args, capture_output=True, text=True, timeout=timeout)
            return r.stdout + r.stderr
        except (OSError, subprocess.TimeoutExpired):
            return ''

    def page_bluetooth(self):
        p = page('Bluetooth', 'Connect headphones, speakers, a keyboard or a mouse.')
        top = Gtk.Box(spacing=12)
        power = Gtk.Switch(valign=Gtk.Align.CENTER)
        top.append(Gtk.Label(label='Use Bluetooth', xalign=0, width_chars=20, css_classes=['key']))
        top.append(power)
        scan = Gtk.Button(label='Search for devices')
        top.append(scan)
        spin = Gtk.Spinner()
        top.append(spin)
        p.append(top)
        status = note('')
        p.append(status)
        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        p.append(lst)
        state = {'busy': False, 'gen': 0}

        def clear():
            while lst.get_first_child():
                lst.remove(lst.get_first_child())

        def read():
            """Off the UI thread: the adapter, then every known device with its paired/connected flags."""
            show = self.btctl(['show'])
            if 'No default controller' in show or not show.strip() or 'Powered:' not in show:
                return None
            devs = []
            for line in self.btctl(['devices']).splitlines():
                m = re.match(r'Device ([0-9A-F:]{17}) (.*)', line)
                if m:
                    info = self.btctl(['info', m.group(1)])
                    flag = lambda k: f'{k}: yes' in info
                    devs.append((m.group(1), m.group(2), flag('Paired'), flag('Connected')))
            return 'Powered: yes' in show, devs

        def row(mac, name, paired, connected):
            r = Gtk.Box(spacing=8)
            lab = Gtk.Label(label=name if name.replace('-', ':') != mac else f'Unnamed device ({mac})', xalign=0, hexpand=True)
            r.append(lab)
            if connected:
                r.append(Gtk.Label(label='Connected'))
            actions = ([('Disconnect' if connected else 'Connect', ['disconnect' if connected else 'connect']),
                        ('Remove', ['remove'])] if paired else [('Pair', ['pair', 'trust', 'connect'])])
            for label, cmds in actions:
                b = Gtk.Button(label=label)
                b.connect('clicked', lambda _b, c=cmds, m=mac, lb=label: act(m, c, lb))
                r.append(b)
            return r

        def show(res):
            clear()
            power.set_sensitive(res is not None)
            scan.set_sensitive(bool(res and res[0]))
            if res is None:
                status.set_label('No Bluetooth adapter was found on this PC.')
                return
            on, devs = res
            state['gen'] += 1
            power.handler_block_by_func(on_power)
            power.set_active(on)
            power.handler_unblock_by_func(on_power)
            if not on:
                status.set_label('Bluetooth is off.')
                return
            status.set_label('')
            for title, want in (('My devices', True), ('Nearby devices', False)):
                group = [d for d in devs if d[2] == want]
                if group:
                    lst.append(section(title))
                    for d in group:
                        lst.append(row(*d))
            if not devs:
                lst.append(note('No devices yet. Put your device in pairing mode and choose Search for devices.'))

        def refresh(extra=None):
            def work():
                if extra:
                    extra()
                res = read()
                GLib.idle_add(lambda: (show(res), spin.stop(), setbusy(False)) and False)
            setbusy(True)
            threading.Thread(target=work, daemon=True).start()

        def setbusy(b):
            state['busy'] = b
            if b:
                spin.start()

        def on_power(sw, _p):
            if state['busy']:
                return
            on = sw.get_active()
            refresh(lambda: (run(['rfkill', 'unblock', 'bluetooth']) if on else None,
                             self.btctl(['power', 'on' if on else 'off'])))

        def act(mac, cmds, label):
            if state['busy'] or not self.BT_MAC.match(mac):
                return
            status.set_label(f'{label}\u2026')

            def work():
                out = ''
                for c in cmds:
                    out = self.btctl([c, mac], timeout=40)
                    if c == 'pair' and 'Failed' in out and 'AlreadyExists' not in out:
                        break  # no point trusting or connecting what did not pair
                bad = [ln for ln in out.splitlines() if 'Failed' in ln]
                res = read()
                GLib.idle_add(lambda: (show(res), status.set_label(f'That did not work: {bad[0]}' if bad else status.get_label()),
                                       spin.stop(), setbusy(False)) and False)
            setbusy(True)
            threading.Thread(target=work, daemon=True).start()

        def do_scan(_b):
            if state['busy']:
                return
            status.set_label('Searching\u2026')
            refresh(lambda: self.btctl(['--timeout', '8', 'scan', 'on'], timeout=20))
        power.connect('notify::active', on_power)
        scan.connect('clicked', do_scan)
        refresh()
        return p

    # ---- Network (NetworkManager through nmcli, the way the bar's network flyout talks to it) -------------------------
    NM_TYPES = {'802-11-wireless': 'Wi-Fi', '802-3-ethernet': 'Ethernet', 'vpn': 'VPN', 'wireguard': 'WireGuard'}

    @staticmethod
    def nm(args, timeout=30):
        """nmcli with its terse output: (exit code, stdout, stderr). Code -1 when nmcli is missing or did not answer."""
        try:
            r = subprocess.run(['nmcli'] + args, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout, r.stderr.strip()
        except OSError:
            return -1, '', 'NetworkManager (nmcli) is not installed.'
        except subprocess.TimeoutExpired:
            return -1, '', 'NetworkManager did not answer in time.'

    @staticmethod
    def nm_split(line):
        """One line of nmcli -t: fields are separated by ':' and a ':' or '\\' inside a value is escaped with '\\'."""
        out, cur, i = [], '', 0
        while i < len(line):
            c = line[i]
            if c == '\\' and i + 1 < len(line):
                cur += line[i + 1]
                i += 2
                continue
            if c == ':':
                out.append(cur)
                cur = ''
            else:
                cur += c
            i += 1
        out.append(cur)
        return out

    def nm_connections(self):
        """Every saved connection of a kind we show: [(name, uuid, type, autoconnect, active)], None if NM did not answer."""
        rc, out, _e = self.nm(['-t', '-f', 'NAME,UUID,TYPE,AUTOCONNECT,ACTIVE', 'connection', 'show'])
        if rc != 0:
            return None
        res = []
        for line in out.splitlines():
            f = self.nm_split(line)
            if len(f) >= 5 and f[2] in self.NM_TYPES:
                res.append((f[0], f[1], f[2], f[3] == 'yes', f[4] == 'yes'))
        return res

    def nm_details(self):
        """The connection in use: [(label, value)] from the first connected Wi-Fi or Ethernet device, [] when offline."""
        rc, out, _e = self.nm(['-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device'])
        dev = None
        for line in out.splitlines() if rc == 0 else []:
            f = self.nm_split(line)
            if len(f) >= 4 and f[2] == 'connected' and f[1] in ('wifi', 'ethernet'):
                dev = f
                break
        if not dev:
            return []
        rc, out, _e = self.nm(['-t', '-f', 'GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS', 'device', 'show', dev[0]])
        vals = {}
        for line in out.splitlines():
            k, _s, v = line.partition(':')
            vals.setdefault(re.sub(r'\[\d+\]$', '', k), []).append(v.replace('\\:', ':'))
        speed = ''
        if dev[1] == 'ethernet':
            try:
                with open(f'/sys/class/net/{dev[0]}/speed') as fh:
                    mbit = int(fh.read().strip())
                speed = f'{mbit} Mbit/s' if mbit > 0 else ''
            except (OSError, ValueError):
                pass
        else:
            rc, out, _e = self.nm(['-t', '-f', 'IN-USE,RATE', 'device', 'wifi', 'list', 'ifname', dev[0]])
            for line in out.splitlines():
                f = self.nm_split(line)
                if f and f[0] == '*' and len(f) > 1:
                    speed = f[1]
        first = lambda k: ', '.join(vals.get(k, [])) or '–'
        return [('Connection', dev[3] or dev[0]), ('Type', 'Wi-Fi' if dev[1] == 'wifi' else 'Ethernet'),
                ('IP address', first('IP4.ADDRESS')), ('Gateway', first('IP4.GATEWAY')), ('DNS', first('IP4.DNS')),
                ('MAC address', first('GENERAL.HWADDR')), ('Speed', speed or '–')]

    def nm_conn(self, uuid):
        """The editable settings of one saved connection."""
        keys = ['connection.autoconnect', 'connection.metered', 'ipv4.method', 'ipv4.addresses', 'ipv4.gateway', 'ipv4.dns']
        rc, out, _e = self.nm(['-t', '-f', ','.join(keys), 'connection', 'show', uuid])
        d = {}
        for line in out.splitlines() if rc == 0 else []:
            k, _s, v = line.partition(':')
            d[k] = v.replace('\\:', ':')
        return d

    def nm_modify_and_up(self, uuid, cmd):
        """Change a connection, then re-activate it when it is up so the change takes effect at once."""
        res = self.nm(cmd)
        if res[0] == 0:
            rc, out, _e = self.nm(['-t', '-f', 'UUID', 'connection', 'show', '--active'])
            if uuid in out.split():
                res = self.nm(['connection', 'up', 'uuid', uuid], 60)
        return res

    @staticmethod
    def clean_err(err):
        lines = err.strip().splitlines()
        return re.sub(r'^Error:\s*', '', lines[-1]) if lines else 'That did not work.'

    def page_network(self):
        p = page('Network', 'Wi-Fi and wired connections, VPN and airplane mode.')
        if not shutil.which('nmcli'):
            p.append(note('Network management is not available: NetworkManager is not installed on this PC.'))
            return p
        status = note('')
        quiet = {'n': 0}  # >0 while the page sets a switch itself, so that is not taken for a click

        def bg(work, then=None, msg=None):
            """Run work() off the UI thread, then then(result) on it; msg is shown while it runs."""
            if msg:
                status.set_label(msg)

            def th():
                res = work()
                if then:
                    GLib.idle_add(lambda: then(res) and False)
            threading.Thread(target=th, daemon=True).start()

        def result(res, ok_text):
            status.set_label(ok_text if res[0] == 0 else self.clean_err(res[2]))
            reload()

        def saved(res):
            result(res, 'Saved.')

        # -- Airplane mode
        p.append(section('Airplane mode'))
        air = Gtk.Switch(valign=Gtk.Align.CENTER)
        r = Gtk.Box(spacing=12)
        r.append(Gtk.Label(label='Turn off all wireless', xalign=0, width_chars=20, css_classes=['key']))
        r.append(air)
        r.append(Gtk.Label(label='Wi-Fi, mobile broadband and Bluetooth', css_classes=['note']))
        p.append(r)

        def on_air(sw, _p):
            if quiet['n']:
                return
            on = sw.get_active()

            def work():
                if on:
                    out = self.nm(['radio', 'all', 'off'])
                    run(['rfkill', 'block', 'all'])
                else:
                    run(['rfkill', 'unblock', 'all'])
                    out = self.nm(['radio', 'all', 'on'])
                return out
            bg(work, lambda res: result(res, 'Airplane mode is on.' if on else 'Wireless is back on.'), 'Please wait…')
        air.connect('notify::active', on_air)

        # -- This connection
        p.append(section('This connection'))
        det = Gtk.Grid(column_spacing=14, row_spacing=3)
        p.append(det)

        def show_details(rows):
            while det.get_first_child():
                det.remove(det.get_first_child())
            if not rows:
                det.attach(note('Not connected to a network.'), 0, 0, 2, 1)
            for i, (k, v) in enumerate(rows):
                det.attach(Gtk.Label(label=k, xalign=0, css_classes=['key']), 0, i, 1, 1)
                det.attach(Gtk.Label(label=v, xalign=0, selectable=True), 1, i, 1, 1)

        # -- Known networks
        p.append(section('Known networks'))
        known = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        p.append(known)
        hid = Gtk.Button(label='Join a hidden network…', halign=Gtk.Align.START, margin_top=4)
        p.append(hid)

        # -- VPN
        p.append(section('VPN'))
        vpnbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        p.append(vpnbox)
        imp = Gtk.Button(label='Import a VPN file…', halign=Gtk.Align.START, margin_top=4)
        p.append(imp)
        p.append(note('WireGuard (.conf) and OpenVPN (.ovpn) files are supported.'))
        p.append(status)

        def switch(on, key, uuid):
            sw = Gtk.Switch(active=on, valign=Gtk.Align.CENTER)
            sw.connect('notify::active', lambda s, _p: bg(
                lambda: self.nm(['connection', 'modify', 'uuid', uuid, key, 'yes' if s.get_active() else 'no']), saved))
            return sw

        def conn_row(name, uuid, kind, active, vpn):
            exp = Gtk.Expander()
            head = Gtk.Box(spacing=8)
            head.append(Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3))
            head.append(Gtk.Label(label=kind, css_classes=['note']))
            if active:
                head.append(Gtk.Label(label='Connected', css_classes=['pill', 'ok']))
            exp.set_label_widget(head)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=22, margin_top=6, margin_bottom=8)
            exp.set_child(body)
            acts = Gtk.Box(spacing=8)
            toggle = Gtk.Button(label='Disconnect' if active else 'Connect')
            toggle.connect('clicked', lambda *_a: bg(
                lambda: self.nm(['connection', 'down' if active else 'up', 'uuid', uuid], 60),
                lambda res: result(res, 'Disconnected.' if active else f'Connected to {name}.'), 'Please wait…'))
            acts.append(toggle)
            if kind == 'Wi-Fi':
                pw = Gtk.Button(label='Show password…')
                pw.connect('clicked', lambda *_a: show_password(name, uuid))
                acts.append(pw)
            forget = Gtk.Button(label='Remove' if vpn else 'Forget', css_classes=['destructive-action'])
            forget.connect('clicked', lambda *_a: bg(lambda: self.nm(['connection', 'delete', 'uuid', uuid]),
                                                    lambda res: result(res, f'{name} removed.')))
            acts.append(forget)
            body.append(acts)
            loaded = [False]

            def fill(d):
                if not d:
                    body.append(note('The settings of this connection could not be read.'))
                    return
                body.append(field('Connect automatically', switch(d.get('connection.autoconnect') != 'no', 'connection.autoconnect', uuid), 22))
                if vpn:
                    return
                metered = Gtk.Switch(active=d.get('connection.metered') == 'yes', valign=Gtk.Align.CENTER)
                # "unknown" hands the decision back to NetworkManager (it guesses: a phone's hotspot is metered).
                metered.connect('notify::active', lambda s, _p: bg(
                    lambda: self.nm(['connection', 'modify', 'uuid', uuid, 'connection.metered',
                                     'yes' if s.get_active() else 'unknown']), saved))
                body.append(field('Metered connection', metered, 22))
                body.append(note('Updates are not downloaded in the background on a metered connection (a phone hotspot, a data plan).'))
                body.append(self.ipv4_editor(uuid, d, bg, result))

            def opened(*_a):
                if exp.get_expanded() and not loaded[0]:
                    loaded[0] = True
                    bg(lambda: self.nm_conn(uuid), fill)
            exp.connect('notify::expanded', opened)
            return exp

        def show_lists(res):
            nets, vpns, rows, off = res
            show_details(rows)
            for box, items, vpn in ((known, nets, False), (vpnbox, vpns, True)):
                while box.get_first_child():
                    box.remove(box.get_first_child())
                if items is None:
                    box.append(note('NetworkManager is not running, so connections cannot be shown.'))
                    continue
                for it in items:
                    box.append(conn_row(it[0], it[1], it[2] if vpn else self.NM_TYPES[it[2]], it[3] if vpn else it[4], vpn))
                if not items:
                    box.append(note('No VPN yet. Import a file from your VPN provider.' if vpn else 'No saved networks yet.'))
            hid.set_sensitive(nets is not None)
            imp.set_sensitive(nets is not None)
            quiet['n'] += 1
            air.set_active(off)
            quiet['n'] -= 1
            return False

        def read():
            conns = self.nm_connections()
            nets = [c for c in conns if c[2] in ('802-11-wireless', '802-3-ethernet')] if conns is not None else None
            # A VPN row is (name, uuid, kind, active): 'active' is in the same slot as the others' autoconnect flag shifted by one.
            vpns = [(c[0], c[1], self.NM_TYPES[c[2]], c[4]) for c in conns if c[2] in ('vpn', 'wireguard')] if conns is not None else None
            rc, out, _e = self.nm(['-t', '-f', 'WIFI', 'radio'])
            off = out.strip() == 'disabled' or 'Soft blocked: yes' in run(['rfkill', 'list', 'wifi'])
            return nets, vpns, self.nm_details(), off

        def reload():
            bg(read, show_lists)

        def show_password(name, uuid):
            dlg = self.small_window('Wi-Fi password', 'settings')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=14,
                          margin_start=18, margin_end=18)
            box.append(Gtk.Label(label=f'Show the saved password of {name}?', xalign=0))
            box.append(note('Anyone who can see your screen will be able to read it.'))
            out = Gtk.Label(xalign=0, selectable=True)
            msg = note('')
            btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            cancel, ok = Gtk.Button(label='Close'), Gtk.Button(label='Show password')
            ok.add_css_class('suggested-action')
            cancel.connect('clicked', lambda *_a: dlg.close())

            def go(*_a):
                ok.set_sensitive(False)

                def done(res):
                    if res[0] == 0 and res[1].strip():
                        out.set_label(res[1].strip())
                        msg.set_label('')
                    else:
                        msg.set_label('This network has no saved password.' if res[0] == 0 else self.clean_err(res[2]))
                        ok.set_sensitive(True)
                # --show-secrets works for the user's own connections; NetworkManager refuses it for anyone else's.
                bg(lambda: self.nm(['--show-secrets', '-g', '802-11-wireless-security.psk', 'connection', 'show', 'uuid', uuid]), done)
            ok.connect('clicked', go)
            btns.append(cancel)
            btns.append(ok)
            for w in (out, msg, btns):
                box.append(w)
            dlg.set_child(box)
            dlg.present()

        def hidden(*_a):
            dlg = self.small_window('Join a hidden network', 'settings')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=14,
                          margin_start=18, margin_end=18)
            ssid = Gtk.Entry(placeholder_text='Network name', width_chars=28)
            sec = Gtk.DropDown.new_from_strings(['WPA / WPA2 / WPA3 (password)', 'No security'])
            key = Gtk.PasswordEntry(show_peek_icon=True)
            msg = note('')
            box.append(field('Network name', ssid, 14))
            box.append(field('Security', sec, 14))
            box.append(field('Password', key, 14))
            box.append(msg)
            btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            cancel, ok = Gtk.Button(label='Cancel'), Gtk.Button(label='Connect')
            ok.add_css_class('suggested-action')
            cancel.connect('clicked', lambda *_a: dlg.close())

            def go(*_a):
                name, pw = ssid.get_text().strip(), key.get_text()
                secure = sec.get_selected() == 0
                if not name or (secure and len(pw) < 8):
                    msg.set_label('Type the network name' + (' and a password of at least 8 characters.' if secure else '.'))
                    return
                ok.set_sensitive(False)
                msg.set_label('Connecting…')
                cmd = ['device', 'wifi', 'connect', name, 'hidden', 'yes'] + (['password', pw] if secure else [])

                def done(res):
                    if res[0] == 0:
                        dlg.close()
                        result(res, f'Connected to {name}.')
                    else:
                        msg.set_label(self.clean_err(res[2]))
                        ok.set_sensitive(True)
                bg(lambda: self.nm(cmd, 60), done)
            ok.connect('clicked', go)
            btns.append(cancel)
            btns.append(ok)
            box.append(btns)
            dlg.set_child(box)
            dlg.present()
        hid.connect('clicked', hidden)

        def do_import(*_a):
            fd = Gtk.FileDialog(title='Import a VPN file')
            flt = Gtk.FileFilter(name='VPN files (.conf, .ovpn)')
            for pat in ('*.conf', '*.ovpn'):
                flt.add_pattern(pat)
            store = Gio.ListStore.new(Gtk.FileFilter)
            store.append(flt)
            fd.set_filters(store)

            def chosen(d, res):
                try:
                    path = d.open_finish(res).get_path()
                except GLib.Error:
                    return  # cancelled
                kind = {'.conf': 'wireguard', '.ovpn': 'openvpn'}.get(os.path.splitext(path)[1].lower())
                if not kind:
                    status.set_label('Choose a WireGuard .conf or an OpenVPN .ovpn file.')
                    return
                bg(lambda: self.nm(['connection', 'import', 'type', kind, 'file', path]),
                   lambda res: result(res, 'VPN imported.'), 'Importing…')
            fd.open(self.get_active_window(), None, chosen)
        imp.connect('clicked', do_import)
        reload()
        return p

    def ipv4_editor(self, uuid, d, bg, result):
        """Automatic or fixed IPv4 address, gateway and DNS of one connection (nmcli connection modify ipv4.*)."""
        import ipaddress
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6)
        v.append(Gtk.Label(label='IPv4', xalign=0, css_classes=['sec-title']))
        manual = d.get('ipv4.method') == 'manual'
        mode = Gtk.DropDown.new_from_strings(['Automatic (DHCP)', 'Manual'])
        mode.set_selected(1 if manual else 0)
        addr = Gtk.Entry(text=d.get('ipv4.addresses', '').split(',')[0].strip() if manual else '',
                         placeholder_text='192.168.1.50/24', width_chars=24)
        gw = Gtk.Entry(text=d.get('ipv4.gateway', '').replace('--', ''), placeholder_text='192.168.1.1', width_chars=24)
        dns = Gtk.Entry(text=d.get('ipv4.dns', '').replace('--', '').replace(',', ', '), placeholder_text='1.1.1.1, 8.8.8.8',
                        width_chars=24)
        msg = note('')
        for lab, w in (('Address mode', mode), ('IP address', addr), ('Gateway', gw), ('DNS servers', dns)):
            v.append(field(lab, w, 22))

        def sync(*_a):
            addr.set_sensitive(mode.get_selected() == 1)
            gw.set_sensitive(mode.get_selected() == 1)
        mode.connect('notify::selected', sync)
        sync()
        save = Gtk.Button(label='Apply', halign=Gtk.Align.START)

        def go(*_a):
            try:
                servers = [s for s in re.split(r'[,\s]+', dns.get_text().strip()) if s]
                for s in servers:
                    ipaddress.IPv4Address(s)
                cmd = ['connection', 'modify', 'uuid', uuid, 'ipv4.dns', ' '.join(servers),
                       'ipv4.ignore-auto-dns', 'yes' if servers and mode.get_selected() == 0 else 'no']
                if mode.get_selected() == 1:
                    text = addr.get_text().strip()
                    iface = ipaddress.IPv4Interface(text if '/' in text else text + '/24')
                    g = gw.get_text().strip()
                    if g:
                        ipaddress.IPv4Address(g)
                    cmd += ['ipv4.method', 'manual', 'ipv4.addresses', str(iface), 'ipv4.gateway', g]
                else:
                    cmd += ['ipv4.method', 'auto', 'ipv4.addresses', '', 'ipv4.gateway', '']
            except ValueError:
                msg.set_label('Check the addresses: they should look like 192.168.1.50 (add /24 for the subnet).')
                return
            msg.set_label('')
            bg(lambda: self.nm_modify_and_up(uuid, cmd), lambda res: result(res, 'Saved.'))
        save.connect('clicked', go)
        v.append(save)
        v.append(msg)
        return v

    # ---- Printers ---------------------------------------------------------------------------------------------------
    PRINTER_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z')

    def page_printers(self):
        p = page('Printers', 'Printers on your network, and USB printers, are found automatically.')
        status = note('')
        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        found = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        find = Gtk.Button(label='Look for printers')
        find.set_halign(Gtk.Align.START)
        p.append(section('Your printers'))
        for w in (lst, status, section('Add a printer'), find, found):
            p.append(w)

        def clear(box):
            while box.get_first_child():
                box.remove(box.get_first_child())

        def read():
            out = run(['lpstat', '-p', '-d'])
            default = (re.search(r'system default destination: (\S+)', out) or [None, None])[1]
            names = re.findall(r'^printer (\S+) ', out, re.M)
            return names, default

        def reload():
            names, default = read()
            clear(lst)
            if not names:
                lst.append(note('No printers are set up yet.'))
            for n in names:
                r = Gtk.Box(spacing=8)
                r.append(Gtk.Label(label=n + ('  (default)' if n == default else ''), xalign=0, hexpand=True))
                for label, fn in (('Print test page', lambda _b, n=n: test(n)),
                                  ('Set as default', lambda _b, n=n: admin(['printer', 'default', n], 'Done.')),
                                  ('Remove', lambda _b, n=n: admin(['printer', 'remove', n], 'Removed.'))):
                    if label == 'Set as default' and n == default:
                        continue
                    b = Gtk.Button(label=label)
                    b.connect('clicked', fn)
                    r.append(b)
                lst.append(r)

        def admin(args, ok_text):
            status.set_label('Working\u2026')

            def done(ok, err):
                status.set_label(ok_text if ok else f'That did not work: {err}')
                reload()
            self.admin(args, done, timeout=120)

        def test(name):
            def work():
                r = subprocess.run(['lp', '-d', name, '/usr/share/cups/data/testprint'], capture_output=True, text=True)
                msg = 'Test page sent.' if r.returncode == 0 else f'That did not work: {r.stderr.strip()}'
                GLib.idle_add(lambda: status.set_label(msg) and False)
            threading.Thread(target=work, daemon=True).start()

        def discover(_b):
            find.set_sensitive(False)
            status.set_label('Looking for printers\u2026')
            clear(found)

            def work():
                try:
                    r = subprocess.run(['pkexec', ADMIN, 'printer', 'discover'], capture_output=True, text=True, timeout=120)
                    lines = r.stdout.splitlines() if r.returncode == 0 else []
                except (OSError, subprocess.TimeoutExpired):
                    lines = []
                GLib.idle_add(lambda: shown(lines) and False)
            threading.Thread(target=work, daemon=True).start()

        def shown(lines):
            find.set_sensitive(True)
            names, _d = read()
            n = 0
            for ln in lines:
                uri, _t, info = ln.partition('\t')
                label = re.sub(r'\s+', ' ', info or uri)
                base = re.sub(r'[^A-Za-z0-9_-]+', '_', label).strip('_')[:40] or 'Printer'
                base = base if base[0].isalnum() else 'P' + base
                name, i = base, 2
                while name in names:
                    name, i = f'{base[:36]}_{i}', i + 1
                r = Gtk.Box(spacing=8)
                r.append(Gtk.Label(label=label, xalign=0, hexpand=True))
                b = Gtk.Button(label='Add')
                b.connect('clicked', lambda _b, nm=name, u=uri: admin(['printer', 'add', nm, u], 'Printer added.'))
                r.append(b)
                found.append(r)
                n += 1
            status.set_label('' if n else 'No new printers were found. Check that the printer is on and connected.')

        find.connect('clicked', discover)
        reload()
        return p

    # ---- Keyboard ---------------------------------------------------------------------------------------------------
    def page_keyboard(self):
        p = page('Keyboard', 'Which keys you type with, and how fast they repeat.')
        p.append(section('Layout'))
        choices = [('English (US), then Romanian', 'us,ro', ',std'), ('Romanian, then English (US)', 'ro,us', 'std,'),
                   ('English (US) only', 'us', ''), ('Romanian only', 'ro', 'std')]
        cur = ini_get('input', 'xkb_layout', 'us,ro')
        dd = Gtk.DropDown.new_from_strings([c[0] for c in choices])
        dd.set_selected(next((i for i, c in enumerate(choices) if c[1] == cur), 0))

        def on_sel(d, _p):
            _, layout, variant = choices[d.get_selected()]
            ini_set('input', 'xkb_layout', layout)
            ini_set('input', 'xkb_variant', variant)
        dd.connect('notify::selected', on_sel)
        dd.set_halign(Gtk.Align.START)
        p.append(dd)
        p.append(note('Switch between layouts with Windows key + Space.'))
        p.append(section('Repeat'))
        delay = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 150, 800, 10)
        delay.set_value(float(ini_get('input', 'kb_repeat_delay', '400') or 400))
        delay.connect('value-changed', lambda s: ini_set('input', 'kb_repeat_delay', str(int(s.get_value()))))
        delay.set_size_request(320, -1)
        delay.set_draw_value(False)
        p.append(field('Delay before repeating', delay))
        p.append(note('Left is a short delay, right is a long one.'))
        return p

    # ---- Mouse ------------------------------------------------------------------------------------------------------
    def page_mouse(self):
        p = page('Mouse', 'Pointer speed, scrolling and buttons.')
        p.append(section('Pointer speed'))
        sp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.05)
        sp.set_value(float(ini_get('input', 'mouse_cursor_speed', '0') or 0))
        sp.add_mark(0, Gtk.PositionType.BOTTOM, 'Default')
        sp.connect('value-changed', lambda s: ini_set('input', 'mouse_cursor_speed', f'{s.get_value():.2f}'))
        sp.set_size_request(320, -1)
        sp.set_draw_value(False)
        sp.set_halign(Gtk.Align.START)
        p.append(sp)
        p.append(section('Scrolling and buttons'))
        nat = Gtk.CheckButton(label='Natural scrolling (content moves with your hand, like on a phone)')
        nat.set_active(ini_get('input', 'mouse_natural_scroll', 'false') == 'true')
        nat.connect('toggled', lambda c: ini_set('input', 'mouse_natural_scroll', 'true' if c.get_active() else 'false'))
        p.append(nat)
        left = Gtk.CheckButton(label='Swap left and right buttons (left-handed)')
        left.set_active(ini_get('input', 'left_handed_mode', 'false') == 'true')
        left.connect('toggled', lambda c: ini_set('input', 'left_handed_mode', 'true' if c.get_active() else 'false'))
        p.append(left)
        return p

    # ---- Desktop (icons and widgets; the desktop layer watches its settings file) ---------------------------------------
    def page_desktop(self):
        p = page('Desktop', 'What the desktop shows. Right-click the desktop for the same choices.')
        p.append(section('On the desktop'))
        path = os.path.join(CONF_DIR, 'desktop.json')

        def load():
            try:
                return json.load(open(path))
            except (OSError, ValueError):
                return {}

        def save(**kw):
            cfg = load()
            cfg.update(kw)
            os.makedirs(CONF_DIR, exist_ok=True)
            with open(path + '.tmp', 'w') as f:
                json.dump(cfg, f)
            os.replace(path + '.tmp', path)
        cfg = load()
        icons = Gtk.CheckButton(label='Show desktop icons')
        icons.set_active(cfg.get('icons', True) is not False)
        icons.connect('toggled', lambda c: save(icons=c.get_active()))
        p.append(icons)
        gadgets = Gtk.CheckButton(label='Show widgets (clock, calendar, computer load, weather)')
        gadgets.set_active(cfg.get('gadgets', True) is not False)
        gadgets.connect('toggled', lambda c: save(gadgets=c.get_active()))
        p.append(gadgets)
        p.append(section('Weather'))
        city = Gtk.Entry(text=str(cfg.get('city') or 'Bucharest'), width_chars=24)
        row = field('City', city)
        status = note('')

        def set_city(*_):
            name = city.get_text().strip()
            if not name:
                return
            status.set_label('Looking it up…')

            def work():
                import urllib.parse
                import urllib.request
                try:
                    url = ('https://geocoding-api.open-meteo.com/v1/search?count=1&name=' + urllib.parse.quote(name))
                    hit = (json.load(urllib.request.urlopen(url, timeout=10)).get('results') or [None])[0]
                except (OSError, ValueError):
                    hit = None

                def done():
                    if hit:
                        save(city=hit['name'], lat=hit['latitude'], lon=hit['longitude'])
                        status.set_label(f"Weather for {hit['name']}, {hit.get('country', '')}.")
                    else:
                        status.set_label('Not found (or no internet).')
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()
        city.connect('activate', set_city)
        p.append(row)
        p.append(note('Type a city and press Enter.'))
        p.append(status)
        return p

    # ---- Sound (PipeWire, through wpctl) --------------------------------------------------------------------------------
    @staticmethod
    def wpctl_devices(text):
        """{'Sinks': [(id, name, is_default)], 'Sources': [...]} from `wpctl status` (only its Audio tree)."""
        found, top, kind = {'Sinks': [], 'Sources': []}, '', None
        for line in text.splitlines():
            if line and line[0] not in ' │├└─':
                top, kind = line.strip(), None
                continue
            if not top.startswith('Audio'):
                continue
            t = line.strip(' │├└─')
            if t.endswith(':'):
                kind = t[:-1]
                continue
            m = re.match(r'(\*)?\s*(\d+)\.\s+(.*?)(\s+\[vol:.*)?$', t)
            if m and kind in found:
                found[kind].append((m.group(2), m.group(3), bool(m.group(1))))
        return found

    @staticmethod
    def audio_streams():
        """Apps playing sound right now: [(node id, app name)], from pw-dump (the Stream/Output/Audio nodes)."""
        try:
            objs = json.loads(run(['pw-dump']) or '[]')
        except ValueError:
            return []
        out = []
        for o in objs:
            props = (o.get('info') or {}).get('props') or {}
            if o.get('type') == 'PipeWire:Interface:Node' and props.get('media.class') == 'Stream/Output/Audio':
                name = props.get('application.name') or props.get('node.description') or props.get('media.name') or 'Sound'
                out.append((str(o['id']), name))
        return out

    @staticmethod
    def fire(cmd):
        """Run a command without waiting for it (sliders send many changes; the window must not stall on them)."""
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    @staticmethod
    def get_volume(target):
        """(0-100, muted) of a wpctl target such as @DEFAULT_AUDIO_SINK@ or a node id; None when unknown."""
        out = run(['wpctl', 'get-volume', target]).split()
        try:
            return round(float(out[1]) * 100), '[MUTED]' in out
        except (IndexError, ValueError):
            return None

    def volume_row(self, target, label=None):
        """A volume slider with a mute box for one wpctl target; returns (row, refresh) where refresh re-reads wpctl."""
        row = Gtk.Box(spacing=10)
        if label:
            row.append(Gtk.Label(label=label, xalign=0, width_chars=20, max_width_chars=20, ellipsize=3, css_classes=['key']))
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_size_request(280, -1)
        scale.set_draw_value(False)
        mute = Gtk.CheckButton(label='Mute')
        busy = [False]

        def refresh():
            v = self.get_volume(target)
            busy[0] = True
            scale.set_value(v[0] if v else 50)
            mute.set_active(bool(v and v[1]))
            busy[0] = False
        scale.connect('value-changed', lambda s: busy[0] or self.fire(['wpctl', 'set-volume', target,
                                                                      f'{s.get_value() / 100:.2f}']))
        mute.connect('toggled', lambda c: busy[0] or self.fire(['wpctl', 'set-mute', target, '1' if c.get_active() else '0']))
        refresh()
        row.append(scale)
        row.append(mute)
        return row, refresh

    def device_picker(self, p, title, devices, refreshers):
        """A drop-down of audio devices that makes the chosen one the default (wpctl set-default)."""
        if not devices:
            p.append(note(f'No {title.split()[0].lower()} device was found.'))
            return
        dd = Gtk.DropDown.new_from_strings([n for _i, n, _d in devices])
        dd.set_selected(next((i for i, d in enumerate(devices) if d[2]), 0))

        def chosen(d, _p):
            run(['wpctl', 'set-default', devices[d.get_selected()][0]])
            for fn in refreshers:
                fn()
        dd.connect('notify::selected', chosen)
        p.append(field(title, dd))

    def page_sound(self):
        p = page('Sound', 'Volume, where sound plays and records, and MWX 7’s own sounds.')
        self.sound_live = lambda on: None  # replaced below when the sound server can be reached
        status = run_cached(['wpctl', 'status'], 2) if shutil.which('wpctl') else ''
        if not status.strip():
            p.append(note('The sound server is not running here, so volume and devices cannot be shown.'))
            self.sound_extras(p)
            return p
        dev = self.wpctl_devices(status)
        refreshers = []
        # Output: the device, its volume, a test sound.
        p.append(section('Output'))
        row, r_out = self.volume_row('@DEFAULT_AUDIO_SINK@')
        refreshers.append(r_out)
        self.device_picker(p, 'Play sound through', dev['Sinks'], refreshers)
        p.append(field('Volume', row))
        test = Gtk.Button(label='Test')
        test.add_css_class('suggested-action')
        test.connect('clicked', lambda _b: self.play_test())
        p.append(field('', test))
        # Input: the device, its volume and a level meter that only runs while this page is on screen.
        p.append(section('Input'))
        mics = [d for d in dev['Sources'] if 'Monitor' not in d[1]]
        meter = None
        self.device_picker(p, 'Record sound from', mics, refreshers)
        if mics:
            row_in, r_in = self.volume_row('@DEFAULT_AUDIO_SOURCE@')
            refreshers.append(r_in)
            p.append(field('Volume', row_in))
            meter = Gtk.LevelBar.new_for_interval(0, 1)
            meter.set_size_request(280, 10)
            p.append(field('Level', meter))
        # Apps: one slider per app that is playing sound right now.
        p.append(section('Apps'))
        apps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        p.append(apps)
        self.sound_extras(p)

        st = {'ids': None, 'proc': None, 'tick': 0, 'apps': 0}

        def fill_apps():
            streams = self.audio_streams()
            ids = [s[0] for s in streams]
            if ids == st['ids']:
                return
            st['ids'] = ids
            while apps.get_first_child():
                apps.remove(apps.get_first_child())
            if not streams:
                apps.append(note('No app is playing sound.'))
            for sid, name in streams:
                apps.append(self.volume_row(sid, name)[0])

        def level():
            proc = st['proc']
            if proc is None:
                return False
            peak = 0
            try:
                data = proc.stdout.read(8192)  # non-blocking pipe: None when nothing has arrived
            except OSError:
                data = None
            if data:
                samples = struct.unpack(f'<{len(data) // 2}h', data[:len(data) // 2 * 2])
                peak = max(abs(s) for s in samples) / 32768
            meter.set_value(min(1.0, peak * 2.5))
            return True

        def live(on):
            """Start (page visible) or stop (hidden or window closed) everything that polls: the meter and the app list."""
            if on and not st['apps']:
                fill_apps()
                st['apps'] = GLib.timeout_add_seconds(3, lambda: fill_apps() or True)
                if meter is not None and shutil.which('pw-record'):
                    try:
                        st['proc'] = subprocess.Popen(
                            ['pw-record', '--rate', '8000', '--channels', '1', '--format', 's16', '-'],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                        os.set_blocking(st['proc'].stdout.fileno(), False)
                        st['tick'] = GLib.timeout_add(90, level)
                    except OSError:
                        st['proc'] = None
                for fn in refreshers:
                    fn()
            elif not on:
                for key in ('apps', 'tick'):
                    if st[key]:
                        GLib.source_remove(st[key])
                        st[key] = 0
                if st['proc']:
                    st['proc'].kill()
                    st['proc'].wait()
                    st['proc'] = None
                st['ids'] = None
                if meter is not None:
                    meter.set_value(0)
        self.sound_live = live
        return p

    @staticmethod
    def play_test():
        """A short sound through the default output: MWX 7's own notification sound, else the sound theme's."""
        snd = '/usr/share/mwx7/sounds/notify.ogg'
        if shutil.which('pw-play') and os.path.exists(snd):
            Settings.fire(['pw-play', snd])
        elif shutil.which('canberra-gtk-play'):
            Settings.fire(['canberra-gtk-play', '-i', 'audio-test-signal'])

    def sound_extras(self, p):
        # MWX 7's own sounds: the startup and log-off chimes and the notification sound.
        p.append(section('MWX 7 sounds'))
        off = os.path.join(CONF_DIR, 'sounds-off')
        chimes = Gtk.CheckButton(label='Play sounds (startup, log off, notifications)')
        chimes.set_active(not os.path.exists(off))

        def toggled(c):
            if c.get_active():
                if os.path.exists(off):
                    os.remove(off)
                subprocess.Popen(['/usr/share/mwx7/bin/mwx7-sound', 'notify'])
            else:
                os.makedirs(CONF_DIR, exist_ok=True)
                open(off, 'w').close()
        chimes.connect('toggled', toggled)
        p.append(chimes)

    # ---- Date & time ------------------------------------------------------------------------------------------------
    # ---- the shell's own choices (Dock; clock format), as on the web: shell.json, followed live by the bar and dock --
    SHELL_JSON = os.path.join(CONF_DIR, 'shell.json')

    def shell_get(self, key, default):
        try:
            v = json.load(open(self.SHELL_JSON)).get(key, default)
        except (OSError, ValueError, AttributeError):
            v = default
        return v

    def shell_set(self, key, value):
        try:
            c = json.load(open(self.SHELL_JSON))
            c = c if isinstance(c, dict) else {}
        except (OSError, ValueError):
            c = {}
        c[key] = value
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(self.SHELL_JSON + '.tmp', 'w') as f:
            json.dump(c, f)
        os.replace(self.SHELL_JSON + '.tmp', self.SHELL_JSON)

    def shell_check(self, label, key, default=True):
        c = Gtk.CheckButton(label=label)
        c.set_active(self.shell_get(key, default) is not False if default else self.shell_get(key, False) is True)
        c.connect('toggled', lambda b: self.shell_set(key, b.get_active()))
        return c

    def page_dock(self):
        p = page('Dock', 'The row of app icons at the bottom of the screen.')
        p.append(section('Magnification'))
        p.append(self.shell_check('Icons grow under the pointer', 'dock_magnify'))
        p.append(section('Icon size'))
        row = Gtk.Box(spacing=0, halign=Gtk.Align.START)
        row.add_css_class('linked')
        cur = self.shell_get('dock_size', 'medium')
        first = None
        for key in ('small', 'medium', 'large'):
            b = Gtk.ToggleButton(label=key.capitalize(), active=key == cur)
            if first:
                b.set_group(first)
            first = first or b
            b.connect('toggled', lambda btn, k=key: btn.get_active() and self.shell_set('dock_size', k))
            row.append(b)
        p.append(row)
        return p

    def page_datetime(self):
        p = page('Date & time', 'The clock in the status bar, and your time zone.')
        p.append(section('Clock'))
        p.append(self.shell_check('Use 24-hour clock', 'clock24'))
        p.append(self.shell_check('Show seconds (uses a little more power)', 'clock_seconds', default=False))
        p.append(section('Time zone'))
        zones = [z for z in run(['timedatectl', 'list-timezones']).split() if '/' in z]
        cur = run(['timedatectl', 'show', '-p', 'Timezone', '--value']).strip() or 'Europe/Bucharest'
        if not zones:
            zones = [cur]
        model = Gtk.StringList.new(zones)
        dd = Gtk.DropDown(model=model)
        dd.set_enable_search(True)
        dd.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, 'string'))
        if cur in zones:
            dd.set_selected(zones.index(cur))
        status = note('')

        def on_zone(d, _p):
            z = zones[d.get_selected()]
            r = subprocess.run(['timedatectl', 'set-timezone', z], capture_output=True, text=True)
            status.set_label('Time zone set. The clock updates within a few seconds.' if r.returncode == 0
                             else 'Could not change the time zone: ' + (r.stderr.strip() or 'not allowed'))
        dd.connect('notify::selected', on_zone)
        dd.set_halign(Gtk.Align.START)
        p.append(dd)
        p.append(status)
        return p

    # ---- Ease of Access ---------------------------------------------------------------------------------------------
    # Text size and cursor size go to GSettings (GTK apps, this one and the shell included, follow them live). High contrast
    # is a marked block in the user's gtk.css (GTK_THEME overrides the gtk-theme setting in MWX 7's session, so switching the
    # theme would do nothing). Magnifier is Wayfire's zoom plugin: in 0.9 it only zooms with modifier + scroll wheel.
    A11Y_JSON = os.path.join(CONF_DIR, 'access.json')
    HC_BEGIN, HC_END = '/* mwx7-high-contrast begin */', '/* mwx7-high-contrast end */'
    HC_CSS = """
window, window.background, dialog, .background, popover contents, list, scrolledwindow, viewport, box.page { background: #000000; background-image: none; color: #ffffff; }
* { border-color: #ffffff; text-shadow: none; }
label, .note, .key, .section, .page-title, row, row label { color: #ffffff; }
button, entry, spinbutton, dropdown, combobox, textview, textview text, text { background: #000000; background-image: none; color: #ffffff; border: 2px solid #ffffff; box-shadow: none; }
button:hover, row:hover { background: #ffffff; background-image: none; color: #000000; }
button:hover label, row:hover label { color: #000000; }
row:selected, :selected, selection { background: #ffff00; background-image: none; color: #000000; }
row:selected label { color: #000000; }
*:focus-visible, *:focus { outline: 3px solid #ffff00; outline-offset: 1px; }
link, link:visited { color: #66ccff; }
"""

    @staticmethod
    def gsettings(schema='org.gnome.desktop.interface'):
        """GSettings for a schema, or None when it is not installed (Gio.Settings would abort the process)."""
        src = Gio.SettingsSchemaSource.get_default()
        return Gio.Settings.new(schema) if src and src.lookup(schema, True) else None

    def a11y_get(self, key, default=None):
        try:
            return json.load(open(self.A11Y_JSON)).get(key, default)
        except (OSError, ValueError, AttributeError):
            return default

    def a11y_set(self, key, value):
        try:
            c = json.load(open(self.A11Y_JSON))
            c = c if isinstance(c, dict) else {}
        except (OSError, ValueError):
            c = {}
        c[key] = value
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(self.A11Y_JSON + '.tmp', 'w') as f:
            json.dump(c, f)
        os.replace(self.A11Y_JSON + '.tmp', self.A11Y_JSON)

    def high_contrast_files(self, on):
        """Add or remove our marked block in the user's GTK 3 and GTK 4 stylesheets; the rest of those files is left alone."""
        for ver in ('gtk-4.0', 'gtk-3.0'):
            path = os.path.join(GLib.get_user_config_dir(), ver, 'gtk.css')
            try:
                text = open(path).read()
            except OSError:
                text = ''
            text = re.sub(re.escape(self.HC_BEGIN) + r'.*?' + re.escape(self.HC_END) + r'\n?', '', text, flags=re.S)
            if on:
                css = self.HC_CSS if ver == 'gtk-4.0' else self.HC_CSS.replace(':focus-visible', ':focus')
                text = text.rstrip('\n') + ('\n' if text.strip() else '') + f'{self.HC_BEGIN}\n{css}{self.HC_END}\n'
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w') as f:
                    f.write(text)
            except OSError:
                pass
        # This window follows at once; apps already open pick the stylesheet up the next time they start.
        if not hasattr(self, 'hc_provider'):
            self.hc_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.hc_provider,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
        self.hc_provider.load_from_string(self.HC_CSS if on else '')
        g = self.gsettings('org.gnome.desktop.a11y.interface')
        if g:
            g.set_boolean('high-contrast', on)

    @staticmethod
    def high_contrast_on():
        try:
            return 'mwx7-high-contrast begin' in open(os.path.join(GLib.get_user_config_dir(), 'gtk-4.0', 'gtk.css')).read()
        except OSError:
            return False

    @staticmethod
    def plugins_get():
        return ini_get('core', 'plugins', '').split()

    def set_magnifier(self, on):
        plugins = [x for x in self.plugins_get() if x != 'zoom']
        if on and plugins:
            plugins.append('zoom')
        if plugins:
            ini_set('core', 'plugins', ' '.join(plugins))

    def page_access(self):
        p = page('Ease of Access', 'Make the screen easier to see and the desktop calmer to use.')
        g = self.gsettings()
        p.append(section('Text size'))
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100, 200, 5)
        scale.set_value(round((g.get_double('text-scaling-factor') if g else 1.0) * 100))
        for v in (100, 150, 200):
            scale.add_mark(v, Gtk.PositionType.BOTTOM, f'{v}%')
        scale.set_size_request(360, -1)
        scale.set_halign(Gtk.Align.START)
        pending = []

        def apply_scale():
            pending.clear()
            if g:
                g.set_double('text-scaling-factor', round(scale.get_value()) / 100)
            return False

        def on_scale(_s):
            # Settings itself grows with the text, which would move the slider under the pointer: wait until it rests.
            for src in pending:
                GLib.source_remove(src)
            pending[:] = [GLib.timeout_add(450, apply_scale)]
        scale.connect('value-changed', on_scale)
        p.append(scale)
        p.append(note('Text in this window and in apps that follow the system text size changes as soon as you stop dragging.'
                      if g else 'Text size needs the GNOME settings schemas, which are not installed.'))

        p.append(section('Contrast'))
        hc = Gtk.CheckButton(label='High contrast: white on black with yellow selection')
        hc.set_active(self.high_contrast_on())
        hc.connect('toggled', lambda c: self.high_contrast_files(c.get_active()))
        p.append(hc)
        p.append(note('Applies to this window now and to apps the next time they start.'))

        p.append(section('Pointer'))
        sizes = [(24, 'Normal'), (32, 'Large'), (48, 'Larger'), (64, 'Extra large'), (96, 'Huge')]
        cur = int(ini_get('input', 'cursor_size', '24') or 24)

        def set_cursor(v):
            ini_set('input', 'cursor_size', str(v))
            if g:
                g.set_int('cursor-size', v)
        p.append(field('Cursor size', self.choice(sizes, cur, set_cursor)))
        p.append(note('The pointer changes at once; apps already open may keep the old size until they restart.'))

        p.append(section('Motion'))
        red = Gtk.CheckButton(label='Reduce motion (turns window animations off)')
        red.set_active(ini_get('mwx7-animate', 'level', 'full') == 'off')

        def on_motion(c):
            if c.get_active():
                self.a11y_set('prev_anim', ini_get('mwx7-animate', 'level', 'full'))
                level = 'off'
            else:
                level = self.a11y_get('prev_anim', 'full')
                level = level if level in ('full', 'reduced') else 'full'
            # The same record Display -> Animations writes, so a level chosen here is never overridden by mwx7-perf.
            os.makedirs(CONF_DIR, exist_ok=True)
            with open(os.path.join(CONF_DIR, 'animations.json'), 'w') as f:
                json.dump({'level': level}, f)
            try:
                os.unlink(os.path.join(CONF_DIR, 'perf-animations.json'))
            except OSError:
                pass
            ini_set('mwx7-animate', 'level', level)
        red.connect('toggled', on_motion)
        p.append(red)
        p.append(note('Display -> Animations has the finer choice (Full, Reduced, Off).'))

        p.append(section('Magnifier'))
        mag = Gtk.CheckButton(label='Zoom the screen with Windows key + scroll wheel')
        mag.set_active('zoom' in self.plugins_get())
        mag.connect('toggled', lambda c: self.set_magnifier(c.get_active()))
        p.append(mag)
        p.append(note('Hold the Windows key and scroll up to zoom in, down to zoom out. Wayfire 0.9 has no zoom keys.'))
        return p

    # ---- Language & region ------------------------------------------------------------------------------------------
    LANG_NAMES = {
        'af': 'Afrikaans', 'ar': 'Arabic', 'bg': 'Bulgarian', 'ca': 'Catalan', 'cs': 'Czech', 'da': 'Danish', 'de': 'German',
        'el': 'Greek', 'en': 'English', 'es': 'Spanish', 'et': 'Estonian', 'fi': 'Finnish', 'fr': 'French', 'he': 'Hebrew',
        'hi': 'Hindi', 'hr': 'Croatian', 'hu': 'Hungarian', 'id': 'Indonesian', 'it': 'Italian', 'ja': 'Japanese',
        'ko': 'Korean', 'lt': 'Lithuanian', 'lv': 'Latvian', 'nb': 'Norwegian Bokmal', 'nl': 'Dutch', 'pl': 'Polish',
        'pt': 'Portuguese', 'ro': 'Romanian', 'ru': 'Russian', 'sk': 'Slovak', 'sl': 'Slovenian', 'sr': 'Serbian',
        'sv': 'Swedish', 'th': 'Thai', 'tr': 'Turkish', 'uk': 'Ukrainian', 'vi': 'Vietnamese', 'zh': 'Chinese'}
    COUNTRIES = {
        'AT': 'Austria', 'AU': 'Australia', 'BE': 'Belgium', 'BG': 'Bulgaria', 'BR': 'Brazil', 'CA': 'Canada',
        'CH': 'Switzerland', 'CN': 'China', 'CZ': 'Czechia', 'DE': 'Germany', 'DK': 'Denmark', 'ES': 'Spain', 'FI': 'Finland',
        'FR': 'France', 'GB': 'United Kingdom', 'GR': 'Greece', 'HR': 'Croatia', 'HU': 'Hungary', 'IE': 'Ireland',
        'IL': 'Israel', 'IN': 'India', 'IT': 'Italy', 'JP': 'Japan', 'KR': 'Korea', 'MD': 'Moldova', 'MX': 'Mexico',
        'NL': 'Netherlands', 'NO': 'Norway', 'NZ': 'New Zealand', 'PL': 'Poland', 'PT': 'Portugal', 'RO': 'Romania',
        'RS': 'Serbia', 'RU': 'Russia', 'SE': 'Sweden', 'SI': 'Slovenia', 'SK': 'Slovakia', 'TR': 'Turkey', 'UA': 'Ukraine',
        'US': 'United States', 'ZA': 'South Africa'}
    REGION_CONF = os.path.join(GLib.get_user_config_dir(), 'environment.d', '50-mwx7-region.conf')
    REGION_KEYS = ('LC_TIME', 'LC_NUMERIC', 'LC_MONETARY', 'LC_PAPER', 'LC_MEASUREMENT')
    KEY_LAYOUTS = [('us', '', 'English (US)'), ('ro', 'std', 'Romanian (standard)'), ('ro', '', 'Romanian (legacy)'),
                   ('gb', '', 'English (UK)'), ('de', '', 'German'), ('fr', '', 'French'), ('es', '', 'Spanish'),
                   ('it', '', 'Italian'), ('pl', '', 'Polish'), ('hu', '', 'Hungarian'), ('bg', '', 'Bulgarian'),
                   ('ru', '', 'Russian'), ('cz', '', 'Czech'), ('pt', '', 'Portuguese'), ('nl', '', 'Dutch')]

    @classmethod
    def locale_label(cls, loc):
        m = re.match(r'([a-z]{2,3})_([A-Z]{2})', loc)
        if not m:
            return loc
        return f'{cls.LANG_NAMES.get(m.group(1), m.group(1))} ({cls.COUNTRIES.get(m.group(2), m.group(2))})'

    @staticmethod
    def installed_locales():
        """Generated UTF-8 locales, spelled the way /usr/share/i18n/SUPPORTED does (ro_RO.UTF-8)."""
        out = run(['locale', '-a']).split()
        return {l.replace('.utf8', '.UTF-8') for l in out if re.fullmatch(r'[a-z]{2,3}_[A-Z]{2}\.utf8', l)}

    @staticmethod
    def supported_locales():
        try:
            lines = open('/usr/share/i18n/SUPPORTED', encoding='utf-8').read().splitlines()
        except OSError:
            return set()
        return {l.split()[0] for l in lines if re.fullmatch(r'[a-z]{2,3}_[A-Z]{2}\.UTF-8 UTF-8\s*(#.*)?', l.strip())}

    @staticmethod
    def system_lang():
        try:
            for l in open('/etc/default/locale'):
                m = re.match(r'LANG="?([^"\s]+)"?', l)
                if m:
                    return m.group(1)
        except OSError:
            pass
        return os.environ.get('LANG', 'en_US.UTF-8')

    def read_region(self):
        try:
            for l in open(self.REGION_CONF):
                k, _, v = l.strip().partition('=')
                if k == 'LC_TIME':
                    return v
        except OSError:
            pass
        return ''

    def write_region(self, loc):
        """~/.config/environment.d drop-in (systemd's format; mwx7-session reads it too). No choice removes the file."""
        if not loc:
            try:
                os.unlink(self.REGION_CONF)
            except OSError:
                pass
            return
        os.makedirs(os.path.dirname(self.REGION_CONF), exist_ok=True)
        with open(self.REGION_CONF, 'w') as f:
            f.write('# Written by MWX 7 Settings -> Language & region.\n' + ''.join(f'{k}={loc}\n' for k in self.REGION_KEYS))

    @staticmethod
    def region_example(loc):
        code = ("import locale,datetime,sys;locale.setlocale(locale.LC_ALL,sys.argv[1]);"
                "print(datetime.datetime(2026,3,9,18,45).strftime('%x  %X'));"
                "print(locale.format_string('%.2f',1234567.89,grouping=True))")
        out = run(['python3', '-I', '-c', code, loc]).strip().splitlines()
        return f'{out[0]}      {out[1]}' if len(out) == 2 else ''

    def page_language(self):
        p = page('Language & region', 'The language of the system, how dates and numbers look, and the keyboards you type with.')
        installed, supported = self.installed_locales(), self.supported_locales()
        names = sorted(installed | supported | {'en_US.UTF-8'}, key=lambda l: (self.locale_label(l), l))
        status = note('')

        def label(l):
            return self.locale_label(l) + ('' if l in installed else '  (downloaded when chosen)')

        p.append(section('Language'))
        cur = self.system_lang()
        dd = Gtk.DropDown.new_from_strings([label(l) for l in names])
        dd.set_enable_search(True)
        dd.set_selected(names.index(cur) if cur in names else 0)

        def on_lang(d, _p):
            loc = names[d.get_selected()]
            if loc == self.system_lang():
                return
            status.set_label('Changing the language...')

            def done(ok, err):
                if ok:
                    installed.add(loc)
                    status.set_label('Language set. Apps that support it use it the next time you sign in.')
                else:
                    status.set_label('Could not change the language: ' + (err or 'not allowed'))
            self.admin(['locale', 'set', loc], done)
        dd.connect('notify::selected', on_lang)
        p.append(field('System language', dd))
        p.append(note("Apps that support it. MWX 7's own windows are in English for now."))

        p.append(section('Regional format'))
        fmt_names = [''] + names
        fdd = Gtk.DropDown.new_from_strings(['Same as the language'] + [label(l) for l in names])
        fdd.set_enable_search(True)
        fcur = self.read_region()
        fdd.set_selected(fmt_names.index(fcur) if fcur in fmt_names else 0)
        example = note('')

        def show_example(loc):
            example.set_label(('Example: ' + self.region_example(loc)) if loc in installed else '')

        def on_fmt(d, _p):
            loc = fmt_names[d.get_selected()]

            def apply():
                self.write_region(loc)
                show_example(loc)
                status.set_label('Formats saved. Apps use them the next time you sign in.')
            if loc and loc not in installed:
                status.set_label('Preparing the formats, this takes a moment...')

                def added(ok, err):
                    if ok:
                        installed.add(loc)
                        apply()
                    else:
                        status.set_label('Could not prepare them: ' + (err or 'not allowed'))
                self.admin(['locale', 'add', loc], added)
            else:
                apply()
        fdd.connect('notify::selected', on_fmt)
        p.append(field('Dates, numbers, currency', fdd))
        p.append(example)
        show_example(fcur)
        p.append(status)

        self.layout_section(p)
        return p

    # Keyboard layouts as Wayfire's [input] xkb_layout / xkb_variant: two comma lists that line up by position.
    def xkb_names(self):
        """{(layout, variant): name}: the curated list first, then everything X11's rules file knows."""
        names = {(l, v): n for l, v, n in self.KEY_LAYOUTS}
        try:
            text = open('/usr/share/X11/xkb/rules/base.lst', encoding='utf-8', errors='replace').read()
        except OSError:
            return names
        sec = None
        for line in text.splitlines():
            if line.startswith('!'):
                sec = line[1:].strip()
                continue
            if sec == 'layout':
                m = re.match(r'\s+([a-z0-9_]+)\s+(.+)', line)
                if m and (m.group(1), '') not in names:
                    names[(m.group(1), '')] = m.group(2).strip()
            elif sec == 'variant':
                m = re.match(r'\s+([a-z0-9_]+)\s+([a-z0-9_]+): (.+)', line)
                if m and (m.group(2), m.group(1)) not in names:
                    names[(m.group(2), m.group(1))] = m.group(3).strip()
        return names

    @staticmethod
    def switch_shortcut():
        opts = ini_get('input', 'xkb_options', 'grp:win_space_toggle')
        for o, label in (('grp:win_space_toggle', 'Windows key + Space'), ('grp:alt_shift_toggle', 'Alt + Shift'),
                         ('grp:ctrl_shift_toggle', 'Ctrl + Shift'), ('grp:alt_space_toggle', 'Alt + Space')):
            if o in opts:
                return label
        return 'the shortcut set in your keyboard options'

    def layout_section(self, p):
        names = self.xkb_names()
        p.append(section('Keyboard layouts'))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        p.append(box)
        hint = note('')

        def current():
            lay = [x.strip() for x in ini_get('input', 'xkb_layout', 'us').split(',')]
            var = [x.strip() for x in ini_get('input', 'xkb_variant', '').split(',')]
            var += [''] * (len(lay) - len(var))
            return [(l, v) for l, v in zip(lay, var) if l] or [('us', '')]

        def save(pairs):
            ini_set('input', 'xkb_layout', ','.join(l for l, _v in pairs))
            ini_set('input', 'xkb_variant', ','.join(v for _l, v in pairs))
            refill()

        def refill():
            while box.get_first_child():
                box.remove(box.get_first_child())
            pairs = current()
            for i, pr in enumerate(pairs):
                r = Gtk.Box(spacing=6)
                r.append(Gtk.Label(label=('Default: ' if i == 0 else '') + names.get(pr, f'{pr[0]} {pr[1]}'.strip()),
                                   xalign=0, width_chars=34))
                for icon, tip, delta in (('go-up-symbolic', 'Move up', -1), ('go-down-symbolic', 'Move down', 1)):
                    b = Gtk.Button.new_from_icon_name(icon)
                    b.set_tooltip_text(tip)
                    b.set_sensitive(0 <= i + delta < len(pairs))

                    def move(_b, i=i, delta=delta):
                        q = current()
                        q[i], q[i + delta] = q[i + delta], q[i]
                        save(q)
                    b.connect('clicked', move)
                    r.append(b)
                rm = Gtk.Button.new_from_icon_name('list-remove-symbolic')
                rm.set_tooltip_text('Remove')
                rm.set_sensitive(len(pairs) > 1)
                rm.connect('clicked', lambda _b, i=i: save([x for j, x in enumerate(current()) if j != i]))
                r.append(rm)
                box.append(r)
            hint.set_label(f'Switch between layouts with {self.switch_shortcut()}.' if len(pairs) > 1
                           else 'Add a second layout to switch between them.')

        keys = sorted(names, key=lambda k: (names[k].lower(), k))
        add = Gtk.DropDown.new_from_strings([names[k] for k in keys])
        add.set_enable_search(True)
        add.set_selected(keys.index(('ro', 'std')) if ('ro', 'std') in keys else 0)
        addb = Gtk.Button(label='Add layout')

        def on_add(_b):
            k, q = keys[add.get_selected()], current()
            if k not in q:
                save(q + [k])
        addb.connect('clicked', on_add)
        row = Gtk.Box(spacing=8)
        row.append(add)
        row.append(addb)
        refill()
        p.append(row)
        p.append(hint)

    # ---- Account ----------------------------------------------------------------------------------------------------
    @staticmethod
    def has_password():
        try:
            return run(['passwd', '-S']).split()[1] != 'NP'
        except IndexError:
            return True

    @staticmethod
    def autologin():
        try:
            text = open(GREETD).read()
        except OSError:
            return False
        return '[initial_session]' in text and f'user = "{USER}"' in text.split('[initial_session]', 1)[1]

    def admin(self, args, done, stdin=None, timeout=300):
        """Runs mwx7-admin through pkexec (MWX 7 asks for the password if the account has one) off the UI thread."""
        def work():
            try:
                r = subprocess.run(['pkexec', ADMIN] + args, input=stdin, capture_output=True, text=True, timeout=timeout)
                ok, err = r.returncode == 0, (r.stderr.strip().splitlines() or [''])[-1]
            except (OSError, subprocess.TimeoutExpired) as e:
                ok, err = False, str(e)
            GLib.idle_add(lambda: done(ok, 'Not allowed.' if not ok and not err else err) and False)
        threading.Thread(target=work, daemon=True).start()

    def page_account(self):
        p = page('User account', 'Your name, picture and password.')
        me = pwd.getpwuid(os.getuid())
        head = Gtk.Box(spacing=14)
        own = f'/var/lib/AccountsService/icons/{USER}'
        self.account_pic = thumb(own if os.path.exists(own) else '/usr/share/mwx7/avatars/03-guitar.jpg', 64, 64)
        head.append(self.account_pic)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        name = Gtk.Label(label=(me.pw_gecos or '').split(',')[0] or USER, xalign=0)
        name.add_css_class('section')
        v.append(name)
        v.append(note(f'Signs in as “{USER}” ({"administrator" if self.is_admin() else "standard user"})'))
        head.append(v)
        p.append(head)
        status = note('')
        status.add_css_class('status')

        p.append(section('Picture'))
        flow = Gtk.FlowBox(max_children_per_line=8, min_children_per_line=4, selection_mode=Gtk.SelectionMode.NONE,
                           column_spacing=6, row_spacing=6)
        for f in sorted(os.listdir('/usr/share/mwx7/avatars')):
            path = os.path.join('/usr/share/mwx7/avatars', f)
            b = Gtk.Button()
            b.add_css_class('swatch')
            b.set_child(thumb(path, 44, 44))
            b.connect('clicked', lambda _b, pth=path: self.admin(
                ['picture', pth], lambda ok, err, pth=pth: (status.set_label('Picture changed.' if ok else err),
                                                          ok and head.remove(self.account_pic) is None and
                                                          self.swap_pic(head, pth))))
            flow.append(b)
        p.append(flow)

        p.append(section('Password'))
        pw_note = note('')
        p.append(pw_note)
        row = Gtk.Box(spacing=8)
        set_btn = Gtk.Button()
        remove_btn = Gtk.Button(label='Remove password')
        row.append(set_btn)
        row.append(remove_btn)
        p.append(row)

        def refresh():
            has = self.has_password()
            pw_note.set_label('Your account has a password: the logon and lock screens ask for it.' if has else
                              'Your account has no password: anyone at this PC can use it. Adding one is a good '
                              'idea on a PC others can reach.')
            set_btn.set_label('Change password' if has else 'Add a password')
            remove_btn.set_visible(has)

        def ask_password(*_):
            # With a password already set the current one is asked for and checked (PAM, in mwx7-admin) before the new
            # one is accepted: someone at an unlocked screen cannot quietly take the account over.
            has = self.has_password()
            dlg = self.small_window('Password', 'user')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16,
                          margin_start=18, margin_end=18)
            cur = Gtk.PasswordEntry(placeholder_text='Current password', show_peek_icon=True)
            a = Gtk.PasswordEntry(placeholder_text='New password', show_peek_icon=True)
            b = Gtk.PasswordEntry(placeholder_text='Type the new password again', show_peek_icon=True)
            msg = note('')
            btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            cancel = Gtk.Button(label='Cancel')
            ok = Gtk.Button(label='Save')
            ok.add_css_class('suggested-action')
            ok.set_sensitive(False)

            def check(*_):
                good = bool(a.get_text()) and a.get_text() == b.get_text() and (bool(cur.get_text()) or not has)
                ok.set_sensitive(good)
                msg.set_label('' if not b.get_text() or a.get_text() == b.get_text() else 'The two passwords differ.')
            for e in (cur, a, b):
                e.connect('changed', check)
            cancel.connect('clicked', lambda *_: dlg.close())

            def save(*_):
                ok.set_sensitive(False)
                msg.set_label('Saving…')

                def done(good, err):
                    status.set_label('Password saved.' if good else err)
                    refresh()
                    if good:
                        dlg.close()
                    else:
                        msg.set_label(err)
                        ok.set_sensitive(True)
                if has:
                    self.admin(['password-change'], done, stdin=cur.get_text() + '\n' + a.get_text() + '\n')
                else:
                    self.admin(['password'], done, stdin=a.get_text() + '\n')
            ok.connect('clicked', save)
            btns.append(cancel)
            btns.append(ok)
            for w in ((cur,) if has else ()) + (a, b, msg, btns):
                box.append(w)
            dlg.set_child(box)
            dlg.present()

        set_btn.connect('clicked', ask_password)
        remove_btn.connect('clicked', lambda *_: self.admin(
            ['nopassword'], lambda ok, err: (status.set_label('Password removed.' if ok else err), refresh())))
        refresh()

        p.append(section('Starting the PC'))
        auto = Gtk.CheckButton(label='Go straight to the desktop when the PC starts (skip the logon screen)')
        auto.set_active(self.autologin())

        def on_auto(c):
            want = c.get_active()
            if want == self.autologin():
                return
            self.admin(['autologin', 'on' if want else 'off'], lambda ok, err: (
                status.set_label(('On: the desktop starts by itself after the PC starts.' if want else
                                  'Off: the PC starts at the logon screen.') if ok else err),
                ok or c.set_active(not want)))
        auto.connect('toggled', on_auto)
        p.append(auto)
        p.append(note('Logging off or locking still shows the logon or lock screen.'))
        self.account_list(p, status)
        p.append(status)
        return p

    # ---- Other accounts ---------------------------------------------------------------------------------------------
    NAME_OK = re.compile(r'[a-z_][a-z0-9_-]{0,31}\Z')

    @staticmethod
    def is_admin(name=None):
        try:
            g = grp.getgrnam('sudo')
            e = pwd.getpwnam(name or USER)
            return e.pw_name in g.gr_mem or e.pw_gid == g.gr_gid
        except KeyError:
            return False

    @staticmethod
    def people():
        """Accounts that sign in (ids from 1000 with a login shell), as mwx7-admin sees them."""
        return sorted((e.pw_name, (e.pw_gecos or '').split(',')[0] or e.pw_name) for e in pwd.getpwall()
                      if 1000 <= e.pw_uid < 60000 and not e.pw_shell.endswith(('nologin', 'false')))

    def account_list(self, p, status):
        p.append(section('Accounts on this PC'))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        p.append(box)
        admin = self.is_admin()

        def fill():
            while box.get_first_child():
                box.remove(box.get_first_child())
            for name, full in self.people():
                r = Gtk.Box(spacing=10)
                r.append(Gtk.Label(label=f'{full} ({name})', xalign=0, hexpand=True))
                r.append(note('Administrator' if self.is_admin(name) else 'Standard user'))
                if admin and name != USER:
                    rm = Gtk.Button(label='Remove…')
                    rm.connect('clicked', lambda _b, n=name, f=full: self.confirm_remove(n, f, status, fill))
                    r.append(rm)
                box.append(r)
        fill()
        if admin:
            add = Gtk.Button(label='Add another account…', halign=Gtk.Align.START)
            add.connect('clicked', lambda *_: self.add_account(status, fill))
            p.append(add)
        else:
            p.append(note('Only an administrator can add or remove accounts.'))

    def add_account(self, status, refill):
        dlg = self.small_window('Add an account', 'user')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16,
                      margin_start=18, margin_end=18)
        full = Gtk.Entry(placeholder_text='Full name', width_chars=28)
        name = Gtk.Entry(placeholder_text='Account name (lowercase letters, digits, - and _)', max_length=32)
        kind = Gtk.DropDown.new_from_strings(['Standard user', 'Administrator'])
        a = Gtk.PasswordEntry(placeholder_text='Password', show_peek_icon=True)
        b = Gtk.PasswordEntry(placeholder_text='Type the password again', show_peek_icon=True)
        msg = note('')
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label='Cancel')
        ok = Gtk.Button(label='Create')
        ok.add_css_class('suggested-action')
        ok.set_sensitive(False)
        filling = [False]
        auto = [True]  # the account name follows the first word of the full name until it is typed by hand

        def check(*_):
            n = name.get_text()
            taken = n in [x for x, _f in self.people()]
            if n and not self.NAME_OK.match(n):
                msg.set_label('The account name needs lowercase letters, digits, - and _, starting with a letter.')
            elif taken:
                msg.set_label('That account name is taken.')
            elif b.get_text() and a.get_text() != b.get_text():
                msg.set_label('The two passwords differ.')
            else:
                msg.set_label('')
            ok.set_sensitive(bool(self.NAME_OK.match(n)) and not taken and bool(a.get_text()) and a.get_text() == b.get_text())

        def on_full(*_):
            if auto[0]:
                words = full.get_text().lower().split()
                filling[0] = True
                name.set_text(re.sub(r'[^a-z0-9_-]', '', words[0])[:32] if words else '')
                filling[0] = False
            check()

        def on_name(*_):
            if not filling[0]:
                auto[0] = False
            check()
        full.connect('changed', on_full)
        name.connect('changed', on_name)
        for e in (a, b):
            e.connect('changed', check)
        cancel.connect('clicked', lambda *_: dlg.close())

        def create(*_):
            ok.set_sensitive(False)
            msg.set_label('Creating…')
            role = 'admin' if kind.get_selected() == 1 else 'standard'

            def done(good, err):
                status.set_label('Account created.' if good else err)
                refill()
                if good:
                    dlg.close()
                else:
                    msg.set_label(err)
            self.admin(['user', 'add', name.get_text(), role], done,
                       stdin=full.get_text().strip() + '\n' + a.get_text() + '\n')
        ok.connect('clicked', create)
        btns.append(cancel)
        btns.append(ok)
        for w in (full, name, kind, a, b, msg, btns):
            box.append(w)
        dlg.set_child(box)
        dlg.present()

    def confirm_remove(self, name, full, status, refill):
        dlg = self.small_window('Remove account', 'user')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16,
                      margin_start=18, margin_end=18)
        box.append(Gtk.Label(label=f'Remove the account of {full}?', xalign=0))
        keep = Gtk.CheckButton(label=f'Keep their files (in /home/{name})', active=True)
        gone = Gtk.CheckButton(label='Delete their files too', group=keep)
        msg = note('')
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label='Cancel')
        ok = Gtk.Button(label='Remove')
        ok.add_css_class('destructive-action')
        cancel.connect('clicked', lambda *_: dlg.close())

        def go(*_):
            ok.set_sensitive(False)

            def done(good, err):
                status.set_label('Account removed.' if good else err)
                refill()
                if good:
                    dlg.close()
                else:
                    msg.set_label(err)
                    ok.set_sensitive(True)
            self.admin(['user', 'remove', name, 'keep' if keep.get_active() else 'delete'], done)
        ok.connect('clicked', go)
        btns.append(cancel)
        btns.append(ok)
        for w in (keep, gone, msg, btns):
            box.append(w)
        dlg.set_child(box)
        dlg.present()

    # ---- Default apps -----------------------------------------------------------------------------------------------
    # (label, MIME types the choice covers; the first one is read to show the current default.) Setting one sets them all, so
    # a different browser also opens .html files and links, a different player every common audio format, and so on.
    DEFAULT_KINDS = [
        ('Web browser', ['x-scheme-handler/http', 'x-scheme-handler/https', 'text/html', 'application/xhtml+xml']),
        ('Email', ['x-scheme-handler/mailto']),
        ('Music', ['audio/mpeg', 'audio/flac', 'audio/ogg', 'audio/x-wav', 'audio/mp4', 'audio/aac', 'audio/opus',
                   'audio/x-vorbis+ogg', 'audio/x-flac', 'audio/webm', 'audio/x-m4a']),
        ('Video', ['video/mp4', 'video/x-matroska', 'video/webm', 'video/mpeg', 'video/quicktime', 'video/x-msvideo',
                   'video/ogg', 'video/x-flv']),
        ('Photos', ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff', 'image/svg+xml',
                    'image/avif', 'image/heif']),
        ('Text editor', ['text/plain', 'text/markdown', 'text/x-python', 'text/x-csrc', 'text/x-shellscript', 'text/css',
                         'application/json', 'application/xml', 'text/xml']),
        ('File manager', ['inode/directory']),
    ]

    @staticmethod
    def apps_for(mimes):
        """Installed apps that open any of these types (Flatpak apps included: their exports are in XDG_DATA_DIRS), by name."""
        seen = {}
        for m in mimes:
            for app in Gio.AppInfo.get_all_for_type(m):
                if app.get_id() and app.should_show():
                    seen.setdefault(app.get_id(), app)
        return sorted(seen.values(), key=lambda a: a.get_display_name().lower())

    def page_defaults(self):
        p = page('Default apps', 'The app that opens each kind of file or link.')
        status = note('')
        status.add_css_class('status')
        for label, mimes in self.DEFAULT_KINDS:
            apps = self.apps_for(mimes)
            if not apps:
                p.append(field(label, Gtk.Label(label='No app installed', css_classes=['note']), 14))
                continue
            current = Gio.AppInfo.get_default_for_type(mimes[0], False)
            dd = Gtk.DropDown.new_from_strings([a.get_display_name() for a in apps])
            dd.set_size_request(260, -1)
            ids = [a.get_id() for a in apps]
            if current and current.get_id() in ids:
                dd.set_selected(ids.index(current.get_id()))
            # Connected after the initial selection, so showing the page never rewrites anyone's defaults.
            dd.connect('notify::selected', lambda d, _p, apps=apps, mimes=mimes, label=label:
                       self.set_default(label, apps[d.get_selected()], mimes, status))
            p.append(field(label, dd, 14))
        p.append(status)
        return p

    def set_default(self, label, app, mimes, status):
        failed = 0
        for m in mimes:
            try:
                app.set_as_default_for_type(m)
            except GLib.Error:
                failed += 1
        if label == 'Web browser' and app.get_id():
            # Also the desktop-wide setting that xdg-open and Chrome-like apps read, besides the MIME entries.
            run(['xdg-settings', 'set', 'default-web-browser', app.get_id()])
        status.set_label(f'{label}: {app.get_display_name()}.' if failed < len(mimes) else 'Could not save that choice.')

    def swap_pic(self, head, path):
        self.account_pic = thumb(path, 64, 64)
        head.prepend(self.account_pic)

    # ---- Updates ----------------------------------------------------------------------------------------------------
    # ---- Power ------------------------------------------------------------------------------------------------------
    POWER_FILE = os.path.join(CONF_DIR, 'power.json')
    LOGIND_DROPIN = '/etc/systemd/logind.conf.d/50-mwx7-power.conf'
    SCREEN_TIMES = [(1, '1 minute'), (2, '2 minutes'), (5, '5 minutes'), (10, '10 minutes'), (15, '15 minutes'),
                    (30, '30 minutes'), (0, 'Never')]
    SLEEP_TIMES = [(5, '5 minutes'), (10, '10 minutes'), (15, '15 minutes'), (30, '30 minutes'), (60, '1 hour'),
                   (120, '2 hours'), (0, 'Never')]
    SAVER_LEVELS = [(0, 'Never'), (10, 'At 10%'), (15, 'At 15%'), (20, 'At 20%'), (30, 'At 30%')]
    BUTTON_ACTIONS = [('poweroff', 'Shut down'), ('suspend', 'Sleep'), ('ignore', 'Do nothing')]
    LID_ACTIONS = [('suspend', 'Sleep'), ('lock', 'Lock the screen'), ('poweroff', 'Shut down'), ('ignore', 'Do nothing')]

    @staticmethod
    def has_battery():
        return bool(glob.glob('/sys/class/power_supply/BAT*'))

    @classmethod
    def logind_value(cls, key, default):
        try:
            for line in open(cls.LOGIND_DROPIN):
                k, _, v = line.strip().partition('=')
                if k == key:
                    return v
        except OSError:
            pass
        return default

    @staticmethod
    def choice(options, current, on_change):
        """A drop-down over (value, label) pairs; on_change gets the value the person picked."""
        dd = Gtk.DropDown.new_from_strings([l for _v, l in options])
        dd.set_selected(next((i for i, (v, _l) in enumerate(options) if v == current), 0))
        dd.connect('notify::selected', lambda d, _p: on_change(options[d.get_selected()][0]))
        return dd

    def page_power(self):
        p = page('Power', 'When the screen turns off, when the PC sleeps and what the buttons do.')
        try:
            cfg = json.load(open(self.POWER_FILE))
            cfg = cfg if isinstance(cfg, dict) else {}
        except (OSError, ValueError):
            cfg = {}
        # The same defaults as bin/mwx7-idle, which reads this file.
        cfg = {'screen': 10, 'sleep': 0, 'lock': True, 'saver': 20, **{k: v for k, v in cfg.items() if k in ('screen', 'sleep', 'lock', 'saver')}}
        status = note('')

        def save(key, value):
            if cfg[key] == value:
                return
            cfg[key] = value
            os.makedirs(CONF_DIR, exist_ok=True)
            with open(self.POWER_FILE, 'w') as f:
                json.dump(cfg, f)
            # mwx7-idle reads the file when it starts: restart it (it stops the battery watcher itself).
            run(['pkill', '-u', str(os.getuid()), '-x', 'swayidle'])
            try:
                subprocess.Popen(['/usr/share/mwx7/bin/mwx7-idle'], start_new_session=True, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            except OSError:
                pass

        p.append(section('Turn off and sleep'))
        p.append(field('Turn off the screen', self.choice(self.SCREEN_TIMES, cfg['screen'], lambda v: save('screen', v)), 22))
        p.append(field('Put the PC to sleep', self.choice(self.SLEEP_TIMES, cfg['sleep'], lambda v: save('sleep', v)), 22))
        lock = Gtk.CheckButton(label='Ask for my password when the screen wakes up')
        lock.set_active(cfg['lock'] is not False)
        lock.connect('toggled', lambda b: save('lock', b.get_active()))
        p.append(lock)
        p.append(note('The screen comes back when you move the mouse. Sleep keeps your apps open.'))

        p.append(section('Buttons'))

        def system_choice(label, what, options, key, default):
            def changed(value):
                if value == self.logind_value(key, default):
                    return
                status.set_label('')
                self.admin(['power', what, value], lambda ok, err: status.set_label('Saved.' if ok else err or 'Not allowed.') and False)
            return field(label, self.choice(options, self.logind_value(key, default), changed), 22)
        p.append(system_choice('When I press the power button', 'button', self.BUTTON_ACTIONS, 'HandlePowerKey', 'poweroff'))
        if self.has_battery():
            p.append(system_choice('When I close the lid', 'lid', self.LID_ACTIONS, 'HandleLidSwitch', 'suspend'))
            p.append(section('Battery'))
            p.append(field('Battery saver', self.choice(self.SAVER_LEVELS, cfg['saver'], lambda v: save('saver', v)), 22))
            p.append(note('When the battery gets this low and the charger is out, the screen is dimmed to make it last longer.'))
        p.append(status)
        return p

    # ---- Storage ----------------------------------------------------------------------------------------------------
    NOT_DISKS = {'squashfs', 'iso9660', 'overlay', 'tmpfs', 'devtmpfs', 'proc', 'sysfs', 'cgroup2', 'efivarfs', 'fuse.portal',
                 'fusectl', 'ramfs', 'devpts', 'securityfs', 'debugfs', 'tracefs', 'configfs', 'bpf', 'mqueue', 'hugetlbfs'}

    @staticmethod
    def fmt_size(n):
        n = float(n)
        for unit in ('bytes', 'KB', 'MB', 'GB'):
            if n < 1000:
                return f'{int(n)} bytes' if unit == 'bytes' else f'{n:.0f} {unit}' if n >= 100 else f'{n:.1f} {unit}'
            n /= 1024
        return f'{n:.1f} TB'

    @staticmethod
    def tree_size(path, deadline=None, one_fs=True):
        """Disk space a file or folder uses (what `du` counts: blocks, links not followed) and whether counting stopped
        early at the deadline. Unreadable things count as nothing."""
        try:
            top = os.lstat(path)
        except OSError:
            return 0, False
        total = top.st_blocks * 512
        stack = [path] if stat.S_ISDIR(top.st_mode) else []
        while stack:
            if deadline and time.monotonic() > deadline:
                return total, True
            try:
                with os.scandir(stack.pop()) as it:
                    for e in it:
                        try:
                            st = e.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        total += st.st_blocks * 512
                        if stat.S_ISDIR(st.st_mode) and not (one_fs and st.st_dev != top.st_dev):
                            stack.append(e.path)
            except OSError:
                continue
        return total, False

    @classmethod
    def mounted_disks(cls):
        """(name, mount point, total, used) for each mounted disk, not the pseudo file systems; one row per device even
        when it is mounted more than once (btrfs sub-volumes)."""
        seen, out = {}, []
        try:
            lines = open('/proc/self/mounts').read().splitlines()
        except OSError:
            return out
        for line in lines:
            f = line.split()
            if len(f) < 3 or not f[0].startswith('/dev/') or f[0].startswith('/dev/loop') or f[2] in cls.NOT_DISKS:
                continue
            mp = f[1].replace('\\040', ' ')
            if mp.startswith(('/snap', '/sys', '/proc', '/dev', '/boot/efi')) or (mp.startswith('/run') and not mp.startswith('/run/media')):
                continue
            if f[0] in seen and len(seen[f[0]]) <= len(mp):
                continue
            seen[f[0]] = mp
        for dev, mp in seen.items():
            try:
                v = os.statvfs(mp)
            except OSError:
                continue
            total = v.f_blocks * v.f_frsize
            if not total:
                continue
            label = run(['lsblk', '-no', 'LABEL', dev]).strip().split('\n')[0]
            name = label or ('This PC' if mp == '/' else os.path.basename(mp.rstrip('/')) or mp)
            out.append((name, mp, total, total - v.f_bfree * v.f_frsize))
        return sorted(out, key=lambda d: (d[1] != '/', d[1]))

    @staticmethod
    def home_folders():
        """The home folder and its named folders [(label, path)]; everything else in it is counted as Other."""
        D = GLib.UserDirectory
        home = os.path.realpath(os.path.expanduser('~'))
        named = []
        for label, which in (('Documents', D.DIRECTORY_DOCUMENTS), ('Pictures', D.DIRECTORY_PICTURES), ('Music', D.DIRECTORY_MUSIC),
                             ('Videos', D.DIRECTORY_VIDEOS), ('Downloads', D.DIRECTORY_DOWNLOAD)):
            path = GLib.get_user_special_dir(which)
            if path and os.path.realpath(path) != home and os.path.isdir(path):
                named.append((label, os.path.realpath(path)))
        return home, named

    def page_storage(self):
        p = page('Storage', 'How full your disks are, and a quick way to get some space back.')
        p.append(section('Disks'))
        disks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        p.append(disks_box)
        p.append(section('Your files'))
        files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        p.append(files_box)
        files_note = note('')
        p.append(files_note)
        p.append(section('Free up space'))
        p.append(note('Tick what to clean. Only the Trash holds anything of yours, and it is emptied for good.'))
        clean_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        p.append(clean_box)
        total_lbl = Gtk.Label(xalign=0, margin_top=8)
        total_lbl.add_css_class('status')
        go = Gtk.Button(label='Free up space', halign=Gtk.Align.START, sensitive=False)
        result = note('')
        for w in (total_lbl, go, result):
            p.append(w)

        def usage_row(name, detail, fraction, css=None):
            r = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            top = Gtk.Box(spacing=8)
            top.append(Gtk.Label(label=name, xalign=0, hexpand=True))
            d = Gtk.Label(label=detail, xalign=1)
            d.add_css_class('note')
            top.append(d)
            bar = Gtk.ProgressBar(fraction=max(0.0, min(1.0, fraction)))
            bar.add_css_class('usage-bar')
            if css:
                bar.add_css_class(css)
            r.append(top)
            r.append(bar)
            return r

        def clear(box):
            while box.get_first_child():
                box.remove(box.get_first_child())

        def show_disks(disks):
            clear(disks_box)
            for name, mp, total, used in disks:
                frac = used / total
                disks_box.append(usage_row('This PC' if mp == '/' and name == 'This PC' else f'{name}  ({mp})',
                                           f'{self.fmt_size(total - used)} free of {self.fmt_size(total)}', frac,
                                           'nearly-full' if frac > 0.9 else None))
            if not disks:
                disks_box.append(note('No disks to show here.'))
            return True

        # Your files: counted in the background (a few seconds, up to half a minute on a big home folder).
        scan = {'running': False, 'at': 0.0}

        def start_scan():
            if scan['running'] or time.monotonic() - scan['at'] < 300:
                return
            scan['running'] = True
            clear(files_box)
            files_box.append(note('Looking at your files…'))
            files_note.set_label('')

            def work():
                home, named = self.home_folders()
                deadline = time.monotonic() + 30
                sizes, cut = [], False
                for label, path in named:
                    s, c = self.tree_size(path, deadline)
                    sizes.append((label, s))
                    cut = cut or c
                everything, c = self.tree_size(home, deadline)
                sizes.append(('Other', max(0, everything - sum(s for _l, s in sizes))))
                GLib.idle_add(lambda: shown(sizes, everything, cut or c) and False)
            threading.Thread(target=work, daemon=True).start()

        def shown(sizes, total, cut):
            scan['running'], scan['at'] = False, time.monotonic()
            clear(files_box)
            for label, s in sizes:
                files_box.append(usage_row(label, self.fmt_size(s), s / total if total else 0, 'files-bar'))
            files_note.set_label(f'Your home folder uses {self.fmt_size(total)} in all.' +
                                 (' This is an estimate: the folder is big, so counting stopped after 30 seconds.' if cut else ''))
            return True

        # Free up space: what each item would free is worked out first, in the background.
        items = [
            {'key': 'trash', 'label': 'Empty the Trash', 'why': 'Things you deleted but kept for a while.'},
            {'key': 'thumbs', 'label': 'Clear picture previews', 'why': 'Small copies of your pictures. They are made again when needed.'},
            {'key': 'apt', 'label': 'Clear downloaded update files', 'why': 'Packages that are already installed.'},
            {'key': 'flatpak', 'label': 'Remove old app components', 'why': 'Parts of apps that no app uses anymore.'},
        ]
        trash = os.path.join(GLib.get_user_data_dir(), 'Trash')
        thumbs = os.path.join(GLib.get_user_cache_dir(), 'thumbnails')

        def flatpak_unused():
            """Bytes the unused Flatpak runtimes take (0: none), or None when that cannot be told. flatpak only lists them when
            asked to remove them, so the question is answered "no" and the list is read."""
            if not shutil.which('flatpak'):
                return 0
            try:
                r = subprocess.run(['flatpak', 'uninstall', '--system', '--unused'], input='n\n', capture_output=True, text=True,
                                   timeout=30, env=dict(os.environ, LC_ALL='C', LANG='C'))
            except (OSError, subprocess.TimeoutExpired):
                return None
            text = r.stdout + r.stderr
            if 'Nothing unused' in text:
                return 0
            units = {'bytes': 1, 'kB': 1000, 'MB': 1000 ** 2, 'GB': 1000 ** 3}
            found = re.findall(r'(\d+(?:\.\d+)?)\s*(bytes|kB|MB|GB)\b', text)
            return int(sum(float(n) * units[u] for n, u in found)) if found else None

        def measure():
            out = {'trash': self.tree_size(trash, time.monotonic() + 20, False)[0],
                   'thumbs': self.tree_size(thumbs, time.monotonic() + 20, False)[0],
                   'apt': sum(os.lstat(f).st_blocks * 512 for f in glob.glob('/var/cache/apt/archives/*.deb')),
                   'flatpak': flatpak_unused()}
            GLib.idle_add(lambda: measured(out) and False)

        rows = {}
        busy = {'on': False}
        for it in items:
            r = Gtk.Box(spacing=10)
            chk = Gtk.CheckButton(active=True, sensitive=False)
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            v.append(Gtk.Label(label=it['label'], xalign=0))
            v.append(note(it['why']))
            size = Gtk.Label(label='…', xalign=1)
            size.add_css_class('note')
            r.append(chk)
            r.append(v)
            r.append(size)
            clean_box.append(r)
            rows[it['key']] = (chk, size)
            it['size'] = 0
            chk.connect('toggled', lambda *_a: update_total())

        def ticked(it):
            chk = rows[it['key']][0]
            return chk.get_active() and chk.get_sensitive()

        def update_total():
            n = sum(it['size'] or 0 for it in items if ticked(it))
            unknown = any(it['size'] is None and ticked(it) for it in items)
            total_lbl.set_label((f'You can free up about {self.fmt_size(n)}' + (' or more' if unknown else '')) if n or unknown
                                else 'There is nothing to clean right now.')
            go.set_sensitive(bool(n or unknown) and not busy['on'])

        def measured(out):
            for it in items:
                it['size'] = out[it['key']]
                chk, size = rows[it['key']]
                size.set_label('Some space' if it['size'] is None else self.fmt_size(it['size']) if it['size'] else 'Nothing')
                chk.set_sensitive(it['size'] is None or it['size'] > 0)
                chk.set_active(it['size'] is None or it['size'] > 0)
            update_total()
            return True

        def run_clean(*_a):
            todo = [it['key'] for it in items if ticked(it)]
            before = sum(it['size'] or 0 for it in items if it['key'] in todo)
            busy['on'] = True
            go.set_sensitive(False)
            result.set_label('Cleaning…')

            def finish(ok=True, err=''):
                busy['on'] = False
                result.set_label(f'Done. About {self.fmt_size(before)} freed.' if ok else f'That did not finish: {err}')
                threading.Thread(target=measure, daemon=True).start()
                scan['at'] = 0.0
                start_scan()
                return False

            def step(rest):
                if not rest:
                    return finish()
                key, rest = rest[0], rest[1:]
                if key in ('apt', 'flatpak'):
                    self.admin(['cleanup', key], lambda ok, err: step(rest) if ok else finish(False, err or 'Not allowed.'), timeout=900)
                else:
                    def work():
                        path = trash if key == 'trash' else thumbs
                        for e in glob.glob(os.path.join(path, '*')) + glob.glob(os.path.join(path, '.*')):
                            if os.path.isdir(e) and not os.path.islink(e):
                                shutil.rmtree(e, ignore_errors=True)
                            else:
                                try:
                                    os.unlink(e)
                                except OSError:
                                    pass
                        GLib.idle_add(lambda: step(rest) and False)
                    threading.Thread(target=work, daemon=True).start()
                return False
            step(todo)
        go.connect('clicked', run_clean)

        def on_map(*_a):
            threading.Thread(target=lambda: GLib.idle_add(lambda d=self.mounted_disks(): show_disks(d) and False), daemon=True).start()
            if not busy['on']:
                threading.Thread(target=measure, daemon=True).start()
            start_scan()
        # Measured when the page is first shown, not when Settings opens (the file count can take a while).
        p.connect('map', on_map)
        return p

    # ---- Security ---------------------------------------------------------------------------------------------------
    @staticmethod
    def tool(name, args):
        """Output of a system tool (they live in /usr/sbin, which a desktop session's PATH may not include), or None."""
        exe = shutil.which(name, path=os.environ.get('PATH', '') + ':/usr/sbin:/sbin:/usr/bin')
        if not exe:
            return None
        try:
            r = subprocess.run([exe] + args, capture_output=True, text=True, timeout=10)
            return r.stdout + r.stderr
        except (OSError, subprocess.TimeoutExpired):
            return None

    def security_state(self):
        """Everything the Security page shows, as {key: (on: True/False/None, short text)}. Slow: not on the UI thread."""
        out = {}
        try:
            ufw_on = re.search(r'^ENABLED=yes', open('/etc/ufw/ufw.conf').read(), re.M) is not None
        except OSError:
            ufw_on = False
        # PCs set up before ufw still have the older nftables firewall running.
        fw = ufw_on or run(['systemctl', 'is-enabled', 'nftables.service']).strip() == 'enabled'
        out['firewall'] = (fw, 'On' if fw else 'Off')
        m = re.search(r'Unattended-Upgrade\s+"(\d+)"', self.tool('apt-config', ['dump', 'APT::Periodic::Unattended-Upgrade']) or '')
        auto = bool(m and m.group(1) != '0')
        out['updates'] = (auto, 'On' if auto else 'Off')
        sb = (self.tool('mokutil', ['--sb-state']) or '').lower()
        out['secureboot'] = (False, 'Off') if 'disabled' in sb else (True, 'On') if 'enabled' in sb else (None, 'Not used')
        src = run(['findmnt', '-no', 'SOURCE', '/']).strip().split('[')[0]
        types = (self.tool('lsblk', ['-s', '-rno', 'TYPE', src]) if src.startswith('/dev/') else None) or self.tool('lsblk', ['-rno', 'TYPE']) or ''
        enc = 'crypt' in types.split()
        out['encryption'] = (enc, 'On' if enc else 'Off')
        aa = (self.tool('aa-enabled', []) or '').strip().lower()
        out['apparmor'] = (None, 'Not available') if not aa else (True, 'On') if aa.startswith('yes') else (False, 'Off')
        return out

    def page_security(self):
        p = page('Security', 'A quick look at how well this PC protects itself.')
        busy = {'on': False}
        msg = note('')

        def toggle(on_args, off_args):
            sw = Gtk.Switch(valign=Gtk.Align.CENTER, sensitive=False)

            def changed(s, active):
                if busy['on']:
                    return True  # being set by the page itself
                busy['on'] = True
                s.set_sensitive(False)
                msg.set_label('Working…')

                def done(ok, err):
                    busy['on'] = False
                    msg.set_label('Saved.' if ok else err or 'Not allowed.')
                    threading.Thread(target=refresh, daemon=True).start()
                    return False
                self.admin(on_args if active else off_args, done, timeout=120)
                return False
            sw.connect('state-set', changed)
            return sw

        def row(title, why, switch=None):
            r = Gtk.Box(spacing=12)
            r.add_css_class('sec-row')
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            t = Gtk.Label(label=title, xalign=0)
            t.add_css_class('sec-title')
            v.append(t)
            v.append(note(why))
            r.append(v)
            state = Gtk.Label(label='…', valign=Gtk.Align.CENTER)
            state.add_css_class('pill')
            r.append(state)
            if switch is not None:
                r.append(switch)
            p.append(r)
            return state

        fw_sw = toggle(['firewall', 'on'], ['firewall', 'off'])
        up_sw = toggle(['autoupdates', 'on'], ['autoupdates', 'off'])
        p.append(section('Protection'))
        labels = {
            'firewall': row('Firewall', 'Keeps strangers on the network out. Your apps can still reach the internet.', fw_sw),
            'updates': row('Automatic security updates', 'Important fixes install by themselves once a day.', up_sw),
        }
        p.append(section('This PC'))
        labels['secureboot'] = row('Secure Boot', 'Only start-up software that is signed gets to run.')
        labels['encryption'] = row('Disk encryption', 'Scrambles your files while the PC is off. It is chosen when MWX 7 is installed.')
        labels['apparmor'] = row('AppArmor', 'Keeps apps inside their limits, even if one of them goes wrong.')
        p.append(msg)

        def show(out):
            for key, (on, text) in out.items():
                lbl = labels[key]
                lbl.set_label(text)
                for c in ('ok', 'off', 'na'):
                    lbl.remove_css_class(c)
                lbl.add_css_class('na' if on is None else 'ok' if on else 'off')
            was = busy['on']
            busy['on'] = True  # moving the switches from here must not run them
            for sw, key in ((fw_sw, 'firewall'), (up_sw, 'updates')):
                sw.set_active(out[key][0])
                sw.set_state(out[key][0])
                sw.set_sensitive(not was)
            busy['on'] = was
            return False

        def refresh():
            out = self.security_state()
            GLib.idle_add(lambda: show(out))
        p.connect('map', lambda *_a: threading.Thread(target=refresh, daemon=True).start())
        return p

    def page_updates(self):
        p = page('Updates')
        try:
            version = open('/usr/share/mwx7/version').read().strip()
        except OSError:
            version = '?'
        current = note(f'You have MWX 7 {version}.')
        p.append(current)
        p.append(note('Security fixes install by themselves. Other updates wait for you: an icon in the status bar '
                      'tells you when they are ready.'))
        # mwx7-update records what it found (checked=<epoch> count= version= ready=); the daily timer keeps it fresh.
        def update_info():
            d = {}
            try:
                for l in open('/var/lib/mwx7/updates.state'):
                    k, _, v = l.strip().partition('=')
                    d[k] = v
            except OSError:
                pass
            return d
        last = note('')

        def show_last():
            try:
                t = datetime.datetime.fromtimestamp(int(update_info()['checked']))
                last.set_label('Last checked: ' + t.strftime('%d %b %Y, %H:%M'))
            except (KeyError, ValueError):
                last.set_label('Last checked: never')
        show_last()
        p.append(last)
        auto_row = Gtk.Box(spacing=12)
        auto_row.append(Gtk.Label(label='Check automatically (daily)', xalign=0, hexpand=True))
        auto = Gtk.Switch(valign=Gtk.Align.CENTER)
        auto.set_active(not os.path.exists('/var/lib/mwx7/no-auto-check'))

        def on_auto(sw, state):
            # Updates download quietly in the background when this is on (not on a metered connection).
            subprocess.Popen(['pkexec', UPDATE, 'autocheck', 'on' if state else 'off'], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return False
        auto.connect('state-set', on_auto)
        auto_row.append(auto)
        p.append(auto_row)
        status = Gtk.Label(xalign=0, wrap=True)
        status.add_css_class('status')
        detail = note('')
        bar = Gtk.ProgressBar(visible=False, show_text=True)
        news = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        def show_news():
            while (c := news.get_first_child()):
                news.remove(c)
            # A waiting version shows its own news (fetched with the check); otherwise the installed version's.
            waiting = update_info().get('version') and os.path.exists('/var/lib/mwx7/whats-new-available')
            try:
                lines = [l.strip() for l in open('/var/lib/mwx7/whats-new-available' if waiting
                                                 else '/usr/share/mwx7/whats-new') if l.strip()]
                lines = [l[2:] if l.startswith('- ') else l for l in lines]
            except OSError:
                lines = []
            if lines:
                news.append(section(f'What’s new in MWX 7 {update_info()["version"]}' if waiting
                                    else 'What’s new in this version'))
                for l in lines[:6]:
                    # The first sentence is enough here; the rest stays in the changelog.
                    short = l.split(': ', 1)[0] if len(l) > 140 else l
                    news.append(note('• ' + (short if len(short) <= 160 else short[:157] + '…')))
        row = Gtk.Box(spacing=8)
        check = Gtk.Button(label='Check for updates')
        check.add_css_class('suggested-action')
        install = Gtk.Button(label='Install now')
        install.add_css_class('suggested-action')
        install.set_visible(False)
        restart = Gtk.Button(label='Restart now')
        restart.add_css_class('suggested-action')
        restart.set_visible(False)
        restart.connect('clicked', lambda *_: subprocess.Popen(['systemctl', 'reboot']))
        for b in (check, install, restart):
            row.append(b)
        for w in (row, status, bar, detail, news):
            p.append(w)
        show_news()

        def show_available(info):
            """The waiting update as the last check recorded it (also shown when the page opens)."""
            ours = info.get('version', '')
            count = int(info.get('count') or 0)
            if not count:
                return False
            others = count - (1 if ours else 0)
            parts = ([f'MWX 7 {ours}'] if ours else []) + ([f'{others} other update' + ('s' if others != 1 else '')]
                                                          if others else [])
            status.set_label('Available: ' + ' and '.join(parts) + '.' +
                             (' Already downloaded: installing is quick.' if info.get('ready') == '1' else ''))
            install.set_visible(True)
            return True

        def busy(on):
            check.set_sensitive(not on)
            install.set_sensitive(not on)

        def on_check(*_):
            busy(True)
            status.set_label('Checking…')
            detail.set_label('')

            def work():
                r = subprocess.run(['pkexec', UPDATE, 'check'], capture_output=True, text=True)
                GLib.idle_add(checked, r)
            threading.Thread(target=work, daemon=True).start()

        def checked(r):
            busy(False)
            show_last()
            show_news()
            if r.returncode != 0:
                status.set_label('Could not check for updates. Is the PC online?')
                detail.set_label((r.stderr.strip().splitlines() or [''])[-1])
                return False
            pkgs = [l.split() for l in r.stdout.splitlines() if l.strip()]
            if not pkgs:
                status.set_label('MWX 7 is up to date.')
                install.set_visible(False)
                return False
            show_available(update_info())
            return False

        def on_install(*_):
            busy(True)
            status.set_label('Installing updates… You can keep working.')
            bar.set_visible(True)
            bar.set_fraction(0)
            bar.set_text('Preparing')

            def stage(pct, name):
                bar.set_fraction(pct / 100)
                bar.set_text(f'{name}…')

            def work():
                proc = subprocess.Popen(['pkexec', UPDATE, 'install'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True)
                for line in proc.stdout:
                    line = line.strip()
                    if line.startswith('MWX7-PROGRESS '):
                        try:
                            _, pct, name = line.split(' ', 2)
                            GLib.idle_add(stage, int(pct), name)
                        except ValueError:
                            pass
                    elif line.startswith(('Unpacking', 'Setting up', 'Get:', 'Preparing')):
                        GLib.idle_add(detail.set_label, line[:120])
                GLib.idle_add(installed, proc.wait())
            threading.Thread(target=work, daemon=True).start()

        def installed(code):
            busy(False)
            bar.set_visible(False)
            show_last()
            install.set_visible(False)
            if code == 0:
                try:
                    current.set_label(f"You have MWX 7 {open('/usr/share/mwx7/version').read().strip()}.")
                except OSError:
                    pass
                # Restart only when something that a running session can't pick up changed (kernel, libc, graphics...).
                r = subprocess.run(['pkexec', UPDATE, 'needs-restart'], capture_output=True, text=True)
                restart_needed = r.returncode != 0 or r.stdout.strip() != 'no'
                if restart_needed:
                    status.set_label('Updates installed. Restart to use everything that changed.')
                else:
                    status.set_label('Updates installed. Nothing to restart.')
                    try:
                        if 'mwx7-desktop' in open('/var/lib/mwx7/last-upgraded').read().split():
                            # mwx7-shell restarts the shell when it exits, so this loads the new one without a logout.
                            subprocess.run(['pkill', '-u', str(os.getuid()), '-f', '/usr/share/mwx7/shell/shell.py'])
                    except OSError:
                        pass
                try:  # the status bar's "updates ready" icon goes away now rather than at its next check
                    os.unlink(os.path.join(os.environ.get('XDG_RUNTIME_DIR') or '/tmp', 'mwx7-updates'))
                except OSError:
                    pass
                show_news()
                detail.set_label('')
                restart.set_visible(restart_needed)
            else:
                status.set_label('Installing updates did not finish. MWX 7 repairs itself the next time it starts; '
                                 'you can also try again in a moment.')
            return False

        check.connect('clicked', on_check)
        install.connect('clicked', on_install)
        show_available(update_info())

        if os.path.exists('/etc/mwx7/installed') and run(['findmnt', '-no', 'SOURCE', '/']).strip().endswith('[/@previous]'):
            # The boot menu fell back to the version before the last update (or it was chosen there): keeping it makes
            # it the version MWX 7 starts from from now on.
            p.append(section('Previous version'))
            p.append(note('This PC is running the version from before the last update. Keep it to start from it from now '
                          'on, or leave it and the next update tries again.'))
            keep_msg = note('')
            keep = Gtk.Button(label='Keep the previous version', halign=Gtk.Align.START)

            def keep_done(ok, err):
                keep.set_sensitive(not ok)
                keep_msg.set_label('Done. MWX 7 starts from this version after a restart.' if ok else (err or 'Not allowed.'))

            def on_keep(*_):
                keep.set_sensitive(False)
                keep_msg.set_label('Keeping the previous version…')
                self.admin(['keep-previous'], keep_done, timeout=600)
            keep.connect('clicked', on_keep)
            p.append(keep)
            p.append(keep_msg)

        if os.path.exists('/etc/mwx7/installed'):
            p.append(section('Repair or reset'))
            p.append(note('Repair fixes MWX 7 and keeps your files. Reset to factory deletes everything and starts fresh. '
                          'Repair is also in the boot menu: hold Esc while the PC starts.'))
            row = Gtk.Box(spacing=8)
            repair = Gtk.Button(label='Repair MWX 7…')
            repair.connect('clicked', lambda *_: self.confirm_reset(True))
            factory = Gtk.Button(label='Reset to factory…')
            factory.add_css_class('destructive-action')
            factory.connect('clicked', lambda *_: self.confirm_reset(False))
            row.append(repair)
            row.append(factory)
            p.append(row)
        return p

    def page_backup(self):
        p = page('Backup', 'Copies the files and settings of every account to an external drive.')
        drives, state = [], {}
        row = Gtk.Box(spacing=8)
        model = Gtk.StringList()
        choose = Gtk.DropDown(model=model, hexpand=True)
        refresh = Gtk.Button(label='Refresh')
        row.append(choose)
        row.append(refresh)
        p.append(section('Backup drive'))
        p.append(row)
        status = Gtk.Label(xalign=0, wrap=True)
        status.add_css_class('status')
        detail = note('')
        buttons = Gtk.Box(spacing=8)
        now = Gtk.Button(label='Back up now')
        restore = Gtk.Button(label='Restore files…')
        buttons.append(now)
        buttons.append(restore)
        sched = Gtk.DropDown(model=Gtk.StringList.new(['Off', 'Every day', 'Every week']), halign=Gtk.Align.START)
        for w in (buttons, status, detail, section('Automatic backup')):
            p.append(w)
        p.append(field('Back up', sched))
        p.append(note('If the drive is not connected at the time, the backup runs the next time it is.'))
        busy = {'on': False}
        loading = {'on': False}

        def current():
            i = choose.get_selected()
            return drives[i] if drives and i < len(drives) else None

        def show_status():
            try:
                st = json.load(open(BACKUP_STATE))
            except (OSError, ValueError):
                st = {}
            state.clear()
            state.update(st)
            if busy['on']:
                return
            if st.get('last'):
                when = st['last'].replace('T', ' ')
                status.set_label(f"Last backup: {when}, to {st.get('drive_name') or 'the drive'}.")
            else:
                status.set_label('No backup yet.')
            fail = st.get('ok') is False and st.get('message')
            detail.set_label(f"The last try ({st.get('last_try', '').replace('T', ' ')}) failed: {st['message']}" if fail else '')

        def load(*_):
            loading['on'] = True
            drives.clear()
            for line in run([BACKUP, 'drives']).splitlines():
                f = line.split('\t')
                if len(f) >= 4:
                    drives.append({'uuid': f[0], 'dev': f[1], 'label': f[4] if len(f) > 4 and f[4] else f[1]})
            model.splice(0, model.get_n_items(), [f"{d['label']}  ({d['dev']})" for d in drives] or ['No external drive found'])
            show_status()
            want = next((i for i, d in enumerate(drives) if d['uuid'] == state.get('drive')), 0)
            choose.set_selected(want)
            sched.set_selected({'daily': 1, 'weekly': 2}.get(state.get('schedule'), 0))
            ok = bool(drives) and not busy['on']
            now.set_sensitive(ok)
            restore.set_sensitive(ok)
            sched.set_sensitive(ok or state.get('schedule') in ('daily', 'weekly'))
            loading['on'] = False

        def done(ok, err):
            busy['on'] = False
            load()
            if not ok:
                detail.set_label(err or 'The backup did not finish.')
            return False

        def on_now(*_):
            d = current()
            if not d:
                return
            busy['on'] = True
            now.set_sensitive(False)
            restore.set_sensitive(False)
            status.set_label(f"Backing up to {d['label']}… this can take a while. Please keep the drive connected.")
            detail.set_label('')
            self.admin(['backup', 'run', d['uuid']], done, timeout=6 * 3600)

        def on_sched(*_):
            d = current()
            mode = ('off', 'daily', 'weekly')[sched.get_selected()]
            if loading['on'] or mode == state.get('schedule', 'off'):
                return
            if mode != 'off' and not d:
                return
            detail.set_label('')
            self.admin(['backup', 'schedule', mode] + ([d['uuid']] if mode != 'off' else []),
                       lambda ok, err: (load(), None if ok else detail.set_label(err or 'Not allowed.')) and False)

        def on_restore(*_):
            d = current()
            if not d:
                return
            detail.set_label('')

            def work():
                # The desktop's own mount (no password): the drive opens like any removable drive.
                mp = run(['findmnt', '-no', 'TARGET', '-S', d['dev']]).strip().split('\n')[0]
                if not mp:
                    subprocess.run(['udisksctl', 'mount', '-b', d['dev'], '--no-user-interaction'], capture_output=True)
                    mp = run(['findmnt', '-no', 'TARGET', '-S', d['dev']]).strip().split('\n')[0]
                GLib.idle_add(opened, mp)
            threading.Thread(target=work, daemon=True).start()

        def opened(mp):
            folder = os.path.join(mp, 'MWX7-Backup') if mp else ''
            if folder and os.path.isdir(folder):
                subprocess.Popen(['python3', '/usr/share/mwx7/apps/explorer.py', folder])
            else:
                detail.set_label('There is no backup on this drive yet.' if mp else 'The drive could not be opened.')
            return False

        refresh.connect('clicked', load)
        now.connect('clicked', on_now)
        restore.connect('clicked', on_restore)
        sched.connect('notify::selected', on_sched)
        load()
        return p

    def small_window(self, title, icon_name):
        """A small window of Settings' own (password, repair): framed in Aero glass like Settings. Not transient: MWX 7's
        frames leave windows with a parent to GTK, which drew this one with no frame and a see-through background."""
        dlg = Gtk.Window(title=title, resizable=False)
        dlg.add_css_class('mwx7-settings')
        dlg.set_titlebar(self.titlebar(dlg, title, icon_name))
        parent = self.get_active_window()
        if parent is not None:
            parent.connect('close-request', lambda *_a: dlg.destroy() and False)
        return dlg

    def confirm_reset(self, keep_all):
        dlg = self.small_window('Repair MWX 7' if keep_all else 'Reset to factory', 'settings')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=18, margin_bottom=16,
                      margin_start=20, margin_end=20)
        if keep_all:
            box.append(Gtk.Label(label='Repair MWX 7?', xalign=0, css_classes=['section']))
            box.append(Gtk.Label(label='MWX 7 is installed again from the recovery copy, at the version you have now, for '
                                       'when something is broken. Everything stays: accounts, files, apps and their '
                                       'settings. Takes a few minutes, then MWX 7 restarts.', xalign=0, wrap=True,
                                 max_width_chars=60))
        else:
            box.append(Gtk.Label(label='Reset to factory?', xalign=0, css_classes=['section']))
            box.append(Gtk.Label(label='Absolutely clean, like a new PC: accounts, files, apps, settings, Wi-Fi networks '
                                       'and logs are deleted for good. MWX 7 stays at the version you have now and starts '
                                       'with the first-start setup.', xalign=0, wrap=True, max_width_chars=60))
        msg = Gtk.Label(xalign=0, wrap=True, max_width_chars=60)
        bar = Gtk.ProgressBar(visible=False)
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=6)
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_: dlg.close())
        go = Gtk.Button(label='Repair and restart' if keep_all else 'Delete everything and restart')
        go.add_css_class('suggested-action' if keep_all else 'destructive-action')
        box.append(Gtk.Label(label='You can keep working until it restarts; if it stops on the way, nothing has changed.', xalign=0, wrap=True, max_width_chars=60,
                             css_classes=['dim-label']))

        def do_reset(*_):
            go.set_sensitive(False)
            cancel.set_sensitive(False)
            bar.set_visible(True)
            msg.set_label('Starting…')

            def work():
                p = subprocess.Popen(['pkexec', ADMIN, 'reset'] + (['keep'] if keep_all else []),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                err = ''
                for line in p.stdout:
                    kind, _, value = line.strip().partition(' ')
                    if kind == 'STEP':
                        GLib.idle_add(msg.set_label, value + '…')
                    elif kind == 'PROGRESS' and value.isdigit():
                        GLib.idle_add(bar.set_fraction, int(value) / 100)
                    elif kind == 'ERROR':
                        err = value
                ok = p.wait() == 0

                def done():
                    if not ok:
                        msg.set_label(err or 'It did not work. Nothing was changed.')
                        cancel.set_sensitive(True)
                        go.set_sensitive(True)  # try again
                        bar.set_visible(False)
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()
        go.connect('clicked', do_reset)
        btns.append(cancel)
        btns.append(go)
        box.append(msg)
        box.append(bar)
        box.append(btns)
        dlg.set_child(box)
        dlg.present()

    @staticmethod
    def acceleration():
        """Whether OpenGL runs on a GPU: asks the GL driver for its name through a GL context of GTK's own. Software
        drawing (llvmpipe) makes everything sluggish; in VMware it means "Accelerate 3D graphics" isn't on or working."""
        try:
            import ctypes
            import ctypes.util
            ctx = Gdk.Display.get_default().create_gl_context()
            ctx.realize()
            ctx.make_current()
            lib = ctypes.CDLL(ctypes.util.find_library('GLESv2') or ctypes.util.find_library('GL') or 'libGL.so.1')
            lib.glGetString.restype = ctypes.c_char_p
            name = (lib.glGetString(0x1F01) or b'').decode(errors='replace')  # GL_RENDERER
            Gdk.GLContext.clear_current()
        except Exception:
            return 'Unknown'
        if not name:
            return 'Unknown'
        if any(w in name.lower() for w in ('llvmpipe', 'softpipe', 'software')):
            return 'Off (software drawing): in VMware, tick Display → Accelerate 3D graphics'
        return 'On (' + name.split(';')[0].split('(')[0].strip() + ')'

    # ---- About ------------------------------------------------------------------------------------------------------
    def page_about(self):
        p = page('About')
        logo = Gtk.Image.new_from_file(os.path.join(ICONS, 'orb.png'))
        logo.set_pixel_size(96)
        logo.set_halign(Gtk.Align.START)
        p.append(logo)
        try:
            version = open('/usr/share/mwx7/version').read().strip()
        except OSError:
            version = '?'
        # /usr/lib/os-release is MWX 7's own; the diverted Debian original says what the system is built on.
        os_name = ''
        try:
            for line in open('/usr/lib/os-release.debian'):
                if line.startswith('PRETTY_NAME='):
                    os_name = line.split('=', 1)[1].strip().strip('"')
        except OSError:
            pass
        if not os_name:
            try:
                os_name = 'Debian ' + open('/etc/debian_version').read().strip()
            except OSError:
                os_name = 'Debian'
        cpu = next((l.split(':', 1)[1].strip() for l in open('/proc/cpuinfo') if l.startswith('model name')), '?')
        mem_kb = next((int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemTotal')), 0)
        gpu = ''
        for line in run_cached(['lspci'], 3600).splitlines():
            if 'VGA' in line or '3D controller' in line or 'Display controller' in line:
                gpu = line.split(': ', 1)[-1]
                break
        disk = shutil.disk_usage('/')
        rows = [('MWX 7', version), ('Based on', os_name), ('Processor', cpu), ('Memory', f'{mem_kb / 1048576:.1f} GB'),
                ('Graphics', gpu or 'Unknown'), ('Acceleration', self.acceleration()),
                ('Free space', f'{disk.free / 1e9:.1f} GB of {disk.total / 1e9:.1f} GB')]
        grid = Gtk.Grid(column_spacing=18, row_spacing=6)
        for i, (k, v) in enumerate(rows):
            a = Gtk.Label(label=k, xalign=0)
            a.add_css_class('key')
            b = Gtk.Label(label=v, xalign=0, wrap=True, selectable=True)
            grid.attach(a, 0, i, 1, 1)
            grid.attach(b, 1, i, 1, 1)
        p.append(grid)
        return p


if __name__ == '__main__':
    Settings().run(None)  # arguments are read from sys.argv above, not by GApplication
