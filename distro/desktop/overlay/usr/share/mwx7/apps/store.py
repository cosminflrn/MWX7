"""Get Apps (native): a store for Flathub. A curated front page (with categories), a search that also asks Flathub for any
other app, a detail page per app, an Updates tab, and Install / Open / Remove / Update all through Flatpak, system-wide
(mwx7-admin does the privileged part through pkexec). App icons are fetched from Flathub when the app is shown and cached in
~/.cache/mwx7/store-icons/; offline (or before they arrive) a generic icon is used, so no logos are shipped here."""
import html
import json
import os
import re
import subprocess
import sys
import threading
import urllib.request

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import GLib, Gtk, Pango  # noqa: E402

ADMIN = '/usr/share/mwx7/bin/mwx7-admin'
API = 'https://flathub.org/api/v2'
ICON_CACHE = os.path.join(GLib.get_user_cache_dir(), 'mwx7', 'store-icons')
# Same shape mwx7-admin enforces; checked here too so nothing odd ever becomes a file name or an argument.
APP_ID = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{1,199}\Z')
# (Flatpak id, name, one-line description, category). The front page; anything else comes from searching Flathub.
CATALOG = [
    ('org.mozilla.firefox', 'Firefox', 'A fast, private web browser.', 'Internet'),
    ('org.chromium.Chromium', 'Chromium', 'The open-source browser behind Chrome.', 'Internet'),
    ('org.libreoffice.LibreOffice', 'LibreOffice', 'Documents, spreadsheets and presentations.', 'Office'),
    ('com.visualstudio.code', 'Visual Studio Code', 'A code editor with extensions.', 'Development'),
    ('org.videolan.VLC', 'VLC', 'Plays almost any video or music file.', 'Media'),
    ('org.gimp.GIMP', 'GIMP', 'Edit and retouch photos and images.', 'Graphics'),
    ('org.inkscape.Inkscape', 'Inkscape', 'Draw vector graphics and illustrations.', 'Graphics'),
    ('org.audacityteam.Audacity', 'Audacity', 'Record and edit audio.', 'Media'),
    ('com.obsproject.Studio', 'OBS Studio', 'Record your screen and stream live.', 'Media'),
    ('com.valvesoftware.Steam', 'Steam', 'Buy, download and play games.', 'Games'),
    ('com.discordapp.Discord', 'Discord', 'Chat with friends and communities.', 'Communication'),
    ('org.telegram.desktop', 'Telegram', 'Fast, secure messaging.', 'Communication'),
    ('com.spotify.Client', 'Spotify', 'Stream music and podcasts.', 'Media'),
    ('us.zoom.Zoom', 'Zoom', 'Video meetings and calls.', 'Communication'),
]
# Sidebar: label -> how to ask Flathub for more apps of it (a Flathub category, or a search for Communication).
CATEGORIES = [('Internet', ('collection', 'Network')), ('Media', ('collection', 'AudioVideo')), ('Graphics', ('collection', 'Graphics')),
              ('Office', ('collection', 'Office')), ('Games', ('collection', 'Game')), ('Development', ('collection', 'Development')),
              ('Communication', ('search', 'chat'))]
