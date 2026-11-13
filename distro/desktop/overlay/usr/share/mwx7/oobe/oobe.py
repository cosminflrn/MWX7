#!/usr/bin/env python3
"""MWX 7 first-start setup: language, where MWX 7 goes, Wi-Fi, account. Runs full screen from the ISO (in cage, as the
ISO's setup user with sudo). As soon as the disk is chosen, install.py starts copying in the background, so most of
the copying happens while the person fills in the rest. With --preview it runs as a normal window on an installed
MWX 7 (Settings -> Updates) and changes nothing."""
import faulthandler
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import unicodedata

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

faulthandler.register(signal.SIGUSR1)  # kill -USR1 prints every thread's stack to the log (for hangs)
HERE = os.path.dirname(os.path.abspath(__file__))
SHARE = '/usr/share/mwx7'
INSTALL = os.path.join(HERE, 'install.py')
PREVIEW = '--preview' in sys.argv
# First start after Settings -> Reset MWX 7: MWX 7 is already on the disk, so newest updates instead of the disk page.
FIRSTBOOT = '--firstboot' in sys.argv
AVATARS = os.path.join(SHARE, 'avatars')

LANGUAGES = [  # (shown, locale, keyboard layout, variant, time zone)
    ('English (United States)', 'en_US.UTF-8', 'us', '', None),
    ('English (United Kingdom)', 'en_GB.UTF-8', 'gb', '', 'Europe/London'),
    ('Română', 'ro_RO.UTF-8', 'ro', 'std', 'Europe/Bucharest'),
]


def keyboards():
    """Every keyboard layout X knows, by name. Romanian means the standard layout (ș and ț with a comma below)."""
    out = []
    try:
        lines = open('/usr/share/X11/xkb/rules/evdev.lst').read().split('! layout', 1)[1].split('!', 1)[0].splitlines()
        for line in lines:
            m = re.match(r'\s+(\S+)\s+(.+)$', line)
            if m:
                out.append((m.group(2).strip(), m.group(1), 'std' if m.group(1) == 'ro' else ''))
    except (OSError, IndexError):
        pass
    out.sort(key=lambda k: k[0].lower())
    return out or [('English (US)', 'us', ''), ('Romanian', 'ro', 'std')]


def timezones():
    try:
        zones = subprocess.run(['timedatectl', 'list-timezones'], capture_output=True, text=True, timeout=5).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        zones = []
    return [z for z in zones if '/' in z] or ['Europe/Bucharest']


def login_from(name):
    """'Cosmin Mircea' -> 'cosmin': the first name, plain lowercase letters (ș -> s), as Linux account names need."""
    first = (name.strip().split() or [''])[0]
    plain = unicodedata.normalize('NFKD', first).encode('ascii', 'ignore').decode().lower()
    plain = re.sub(r'[^a-z0-9_-]', '', plain).lstrip('-0123456789')
    if plain in ('root', 'mwx', 'admin', 'daemon', 'bin', 'sys', 'nobody') or not plain:
        plain = (plain or 'user') + '1'
    return plain[:31]


def gb(n):
    # Binary gigabytes, the way Windows and VMware count them (a "60 GB" virtual disk shows as 60 GB here too).
    g = n / 2 ** 30
    return f'{g:.0f} GB' if g >= 10 else f'{g:.1f} GB'


