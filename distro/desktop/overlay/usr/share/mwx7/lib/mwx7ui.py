"""What MWX 7's own GTK 4 apps share: the Aero title bar in the chosen window colour, the Settings look, the fonts.

    app = mwx7ui.App('org.mwx7.calculator', 'Calculator', 'calculator', (260, 330), CSS, build)

build(app, win) returns the window's content. GTK 4 draws these apps' title bars itself (it doesn't let Wayfire frame
them), so the bar here matches the Wayfire frames: glass in the window colour, icon and title left, lights right.
"""
import os
import sys

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

sys.path.insert(0, '/usr/share/mwx7/settings')
import settings as base  # noqa: E402

ICONS = base.ICONS


def remember(path):
    """Adds a file or folder to the recent list under this app's name: the dock's right-click menu lists them (jump
    lists, as in Windows 7)."""
    try:
        Gtk.RecentManager.get_default().add_item(Gio.File.new_for_path(path).get_uri())
    except (GLib.Error, TypeError):
        pass


def dialog(parent, title, icon_name='about'):
    """A small window of an MWX 7 app (Properties, Find, Rename...): the same Aero title bar as its app, not GTK's."""
    # Not transient: MWX 7's frames treat windows with a parent as GTK's own dialogs and leave them unframed.
    w = Gtk.Window(title=title, resizable=False)
    if parent is not None:
        parent.connect('close-request', lambda *_a: w.destroy() and False)
    w.add_css_class('mwx7-settings')
    w.set_titlebar(base.Settings.titlebar(w, title, icon_name))
    return w


def css(text, priority=1):
    p = Gtk.CssProvider()
    p.load_from_data(text.encode())
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_USER + priority)
    return p


def icon(name, size=16):
    img = Gtk.Image.new_from_file(os.path.join(ICONS, name + '.png'))
    img.set_pixel_size(size)
    return img


def tint_css():
    rgb, intensity = base.glass_now()
    a = base.glass_alpha(intensity)
    return (base.titlebar_css('headerbar.mwx7-titlebar', rgb, a) +
            base.titlebar_css('window.mwx7-settings:backdrop headerbar.mwx7-titlebar', rgb, a, False) +
            'window.mwx7-settings { background: transparent; }\n'
            'window.mwx7-settings > box { background: #ffffff; }\n')


# A menu strip under the title bar, as XP/7 apps have it (the concept shows app menus in the top bar; a real app's menus
# can't move there, so they sit where Windows had them).
MENU_CSS = """
window.mwx7-settings popovermenubar { padding: 0 2px; background: linear-gradient(to bottom, #fbfdff, #edf2f9);
  border-bottom: 1px solid #d5dfec; }
window.mwx7-settings popovermenubar > item { padding: 3px 8px; border-radius: 3px; color: #1c3150; }
window.mwx7-settings popovermenubar > item:hover, window.mwx7-settings popovermenubar > item:selected {
  background: linear-gradient(to bottom, #f4f9ff, #dbeafc); box-shadow: inset 0 0 0 1px #a8c6ec; }
"""


# ---- Open / Save As ---------------------------------------------------------------------------------------------------
FILE_CSS = """
window.mwx7-filedlg > box { background: #ffffff; }
.fd-nav { padding: 6px 8px; background: linear-gradient(180deg, #e9f2fc, #d5e5f7); border-bottom: 1px solid #a9c1de; }
.fd-nav entry { min-height: 26px; border-radius: 3px; border: 1px solid #8ea8c9; background: #ffffff; }
.fd-side { background: linear-gradient(90deg, #f3f8fd, #e6eff9); border-right: 1px solid #cfdcec; padding: 6px 0; }
.fd-side row, .fd-list row { padding: 3px 8px; border-radius: 3px; margin: 0 4px; }
.fd-side row:selected, .fd-list row:selected { background: linear-gradient(180deg, #e5f1fd, #c9e0fa);
  box-shadow: inset 0 0 0 1px #84acdd; color: #10223b; }
.fd-side row:hover, .fd-list row:hover { background-color: #eaf3fd; }
.fd-list { background: #ffffff; }
.fd-head { padding: 4px 12px; color: #4b5d78; font-size: 0.9em; border-bottom: 1px solid #e3e9f1; }
.fd-dim { color: #6b7b92; }
.fd-foot { padding: 10px 12px; background: linear-gradient(180deg, #f4f7fb, #e5ecf5); border-top: 1px solid #c9d6e6; }
"""
FILE_KINDS = (('image/', 'image'), ('audio/', 'audio'), ('video/', 'video'), ('text/', 'text'))
PLACES = [(GLib.UserDirectory.DIRECTORY_DESKTOP, 'Desktop', 'desktop'),
          (GLib.UserDirectory.DIRECTORY_DOCUMENTS, 'Documents', 'folder-documents'),
          (GLib.UserDirectory.DIRECTORY_DOWNLOAD, 'Downloads', 'folder'),
          (GLib.UserDirectory.DIRECTORY_MUSIC, 'Music', 'folder-music'),
          (GLib.UserDirectory.DIRECTORY_PICTURES, 'Pictures', 'folder-pictures'),
          (GLib.UserDirectory.DIRECTORY_VIDEOS, 'Videos', 'folder')]