CSS = """
window.mwx7-store > box { background: #f4f7fc; }
.st-bar { padding: 8px 10px; background: linear-gradient(180deg, #fbfdff, #e9f0f9); border-bottom: 1px solid #c9d6e8; }
.st-card { background: #fff; border: 1px solid #c3d1e4; border-radius: 4px; padding: 10px; box-shadow: 0 1px 2px rgba(40,70,110,.12); }
.st-name { font-weight: 700; color: #1c2530; }
.st-desc { color: #55657a; font-size: 12px; }
.st-state { color: #3b6a3b; font-size: 11px; }
.st-note { padding: 24px; color: #55657a; }
window.mwx7-store .st-card button { min-height: 24px; padding: 0 14px; border-radius: 3px; color: #1c2530;
  border: 1px solid #8b9db5; box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
  background: linear-gradient(180deg, #f6f9fd 0%, #e6edf6 49%, #d6e1ee 50%, #e3ebf5 100%); }
window.mwx7-store .st-card button:hover { border-color: #3c7fb1;
  background: linear-gradient(180deg, #eaf6fd 0%, #d9f0fc 49%, #bee6fd 50%, #a7d9f5 100%); }
window.mwx7-store .st-card button:active { background: linear-gradient(180deg, #c2e4f6 0%, #a9d9f2 49%, #90cbeb 50%, #a4d5ef 100%); }
window.mwx7-store .st-card button:disabled { color: #9aa5b3; }
flowboxchild { padding: 5px; background: transparent; }
.st-side { background: #e9f0f9; border-right: 1px solid #c9d6e8; min-width: 160px; }
.st-side row { padding: 7px 14px; color: #1c2530; border-radius: 0; }
.st-side row:hover { background: #dcebf8; }
.st-side row:selected { background: #bcd9f3; color: #0b2a4a; font-weight: 700; }
.st-title { font-size: 16px; font-weight: 700; color: #1c2530; padding: 10px 12px 2px 12px; }
.st-big { font-size: 20px; font-weight: 700; color: #1c2530; }
.st-err { background: #fdecea; color: #8a1f17; border-bottom: 1px solid #e6b3ae; padding: 6px 10px; }
.st-body { color: #2b3a4d; }
progressbar.st-progress trough, progressbar.st-progress progress { min-height: 8px; }
"""
PCT = re.compile(r'(\d{1,3})%')
STEP = re.compile(r'(\d+)/(\d+)')
ENV = dict(os.environ, LC_ALL='C')


def http_json(path, body=None):
    """JSON from the Flathub API, or None when offline / it fails. Runs in a background thread, never in the UI."""
    req = urllib.request.Request(API + path, headers={'User-Agent': 'MWX7-GetApps', 'Accept': 'application/json'})
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r)
    except (OSError, ValueError):
        return None


def bg(fn, then):
    """Run fn() in a thread; then(result) back on the UI thread."""
    threading.Thread(target=lambda: GLib.idle_add(then, fn()), daemon=True).start()


_icon_slots = threading.Semaphore(4)


def icon_file(ref, url=None):
    """Path of the cached Flathub icon for ref, downloading it first if needed; None if that is not possible (offline)."""
    if not APP_ID.match(ref):
        return None
    path = os.path.join(ICON_CACHE, ref + '.png')
    if os.path.exists(path):
        return path
    with _icon_slots:
        if not url:
            d = http_json('/appstream/' + ref)
            url = d.get('icon') if isinstance(d, dict) else None
        if not url or not url.startswith('https://'):
            return None
        try:
            os.makedirs(ICON_CACHE, exist_ok=True)
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'MWX7-GetApps'}), timeout=12) as r:
                data = r.read(2_000_000)
            if not data.startswith(b'\x89PNG'):
                return None
            tmp = path + '.part'
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, path)
            return path
        except OSError:
            return None


def plain(text):
    """Flathub descriptions are small HTML; show them as text."""
    text = re.sub(r'</p>|<br ?/?>', '\n\n', text or '')
    text = re.sub(r'<li>', '\n• ', text)
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]+', ' ', text)).strip()


def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024


def hit_entry(h):
    """A Flathub search/collection hit as (id, name, summary, icon url), or None if it is not an app."""
    ref = h.get('app_id') or ''
    if not APP_ID.match(ref) or h.get('type') not in (None, 'desktop-application', 'console-application'):
        return None
    return (ref, h.get('name') or ref, h.get('summary') or '', h.get('icon'))


def flatpak_lines(*args):
    """Output lines of a read-only flatpak command, or None if flatpak is missing / the command failed."""
    try:
        r = subprocess.run(['flatpak', *args], capture_output=True, text=True, timeout=90, env=ENV)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.splitlines() if r.returncode == 0 else None


