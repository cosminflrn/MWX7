"""Get Apps (native): a small store of popular apps from Flathub. Install, Open and Remove go through Flatpak, system-wide
(mwx7-admin does the privileged part through pkexec). Each card shows the app's own icon once it is installed (Flatpak
puts it in its exports); before that a generic one, so no logos are shipped here."""
import glob
import os
import re
import subprocess
import sys
import threading

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import GLib, Gtk, Pango  # noqa: E402

ADMIN = '/usr/share/mwx7/bin/mwx7-admin'
EXPORTS = ['/var/lib/flatpak/exports/share/icons/hicolor', os.path.expanduser('~/.local/share/flatpak/exports/share/icons/hicolor')]
# (Flatpak id, name, one-line description). mwx7-admin only accepts these ids: keep FLATPAK_REFS there in step.
CATALOG = [
    ('org.mozilla.firefox', 'Firefox', 'A fast, private web browser.'),
    ('org.chromium.Chromium', 'Chromium', 'The open-source browser behind Chrome.'),
    ('org.libreoffice.LibreOffice', 'LibreOffice', 'Documents, spreadsheets and presentations.'),
    ('com.visualstudio.code', 'Visual Studio Code', 'A code editor with extensions.'),
    ('org.videolan.VLC', 'VLC', 'Plays almost any video or music file.'),
    ('org.gimp.GIMP', 'GIMP', 'Edit and retouch photos and images.'),
    ('org.inkscape.Inkscape', 'Inkscape', 'Draw vector graphics and illustrations.'),
    ('org.audacityteam.Audacity', 'Audacity', 'Record and edit audio.'),
    ('com.obsproject.Studio', 'OBS Studio', 'Record your screen and stream live.'),
    ('com.valvesoftware.Steam', 'Steam', 'Buy, download and play games.'),
    ('com.discordapp.Discord', 'Discord', 'Chat with friends and communities.'),
    ('org.telegram.desktop', 'Telegram', 'Fast, secure messaging.'),
    ('com.spotify.Client', 'Spotify', 'Stream music and podcasts.'),
    ('us.zoom.Zoom', 'Zoom', 'Video meetings and calls.'),
]
CSS = """
window.mwx7-store > box { background: #f4f7fc; }
.st-bar { padding: 8px 10px; background: linear-gradient(180deg, #fbfdff, #e9f0f9); border-bottom: 1px solid #c9d6e8; }
.st-card { background: #fff; border: 1px solid #c3d1e4; border-radius: 4px; padding: 10px; box-shadow: 0 1px 2px rgba(40,70,110,.12); }
.st-name { font-weight: 700; color: #1c2530; }
.st-desc { color: #55657a; font-size: 12px; }
.st-state { color: #3b6a3b; font-size: 11px; }
.st-note { padding: 24px; color: #55657a; }
flowboxchild { padding: 5px; background: transparent; }
progressbar.st-progress trough, progressbar.st-progress progress { min-height: 8px; }
"""
PCT = re.compile(r'(\d{1,3})%')
STEP = re.compile(r'(\d+)/(\d+)')


def app_icon(ref):
    """The icon Flatpak exported for an installed app, or None."""
    for base in EXPORTS:
        for size in ('128x128', '256x256', '64x64', '512x512', '48x48', 'scalable'):
            for ext in ('png', 'svg'):
                path = f'{base}/{size}/apps/{ref}.{ext}'
                if os.path.exists(path):
                    return path
    return None


def installed_refs():
    """Ids of the system-wide Flatpak apps installed, or None if Flatpak itself is missing."""
    try:
        r = subprocess.run(['flatpak', 'list', '--system', '--app', '--columns=application'], capture_output=True, text=True,
                           timeout=30, env=dict(os.environ, LC_ALL='C'))
    except (OSError, subprocess.SubprocessError):
        return None
    return set(r.stdout.split()) if r.returncode == 0 else set()