_file_css = None


class FileDialog:
    """Open / Save As in the MWX 7 look (an Explorer in miniature), with Gtk.FileDialog's calls so apps swap one for
    the other: FileDialog(title=, initial_folder=, initial_name=, filters=).open(parent, None, cb) -> cb(dlg, res),
    then dlg.open_finish(res) / save_finish(res) give a Gio.File or raise GLib.Error when cancelled."""

    def __init__(self, title='Open', initial_folder=None, initial_name='', filters=None):
        self.title, self.name = title, initial_name or ''
        self.folder = initial_folder.get_path() if initial_folder else None
        if not self.folder and self.name and os.path.isabs(self.name):
            self.folder, self.name = os.path.split(self.name)
        self.folder = self.folder or GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or \
            os.path.expanduser('~')
        self.filters = [filters.get_item(i) for i in range(filters.get_n_items())] if filters else []
        self.result = None

    def open(self, parent, _cancellable, callback):
        self.run(parent, callback, saving=False)

    def save(self, parent, _cancellable, callback):
        self.run(parent, callback, saving=True)

    def open_finish(self, _res):
        if self.result is None:
            raise GLib.Error('Dismissed by user')
        return self.result

    save_finish = open_finish

    # ---- the window --------------------------------------------------------------------------------------------------
    def run(self, parent, callback, saving):
        global _file_css
        if _file_css is None:
            _file_css = css(FILE_CSS, 3)
        self.saving, self.callback, self.done = saving, callback, False
        w = self.win = dialog(parent, self.title, 'explorer')
        w.set_resizable(True)
        w.set_default_size(720, 470)
        w.add_css_class('mwx7-filedlg')
        w.connect('close-request', lambda *_a: self.finish(None, close=False) or False)
        if parent is not None:
            # Keep it over its app: GTK can't make it transient (MWX 7 frames only windows without a parent).
            w.set_modal(True)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        nav = Gtk.Box(spacing=6, css_classes=['fd-nav'])
        up = Gtk.Button(icon_name='go-up-symbolic', tooltip_text='Up one level')
        up.connect('clicked', lambda *_a: self.go(os.path.dirname(self.folder) or '/'))
        self.addr = Gtk.Entry(hexpand=True)
        self.addr.connect('activate', lambda e: self.go(os.path.expanduser(e.get_text())))
        nav.append(up)
        nav.append(self.addr)
        root.append(nav)

        mid = Gtk.Paned(vexpand=True, position=170, shrink_start_child=False)
        side = Gtk.ListBox(css_classes=['fd-side'])
        self.places = []
        home = os.path.expanduser('~')
        for d, label, ic in PLACES:
            path = GLib.get_user_special_dir(d)
            if path and os.path.isdir(path) and path != home and path not in [p for p, _l in self.places]:
                self.places.append((path, label))
                side.append(self.place_row(ic, label))
        self.places += [(home, GLib.get_user_name()), ('/', 'Computer')]
        side.append(self.place_row('user', GLib.get_user_name()))
        side.append(self.place_row('computer', 'Computer'))
        side.connect('row-activated', lambda _b, r: self.go(self.places[r.get_index()][0]))
        side.set_activate_on_single_click(True)
        mid.set_start_child(Gtk.ScrolledWindow(child=side, hscrollbar_policy=Gtk.PolicyType.NEVER))

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        head = Gtk.Box(css_classes=['fd-head'])
        head.append(Gtk.Label(label='Name', xalign=0, hexpand=True))
        head.append(Gtk.Label(label='Date modified', xalign=0, width_chars=18))
        head.append(Gtk.Label(label='Size', xalign=1, width_chars=9))
        right.append(head)
        self.list = Gtk.ListBox(css_classes=['fd-list'])
        self.list.connect('row-activated', lambda _b, r: self.activate(r.path, r.is_dir))
        self.list.connect('row-selected', self.selected)
        right.append(Gtk.ScrolledWindow(child=self.list, vexpand=True))
        mid.set_end_child(right)
        root.append(mid)

        foot = Gtk.Grid(column_spacing=8, row_spacing=8, css_classes=['fd-foot'])
        foot.attach(Gtk.Label(label='File name:', xalign=1), 0, 0, 1, 1)
        self.entry = Gtk.Entry(hexpand=True, text=self.name)
        self.entry.connect('activate', lambda *_a: self.accept())
        foot.attach(self.entry, 1, 0, 1, 1)
        self.kind = None
        if self.filters:
            self.kind = Gtk.DropDown.new_from_strings([f.get_name() or 'Files' for f in self.filters])
            self.kind.connect('notify::selected', lambda *_a: self.fill())
            foot.attach(self.kind, 2, 0, 1, 1)
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        ok = Gtk.Button(label='Save' if saving else 'Open', css_classes=['suggested-action'], width_request=88)
        ok.connect('clicked', lambda *_a: self.accept())
        cancel = Gtk.Button(label='Cancel', width_request=88)
        cancel.connect('clicked', lambda *_a: self.finish(None))
        btns.append(ok)
        btns.append(cancel)
        foot.attach(btns, 1, 1, 2, 1)
        root.append(foot)
        w.set_child(root)
        self.go(self.folder)
        w.present()
        self.entry.grab_focus()
        if saving and '.' in self.name:
            self.entry.select_region(0, self.name.rindex('.'))

    @staticmethod
    def place_row(ic, label):
        box = Gtk.Box(spacing=8)
        box.append(icon(ic, 16))
        box.append(Gtk.Label(label=label, xalign=0))
        return box

    def go(self, path):
        if not os.path.isdir(path):
            return
        self.folder = os.path.abspath(path)
        self.addr.set_text(self.folder)
        self.fill()

    def wanted(self, info):
        if not self.filters or info.get_file_type() == Gio.FileType.DIRECTORY:
            return True
        return self.filters[self.kind.get_selected()].match(info)

    def fill(self):
        while (r := self.list.get_first_child()) is not None:
            self.list.remove(r)
        try:
            en = Gio.File.new_for_path(self.folder).enumerate_children(
                'standard::name,standard::display-name,standard::type,standard::size,standard::content-type,standard::is-hidden,'
                'time::modified', Gio.FileQueryInfoFlags.NONE, None)
            infos = [i for i in en if not i.get_is_hidden() and not i.get_name().startswith('.')]
        except GLib.Error:
            infos = []
        infos.sort(key=lambda i: (i.get_file_type() != Gio.FileType.DIRECTORY, i.get_name().lower()))
        for info in infos:
            if not self.wanted(info):
                continue
            is_dir = info.get_file_type() == Gio.FileType.DIRECTORY
            mime = Gio.content_type_get_mime_type(info.get_content_type() or '') or ''
            ic = 'folder' if is_dir else next((k for p, k in FILE_KINDS if mime.startswith(p)), 'file')
            row = Gtk.ListBoxRow()
            row.path, row.is_dir = os.path.join(self.folder, info.get_name()), is_dir
            box = Gtk.Box(spacing=8)
            box.append(icon(ic, 16))
            box.append(Gtk.Label(label=info.get_name(), xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE))
            dt = info.get_modification_date_time()
            box.append(Gtk.Label(label=dt.to_local().format('%d/%m/%Y %H:%M') if dt else '', xalign=0,
                                 width_chars=18, css_classes=['fd-dim']))
            size = '' if is_dir else self.human(info.get_size())
            box.append(Gtk.Label(label=size, xalign=1, width_chars=9, css_classes=['fd-dim']))
            row.set_child(box)
            self.list.append(row)

    @staticmethod
    def human(n):
        for unit in ('bytes', 'KB', 'MB', 'GB'):
            if n < 1024 or unit == 'GB':
                return f'{n:.0f} {unit}' if unit == 'bytes' else f'{n:.1f} {unit}'
            n /= 1024
        return ''

    def selected(self, _box, row):
        if row is not None and not row.is_dir:
            self.entry.set_text(os.path.basename(row.path))

    def activate(self, path, is_dir):
        if is_dir:
            self.go(path)
        else:
            self.entry.set_text(os.path.basename(path))
            self.accept()

    def accept(self):
        name = self.entry.get_text().strip()
        if not name:
            return
        path = os.path.join(self.folder, os.path.expanduser(name))
        if os.path.isdir(path):
            self.entry.set_text('')
            self.go(path)
            return
        if not self.saving:
            if os.path.isfile(path):
                self.finish(path)
            return
        if not os.path.isdir(os.path.dirname(path)):
            return
        if not os.path.exists(path):
            self.finish(path)
            return
        ask = Gtk.AlertDialog(message='Confirm Save As',
                              detail=f'{os.path.basename(path)} already exists.\nDo you want to replace it?',
                              buttons=['Yes', 'No'], default_button=1, cancel_button=1)
        ask.choose(self.win, None, lambda d, res: (d.choose_finish(res) == 0) and self.finish(path))

    def finish(self, path, close=True):
        if self.done:
            return
        self.done = True
        self.result = Gio.File.new_for_path(path) if path else None
        if close:
            self.win.destroy()
        self.callback(self, None)