class Actions:
    """Install / Open / Remove buttons with state text and a progress bar for one app; used on cards and on the detail page."""

    def __init__(self, store, ref, name):
        self.store, self.ref, self.name = store, ref, name
        self.state = Gtk.Label(label='', xalign=0, wrap=True)
        self.state.add_css_class('st-state')
        self.progress = Gtk.ProgressBar(visible=False)
        self.progress.add_css_class('st-progress')
        self.row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        self.remove_btn = Gtk.Button(label='Remove')
        self.remove_btn.connect('clicked', lambda *_: store.run(ref, name, 'remove'))
        self.main_btn = Gtk.Button(label='Install')
        self.main_btn.connect('clicked', lambda *_: store.launch(ref, name) if ref in store.installed else store.run(ref, name, 'install'))
        self.row.append(self.remove_btn)
        self.row.append(self.main_btn)
        store.live.append(self)
        self.sync()

    def sync(self):
        s = self.store
        job = s.job if s.job and s.job['ref'] == self.ref else None
        inst = self.ref in s.installed
        starting = s.starting.get(self.ref)
        self.progress.set_visible(bool(job))
        if job:
            self.progress.set_fraction(job['fraction'])
        self.state.set_label(job['text'] if job else ('Starting…' if starting else 'Installed' if inst else ''))
        self.main_btn.set_visible(not job)
        self.remove_btn.set_visible(not job and inst)
        self.main_btn.set_label('Starting…' if starting else 'Open' if inst else 'Install')
        # Only one install/update runs at a time (one privileged helper), so the other buttons wait.
        idle = not s.job
        self.main_btn.set_sensitive(not starting and idle)
        self.remove_btn.set_sensitive(idle)