def describe(disk):
    """What a person would call this disk and what is on it, in plain words."""
    # Model, size, kind and device name: on a real PC with several disks this is how the right one is told apart.
    kind = {'nvme': 'NVMe', 'sata': 'SATA', 'ata': 'SATA', 'usb': 'USB'}.get(disk.get('tran') or '', '')
    where = ', '.join(x for x in (kind, disk.get('name')) if x)
    title = f"{disk['model'] or 'Disk'} — {gb(disk['size'])}" + (f' ({where})' if where else '')
    if disk['live']:
        return title, 'This is the MWX 7 USB stick you started from. It is never touched.'
    if disk['empty']:
        return title, 'Empty: nothing is on it.'
    names = {'windows': 'Windows', 'linux': 'Linux', 'data': 'files', 'recovery': 'recovery', 'efi': 'boot files',
             'encrypted': 'encrypted data', 'swap': 'swap', 'other': 'other data', 'bios': 'boot files'}
    seen = []
    for p in disk['parts']:
        if p['kind'] in ('empty', 'efi', 'bios', 'swap'):
            continue
        what = names[p['kind']]
        label = p.get('label') or ''
        if label == 'MWX7' and p.get('fstype') == 'btrfs':
            what, label = 'MWX 7', ''
        if label and p['kind'] in ('windows', 'linux', 'data') and label.lower() not in what.lower():
            what += f' ({label})'
        if what not in seen:
            seen.append(what)
    text = 'Has ' + ', '.join(seen) if seen else 'Has partitions'
    if disk['free'] >= 1e9:
        text += f" · {gb(disk['free'])} free"
    return title, text + '.'


def sudo(*args):
    return ([] if os.geteuid() == 0 else ['sudo', '-n']) + [sys.executable, INSTALL, *args]


