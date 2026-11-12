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
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

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

# Window colours: (name, active RGBA, inactive RGBA), MWX 7's glass tints.
COLORS = [
    ('Sky', '#9CC4ECC0', '#D2DEEBB0'),
    ('Twilight', '#7FA3D6C8', '#C3D0E3B0'),
    ('Sea', '#86D0D8C0', '#CFE3E6B0'),
    ('Leaf', '#A8D99AC0', '#D6E6D1B0'),
    ('Lavender', '#B9A9E3C0', '#DCD6EDB0'),
    ('Blush', '#EDB0C4C0', '#EED8E0B0'),
    ('Sun', '#F2D27EC0', '#F1E6C8B0'),
    ('Graphite', '#A9B3BEC8', '#D5D9DEB0'),
]


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


def titlebar_css(selector, rgba):
    """Aero gloss over a window colour (#RRGGBBAA): a bright upper half, the colour itself below the gloss line."""
    try:
        c = [int(rgba[i:i + 2], 16) for i in (1, 3, 5)]
    except ValueError:
        c = [156, 196, 236]
    def mix(k):  # k of white over the colour
        return 'rgb({}, {}, {})'.format(*(round(v + (255 - v) * k) for v in c))
    return (f'{selector} {{ background: linear-gradient(to bottom, {mix(0.78)} 0%, {mix(0.5)} 50%, {mix(0.12)} 51%, '
            f'{mix(0.35)} 100%); }}\n')


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
            ('personalize', 'Personalize', 'desktop', self.page_personalize),
            ('account', 'Account', 'user', self.page_account),
            ('display', 'Display', 'computer', self.page_display),
            ('keyboard', 'Keyboard', 'text', self.page_keyboard),
            ('mouse', 'Mouse', 'settings', self.page_mouse),
            ('datetime', 'Date & time', 'about', self.page_datetime),
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
        # "--updates" (the update notification) opens straight at Updates.
        start = next((i for i, pg in enumerate(pages) if pg[0] == 'updates'), 0) if '--updates' in sys.argv else 0
        nav.select_row(nav.get_row_at_index(start))
        root.append(nav)
        root.append(self.stack)
        w.set_child(root)
        w.present()

    @staticmethod
    def titlebar(win, title):
        # GTK 4 always draws its own title bar (it doesn't let the window manager frame it), so MWX 7's own apps draw
        # one that matches the Wayfire frames: Aero gloss, title on the left, glossy traffic lights on the right.
        bar = Gtk.HeaderBar()
        bar.add_css_class('mwx7-titlebar')
        bar.set_show_title_buttons(False)
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
        return bar

    # ---- Personalize ------------------------------------------------------------------------------------------------
    def page_personalize(self):
        p = page()
        p.append(heading('Personalize'))
        p.append(section('Wallpaper'))
        flow = Gtk.FlowBox(max_children_per_line=4, selection_mode=Gtk.SelectionMode.SINGLE, column_spacing=10,
                           row_spacing=10, homogeneous=True)
        flow.add_css_class('walls')
        current = self.current_wallpaper()
        files = sorted(f for f in os.listdir(WALLPAPERS) if f.lower().endswith(('.jpg', '.png')))
        for f in files:
            path = os.path.join(WALLPAPERS, f)
            child = Gtk.FlowBoxChild()
            child.path = path
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            v.append(thumb(path, 150, 94))
            v.append(Gtk.Label(label=os.path.splitext(f)[0].replace('-', ' ').capitalize()))
            child.set_child(v)
            flow.append(child)
            if path == current:
                flow.select_child(child)
        flow.connect('child-activated', lambda _f, c: self.set_wallpaper(c.path))
        p.append(flow)

        p.append(section('Window color'))
        p.append(note('The tint of window frames. The glass lets the wallpaper show through.'))
        row = Gtk.Box(spacing=8)
        active = ini_get('decoration', 'active_color').replace('\\\\', '\\')
        for name, act, inact in COLORS:
            b = Gtk.Button()
            b.add_css_class('swatch')
            b.set_tooltip_text(name)
            sw = Gtk.Box()
            sw.set_size_request(40, 40)
            prov = Gtk.CssProvider()
            prov.load_from_data(f'box {{ background: {act[:7]}; border-radius: 4px; }}'.encode())
            sw.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            b.set_child(sw)
            if active.lstrip('\\').upper() == act.upper():
                b.add_css_class('chosen')
            b.connect('clicked', self.on_color, act, inact, row)
            row.append(b)
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
        act = ini_get('decoration', 'active_color', COLORS[0][1]).lstrip('\\')
        inact = ini_get('decoration', 'inactive_color', COLORS[0][2]).lstrip('\\')
        self.tint.load_from_data((titlebar_css('headerbar.mwx7-titlebar', act) +
                                  titlebar_css('window.mwx7-settings:backdrop headerbar.mwx7-titlebar', inact)).encode())

    def on_color(self, btn, act, inact, row):
        ini_set('decoration', 'active_color', '\\' + act)
        ini_set('decoration', 'inactive_color', '\\' + inact)
        self.apply_tint()
        child = row.get_first_child()
        while child:
            child.remove_css_class('chosen')
            child = child.get_next_sibling()
        btn.add_css_class('chosen')

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

    # ---- Date & time ------------------------------------------------------------------------------------------------
    def page_datetime(self):
        p = page()
        p.append(heading('Date & time'))
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
                      'also install by themselves every day.'))
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
                status.set_label('Updates installed. Restart to use everything that changed.')
                show_news()
                detail.set_label('')
                restart.set_visible(True)
            else:
                status.set_label('Installing updates did not finish. Try again in a moment.')
            return False

        check.connect('clicked', on_check)
        install.connect('clicked', on_install)

        if os.path.exists('/etc/mwx7/installed'):
            p.append(section('Reset MWX 7'))
            p.append(note('Back to a fresh MWX 7, no ISO needed. You choose: keep your files and account, or delete '
                          'everything and start with the first-start setup.'))
            reset = Gtk.Button(label='Reset MWX 7…', halign=Gtk.Align.START)
            reset.add_css_class('destructive-action')
            reset.connect('clicked', self.confirm_reset)
            p.append(reset)
            # Systems set up before Reset existed make their fresh copy in the background right after the update.
            waiting = note('Getting Reset ready. This takes a minute after an update.')
            p.append(waiting)

            tries = [120]  # checks every 5 s for 10 minutes

            def ready():
                ok = os.path.exists('/etc/mwx7/factory')
                reset.set_sensitive(ok)
                waiting.set_visible(not ok)
                tries[0] -= 1
                return not ok and tries[0] > 0
            if ready():
                GLib.timeout_add_seconds(5, ready)
        return p

    def confirm_reset(self, *_):
        dlg = Gtk.Window(title='Reset MWX 7', modal=True, transient_for=self.get_active_window())
        dlg.add_css_class('mwx7-settings')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=18, margin_bottom=16,
                      margin_start=20, margin_end=20)
        box.append(Gtk.Label(label='Reset MWX 7', xalign=0, css_classes=['section']))
        keep = Gtk.CheckButton(label='Keep my files')
        keep.set_active(True)
        box.append(keep)
        box.append(Gtk.Label(label='MWX 7 itself is made fresh. Your account, files and settings stay; apps you added '
                                   'go. You sign in as before.', xalign=0, wrap=True, max_width_chars=60,
                             margin_start=26, css_classes=['dim-label']))
        wipe = Gtk.CheckButton(label='Delete everything', group=keep)
        box.append(wipe)
        box.append(Gtk.Label(label='Accounts, files, apps and settings are deleted for good. MWX 7 starts with the '
                                   'first-start setup, like a new PC.', xalign=0, wrap=True, max_width_chars=60,
                             margin_start=26, css_classes=['dim-label']))
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=6)
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_: dlg.close())
        go = Gtk.Button(label='Reset and restart')
        go.add_css_class('destructive-action')
        msg = Gtk.Label(xalign=0, wrap=True)

        def do_reset(*_):
            go.set_sensitive(False)
            cancel.set_sensitive(False)
            msg.set_label('Resetting… MWX 7 restarts in a moment.')
            self.admin(['reset'] + (['keep'] if keep.get_active() else []),
                       lambda ok, err: ok or (msg.set_label(err or 'Reset did not work.'), cancel.set_sensitive(True)))
        go.connect('clicked', do_reset)
        btns.append(cancel)
        btns.append(go)
        box.append(msg)
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