class Card:
    def __init__(self, store, entry):
        ref, name, desc, icon_url = entry
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=190)
        self.box.add_css_class('st-card')
        top = Gtk.Box(spacing=10)
        self.icon = Gtk.Image(pixel_size=48, icon_name='application-x-executable')
        top.append(self.icon)
        self.actions = Actions(store, ref, name)
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        n = Gtk.Label(label=name, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        n.add_css_class('st-name')
        title.append(n)
        title.append(self.actions.state)
        top.append(title)
        self.box.append(top)
        d = Gtk.Label(label=desc, xalign=0, wrap=True, lines=2, max_width_chars=24, vexpand=True, valign=Gtk.Align.START,
                      ellipsize=Pango.EllipsizeMode.END)
        d.add_css_class('st-desc')
        self.box.append(d)
        self.box.append(self.actions.progress)
        more = Gtk.Button(label='Details', halign=Gtk.Align.START)
        more.connect('clicked', lambda *_: store.show_detail(entry))
        bottom = Gtk.Box(spacing=6)
        bottom.append(more)
        self.actions.row.set_hexpand(True)
        bottom.append(self.actions.row)
        self.box.append(bottom)
        store.load_icon(ref, icon_url, self.icon)


class Store:
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-store')
        self.live = []          # Actions currently on screen (cards, detail page)
        self.installed = set()
        self.installed_names = {}
        self.job = None         # {'ref', 'text', 'fraction'} of the one running install/remove/update
        self.starting = {}
        self.pulse_id = 0
        self.gen = 0            # bumps on every page change so late network answers are dropped
        self.updates = None     # [(id, name)] or None = not checked yet
        self.page = ('featured',)
        self.search_id = 0
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('File', [('Refresh', 'refresh', self.refresh), None, ('Close', 'close', win.close)]),
            ('Help', [('About Get Apps', 'about', lambda: subprocess.Popen(['/usr/share/mwx7/bin/mwx7-app', 'about']))]),
        ]))
        bar = Gtk.Box(spacing=8)
        bar.add_css_class('st-bar')
        self.search = Gtk.SearchEntry(placeholder_text='Search all of Flathub', hexpand=True)
        self.search.connect('search-changed', self.on_search)
        bar.append(self.search)
        root.append(bar)
        errbox = Gtk.Box(spacing=8, visible=False)
        errbox.add_css_class('st-err')
        self.note = Gtk.Label(label='', wrap=True, xalign=0, hexpand=True, selectable=True)
        dismiss = Gtk.Button(label='Dismiss')
        dismiss.connect('clicked', lambda *_: errbox.set_visible(False))
        errbox.append(self.note)
        errbox.append(dismiss)
        self.errbox = errbox
        root.append(errbox)

        body = Gtk.Box(vexpand=True)
        self.side = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.side.add_css_class('st-side')
        self.side_rows = {}
        for key, label in [('featured', 'Featured')] + [(c, c) for c, _ in CATEGORIES] + [('installed', 'Installed'), ('updates', 'Updates')]:
            lab = Gtk.Label(label=label, xalign=0)
            row = Gtk.ListBoxRow(child=lab)
            row.key, row.lab = key, lab
            self.side.append(row)
            self.side_rows[key] = row
        self.side.connect('row-selected', lambda _b, row: row and self.go((row.key,), from_side=True))
        body.append(self.side)

        self.stack = Gtk.Stack(hexpand=True)
        # Page 1: a grid of app cards under a title.
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.title = Gtk.Label(label='', xalign=0)
        self.title.add_css_class('st-title')
        page.append(self.title)
        self.status = Gtk.Label(label='', xalign=0, margin_start=12, margin_top=4)
        self.status.add_css_class('st-desc')
        page.append(self.status)
        self.grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=3,
                                homogeneous=True, valign=Gtk.Align.START, margin_start=6, margin_end=6, margin_top=6)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_child(self.grid)
        page.append(sc)
        self.stack.add_named(page, 'apps')
        # Page 2: detail of one app.
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=14, margin_end=14, margin_top=10)
        self.stack.add_named(self.detail, 'detail')
        # Page 3: updates.
        up = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=14, margin_end=14, margin_top=10, margin_bottom=10)
        t = Gtk.Label(label='Updates', xalign=0)
        t.add_css_class('st-big')
        up.append(t)
        self.up_status = Gtk.Label(label='', xalign=0, wrap=True)
        self.up_status.add_css_class('st-desc')
        up.append(self.up_status)
        self.up_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        usc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        usc.set_child(self.up_list)
        up.append(usc)
        self.up_progress = Gtk.ProgressBar(visible=False)
        self.up_progress.add_css_class('st-progress')
        up.append(self.up_progress)
        ub = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        self.up_check = Gtk.Button(label='Check again')
        self.up_check.connect('clicked', lambda *_: self.check_updates(True))
        self.up_all = Gtk.Button(label='Update all')
        self.up_all.connect('clicked', lambda *_: self.run('*updates', 'Updates', 'update'))
        ub.append(self.up_check)
        ub.append(self.up_all)
        up.append(ub)
        self.stack.add_named(up, 'updates')
        body.append(self.stack)
        root.append(body)
        win.set_default_size(860, 580)
        self.side.select_row(self.side_rows['featured'])
        self.refresh()
        return root

    # ---- navigation -------------------------------------------------------------------------------------------------
    def go(self, page, from_side=False):
        self.gen += 1
        self.page = page
        self.live = []
        if not from_side:
            self.side.unselect_all()
        key = page[0]
        if key != 'search' and self.search.get_text():
            self.search.set_text('')
        if key == 'updates':
            self.stack.set_visible_child_name('updates')
            self.fill_updates()
            if self.updates is None:
                self.check_updates()
            return
        gen = self.gen
        if key == 'featured':
            self.show('Featured', [(r, n, d, None) for r, n, d, _c in CATALOG])
        elif key == 'installed':
            ents = [(r, self.installed_names.get(r, r), 'Installed on this PC', None) for r in sorted(self.installed, key=str.lower)]
            self.show('Installed', ents, '' if ents else 'No apps installed through Flatpak yet.')
        elif key == 'search':
            self.do_search(page[1], gen)
        else:
            cur = [(r, n, d, None) for r, n, d, c in CATALOG if c == key]
            self.show(key, cur, 'Looking for more on Flathub…')
            kind, arg = dict(CATEGORIES)[key]
            if kind == 'collection':
                def fetch():
                    return http_json(f'/collection/category/{arg}?page=1&per_page=24')
            else:
                def fetch():
                    return http_json('/search', {'query': arg})

            def more(data):
                if gen != self.gen:
                    return False
                if not isinstance(data, dict):
                    self.status.set_label('Showing the built-in list. Connect to the internet to see more from Flathub.')
                    return False
                seen = {e[0] for e in cur}
                extra = [e for e in map(hit_entry, data.get('hits', [])) if e and e[0] not in seen]
                self.show(key, cur + extra)
                return False
            bg(fetch, more)

    def show(self, title, entries, status=''):
        self.live = []
        self.title.set_label(title)
        self.status.set_label(status)
        self.status.set_visible(bool(status))
        while (c := self.grid.get_first_child()):
            self.grid.remove(c)
        for e in entries:
            self.grid.append(Gtk.FlowBoxChild(child=Card(self, e).box))
        self.stack.set_visible_child_name('apps')

    def on_search(self, *_):
        if self.search_id:
            GLib.source_remove(self.search_id)
            self.search_id = 0
        q = self.search.get_text().strip()
        if not q:
            if self.page[0] == 'search':
                self.side.select_row(self.side_rows['featured'])
            return

        def fire():
            self.search_id = 0
            self.go(('search', q))
            return False
        self.search_id = GLib.timeout_add(350, fire)

    def do_search(self, q, gen):
        ql = q.lower()
        cur = [(r, n, d, None) for r, n, d, _c in CATALOG if ql in n.lower() or ql in d.lower() or ql in r.lower()]
        title = f'Results for “{q}”'
        self.show(title, cur, 'Searching Flathub…')

        def done(data):
            if gen != self.gen:
                return False
            if not isinstance(data, dict):
                self.status.set_label('Could not reach Flathub, so only the built-in apps are searched.' if cur else
                                      'Could not reach Flathub. Check your internet connection.')
                return False
            seen = {e[0] for e in cur}
            extra = [e for e in map(hit_entry, data.get('hits', [])) if e and e[0] not in seen]
            self.show(title, cur + extra, '' if cur or extra else 'No apps found.')
            return False
        bg(lambda: http_json('/search', {'query': q}), done)

    # ---- detail -----------------------------------------------------------------------------------------------------
    def show_detail(self, entry):
        ref, name, desc, icon_url = entry
        back_page = self.page
        self.gen += 1
        gen = self.gen
        self.live = []
        d = self.detail
        while (c := d.get_first_child()):
            d.remove(c)
        back = Gtk.Button(label='‹ Back', halign=Gtk.Align.START)
        back.connect('clicked', lambda *_: self.go(back_page, from_side=back_page[0] != 'search'))
        d.append(back)
        head = Gtk.Box(spacing=14)
        ic = Gtk.Image(pixel_size=96, icon_name='application-x-executable')
        head.append(ic)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER, hexpand=True)
        n = Gtk.Label(label=name, xalign=0)
        n.add_css_class('st-big')
        col.append(n)
        sub = Gtk.Label(label=desc, xalign=0, wrap=True)
        sub.add_css_class('st-desc')
        col.append(sub)
        meta = Gtk.Label(label='Loading details…', xalign=0, wrap=True)
        meta.add_css_class('st-desc')
        col.append(meta)
        head.append(col)
        acts = Actions(self, ref, name)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER, width_request=180)
        side.append(acts.state)
        side.append(acts.progress)
        side.append(acts.row)
        head.append(side)
        d.append(head)
        text = Gtk.Label(label='', xalign=0, yalign=0, wrap=True, selectable=True)
        text.add_css_class('st-body')
        tsc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        tsc.set_child(text)
        d.append(tsc)
        self.stack.set_visible_child_name('detail')
        self.load_icon(ref, icon_url, ic)

        def fetch():
            return http_json('/appstream/' + ref), http_json('/summary/' + ref)

        def got(res):
            if gen != self.gen:
                return False
            info, summ = res
            bits = []
            if isinstance(info, dict):
                if info.get('developer_name'):
                    bits.append('By ' + info['developer_name'])
                if info.get('summary'):
                    sub.set_label(info['summary'])
                text.set_label(plain(info.get('description')) or desc)
            else:
                text.set_label(desc + '\n\nMore details need an internet connection.')
            br = (summ or {}).get('branches', {}).get('stable') if isinstance(summ, dict) else None
            if br and br.get('download_size'):
                bits.append(f'Download {human(br["download_size"])}')
                if br.get('installed_size'):
                    bits.append(f'Installed size {human(br["installed_size"])}')
            else:
                bits.append('Size not available')
            meta.set_label(' · '.join(bits))
            return False
        bg(fetch, got)

    # ---- icons ------------------------------------------------------------------------------------------------------
    def load_icon(self, ref, url, image):
        def got(path):
            if path:
                image.set_from_file(path)
            return False
        bg(lambda: icon_file(ref, url), got)

    # ---- installed / updates ----------------------------------------------------------------------------------------
    def refresh(self):
        bg(lambda: flatpak_lines('list', '--system', '--app', '--columns=application,name'), self.apply)

    def apply(self, lines):
        if lines is None:
            self.error('Flatpak is not available on this PC, so apps cannot be added here yet.')
        elif self.job is None:
            rows = [l.split('\t') for l in lines if l.strip()]
            self.installed = {r[0] for r in rows}
            self.installed_names = {r[0]: (r[1] if len(r) > 1 else r[0]) for r in rows}
            for a in self.live:
                a.sync()
            if self.page[0] == 'installed':
                self.go(self.page, from_side=True)
        if lines is not None:
            self.check_updates()
        return False

    def check_updates(self, show=False):
        if show:
            self.up_status.set_label('Checking for updates…')
            self.up_check.set_sensitive(False)

        def done(lines):
            self.up_check.set_sensitive(not self.job)
            if lines is None:
                self.up_status.set_label('Could not check for updates. Are you connected to the internet?')
                return False
            self.updates = [tuple((l.split('\t') + [''])[:2]) for l in lines if l.strip()]
            self.update_badge()
            if self.page[0] == 'updates':
                self.fill_updates()
            return False
        bg(lambda: flatpak_lines('remote-ls', '--updates', '--system', '--app', '--columns=application,name'), done)

    def update_badge(self):
        n = len(self.updates or [])
        self.side_rows['updates'].lab.set_label(f'Updates ({n})' if n else 'Updates')

    def fill_updates(self):
        while (c := self.up_list.get_first_child()):
            self.up_list.remove(c)
        ups = self.updates
        if ups is None:
            self.up_status.set_label('Checking for updates…')
        else:
            self.up_status.set_label(f'{len(ups)} app{"s" if len(ups) != 1 else ""} can be updated.' if ups else
                                     'Everything is up to date.')
            for ref, name in ups:
                self.up_list.append(Gtk.Label(label=name or ref, xalign=0, margin_top=5, margin_bottom=5, margin_start=8))
        self.up_all.set_sensitive(bool(ups) and not self.job)

    # ---- running things ---------------------------------------------------------------------------------------------
    def error(self, text):
        self.note.set_label(text)
        self.errbox.set_visible(True)

    def pulse(self):
        # Until a percentage shows up (Flatpak prints none while it looks things up) the bars just move.
        if not self.job:
            self.pulse_id = 0
            return False
        if self.job['fraction'] == 0:
            for a in self.live:
                if a.ref == self.job['ref']:
                    a.progress.pulse()
            if self.job['ref'] == '*updates':
                self.up_progress.pulse()
        return True

    def set_job(self, **kw):
        if self.job:
            self.job.update(kw)
            for a in self.live:
                a.sync()
            if self.job['ref'] == '*updates':
                self.up_progress.set_fraction(self.job['fraction'])
                self.up_status.set_label(self.job['text'])
        return False

    def run(self, ref, name, action):
        if self.job or (action != 'update' and not APP_ID.match(ref)):
            return
        self.errbox.set_visible(False)
        verb = {'install': 'Installing', 'remove': 'Removing', 'update': 'Updating'}[action]
        self.job = {'ref': ref, 'text': verb + '…', 'fraction': 0}
        for a in self.live:
            a.sync()
        if action == 'update':
            self.up_progress.set_visible(True)
            self.up_progress.set_fraction(0)
            self.up_all.set_sensitive(False)
            self.up_check.set_sensitive(False)
            self.up_status.set_label('Updating…')
        self.pulse_id = GLib.timeout_add(120, self.pulse)
        cmd = ['pkexec', ADMIN, 'flatpak', action] + ([] if action == 'update' else [ref])

        def work():
            code, last, err = 1, '', ''
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:  # text mode turns Flatpak's carriage returns into line ends
                    line = line.strip()
                    if not line:
                        continue
                    last = line
                    if line.lower().startswith(('error', 'fatal')) or 'failed' in line.lower():
                        err = line
                    m = PCT.search(line)
                    if m:
                        GLib.idle_add(self.set_job, fraction=min(int(m.group(1)), 100) / 100)
                    elif line.lower().startswith(('installing', 'uninstalling', 'updating')):
                        s = STEP.search(line)
                        GLib.idle_add(self.set_job, text=f'{verb} {s.group(0)}…' if s else line[:40])
                code = proc.wait()
            except OSError:
                last = 'pkexec is missing'
            GLib.idle_add(self.done, ref, name, action, code, err or last)
        threading.Thread(target=work, daemon=True).start()

    def done(self, ref, name, action, code, last):
        self.job = None
        self.up_progress.set_visible(False)
        self.up_check.set_sensitive(True)
        # 126/127: the password prompt was cancelled or not allowed; say nothing alarming then.
        if code not in (0, 126, 127):
            what = {'install': f'{name} could not be installed', 'remove': f'{name} could not be removed',
                    'update': 'The updates could not be installed'}[action]
            hint = ' Check your internet connection and free disk space.' if re.search(r'network|resolve|connect|timed|space', last, re.I) else ''
            self.error(f'{what}: {last[:220]}{hint}')
        if code == 0 and action == 'install':
            self.installed.add(ref)
            self.installed_names.setdefault(ref, name)
        elif code == 0 and action == 'remove':
            self.installed.discard(ref)
        elif code == 0:
            self.updates = []
            self.update_badge()
        for a in self.live:
            a.sync()
        if self.page[0] == 'updates':
            self.fill_updates()
        self.refresh()
        return False

    def launch(self, ref, name):
        """Flatpak starts the app itself, detached so closing Get Apps doesn't close it. A first start can take a while
        in a VM (Flatpak sets the app up), so the button says so; if the app quits, the reason is shown."""
        log = os.path.join(GLib.get_user_cache_dir(), 'mwx7', 'get-apps-' + ref + '.log')
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, 'w') as out:
            p = subprocess.Popen(['flatpak', 'run', ref], start_new_session=True, stdout=out, stderr=out)
        self.starting[ref] = True
        for a in self.live:
            a.sync()
        ticks = [0]

        def check():
            ticks[0] += 1
            code = p.poll()
            if code not in (None, 0):
                try:
                    last = [l for l in open(log).read().splitlines() if l.strip()][-1]
                except (OSError, IndexError):
                    last = f'it stopped with code {code}'
                self.error(f'{name} did not start: {last[:200]}')
            elif code is None and ticks[0] < 8:
                return True
            self.starting.pop(ref, None)
            for a in self.live:
                a.sync()
            return False
        GLib.timeout_add_seconds(1, check)


if __name__ == '__main__':
    mwx7ui.App('org.mwx7.store', 'Get Apps', 'store', (860, 580), CSS, Store().build).run_main()
