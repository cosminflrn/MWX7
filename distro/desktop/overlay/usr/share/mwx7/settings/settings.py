"""MWX 7 Settings: the system settings as an MWX 7 app (GTK 4).

Most settings live in the user's Wayfire config (~/.config/mwx7/wayfire.ini), which Wayfire reloads by itself, so
changes apply immediately. The wallpaper is a separate swaybg process that this app restarts.
"""
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import threading

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = '/usr/share/mwx7/icons'
CONF_DIR = os.path.join(GLib.get_user_config_dir(), 'mwx7')
WF_INI = os.path.join(CONF_DIR, 'wayfire.ini')
WALL_FILE = os.path.join(CONF_DIR, 'wallpaper')
WALLPAPERS = '/usr/share/mwx7/wallpapers'
ADMIN = '/usr/share/mwx7/bin/mwx7-admin'
UPDATE = '/usr/share/mwx7/bin/mwx7-update'
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
    l = Gtk.Label(label=text, xalign=0, wrap=True)
    l.add_css_class('note')
    return l


def page():
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    b.add_css_class('page')
    return b


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
        pages = [
            ('wallpapers', 'Wallpapers', 'image', self.page_wallpapers),
            ('account', 'User account', 'user', self.page_account),
            ('wincolor', 'Window Color', 'paint', self.page_wincolor),
            ('desktop', 'Desktop', 'desktop', self.page_desktop),
            ('dock', 'Dock', 'computer', self.page_dock),
            ('display', 'Display', 'computer', self.page_display),
            ('keyboard', 'Keyboard', 'text', self.page_keyboard),
            ('mouse', 'Mouse', 'settings', self.page_mouse),
            ('datetime', 'Date & time', 'about', self.page_datetime),
            ('sound', 'Sound', 'audio', self.page_sound),
            ('updates', 'Updates', 'drive', self.page_updates),
            ('about', 'About', 'about', self.page_about),
        ]
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
            scroll.set_child(build())
            self.stack.add_named(scroll, pid)
        nav.connect('row-selected', lambda _l, r: r and self.stack.set_visible_child_name(r.pid))
        # "--updates" (the update notification) opens straight at Updates; "--page <id>" at any page (the bar's clock
        # opens Date & time, the desktop's menu Personalize).
        want = 'updates' if '--updates' in sys.argv else (sys.argv[sys.argv.index('--page') + 1]
                                                         if '--page' in sys.argv[:-1] else '')
        want = {'personalize': 'wallpapers'}.get(want, want)  # the desktop menu's old "Personalize" page id
        start = next((i for i, pg in enumerate(pages) if pg[0] == want), 0)
        nav.select_row(nav.get_row_at_index(start))
        self.sync_personalize()  # mark the current theme and wallpaper
        root.append(nav)
        root.append(self.stack)
        w.set_child(root)
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
        p = page()
        p.append(heading('Choose your desktop background'))
        p.append(note('Click a picture to use it as your desktop background.'))
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
        return p

    def page_wincolor(self):
        p = page()
        p.append(heading('Change the color of your window borders, Start menu and taskbar'))
        p.append(note('The tint of the glass on window frames, the status bar and the dock.'))
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
        row = Gtk.Box(spacing=10)
        row.append(Gtk.Label(label='Color intensity', css_classes=['key']))
        self.intensity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.intensity.set_value(intensity)
        self.intensity.set_size_request(260, -1)
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
        row.append(self.intensity)
        p.append(row)
        return p

    @staticmethod
    def current_wallpaper():
        try:
            return open(WALL_FILE).read().strip()
        except OSError:
            return '/usr/share/mwx7/wallpaper.jpg'

    @staticmethod
    def set_wallpaper(path):
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(WALL_FILE, 'w') as f:
            f.write(path + '\n')
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
    def page_display(self):
        p = page()
        p.append(heading('Display'))
        try:
            outputs = json.loads(run(['wlr-randr', '--json']) or '[]')
        except ValueError:
            outputs = []
        if not outputs:
            p.append(note('No display information is available.'))
            return p
        for o in outputs:
            name = o.get('name', '?')
            p.append(section(f"{o.get('make') or ''} {o.get('model') or ''} ({name})".strip()))
            modes = []
            cur = None
            for m in o.get('modes', []):
                label = f"{m['width']} × {m['height']} at {round(m['refresh'])} Hz" + (' (recommended)' if m.get('preferred') else '')
                value = f"{m['width']}x{m['height']}@{int(round(m['refresh'] * 1000))}"
                if (label, value) not in modes:
                    modes.append((label, value))
                if m.get('current'):
                    cur = value
            # Highest refresh first within a resolution, so a 144 Hz monitor's best mode is easy to find.
            modes.sort(key=lambda m: (-int(m[1].split('x')[0]), -int(m[1].split('x')[1].split('@')[0]),
                                      -int(m[1].split('@')[1])))
            dd = Gtk.DropDown.new_from_strings([m[0] for m in modes])
            if cur:
                dd.set_selected(next((i for i, m in enumerate(modes) if m[1] == cur), 0))
            dd.connect('notify::selected', lambda d, _p, n=name, ms=modes: ini_set(f'output:{n}', 'mode',
                                                                               ms[d.get_selected()][1]))
            r = Gtk.Box(spacing=10)
            r.append(Gtk.Label(label='Resolution', xalign=0, width_chars=14))
            r.append(dd)
            p.append(r)
            scales = ['100%', '125%', '150%', '175%', '200%']
            sd = Gtk.DropDown.new_from_strings(scales)
            try:
                sd.set_selected(scales.index(f"{round(float(o.get('scale', 1)) * 100)}%"))
            except ValueError:
                pass
            sd.connect('notify::selected', lambda d, _p, n=name: ini_set(
                f'output:{n}', 'scale', str(int(scales[d.get_selected()][:-1]) / 100)))
            r2 = Gtk.Box(spacing=10)
            r2.append(Gtk.Label(label='Size of text and apps', xalign=0, width_chars=14, wrap=True))
            r2.append(sd)
            p.append(r2)
            # A monitor with tiny text out of the box gets a hint (Wayfire starts every screen at 100%).
            mm_w = int(o.get('physical_size', {}).get('width') or 0)
            cur_w = next((m['width'] for m in o.get('modes', []) if m.get('current')), 0)
            if mm_w and cur_w and cur_w / (mm_w / 25.4) > 140 and float(o.get('scale', 1)) < 1.25:
                p.append(note('This screen has small pixels; 150% or 200% may be easier to read.'))
        # Night light: warmer colours from sunset to sunrise, where the weather gadget's city is.
        p.append(section('Night light'))
        flag = os.path.join(CONF_DIR, 'nightlight')
        night = Gtk.CheckButton(label='Warmer colours from sunset to sunrise')
        night.set_active(os.path.exists(flag))

        def toggled(c):
            if c.get_active():
                os.makedirs(CONF_DIR, exist_ok=True)
                open(flag, 'w').close()
                subprocess.Popen(['/usr/share/mwx7/bin/mwx7-nightlight'], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                if os.path.exists(flag):
                    os.remove(flag)
                run(['pkill', '-u', str(os.getuid()), '-x', 'wlsunset'])
        night.connect('toggled', toggled)
        p.append(night)
        p.append(note('The times follow the city chosen for the weather gadget (Settings \u2192 Desktop).'))
        return p

    # ---- Keyboard ---------------------------------------------------------------------------------------------------
    def page_keyboard(self):
        p = page()
        p.append(heading('Keyboard'))
        p.append(section('Layout'))
        p.append(note('Switch between layouts with Windows key + Space.'))
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
        p.append(dd)
        p.append(section('Repeat'))
        delay = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 150, 800, 10)
        delay.set_value(float(ini_get('input', 'kb_repeat_delay', '400') or 400))
        delay.connect('value-changed', lambda s: ini_set('input', 'kb_repeat_delay', str(int(s.get_value()))))
        p.append(Gtk.Label(label='Delay before repeating', xalign=0))
        p.append(delay)
        return p

    # ---- Mouse ------------------------------------------------------------------------------------------------------
    def page_mouse(self):
        p = page()
        p.append(heading('Mouse'))
        p.append(section('Pointer speed'))
        sp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.05)
        sp.set_value(float(ini_get('input', 'mouse_cursor_speed', '0') or 0))
        sp.add_mark(0, Gtk.PositionType.BOTTOM, 'Default')
        sp.connect('value-changed', lambda s: ini_set('input', 'mouse_cursor_speed', f'{s.get_value():.2f}'))
        p.append(sp)
        nat = Gtk.CheckButton(label='Natural scrolling (content follows your fingers, like a phone)')
        nat.set_active(ini_get('input', 'mouse_natural_scroll', 'false') == 'true')
        nat.connect('toggled', lambda c: ini_set('input', 'mouse_natural_scroll', 'true' if c.get_active() else 'false'))
        p.append(nat)
        left = Gtk.CheckButton(label='Swap left and right buttons (left-handed)')
        left.set_active(ini_get('input', 'left_handed_mode', 'false') == 'true')
        left.connect('toggled', lambda c: ini_set('input', 'left_handed_mode', 'true' if c.get_active() else 'false'))
        p.append(left)
        return p

    # ---- Desktop (icons and gadgets; the desktop layer watches its settings file) ---------------------------------------
    def page_desktop(self):
        p = page()
        p.append(heading('Desktop icons and gadgets'))
        p.append(note('What the desktop shows. Right-click the desktop for the same choices.'))
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
        gadgets = Gtk.CheckButton(label='Show gadgets (clock, calendar, CPU and memory, weather)')
        gadgets.set_active(cfg.get('gadgets', True) is not False)
        gadgets.connect('toggled', lambda c: save(gadgets=c.get_active()))
        p.append(gadgets)
        p.append(section('Weather'))
        row = Gtk.Box(spacing=8)
        row.append(Gtk.Label(label='City', css_classes=['key']))
        city = Gtk.Entry(text=str(cfg.get('city') or 'Bucharest'), width_chars=24)
        row.append(city)
        status = note('')
        row.append(status)

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
        return p

    # ---- Sound (PipeWire, through wpctl) --------------------------------------------------------------------------------
    def page_sound(self):
        p = page()
        p.append(heading('Sound'))
        p.append(section('Volume'))
        out = run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@']).split()
        try:
            level = round(float(out[1]) * 100)
        except (IndexError, ValueError):
            level = 50
        vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        vol.set_value(level)
        vol.set_size_request(320, -1)
        vol.set_halign(Gtk.Align.START)
        vol.connect('value-changed', lambda s: run(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@',
                                                    f'{s.get_value() / 100:.2f}']))
        p.append(vol)
        mute = Gtk.CheckButton(label='Mute')
        mute.set_active('[MUTED]' in out)
        mute.connect('toggled', lambda c: run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '1' if c.get_active() else '0']))
        p.append(mute)
        # Outputs: the "Sinks" part of wpctl status ("│  *   46. Speakers [vol: 0.40]").
        sinks, cur, in_sinks = [], None, False
        for line in run(['wpctl', 'status']).splitlines():
            t = line.strip(' │├└─')
            if 'Sinks:' in line:
                in_sinks = True
                continue
            if in_sinks and (not t or t.endswith(':')):
                if sinks:
                    break
                continue
            m = re.match(r'(\*)?\s*(\d+)\.\s+(.*?)(\s+\[vol:.*)?$', t)
            if in_sinks and m:
                sinks.append((m.group(2), m.group(3)))
                if m.group(1):
                    cur = len(sinks) - 1
        if len(sinks) > 1:
            p.append(section('Play sound through'))
            dd = Gtk.DropDown.new_from_strings([n for _i, n in sinks])
            dd.set_halign(Gtk.Align.START)
            if cur is not None:
                dd.set_selected(cur)
            dd.connect('notify::selected', lambda d, _p: run(['wpctl', 'set-default', sinks[d.get_selected()][0]]))
            p.append(dd)
        elif not sinks:
            p.append(note('No sound output was found.'))
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
        return p

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

    def shell_check(self, label, key):
        c = Gtk.CheckButton(label=label)
        c.set_active(self.shell_get(key, True) is not False)
        c.connect('toggled', lambda b: self.shell_set(key, b.get_active()))
        return c

    def page_dock(self):
        p = page()
        p.append(heading('Change how the dock behaves'))
        p.append(note('Icons grow under the pointer when magnification is on.'))
        p.append(self.shell_check('Magnification', 'dock_magnify'))
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
        p = page()
        p.append(heading('Date & time'))
        p.append(section('Clock in the menu bar'))
        p.append(self.shell_check('Use 24-hour clock', 'clock24'))
        p.append(self.shell_check('Show seconds', 'clock_seconds'))
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
        p.append(dd)
        p.append(status)
        p.append(note('The clock uses the 24-hour format with seconds.'))
        return p

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

    def admin(self, args, done, stdin=None):
        """Runs mwx7-admin through pkexec (MWX 7 asks for the password if the account has one) off the UI thread."""
        def work():
            try:
                r = subprocess.run(['pkexec', ADMIN] + args, input=stdin, capture_output=True, text=True, timeout=300)
                ok, err = r.returncode == 0, (r.stderr.strip().splitlines() or [''])[-1]
            except (OSError, subprocess.TimeoutExpired) as e:
                ok, err = False, str(e)
            GLib.idle_add(lambda: done(ok, 'Not allowed.' if not ok and not err else err) and False)
        threading.Thread(target=work, daemon=True).start()

    def page_account(self):
        p = page()
        p.append(heading('Account'))
        me = pwd.getpwuid(os.getuid())
        head = Gtk.Box(spacing=14)
        own = f'/var/lib/AccountsService/icons/{USER}'
        self.account_pic = thumb(own if os.path.exists(own) else '/usr/share/mwx7/avatars/03-guitar.jpg', 64, 64)
        head.append(self.account_pic)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        name = Gtk.Label(label=(me.pw_gecos or '').split(',')[0] or USER, xalign=0)
        name.add_css_class('section')
        v.append(name)
        v.append(note(f'Signs in as “{USER}” · Administrator'))
        head.append(v)
        p.append(head)
        status = note('')
        status.add_css_class('status')

        p.append(section('Picture'))
        flow = Gtk.FlowBox(max_children_per_line=10, min_children_per_line=5, selection_mode=Gtk.SelectionMode.NONE,
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
            dlg = Gtk.Window(title='Password', modal=True, transient_for=self.get_active_window())
            dlg.add_css_class('mwx7-settings')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16,
                          margin_start=18, margin_end=18)
            a = Gtk.PasswordEntry(placeholder_text='New password', show_peek_icon=True)
            b = Gtk.PasswordEntry(placeholder_text='Type it again', show_peek_icon=True)
            msg = note('')
            btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            cancel = Gtk.Button(label='Cancel')
            ok = Gtk.Button(label='Save')
            ok.add_css_class('suggested-action')
            ok.set_sensitive(False)
            for e in (a, b):
                e.connect('changed', lambda *_: ok.set_sensitive(bool(a.get_text()) and a.get_text() == b.get_text()))
            cancel.connect('clicked', lambda *_: dlg.close())

            def save(*_):
                ok.set_sensitive(False)
                msg.set_label('Saving…')
                self.admin(['password'], lambda good, err: (status.set_label('Password saved.' if good else err),
                                                            refresh(), dlg.close()), stdin=a.get_text() + '\n')
            ok.connect('clicked', save)
            btns.append(cancel)
            btns.append(ok)
            for w in (a, b, msg, btns):
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
        p.append(status)
        return p

    def swap_pic(self, head, path):
        self.account_pic = thumb(path, 64, 64)
        head.prepend(self.account_pic)

    # ---- Updates ----------------------------------------------------------------------------------------------------
    def page_updates(self):
        p = page()
        p.append(heading('Updates'))
        try:
            version = open('/usr/share/mwx7/version').read().strip()
        except OSError:
            version = '?'
        current = note(f'You have MWX 7 {version}.')
        p.append(current)
        p.append(note('Updates bring MWX 7’s newest changes, plus Debian’s and Google Chrome’s fixes. Security fixes '
                      'install by themselves; everything else waits for you: an icon in the status bar says when '
                      'updates are ready, and Shut Down and Restart offer to install them first.'))
        status = Gtk.Label(xalign=0, wrap=True)
        status.add_css_class('status')
        detail = note('')
        news = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        def show_news():
            while (c := news.get_first_child()):
                news.remove(c)
            try:
                lines = [l.strip() for l in open('/usr/share/mwx7/whats-new') if l.strip()]
            except OSError:
                lines = []
            if lines:
                news.append(section('What’s new in this version'))
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
        for w in (row, status, detail, news):
            p.append(w)
        show_news()

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
            if r.returncode != 0:
                status.set_label('Could not check for updates. Is the PC online?')
                detail.set_label((r.stderr.strip().splitlines() or [''])[-1])
                return False
            pkgs = [l.split() for l in r.stdout.splitlines() if l.strip()]
            if not pkgs:
                status.set_label('MWX 7 is up to date.')
                install.set_visible(False)
                return False
            ours = next((v for n, v in pkgs if n == 'mwx7-desktop'), None)
            others = len(pkgs) - (1 if ours else 0)
            parts = ([f'MWX 7 {ours}'] if ours else []) + ([f'{others} other update' + ('s' if others != 1 else '')]
                                                         if others else [])
            status.set_label('Available: ' + ' and '.join(parts) + '.')
            install.set_visible(True)
            return False

        def on_install(*_):
            busy(True)
            status.set_label('Installing updates… You can keep working.')

            def work():
                proc = subprocess.Popen(['pkexec', UPDATE, 'install'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True)
                for line in proc.stdout:
                    line = line.strip()
                    if line.startswith(('Unpacking', 'Setting up', 'Get:', 'Preparing')):
                        GLib.idle_add(detail.set_label, line[:120])
                GLib.idle_add(installed, proc.wait())
            threading.Thread(target=work, daemon=True).start()

        def installed(code):
            busy(False)
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
                status.set_label('Installing updates did not finish. Try again in a moment.')
            return False

        check.connect('clicked', on_check)
        install.connect('clicked', on_install)

        if os.path.exists('/etc/mwx7/installed'):
            p.append(section('Repair or reset'))
            p.append(note('Both work offline, from the recovery copy MWX 7 keeps on the disk (this version, nothing to '
                          'download). Repair also runs from the boot menu: hold Esc while the PC starts.'))
            row = Gtk.Box(spacing=8)
            repair = Gtk.Button(label='Repair MWX 7…')
            repair.connect('clicked', lambda *_: self.confirm_reset(True))
            factory = Gtk.Button(label='Reset to factory…')
            factory.add_css_class('destructive-action')
            factory.connect('clicked', lambda *_: self.confirm_reset(False))
            row.append(repair)
            row.append(factory)
            p.append(row)
            rec_note = note('')
            prepare = Gtk.Button(label='Prepare the recovery copy', halign=Gtk.Align.START, visible=False)
            p.append(rec_note)
            p.append(prepare)

            def rec_state():
                try:
                    st = json.load(open('/var/lib/mwx7/recovery.json'))
                except (OSError, ValueError):
                    st = None
                ready = bool(st) and not st.get('missing')
                repair.set_sensitive(ready)
                factory.set_sensitive(ready)
                if ready:
                    rec_note.set_label('')
                elif st:
                    rec_note.set_label(f"The recovery copy misses {st['missing']} package files (they download when the PC "
                                       'is online).')
                else:
                    rec_note.set_label('The recovery copy is being prepared: MWX 7 is downloaded once (about 900 MB).')
                rec_note.set_visible(not ready)
                prepare.set_visible(not ready)
                return False
            rec_state()

            def do_prepare(*_):
                prepare.set_sensitive(False)
                rec_note.set_label('Preparing the recovery copy…')

                def work():
                    subprocess.run(['pkexec', ADMIN, 'recovery-prepare'], capture_output=True)
                    GLib.idle_add(lambda: (prepare.set_sensitive(True), rec_state()) and False)
                threading.Thread(target=work, daemon=True).start()
            prepare.connect('clicked', do_prepare)
        return p

    def confirm_reset(self, keep_all):
        dlg = Gtk.Window(title='Repair MWX 7' if keep_all else 'Reset to factory', modal=True,
                         transient_for=self.get_active_window())
        dlg.add_css_class('mwx7-settings')
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
        box.append(Gtk.Label(label='Nothing is downloaded. You can keep working until it restarts; if it stops on the '
                                   'way, nothing has changed.', xalign=0, wrap=True, max_width_chars=60,
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
        p = page()
        p.append(heading('About'))
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
        for line in run(['lspci']).splitlines():
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