class Card:
    def __init__(self, store, ref, name, desc):
        self.store, self.ref, self.name, self.desc = store, ref, name, desc
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=190)
        self.box.add_css_class('st-card')
        top = Gtk.Box(spacing=10)
        self.icon = Gtk.Image(pixel_size=48)
        top.append(self.icon)
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        n = Gtk.Label(label=name, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        n.add_css_class('st-name')
        self.state = Gtk.Label(label='', xalign=0)
        self.state.add_css_class('st-state')
        title.append(n)
        title.append(self.state)
        top.append(title)
        self.box.append(top)
        d = Gtk.Label(label=desc, xalign=0, wrap=True, lines=2, max_width_chars=24, vexpand=True, valign=Gtk.Align.START)
        d.add_css_class('st-desc')
        self.box.append(d)
        self.progress = Gtk.ProgressBar(visible=False)
        self.progress.add_css_class('st-progress')
        self.box.append(self.progress)
        row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        self.remove_btn = Gtk.Button(label='Remove')
        self.remove_btn.connect('clicked', lambda *_: store.run(self, 'remove'))
        self.main_btn = Gtk.Button(label='Install')
        self.main_btn.connect('clicked', self.on_main)
        row.append(self.remove_btn)
        row.append(self.main_btn)
        self.box.append(row)
        self.pulse_id = 0
        self.set_installed(False)

    def on_main(self, *_):
        if self.installed:
            self.launch()
        else:
            self.store.run(self, 'install')

    def launch(self):
        """Flatpak starts the app itself, detached so closing Get Apps doesn't close it. A first start can take a while
        in a VM (Flatpak sets the app up), so the button says so; if the app quits at once, the reason is shown."""
        log = os.path.join(GLib.get_user_cache_dir(), 'mwx7', 'get-apps-' + self.ref + '.log')
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, 'w') as out:
            p = subprocess.Popen(['flatpak', 'run', self.ref], start_new_session=True, stdout=out, stderr=out)
        self.main_btn.set_label('Starting…')
        self.main_btn.set_sensitive(False)

        def check():
            self.main_btn.set_label('Open')
            self.main_btn.set_sensitive(True)
            code = p.poll()
            if code not in (None, 0):
                try:
                    last = [l for l in open(log).read().splitlines() if l.strip()][-1]
                except (OSError, IndexError):
                    last = f'it stopped with code {code}'
                self.store.note.set_label(f'{self.name} did not start: {last[:200]}')
                self.store.note.set_visible(True)
            return False
        GLib.timeout_add_seconds(8, check)

    def set_installed(self, yes):
        self.installed = yes
        self.state.set_label('Installed' if yes else '')
        self.main_btn.set_label('Open' if yes else 'Install')
        self.remove_btn.set_visible(yes)
        path = app_icon(self.ref) if yes else None
        if path:
            self.icon.set_from_file(path)
        else:
            self.icon.set_from_icon_name('application-x-executable')

    def busy(self, text):
        """text: what is going on ('Installing…'), or None when it ended."""
        working = text is not None
        self.progress.set_visible(working)
        self.state.set_label(text or ('Installed' if self.installed else ''))
        self.main_btn.set_visible(not working)
        self.remove_btn.set_visible(not working and self.installed)
        if working:
            self.progress.set_fraction(0)
            self.pulse_id = GLib.timeout_add(120, self.pulse)
        elif self.pulse_id:
            GLib.source_remove(self.pulse_id)
            self.pulse_id = 0

    def pulse(self):
        # Until a percentage shows up (Flatpak prints none while it looks things up) the bar just moves.
        if self.progress.get_fraction() == 0:
            self.progress.pulse()
        return True

    def matches(self, q):
        return q in self.name.lower() or q in self.desc.lower()


class Store:
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-store')
        self.cards = []
        self.working = False
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('File', [('Refresh', 'refresh', self.refresh), None, ('Close', 'close', win.close)]),
            ('Help', [('About Get Apps', 'about', lambda: subprocess.Popen(['/usr/share/mwx7/bin/mwx7-app', 'about']))]),
        ]))
        bar = Gtk.Box(spacing=8)
        bar.add_css_class('st-bar')
        self.search = Gtk.SearchEntry(placeholder_text='Search apps', hexpand=True)
        self.search.connect('search-changed', lambda *_: self.grid.invalidate_filter())
        bar.append(self.search)
        root.append(bar)
        self.note = Gtk.Label(label='', wrap=True, visible=False)
        self.note.add_css_class('st-note')
        root.append(self.note)
        self.grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=4,
                                homogeneous=True, valign=Gtk.Align.START, margin_start=6, margin_end=6, margin_top=6)
        self.grid.set_filter_func(lambda child: child.card.matches(self.search.get_text().strip().lower()))
        for ref, name, desc in CATALOG:
            c = Card(self, ref, name, desc)
            self.cards.append(c)
            child = Gtk.FlowBoxChild()
            child.set_child(c.box)
            child.card = c
            self.grid.append(child)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_child(self.grid)
        root.append(sc)
        win.set_default_size(760, 560)
        self.refresh()
        return root

    def refresh(self):
        def work():
            GLib.idle_add(self.apply, installed_refs())
        threading.Thread(target=work, daemon=True).start()

    def apply(self, refs):
        if refs is None:
            self.note.set_label('Flatpak is not installed on this PC, so apps can not be added here yet.')
        self.note.set_visible(refs is None)
        for c in self.cards:
            if not self.working:
                c.set_installed(bool(refs) and c.ref in refs)

    def run(self, card, action):
        if self.working:
            return
        self.working = True
        self.note.set_visible(False)
        card.busy('Installing…' if action == 'install' else 'Removing…')
        for c in self.cards:
            if c is not card:
                c.main_btn.set_sensitive(False)
                c.remove_btn.set_sensitive(False)

        def work():
            code, last = 1, ''
            try:
                proc = subprocess.Popen(['pkexec', ADMIN, 'flatpak', action, card.ref], stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:  # text mode turns Flatpak's carriage returns into line ends
                    line = line.strip()
                    if not line:
                        continue
                    last = line
                    m = PCT.search(line)
                    if m:
                        GLib.idle_add(card.progress.set_fraction, min(int(m.group(1)), 100) / 100)
                    elif line.lower().startswith(('installing', 'uninstalling', 'updating')):
                        s = STEP.search(line)
                        GLib.idle_add(card.state.set_label, f'{"Installing" if action == "install" else "Removing"} {s.group(0)}…'
                                      if s else line[:40])
                code = proc.wait()
            except OSError:
                last = 'pkexec is missing'
            GLib.idle_add(self.done, card, action, code, last)
        threading.Thread(target=work, daemon=True).start()

    def done(self, card, action, code, last):
        self.working = False
        card.busy(None)
        for c in self.cards:
            c.main_btn.set_sensitive(True)
            c.remove_btn.set_sensitive(True)
        if code == 0:
            card.set_installed(action == 'install')
        else:
            # 126/127: the password prompt was cancelled or not allowed; say nothing alarming then.
            if code not in (126, 127):
                self.note.set_label(f'{card.name} could not be {"installed" if action == "install" else "removed"}: {last[:160]}')
                self.note.set_visible(True)
            card.set_installed(card.installed)
        return False


if __name__ == '__main__':
    mwx7ui.App('org.mwx7.store', 'Get Apps', 'store', (760, 560), CSS, Store().build).run_main()