class App(Gtk.Application):
    def __init__(self, app_id, title, icon_name, size, extra_css, build, resizable=True):
        super().__init__(application_id=app_id, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        # The window's app id (dock icon, bar name) even when there is no session bus to register the app on.
        GLib.set_prgname(app_id)
        self.title, self.icon_name, self.size, self.extra_css, self.build = title, icon_name, size, extra_css, build
        self.resizable = resizable
        self.files = []
        self.win = None

    def do_open(self, files, _n, _hint):
        self.files = files
        self.do_activate()

    def do_activate(self):
        if self.win:
            self.win.present()
            if self.files and hasattr(self, 'on_open'):
                self.on_open(self.files)
            return
        sheet = Gtk.CssProvider()
        sheet.load_from_path('/usr/share/mwx7/settings/settings.css')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), sheet, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        css(MENU_CSS + (self.extra_css or ''), 1)
        tint = css(tint_css(), 2)
        # Follow Settings -> Window Color while open, as the frames around other apps do.
        self.tint_mon = Gio.File.new_for_path(base.WF_INI).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.tint_mon.connect('changed', lambda *_a: GLib.timeout_add(
            200, lambda: tint.load_from_data(tint_css().encode()) and False))
        w = self.win = Gtk.ApplicationWindow(application=self, title=self.title, show_menubar=False)
        w.set_default_size(*self.size)
        w.set_resizable(self.resizable)
        w.add_css_class('mwx7-settings')
        w.add_css_class('mwx7-app')
        w.set_titlebar(base.Settings.titlebar(w, self.title, self.icon_name))
        w.set_child(self.build(self, w))
        w.present()

    def set_title(self, text):
        """The window's title (the dock and the bar show it) and the title bar's label."""
        self.win.set_title(text)
        bar = self.win.get_titlebar()
        child = bar.get_first_child() if bar else None
        stack = [child]
        while stack:
            c = stack.pop()
            if c is None:
                continue
            if isinstance(c, Gtk.Label) and c.has_css_class('mwx7-title'):
                c.set_label(text)
                return
            stack += [c.get_first_child(), c.get_next_sibling()]

    def menubar(self, menus):
        """menus: [(label, [(item label, action name, callback) | None for a separator, ...]), ...]

        The menus go to the top bar, as on the web (and a Mac): GtkApplication publishes them on the session bus and
        the shell shows the focused app's. The window itself shows none; this returns an empty placeholder."""
        model = Gio.Menu()
        for label, items in menus:
            sub, section = Gio.Menu(), Gio.Menu()
            for it in items:
                if it is None:
                    sub.append_section(None, section)
                    section = Gio.Menu()
                    continue
                text, name, fn = it
                if not self.lookup_action(name):
                    a = Gio.SimpleAction.new(name, None)
                    a.connect('activate', lambda *_a, f=fn: f())
                    self.add_action(a)
                section.append(text, 'app.' + name)
            sub.append_section(None, section)
            model.append_submenu(label, sub)
        self.set_menubar(model)
        if self.win:
            self.win.set_show_menubar(False)
        return Gtk.Box(visible=False)

    def run_main(self):
        return self.run(sys.argv)
