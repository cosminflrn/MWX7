"""MWX 7 Settings: the system settings as an MWX 7 app (GTK 4).

Most settings live in the user's Wayfire config (~/.config/mwx7/wayfire.ini), which Wayfire reloads by itself, so
changes apply immediately. The wallpaper is a separate swaybg process that this app restarts.
"""
import json
import os
import re
import shutil
import subprocess
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
LIVE = os.path.exists('/usr/local/bin/mwx7-install')
KEEP_LABEL = 'mwx7-data'

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
    tmp = WF_INI + '.tmp'
    with open(tmp, 'w') as f:
        f.write(text)
    os.replace(tmp, WF_INI)  # atomic, so Wayfire never reads half a file


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
        root = Gtk.Box()
        nav = Gtk.ListBox()
        nav.add_css_class('nav')
        nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120)
        self.stack.set_hexpand(True)
        pages = [
            ('personalize', 'Personalize', 'desktop', self.page_personalize),
            ('display', 'Display', 'computer', self.page_display),
            ('keyboard', 'Keyboard', 'text', self.page_keyboard),
            ('mouse', 'Mouse', 'settings', self.page_mouse),
            ('datetime', 'Date & time', 'about', self.page_datetime),
            ('about', 'About', 'about', self.page_about),
        ]
        if LIVE:
            pages.insert(0, ('keep', 'Keep settings', 'drive', self.page_keep))
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
        nav.select_row(nav.get_row_at_index(0))  # Keep settings comes first on the live medium
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

    def on_color(self, btn, act, inact, row):
        ini_set('decoration', 'active_color', '\\' + act)
        ini_set('decoration', 'inactive_color', '\\' + inact)
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

    # ---- Keep settings (live session only) --------------------------------------------------------------------------
    @staticmethod
    def disks():
        try:
            tree = json.loads(run(['lsblk', '-J', '-b', '-o', 'NAME,SIZE,TYPE,PTTYPE,FSTYPE,LABEL,MODEL,MOUNTPOINTS']))
        except ValueError:
            return None, []
        kept, blank = None, []
        for d in tree.get('blockdevices', []):
            for part in d.get('children') or []:
                if part.get('label') == KEEP_LABEL:
                    kept = d
            if (d.get('type') == 'disk' and not d.get('children') and not d.get('pttype') and not d.get('fstype')
                    and int(d.get('size') or 0) >= 2_000_000_000 and not d['name'].startswith(('zram', 'loop'))):
                blank.append(d)
        return kept, blank

    def page_keep(self):
        p = page()
        p.append(heading('Keep settings'))
        p.append(note('MWX 7 is running from its ISO, so it starts fresh every time. Give it an empty disk and it '
                      'remembers your wallpaper, settings, Chrome sign-in, files and Wi-Fi networks, with no installing. '
                      'Starting a newer MWX 7 ISO with the same disk keeps all of it.'))
        status = note('')
        status.add_css_class('status')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        p.append(box)
        p.append(status)
        mounted = os.path.isdir('/run/live/persistence') and bool(os.listdir('/run/live/persistence'))

        def fill():
            while (c := box.get_first_child()):
                box.remove(c)
            kept, blank = self.disks()
            if kept and mounted:
                box.append(section('Your settings are kept'))
                box.append(note(f"On {kept.get('model') or kept['name']} ({int(kept['size']) / 1e9:.0f} GB)."))
                return
            if kept:
                box.append(section('Ready'))
                box.append(note('The disk is set up. MWX 7 starts keeping your settings from the next start, so '
                                'restart now: what you change before that is not kept.'))
                b = Gtk.Button(label='Restart now')
                b.add_css_class('suggested-action')
                b.set_halign(Gtk.Align.START)
                b.connect('clicked', lambda *_: subprocess.Popen(['systemctl', 'reboot']))
                box.append(b)
                return
            box.append(section('Empty disks'))
            if not blank:
                box.append(note('There is no empty disk. In VMware or VirtualBox, give the virtual machine a new '
                                '(empty) virtual disk of 4 GB or more and start again. Disks that hold anything are '
                                'never touched here.'))
            for d in blank:
                row = Gtk.Box(spacing=12)
                lbl = Gtk.Label(label=f"{d.get('model') or 'Disk'} — {int(d['size']) / 1e9:.0f} GB (/dev/{d['name']})",
                                xalign=0, hexpand=True)
                row.append(lbl)
                b = Gtk.Button(label='Use this disk')
                b.add_css_class('suggested-action')
                b.connect('clicked', lambda _b, dev=d: ask(dev))
                row.append(b)
                box.append(row)

        def ask(dev):
            dlg = Gtk.AlertDialog()
            dlg.set_message(f"Use /dev/{dev['name']} to keep your settings?")
            dlg.set_detail('The disk is empty, so nothing is lost. It is set up for MWX 7 and cannot hold anything '
                           'else afterwards (until it is erased again).')
            dlg.set_buttons(['Cancel', 'Use this disk'])
            dlg.set_cancel_button(0)
            dlg.set_default_button(1)
            dlg.choose(self.get_active_window(), None, lambda d, res: d.choose_finish(res) == 1 and go(dev))

        def go(dev):
            status.set_label('Setting up the disk…')
            box.set_sensitive(False)

            def work():
                r = subprocess.run(['sudo', '-n', '/usr/share/mwx7/bin/mwx7-keep-settings', '/dev/' + dev['name']],
                                   capture_output=True, text=True)
                GLib.idle_add(done, r)
            threading.Thread(target=work, daemon=True).start()

        def done(r):
            box.set_sensitive(True)
            status.set_label('' if r.returncode == 0
                             else 'That did not work: ' + (r.stderr.strip().splitlines() or ['unknown error'])[-1])
            fill()
            return False

        fill()
        return p

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
        os_name = ''
        try:
            for line in open('/etc/os-release'):
                if line.startswith('PRETTY_NAME='):
                    os_name = line.split('=', 1)[1].strip().strip('"')
        except OSError:
            pass
        cpu = next((l.split(':', 1)[1].strip() for l in open('/proc/cpuinfo') if l.startswith('model name')), '?')
        mem_kb = next((int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemTotal')), 0)
        gpu = ''
        for line in run(['lspci']).splitlines():
            if 'VGA' in line or '3D controller' in line or 'Display controller' in line:
                gpu = line.split(': ', 1)[-1]
                break
        disk = shutil.disk_usage('/')
        rows = [('MWX 7', version), ('Based on', os_name), ('Processor', cpu), ('Memory', f'{mem_kb / 1048576:.1f} GB'),
                ('Graphics', gpu or 'Unknown'), ('Free space', f'{disk.free / 1e9:.1f} GB of {disk.total / 1e9:.1f} GB')]
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
    Settings().run(None)