class Setup(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.mwx7.setup' + ('.preview' if PREVIEW else ''))
        self.lang = LANGUAGES[0]
        self.kbd = ('English (US)', 'us', '')
        self.tz = 'Europe/Bucharest'
        self.disk = None
        self.mode = None
        self.picture = os.path.join(AVATARS, '03-guitar.jpg')
        self.copy_state = 'done' if FIRSTBOOT else 'idle'  # idle | running | done | failed
        self.copy_error = ''
        self.progress = 0
        self.step = ''
        self.finished = False
        self.index = 0
        self.pages = []

    # ---- frame --------------------------------------------------------------------------------------------------
    def do_activate(self):
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(HERE, 'oobe.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = Gtk.ApplicationWindow(application=self, title='MWX 7 setup')
        win.add_css_class('oobe')
        self.win = win
        overlay = Gtk.Overlay()
        back = Gtk.Picture.new_for_filename(os.path.join(SHARE, 'wallpaper.jpg'))
        back.set_content_fit(Gtk.ContentFit.COVER)
        overlay.set_child(back)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class('card')
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        card.set_size_request(720, 540)
        top = Gtk.Box(spacing=12)
        top.add_css_class('top')
        orb = Gtk.Image.new_from_file(os.path.join(SHARE, 'icons', 'orb.png'))
        orb.set_pixel_size(40)
        top.append(orb)
        self.title = Gtk.Label(xalign=0, hexpand=True)
        self.title.add_css_class('title')
        top.append(self.title)
        if PREVIEW:
            tag = Gtk.Label(label='Preview: nothing is changed')
            tag.add_css_class('preview-tag')
            top.append(tag)
        card.append(top)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=220,
                               vexpand=True)
        card.append(self.stack)
        bottom = Gtk.Box(spacing=8)
        bottom.add_css_class('bottom')
        self.status = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.status.add_css_class('status')
        bottom.append(self.status)
        self.back = Gtk.Button(label='Back')
        self.back.connect('clicked', lambda *_: self.go(-1))
        bottom.append(self.back)
        self.next = Gtk.Button(label='Next')
        self.next.add_css_class('primary')
        self.next.connect('clicked', lambda *_: self.go(1))
        bottom.append(self.next)
        card.append(bottom)
        overlay.add_overlay(card)
        win.set_child(overlay)

        first = (('update', 'Updates', self.page_update),) if FIRSTBOOT else ()
        disk = () if FIRSTBOOT else (('disk', 'Where should MWX 7 go?', self.page_disk),)
        for pid, title, build in first + (('welcome', 'Hi! Let’s set up MWX 7', self.page_welcome),) + disk + (
                ('wifi', 'Connect to the internet', self.page_wifi),
                ('account', 'Who’s going to use this PC?', self.page_account),
                ('done', 'Getting everything ready', self.page_done)):
            self.stack.add_named(build(), pid)
            self.pages.append((pid, title))
        self.index = 0
        self.show_page()
        if PREVIEW:
            win.set_default_size(1000, 700)
        else:
            win.set_decorated(False)
            win.fullscreen()
            if not FIRSTBOOT:
                subprocess.Popen(sudo('ready'), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        win.present()
        GLib.timeout_add(400, self.tick)

    def show_page(self):
        pid, title = self.pages[self.index]
        self.stack.set_visible_child_name(pid)
        self.title.set_label(title)
        self.back.set_visible(self.target(-1) is not None and pid != 'done')
        self.next.set_visible(pid != 'done')
        self.next.set_label('Next')
        if pid == 'update':
            self.start_update()
        if pid == 'disk':
            self.refresh_disks()
        if pid == 'wifi':
            self.refresh_wifi()
        if pid == 'done':
            self.start_finish()
        self.validate()

    def target(self, step):
        """The page one step away, skipping Wi-Fi when already online; never back to the disk once copying runs."""
        i = self.index + step
        if 0 <= i < len(self.pages) and self.pages[i][0] == 'wifi' and self.online():
            i += step  # nothing to do there: a cable or a known network is already connected
        barrier = next((n for n, (pid, _t) in enumerate(self.pages) if pid in ('disk', 'update')), -1)
        if not 0 <= i < len(self.pages) or (step < 0 and self.copy_state != 'idle' and i <= barrier):
            return None
        return i

    def go(self, step):
        pid = self.pages[self.index][0]
        if step > 0 and pid == 'disk' and self.copy_state == 'idle':
            self.start_copy()
        i = self.target(step)
        if i is not None:
            self.index = i
            self.show_page()

    def validate(self):
        if not self.pages or self.index >= len(self.pages):
            return
        pid = self.pages[self.index][0]
        ok = True
        if pid == 'update':
            ok = self.update_state in ('done', 'failed', 'asked')
        elif pid == 'disk':
            ok = self.disk is not None and self.mode is not None and (self.mode != 'erase' or self.disk['empty'] or
                                                                      self.erase_ok.get_active())
        elif pid == 'account':
            ok = bool(self.fullname.get_text().strip()) and (
                self.nopass.get_active() or (self.pw1.get_text() and self.pw1.get_text() == self.pw2.get_text()))
        self.next.set_sensitive(ok)

    def tick(self):
        """Keeps the copy progress visible at the bottom on every page."""
        on_done_page = self.pages[self.index][0] == 'done'
        if on_done_page:
            self.status.set_label('')
        elif self.copy_state == 'running':
            self.status.set_label(f'{self.step}… {self.progress}%')
        elif self.copy_state == 'failed':
            self.status.set_label('Something went wrong: ' + self.copy_error)
        elif self.copy_state == 'done' and not self.finished:
            self.status.set_label('MWX 7 is on the disk.')
        if on_done_page and not self.finished:
            self.bar.set_fraction(self.progress / 100)
            self.done_step.set_label(f'{self.step} · {self.progress}%' if self.copy_state == 'running' else '')
        return True

    # ---- 0. newest updates (first start after a reset) ------------------------------------------------------------
    def page_update(self):
        p = self.page()
        p.set_valign(Gtk.Align.CENTER)
        self.update_text = Gtk.Label(label='MWX 7 was reset. Looking for a newer version…',
                                     wrap=True, max_width_chars=60, justify=Gtk.Justification.CENTER)
        self.update_text.add_css_class('big')
        p.append(self.update_text)
        self.update_bar = Gtk.ProgressBar(margin_top=18)
        p.append(self.update_bar)
        self.update_step = Gtk.Label(wrap=True, max_width_chars=70)
        self.update_step.add_css_class('hint')
        p.append(self.update_step)
        self.update_btn = Gtk.Button(label='Install updates', halign=Gtk.Align.CENTER, margin_top=14, visible=False)
        self.update_btn.add_css_class('suggested-action')
        self.update_btn.connect('clicked', lambda *_: self.run_update('install'))
        p.append(self.update_btn)
        self.update_state = 'idle'
        return p

    def start_update(self):
        if self.update_state == 'idle':
            self.run_update('check')

    def run_update(self, action):
        """check: what is new, then the person chooses (Install updates, or Next to skip); install: installs it."""
        self.update_state = 'running'
        self.update_btn.set_visible(False)
        self.validate()
        GLib.timeout_add(120, lambda: self.update_state == 'running' and (self.update_bar.pulse() or True))

        def work():
            p = subprocess.Popen(sudo('update', action), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            err, newest, count = '', '', 0
            for line in p.stdout:
                kind, _, value = line.strip().partition(' ')
                if kind == 'STEP':
                    GLib.idle_add(self.update_step.set_label, value)
                elif kind == 'ERROR':
                    err = value
                elif kind == 'NEWEST':
                    newest = value
                elif kind == 'COUNT':
                    count = int(value or 0)
            ok = p.wait() == 0
            GLib.idle_add(self.updated, action, ok, err, newest, count)
        threading.Thread(target=work, daemon=True).start()

    def updated(self, action, ok, err, newest, count):
        self.update_bar.set_fraction(1 if ok else 0)
        self.update_step.set_label('')
        if not ok:
            self.update_state = 'failed'
            self.update_text.set_label(err or 'Updates could not be installed now. Settings → Updates can do it later.')
        elif action == 'check' and count:
            self.update_state = 'asked'
            what = f'MWX 7 {newest} is available' if newest else f'{count} updates are available'
            self.update_text.set_label(f'{what}. Install it now? Recommended: you start with the newest version and '
                                       'its fixes. Next skips it; Settings → Updates can install it later.')
            self.update_btn.set_visible(True)
        else:
            self.update_state = 'done'
            self.update_text.set_label('MWX 7 is up to date.')
            GLib.timeout_add(1200, lambda: (self.pages[self.index][0] == 'update' and self.go(1)) and False)
        self.validate()
        return False

    # ---- 1. language, keyboard, time zone ----------------------------------------------------------------------
    def page_welcome(self):
        p = self.page()
        p.append(self.text('Pick your language, keyboard and time zone. You can change all of them later in Settings.'))
        grid = Gtk.Grid(column_spacing=14, row_spacing=12, margin_top=10)
        lang = Gtk.DropDown.new_from_strings([l[0] for l in LANGUAGES])
        self.kbds = keyboards()
        kbd = Gtk.DropDown.new_from_strings([k[0] for k in self.kbds])
        kbd.set_enable_search(True)
        kbd.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, 'string'))
        self.zones = timezones()
        tz = Gtk.DropDown.new_from_strings([z.replace('_', ' ') for z in self.zones])
        tz.set_enable_search(True)
        tz.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, 'string'))

        def pick_kbd(layout, variant):
            i = next((i for i, k in enumerate(self.kbds) if k[1] == layout), None)
            if i is not None:
                kbd.set_selected(i)
                self.kbd = (self.kbds[i][0], layout, variant)

        def on_lang(d, _p):
            self.lang = LANGUAGES[d.get_selected()]
            pick_kbd(self.lang[2], self.lang[3])
            if self.lang[4] and self.lang[4] in self.zones:
                tz.set_selected(self.zones.index(self.lang[4]))
        lang.connect('notify::selected', on_lang)
        kbd.connect('notify::selected', lambda d, _p: setattr(self, 'kbd', self.kbds[d.get_selected()]))
        tz.connect('notify::selected', lambda d, _p: setattr(self, 'tz', self.zones[d.get_selected()]))
        pick_kbd('us', '')
        if self.tz in self.zones:
            tz.set_selected(self.zones.index(self.tz))
        for row, (label, w) in enumerate((('Language', lang), ('Keyboard', kbd), ('Time zone', tz))):
            l = Gtk.Label(label=label, xalign=0)
            l.add_css_class('field')
            grid.attach(l, 0, row, 1, 1)
            w.set_hexpand(True)
            grid.attach(w, 1, row, 1, 1)
        p.append(grid)
        # Started from the ISO although MWX 7 is already on the disk: most likely the ISO is still attached.
        self.installed_note = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=18)
        self.installed_note.add_css_class('notice')
        self.installed_note.append(self.text('MWX 7 is already on this PC. To start it, remove the MWX 7 ISO or USB stick '
                                             '(VMware: VM → Settings → CD/DVD → untick “Connected”) and restart. '
                                             'Or continue to set it up again.'))
        b = Gtk.Button(label='Restart', halign=Gtk.Align.START)
        b.connect('clicked', lambda *_: subprocess.Popen(['systemctl', 'reboot']))
        self.installed_note.append(b)
        self.installed_note.set_visible(False)
        p.append(self.installed_note)
        if not PREVIEW and not FIRSTBOOT:
            def look():
                try:
                    found = any(d.get('has_mwx7') for d in json.loads(subprocess.run(
                        sudo('survey'), capture_output=True, text=True, timeout=30).stdout)['disks'])
                except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
                    found = False
                GLib.idle_add(self.installed_note.set_visible, found)
            threading.Thread(target=look, daemon=True).start()
        return p

    # ---- 2. disk ------------------------------------------------------------------------------------------------
    def page_disk(self):
        p = self.page()
        p.append(self.text('MWX 7 is copied to the disk you choose. Nothing is erased unless you choose that below. To keep '
                           'Windows on the same disk, first make free space in Windows (Disk Management, Shrink Volume), '
                           'or use Advanced below.'))
        self.disk_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=6)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.disk_list)
        p.append(scroll)
        self.options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        p.append(self.options)
        adv = Gtk.Button(label='Advanced: choose partitions yourself (next to Windows, disk encryption)…')
        adv.add_css_class('link')
        adv.set_halign(Gtk.Align.START)
        adv.connect('clicked', self.on_advanced)
        if PREVIEW:
            adv.set_sensitive(False)
        p.append(adv)
        self.survey = None
        return p

    def refresh_disks(self):
        if self.copy_state != 'idle':
            return
        try:
            self.survey = json.loads(subprocess.run(sudo('survey'), capture_output=True, text=True, timeout=30).stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.survey = {'disks': []}
        while (c := self.disk_list.get_first_child()):
            self.disk_list.remove(c)
        usable = [d for d in self.survey['disks'] if not d['live'] and d['big_enough']]
        group = None
        for d in self.survey['disks']:
            title, sub = describe(d)
            if not d['big_enough'] and not d['live']:
                sub = f"Too small: MWX 7 needs at least {gb(self.survey.get('min_size', 20 * 2 ** 30))}."
            b = Gtk.ToggleButton()
            b.add_css_class('disk')
            if group:
                b.set_group(group)
            group = group or b
            row = Gtk.Box(spacing=12)
            img = Gtk.Image.new_from_file(os.path.join(SHARE, 'icons', 'drive.png'))
            img.set_pixel_size(40)
            row.append(img)
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t = Gtk.Label(label=title, xalign=0)
            t.add_css_class('disk-title')
            v.append(t)
            v.append(Gtk.Label(label=sub, xalign=0, wrap=True, max_width_chars=60))
            row.append(v)
            b.set_child(row)
            b.set_sensitive(d in usable)
            b.connect('toggled', lambda btn, disk=d: btn.get_active() and self.choose_disk(disk))
            self.disk_list.append(b)
            if len(usable) == 1 and d in usable and d['empty']:
                b.set_active(True)
        if not self.survey['disks'] or not usable:
            self.disk_list.append(self.text('There is no disk MWX 7 fits on. In VMware or VirtualBox, give the virtual '
                                            'machine a disk of 20 GB or more (60 GB recommended).'))

    def choose_disk(self, disk):
        self.disk = disk
        self.mode = 'erase' if disk['empty'] else ('free' if disk['can_free'] else None)
        while (c := self.options.get_first_child()):
            self.options.remove(c)
        self.erase_ok = Gtk.CheckButton()
        if not disk['empty']:
            what = describe(disk)[1].removeprefix('Has ').split(' · ')[0].rstrip('.')
            free = Gtk.CheckButton(label=f"Use the free space ({gb(disk['free'])}) and keep everything on the disk")
            erase = Gtk.CheckButton(label='Erase this disk and use all of it')
            erase.set_group(free)
            if disk['can_free']:
                free.set_active(True)
            else:
                free.set_sensitive(False)
                free.set_label('Use the free space (there is not enough of it: MWX 7 needs '
                               f"{gb(self.survey.get('min_size', 20 * 2 ** 30))})")
            gone = ' This removes Windows too.' if any(p['kind'] == 'windows' for p in disk['parts']) else ''
            self.erase_ok = Gtk.CheckButton(label=f"Yes, delete everything on {describe(disk)[0]} ({what}).{gone}")
            self.erase_ok.add_css_class('danger')
            self.erase_ok.set_visible(False)
            self.erase_ok.connect('toggled', lambda *_: self.validate())

            def on_mode(_c):
                self.mode = 'erase' if erase.get_active() else ('free' if free.get_active() else None)
                self.erase_ok.set_visible(self.mode == 'erase')
                self.erase_ok.set_active(False)
                self.validate()
            free.connect('toggled', on_mode)
            erase.connect('toggled', on_mode)
            for w in (free, erase, self.erase_ok):
                self.options.append(w)
        self.validate()

    def on_advanced(self, *_):
        # The full installer: partitions by hand, next to Windows, encryption. It does the whole setup itself.
        subprocess.Popen(['/usr/local/bin/mwx7-install'])

    # ---- copying ------------------------------------------------------------------------------------------------
    def start_copy(self):
        self.copy_state = 'running'
        self.step = 'Preparing the disk'
        if PREVIEW:
            def fake():
                self.progress = min(100, self.progress + 4)
                if self.progress >= 100:
                    self.copy_state, self.step = 'done', 'Done'
                    return False
                self.step = 'Copying MWX 7 (preview)'
                return True
            GLib.timeout_add(250, fake)
            return

        def work():
            p = subprocess.Popen(sudo('copy', self.mode, self.disk['path']), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
            last_error = ''
            for line in p.stdout:
                kind, _, value = line.strip().partition(' ')
                if kind == 'PROGRESS' and value.isdigit():
                    self.progress = int(value)
                elif kind == 'STEP':
                    self.step = value
                elif kind == 'ERROR':
                    last_error = value
            ok = p.wait() == 0
            self.copy_error = last_error or 'copying stopped unexpectedly'
            self.copy_state = 'done' if ok else 'failed'
            GLib.idle_add(self.maybe_finish)
        threading.Thread(target=work, daemon=True).start()

    # ---- 3. Wi-Fi -----------------------------------------------------------------------------------------------
    def online(self):
        # Asked on every page change; NetworkManager is only asked again after a few seconds.
        now = GLib.get_monotonic_time()
        if getattr(self, '_online', None) and now - self._online[1] < 3_000_000:
            return self._online[0]
        self._online = (self.check_online(), now)
        return self._online[0]

    @staticmethod
    def check_online():
        try:
            state = subprocess.run(['nmcli', '-t', '-f', 'STATE', 'general'], capture_output=True, text=True,
                                   timeout=5).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return True  # no NetworkManager: nothing the page could do
        return state.startswith('connected') or not Setup.wifi_device()

    @staticmethod
    def wifi_device():
        try:
            out = subprocess.run(['nmcli', '-t', '-f', 'TYPE', 'device'], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            return False
        return 'wifi' in out.split()

    def page_wifi(self):
        p = self.page()
        p.append(self.text('Connect now to get updates right away, or skip this and do it later from the status bar.'))
        self.nets = Gtk.ListBox()
        self.nets.add_css_class('nets')
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.nets)
        p.append(scroll)
        row = Gtk.Box(spacing=8)
        self.wifi_pw = Gtk.PasswordEntry(placeholder_text='Network password', show_peek_icon=True, hexpand=True)
        row.append(self.wifi_pw)
        join = Gtk.Button(label='Connect')
        join.connect('clicked', self.on_join)
        row.append(join)
        p.append(row)
        self.wifi_msg = self.text('')
        p.append(self.wifi_msg)
        return p

    def refresh_wifi(self):
        self.next.set_label('Skip' if not self.online() else 'Next')
        try:
            out = subprocess.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list', '--rescan',
                                  'yes'], capture_output=True, text=True, timeout=15).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ''
        while (c := self.nets.get_first_child()):
            self.nets.remove(c)
        seen = set()
        for line in out.splitlines():
            parts = re.split(r'(?<!\\):', line)
            if len(parts) < 3 or not parts[0] or parts[0] in seen:
                continue
            seen.add(parts[0])
            r = Gtk.ListBoxRow()
            r.ssid = parts[0].replace('\\:', ':')
            r.secure = bool(parts[2])
            r.set_child(Gtk.Label(label=f"{r.ssid}   ·   {parts[1]}%{'   🔒' if r.secure else ''}", xalign=0))
            self.nets.append(r)

    def on_join(self, *_):
        r = self.nets.get_selected_row()
        if not r:
            self.wifi_msg.set_label('Pick a network first.')
            return
        cmd = ['nmcli', 'device', 'wifi', 'connect', r.ssid] + (['password', self.wifi_pw.get_text()] if r.secure else [])
        self.wifi_msg.set_label(f'Connecting to {r.ssid}…')

        def work():
            res = subprocess.run(cmd, capture_output=True, text=True)
            GLib.idle_add(lambda: (self.wifi_msg.set_label('Connected.' if res.returncode == 0 else
                                                           'That did not work. Check the password and try again.'),
                                   self.next.set_label('Next'), False)[-1])
        threading.Thread(target=work, daemon=True).start()

    # ---- 4. account ---------------------------------------------------------------------------------------------
    def page_account(self):
        p = self.page()
        grid = Gtk.Grid(column_spacing=14, row_spacing=10)
        self.fullname = Gtk.Entry(placeholder_text='Your name', hexpand=True)
        self.login_label = Gtk.Label(xalign=0)
        self.login_label.add_css_class('hint')
        self.pw1 = Gtk.PasswordEntry(placeholder_text='Password', show_peek_icon=True)
        self.pw2 = Gtk.PasswordEntry(placeholder_text='Type it again', show_peek_icon=True)
        self.nopass = Gtk.CheckButton(label='No password (anyone at this PC can use it; you can add one later in Settings)')
        for w in (self.fullname, self.pw1, self.pw2):
            w.connect('changed', lambda *_: self.on_account_changed())
        self.nopass.connect('toggled', lambda c: (self.pw1.set_sensitive(not c.get_active()),
                                                  self.pw2.set_sensitive(not c.get_active()), self.validate()))
        rows = (('Name', self.fullname), ('', self.login_label), ('Password', self.pw1), ('', self.pw2),
                ('', self.nopass))
        for i, (label, w) in enumerate(rows):
            l = Gtk.Label(label=label, xalign=0)
            l.add_css_class('field')
            grid.attach(l, 0, i, 1, 1)
            grid.attach(w, 1, i, 1, 1)
        p.append(grid)
        l = Gtk.Label(label='Picture', xalign=0, margin_top=6)
        l.add_css_class('field')
        p.append(l)
        flow = Gtk.FlowBox(max_children_per_line=10, min_children_per_line=10, selection_mode=Gtk.SelectionMode.SINGLE,
                           column_spacing=6, row_spacing=6, homogeneous=True)
        flow.add_css_class('pictures')
        for f in sorted(os.listdir(AVATARS)) if os.path.isdir(AVATARS) else []:
            path = os.path.join(AVATARS, f)
            child = Gtk.FlowBoxChild()
            child.path = path
            try:
                buf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 52, 52, False)
            except GLib.Error:
                continue
            pic = Gtk.Image.new_from_paintable(Gdk.Texture.new_for_pixbuf(buf))
            pic.set_pixel_size(52)
            child.set_child(pic)
            flow.append(child)
            if path == self.picture:
                flow.select_child(child)
        flow.connect('child-activated', lambda _f, c: setattr(self, 'picture', c.path))
        p.append(flow)
        self.on_account_changed()
        return p

    def on_account_changed(self):
        name = self.fullname.get_text().strip()
        self.login = login_from(name) if name else ''
        self.login_label.set_label(f'You sign in as “{self.login}”, and this PC is called “{self.login}-pc”.'
                                   if name else 'Your first name is enough.')
        self.validate()

    # ---- 5. finishing -------------------------------------------------------------------------------------------
    def page_done(self):
        p = self.page()
        p.set_valign(Gtk.Align.CENTER)
        self.done_text = Gtk.Label(label='Almost there. MWX 7 is being copied to the disk.', wrap=True,
                                   max_width_chars=60, justify=Gtk.Justification.CENTER)
        self.done_text.add_css_class('big')
        p.append(self.done_text)
        self.bar = Gtk.ProgressBar(margin_top=18)
        p.append(self.bar)
        self.done_step = Gtk.Label()
        self.done_step.add_css_class('hint')
        p.append(self.done_step)
        self.restart = Gtk.Button(label='Restart now', halign=Gtk.Align.CENTER, margin_top=18)
        self.restart.add_css_class('primary')
        self.restart.set_visible(False)
        self.restart.connect('clicked', self.on_restart)
        p.append(self.restart)
        return p

    def start_finish(self):
        self.answers = {'fullname': self.fullname.get_text().strip(), 'login': self.login,
                        'hostname': f'{self.login}-pc', 'password': '' if self.nopass.get_active() else self.pw1.get_text(),
                        'language': self.lang[1], 'layout': self.kbd[1], 'variant': self.kbd[2], 'timezone': self.tz,
                        'picture': self.picture}
        self.maybe_finish()

    def maybe_finish(self):
        if self.pages[self.index][0] != 'done' or self.finished:
            return False
        if self.copy_state == 'failed':
            self.done_text.set_label('MWX 7 could not be put on the disk:\n' + self.copy_error)
            self.restart.set_label('Restart and try again')
            self.restart.set_visible(True)
            return False
        if self.copy_state != 'done':
            return False
        self.finished = True
        self.done_text.set_label('Saving your settings…')
        if PREVIEW:
            GLib.timeout_add(800, self.all_done)
            return False

        def work():
            fd, path = tempfile.mkstemp(prefix='mwx7-answers-', suffix='.json')
            with os.fdopen(fd, 'w') as f:
                json.dump(self.answers, f)
            r = subprocess.run(sudo('finish', path, *(['--here'] if FIRSTBOOT else [])), capture_output=True, text=True)
            err = next((l[6:] for l in r.stdout.splitlines() if l.startswith('ERROR ')), r.stderr.strip()[-200:])
            GLib.idle_add(self.all_done, None if r.returncode == 0 else err or 'unknown error')
        threading.Thread(target=work, daemon=True).start()
        return False

    def all_done(self, error=None):
        self.bar.set_fraction(1)
        if error:
            self.done_text.set_label('Your settings could not be saved:\n' + error)
            self.restart.set_label('Restart and try again')
        elif PREVIEW:
            self.done_text.set_label('That was the whole setup. In a real setup, MWX 7 now restarts into the logon screen.')
            self.restart.set_label('Close')
        elif FIRSTBOOT:
            self.done_text.set_label('MWX 7 is ready. It restarts in a moment; then click your picture to sign in.')
            self.done_step.set_label('')
            self.status.set_label('')
            return False  # install.py restarts the PC itself (this setup's user no longer exists)
        else:
            self.done_text.set_label('MWX 7 is ready. It restarts in a moment; then click your picture to sign in.')
            self.restart.set_label('Restart now')
            GLib.timeout_add_seconds(6, lambda: self.on_restart() and False)
        self.done_step.set_label('')
        self.status.set_label('')
        self.restart.set_visible(True)
        return False

    def on_restart(self, *_):
        if PREVIEW:
            self.quit()
            return False
        subprocess.Popen(['systemctl', 'reboot'])
        return False

    # ---- helpers ------------------------------------------------------------------------------------------------
    @staticmethod
    def page():
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        b.add_css_class('page')
        return b

    @staticmethod
    def text(t):
        l = Gtk.Label(label=t, xalign=0, wrap=True, max_width_chars=70)  # wrap inside the card, never widen it
        l.add_css_class('text')
        return l


if __name__ == '__main__':
    Setup().run(None)
