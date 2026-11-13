"""My Computer (native): the concept's Explorer, Windows 7 style. Back/forward, the path as clickable parts, search
in the folder; Favorites, My Computer and the Trash on the left; large icons or details; open, cut/copy/paste,
rename, new folder, move to Trash, restore, properties. My Computer itself shows the disk and the person's folders."""
import datetime
import os
import shutil
import sys
import urllib.parse

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk  # noqa: E402
import gi  # noqa: E402

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf  # noqa: E402

COMPUTER = 'computer:'
TRASH = os.path.join(GLib.get_user_data_dir(), 'Trash')
ICONS = mwx7ui.ICONS
SPECIAL = [(GLib.UserDirectory.DIRECTORY_DESKTOP, 'desktop'), (GLib.UserDirectory.DIRECTORY_DOCUMENTS, 'folder-documents'),
           (GLib.UserDirectory.DIRECTORY_DOWNLOAD, 'folder'), (GLib.UserDirectory.DIRECTORY_MUSIC, 'folder-music'),
           (GLib.UserDirectory.DIRECTORY_PICTURES, 'folder-pictures'), (GLib.UserDirectory.DIRECTORY_VIDEOS, 'folder')]
IMAGES = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
CSS = """
window.mwx7-explorer > box { background: #ffffff; }
.ex-nav { padding: 6px 8px; background: linear-gradient(180deg, #e9f2fc, #d5e5f7); border-bottom: 1px solid #a9c1de; }
.ex-nav button.ex-round { min-width: 28px; min-height: 28px; padding: 0; border-radius: 999px; border: 1px solid #2b5a94;
  background: radial-gradient(circle at 50% 30%, #bfe0ff, #3d86d8 60%, #1d559c); color: #ffffff;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.6); }
.ex-nav button.ex-round:disabled { background: radial-gradient(circle at 50% 30%, #eef3f9, #b7c4d4); border-color: #94a3b8;
  color: #f4f6f9; }
.ex-crumbs { padding: 0 4px; min-height: 26px; border: 1px solid #8ea7c6; border-radius: 2px; background: #ffffff; }
.ex-crumbs button { padding: 2px 6px; min-height: 0; border: 1px solid transparent; border-radius: 2px; background: none;
  box-shadow: none; color: #1c3150; }
.ex-crumbs button:hover { border-color: #a8c6ec; background: linear-gradient(180deg, #f4f9ff, #dbeafc); }
.ex-search { min-height: 26px; }
.ex-cmd { padding: 3px 8px; border-bottom: 1px solid #c8d8ea;
  background: linear-gradient(180deg, #fbfdff 0%, #eef4fb 50%, #e1ebf7 51%, #eaf1fa 100%); }
.ex-cmd button { padding: 3px 9px; min-height: 0; border: 1px solid transparent; border-radius: 3px; background: none;
  box-shadow: none; color: #1c3150; }
.ex-cmd button:hover { border-color: #a8c6ec; background: linear-gradient(180deg, #f4f9ff, #dbeafc); }
.ex-side { background: linear-gradient(180deg, #f3f8fe, #e8f1fb); border-right: 1px solid #c8d8ea; }
.ex-side row { padding: 3px 10px; color: #1c3150; border-radius: 3px; }
.ex-side row:selected { background: linear-gradient(180deg, #e2efff, #c9e0fb); box-shadow: inset 0 0 0 1px #84acdd; color: #0b2440; }
.ex-side .ex-head { padding: 8px 10px 2px; font-weight: 700; color: #1e3f66; }
flowbox.ex-items flowboxchild { padding: 4px; border-radius: 3px; border: 1px solid transparent; }
flowbox.ex-items flowboxchild:hover { background: linear-gradient(180deg, #f2f8ff, #e2efff); border-color: #b8d6fb; }
flowbox.ex-items flowboxchild:selected { background: linear-gradient(180deg, #dcebfc, #c1dcfc); border-color: #7da2ce; }
.ex-name { color: #1c2530; }
.ex-meta { color: #6a7f99; font-size: 11px; }
.ex-details { padding: 6px 12px; border-top: 1px solid #c8d8ea; background: linear-gradient(180deg, #f3f8fe, #dfeaf7); }
.ex-details-title { font-weight: 600; color: #1c3150; }
.ex-drive-bar trough { min-height: 10px; background: #e3e8ef; border: 1px solid #9aa9bd; border-radius: 1px; }
.ex-drive-bar progress { min-height: 10px; background: linear-gradient(180deg, #5fb0ff, #2a7fd9); border-radius: 1px; }
.ex-group { padding: 12px 14px 4px; font-weight: 600; color: #1e3f66; }
"""


def human(n):
    for unit in ('bytes', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.0f} {unit}' if unit == 'bytes' else f'{n:.1f} {unit}'
        n /= 1024
    return ''


def special_dirs():
    out = []
    for d, icon in SPECIAL:
        p = GLib.get_user_special_dir(d)
        if p and os.path.isdir(p) and p != os.path.expanduser('~') and p not in [x[0] for x in out]:
            out.append((p, icon))
    return out


class Explorer:
    def __init__(self):
        self.loc, self.back, self.fwd = COMPUTER, [], []
        self.clip, self.clip_cut = [], False
        self.view = 'icons'
        self.query = ''

    # ---- layout ---------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-explorer')
        app.on_open = lambda files: self.go(files[0].get_path())
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        nav = Gtk.Box(spacing=6)
        nav.add_css_class('ex-nav')
        self.back_btn = self.round('go-previous-symbolic', 'Back', lambda: self.history(-1))
        self.fwd_btn = self.round('go-next-symbolic', 'Forward', lambda: self.history(1))
        nav.append(self.back_btn)
        nav.append(self.fwd_btn)
        self.crumbs = Gtk.Box(hexpand=True)
        self.crumbs.add_css_class('ex-crumbs')
        nav.append(self.crumbs)
        self.search = Gtk.SearchEntry(placeholder_text='Search', width_chars=22)
        self.search.add_css_class('ex-search')
        self.search.connect('search-changed', lambda e: (setattr(self, 'query', e.get_text().lower()), self.fill()))
        nav.append(self.search)
        root.append(nav)
        cmd = Gtk.Box(spacing=2)
        cmd.add_css_class('ex-cmd')
        org = Gtk.MenuButton(label='Organize')
        menu = Gio.Menu()
        for label, name, fn in (('Cut', 'cut', lambda: self.copy(True)), ('Copy', 'copy', lambda: self.copy(False)),
                                ('Paste', 'paste', self.paste), ('Select all', 'selectall', lambda: self.flow.select_all()),
                                ('Rename', 'rename', self.rename), ('Delete', 'delete', self.delete),
                                ('Properties', 'props', self.properties)):
            a = Gio.SimpleAction.new(name, None)
            a.connect('activate', lambda *_a, f=fn: f())
            app.add_action(a)
            menu.append(label, 'app.' + name)
        org.set_menu_model(menu)
        cmd.append(org)
        self.newdir_btn = Gtk.Button(label='New folder')
        self.newdir_btn.connect('clicked', lambda *_: self.new_folder())
        cmd.append(self.newdir_btn)
        self.empty_btn = Gtk.Button(label='Empty the Trash')
        self.empty_btn.connect('clicked', lambda *_: self.empty_trash())
        cmd.append(self.empty_btn)
        self.restore_btn = Gtk.Button(label='Restore')
        self.restore_btn.connect('clicked', lambda *_: self.restore())
        cmd.append(self.restore_btn)
        spacer = Gtk.Box(hexpand=True)
        cmd.append(spacer)
        self.view_btn = Gtk.Button(label='Details')
        self.view_btn.connect('clicked', lambda *_: self.toggle_view())
        cmd.append(self.view_btn)
        root.append(cmd)

        body = Gtk.Paned(vexpand=True, shrink_start_child=False, position=190)
        side = Gtk.ScrolledWindow()
        side.add_css_class('ex-side')
        self.side = Gtk.ListBox()
        self.side.connect('row-activated', lambda _l, r: getattr(r, 'path', None) and self.go(r.path))
        side.set_child(self.side)
        body.set_start_child(side)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.MULTIPLE, activate_on_single_click=False,
                                homogeneous=True, valign=Gtk.Align.START, row_spacing=2, column_spacing=2,
                                max_children_per_line=40, margin_top=6, margin_start=6, margin_end=6)
        self.flow.add_css_class('ex-items')
        self.drop_on(self.flow, lambda: self.loc if self.loc not in (COMPUTER,) else COMPUTER)
        self.flow.connect('child-activated', lambda _f, c: self.open_item(c.item))
        self.flow.connect('selected-children-changed', lambda *_: self.details())
        click = Gtk.GestureClick(button=3)
        click.connect('pressed', self.context_menu)
        self.flow.add_controller(click)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content.append(self.flow)
        sc = Gtk.ScrolledWindow(hexpand=True)
        sc.set_child(self.content)
        body.set_end_child(sc)
        root.append(body)
        self.detail = Gtk.Box(spacing=12)
        self.detail.add_css_class('ex-details')
        self.detail_icon = Gtk.Image(pixel_size=48)
        dcol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.detail_title = Gtk.Label(xalign=0)
        self.detail_title.add_css_class('ex-details-title')
        self.detail_text = Gtk.Label(xalign=0)
        self.detail_text.add_css_class('ex-meta')
        dcol.append(self.detail_title)
        dcol.append(self.detail_text)
        self.detail.append(self.detail_icon)
        self.detail.append(dcol)
        root.append(self.detail)

        self.monitor = None
        start = app.files[0].get_path() if app.files else (sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else COMPUTER)
        self.fill_side()
        self.go(start, remember=False)
        return root

    def round(self, icon, tip, fn):
        b = Gtk.Button(icon_name=icon, tooltip_text=tip, focusable=False, valign=Gtk.Align.CENTER)
        b.add_css_class('ex-round')
        b.connect('clicked', lambda *_: fn())
        return b

    def side_row(self, label, icon, path):
        row = Gtk.ListBoxRow()
        row.path = path
        self.drop_on(row, lambda: path)
        box = Gtk.Box(spacing=8)
        box.append(mwx7ui.icon(icon, 16))
        box.append(Gtk.Label(label=label, xalign=0))
        row.set_child(box)
        return row

    def side_head(self, label):
        row = Gtk.ListBoxRow(selectable=False, activatable=False)
        l = Gtk.Label(label=label, xalign=0)
        l.add_css_class('ex-head')
        row.set_child(l)
        return row

    def fill_side(self):
        self.side.append(self.side_head('Favorites'))
        for p, icon in special_dirs():
            self.side.append(self.side_row(os.path.basename(p), icon, p))
        self.side.append(self.side_head('My Computer'))
        self.side.append(self.side_row('Local Disk', 'drive', '/'))
        self.side.append(self.side_row(GLib.get_real_name() or GLib.get_user_name(), 'user', os.path.expanduser('~')))
        self.side.append(self.side_head(''))
        self.side.append(self.side_row('Trash', 'trash-empty', TRASH))

    # ---- navigation -----------------------------------------------------------------------------------------------
    def go(self, path, remember=True):
        if path.rstrip('/') == TRASH:
            path = TRASH
            for sub in ('files', 'info'):
                os.makedirs(os.path.join(TRASH, sub), exist_ok=True)
        if path != COMPUTER and not os.path.isdir(path):
            return
        if remember and path != self.loc:
            self.back.append(self.loc)
            self.fwd.clear()
        self.loc = path
        if path not in (COMPUTER, TRASH):
            mwx7ui.remember(path)
        self.search.set_text('')
        self.query = ''
        self.watch()
        self.fill()

    def history(self, d):
        src, dst = (self.back, self.fwd) if d < 0 else (self.fwd, self.back)
        if src:
            dst.append(self.loc)
            self.loc = src.pop()
            self.watch()
            self.fill()

    def watch(self):
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        folder = os.path.join(TRASH, 'files') if self.loc == TRASH else self.loc
        if folder != COMPUTER and os.path.isdir(folder):
            self.monitor = Gio.File.new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.monitor.connect('changed', lambda *_: self.later_fill())

    def later_fill(self):
        if not getattr(self, 'fill_pending', False):
            self.fill_pending = True
            GLib.timeout_add(250, lambda: (setattr(self, 'fill_pending', False), self.fill(), False)[2])

    def title_of(self, path):
        if path == COMPUTER:
            return 'My Computer'
        if path == TRASH:
            return 'Trash'
        if path == '/':
            return 'Local Disk'
        if path == os.path.expanduser('~'):
            return GLib.get_real_name() or GLib.get_user_name()
        return os.path.basename(path.rstrip('/')) or path

    def fill_crumbs(self):
        while (c := self.crumbs.get_first_child()) is not None:
            self.crumbs.remove(c)
        parts = [COMPUTER]
        if self.loc == TRASH:
            parts = [TRASH]
        elif self.loc != COMPUTER:
            home = os.path.expanduser('~')
            base = home if self.loc.startswith(home) else '/'
            parts.append(base)
            rest = os.path.relpath(self.loc, base)
            if rest != '.':
                acc = base
                for part in rest.split(os.sep):
                    acc = os.path.join(acc, part)
                    parts.append(acc)
        for i, p in enumerate(parts):
            if i:
                self.crumbs.append(Gtk.Label(label='›'))
            b = Gtk.Button(label=self.title_of(p), focusable=False)
            b.connect('clicked', lambda _b, p=p: self.go(p))
            self.crumbs.append(b)

    # ---- items ----------------------------------------------------------------------------------------------------
    def items(self):
        """[(path, name, is_dir, icon_widget_factory, meta)] for the current place."""
        if self.loc == COMPUTER:
            return []
        folder = os.path.join(TRASH, 'files') if self.loc == TRASH else self.loc
        try:
            names = os.listdir(folder)
        except OSError:
            return []
        out = []
        for n in names:
            if n.startswith('.') and self.loc != TRASH:
                continue
            if self.query and self.query not in n.lower():
                continue
            p = os.path.join(folder, n)
            out.append((p, n, os.path.isdir(p)))
        out.sort(key=lambda t: (not t[2], t[1].lower()))
        return out

    def icon_for(self, path, is_dir, size):
        if is_dir:
            for p, icon in special_dirs():
                if p == path:
                    return mwx7ui.icon(icon, size)
            return mwx7ui.icon('folder', size)
        if path.lower().endswith(IMAGES) and size >= 48:
            img = Gtk.Image(pixel_size=size)
            img.set_from_icon_name('image-x-generic')

            def load():
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
                    img.set_from_paintable(Gdk.Texture.new_for_pixbuf(pb))
                except GLib.Error:
                    pass
                return False
            GLib.idle_add(load)
            return img
        ctype, _u = Gio.content_type_guess(path, None)
        img = Gtk.Image.new_from_gicon(Gio.content_type_get_icon(ctype))
        img.set_pixel_size(size)
        return img

    def fill(self):
        self.fill_crumbs()
        self.app.set_title(self.title_of(self.loc))
        self.back_btn.set_sensitive(bool(self.back))
        self.fwd_btn.set_sensitive(bool(self.fwd))
        in_trash, real = self.loc == TRASH, self.loc not in (COMPUTER, TRASH)
        self.newdir_btn.set_visible(real)
        self.empty_btn.set_visible(in_trash)
        self.restore_btn.set_visible(in_trash)
        self.view_btn.set_visible(self.loc != COMPUTER)
        while (c := self.flow.get_first_child()) is not None:
            self.flow.remove(c)
        child = self.content.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            if child is not self.flow:
                self.content.remove(child)
            child = nxt
        i, mine = 0, None
        while (r := self.side.get_row_at_index(i)) is not None:
            if getattr(r, 'path', None) == self.loc:
                mine = r
                break
            i += 1
        if mine:
            self.side.select_row(mine)
        else:
            self.side.unselect_all()
        if self.loc == COMPUTER:
            self.fill_computer()
        else:
            details = self.view == 'details'
            self.flow.set_max_children_per_line(1 if details else 40)
            self.flow.set_homogeneous(not details)
            for path, name, is_dir in self.items():
                self.flow.append(self.cell(path, name, is_dir, details))
        self.details()

    def cell(self, path, name, is_dir, details):
        c = Gtk.FlowBoxChild()
        c.item = path
        self.dnd(c, path, is_dir)
        if details:
            row = Gtk.Box(spacing=8)
            row.append(self.icon_for(path, is_dir, 16))
            n = Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3)
            n.add_css_class('ex-name')
            row.append(n)
            try:
                st = os.stat(path)
                when = datetime.datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M')
                size = '' if is_dir else human(st.st_size)
            except OSError:
                when = size = ''
            for text, w in ((when, 16), ('File folder' if is_dir else Gio.content_type_get_description(
                    Gio.content_type_guess(path, None)[0]), 18), (size, 9)):
                l = Gtk.Label(label=text, xalign=0, width_chars=w, max_width_chars=w, ellipsize=3)
                l.add_css_class('ex-meta')
                row.append(l)
            c.set_child(row)
        else:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            box.set_size_request(96, -1)
            box.append(self.icon_for(path, is_dir, 48))
            l = Gtk.Label(label=name, wrap=True, wrap_mode=2, max_width_chars=12, lines=2, ellipsize=3,
                          justify=Gtk.Justification.CENTER)
            l.add_css_class('ex-name')
            box.append(l)
            c.set_child(box)
        return c

    def fill_computer(self):
        """My Computer: the disk with how full it is, then the person's folders."""
        def group(text):
            g = Gtk.Label(label=text, xalign=0)
            g.add_css_class('ex-group')
            return g
        self.content.prepend(group('Hard Disk Drives'))
        disk = Gtk.FlowBoxChild()
        disk.item = '/'
        row = Gtk.Box(spacing=10)
        row.append(mwx7ui.icon('drive', 48))
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, valign=Gtk.Align.CENTER)
        col.append(Gtk.Label(label='Local Disk', xalign=0, css_classes=['ex-name']))
        d = shutil.disk_usage('/')
        bar = Gtk.ProgressBar(fraction=(d.total - d.free) / d.total if d.total else 0)
        bar.add_css_class('ex-drive-bar')
        bar.set_size_request(180, -1)
        col.append(bar)
        col.append(Gtk.Label(label=f'{human(d.free)} free of {human(d.total)}', xalign=0, css_classes=['ex-meta']))
        row.append(col)
        disk.set_child(row)
        self.flow.set_max_children_per_line(40)
        self.flow.set_homogeneous(False)
        self.flow.append(disk)
        folders = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=False,
                              max_children_per_line=40, margin_start=6, margin_end=6)
        folders.add_css_class('ex-items')
        folders.connect('child-activated', lambda _f, c: self.go(c.item))
        for p, _icon in special_dirs():
            folders.append(self.cell(p, os.path.basename(p), True, False))
        self.content.append(group('Your Folders'))
        self.content.append(folders)

    # ---- drag and drop: drag items onto a folder (or a place on the left) to move them there, as in Explorer ----
    def dnd(self, widget, path, is_dir):
        if self.loc == TRASH:
            return
        src = Gtk.DragSource(actions=Gdk.DragAction.MOVE | Gdk.DragAction.COPY)

        def prepare(_s, _x, _y):
            paths = self.selected() if path in self.selected() else [path]
            files = [Gio.File.new_for_path(p) for p in paths]
            return Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list(files))
        src.connect('prepare', prepare)
        widget.add_controller(src)
        if is_dir:
            self.drop_on(widget, lambda: path)

    def drop_on(self, widget, where):
        tgt = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.MOVE | Gdk.DragAction.COPY)

        def drop(_t, value, _x, _y):
            dest = where()
            if dest == COMPUTER:
                return False
            files = [f.get_path() for f in value.get_files() if f.get_path()]
            self.move_into(files, dest)
            return True
        tgt.connect('drop', drop)
        widget.add_controller(tgt)

    def move_into(self, files, dest):
        to_trash = dest == TRASH
        for src in files:
            if not os.path.exists(src) or os.path.dirname(src.rstrip('/')) == dest.rstrip('/') or \
                    dest.startswith(src.rstrip('/') + '/') or src == dest:
                continue
            try:
                if to_trash:
                    Gio.File.new_for_path(src).trash(None)
                else:
                    shutil.move(src, self.unique(dest, os.path.basename(src)))
            except (OSError, GLib.Error) as e:
                self.alert('This could not be moved.', str(e))
                break
        self.fill()

    # ---- actions --------------------------------------------------------------------------------------------------
    def selected(self):
        return [c.item for c in self.flow.get_selected_children()]

    def open_item(self, path):
        if self.loc == TRASH:
            return
        if os.path.isdir(path):
            self.go(path)
            return
        try:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None)
        except GLib.Error as e:
            Gtk.AlertDialog(message=f'MWX 7 has no app to open {os.path.basename(path)}.', detail=e.message).show(self.win)

    def details(self):
        sel = self.selected()
        if len(sel) == 1:
            p = sel[0]
            is_dir = os.path.isdir(p)
            self.detail_icon.set_from_paintable(None)
            img = self.icon_for(p, is_dir, 48)
            if img.get_paintable():
                self.detail_icon.set_from_paintable(img.get_paintable())
            elif img.get_gicon():
                self.detail_icon.set_from_gicon(img.get_gicon())
            self.detail_title.set_label(os.path.basename(p) or p)
            try:
                st = os.stat(p)
                when = datetime.datetime.fromtimestamp(st.st_mtime).strftime('%d %B %Y, %H:%M')
                self.detail_text.set_label(('File folder' if is_dir else human(st.st_size)) + f'  ·  Modified {when}')
            except OSError:
                self.detail_text.set_label('')
        else:
            n = len(sel) if sel else len(self.items()) if self.loc != COMPUTER else 0
            here = 'computer' if self.loc == COMPUTER else 'trash-empty' if self.loc == TRASH else 'folder'
            self.detail_icon.set_from_file(os.path.join(ICONS, here + '.png'))
            self.detail_title.set_label(f'{n} items selected' if sel else self.title_of(self.loc))
            self.detail_text.set_label('' if sel else (f'{n} items' if self.loc != COMPUTER else ''))

    def toggle_view(self):
        self.view = 'icons' if self.view == 'details' else 'details'
        self.view_btn.set_label('Large icons' if self.view == 'details' else 'Details')
        self.fill()

    def copy(self, cut):
        self.clip, self.clip_cut = self.selected(), cut

    def unique(self, folder, name):
        base, ext = os.path.splitext(name)
        cand, i = name, 2
        while os.path.exists(os.path.join(folder, cand)):
            cand = f'{base} ({i}){ext}'
            i += 1
        return os.path.join(folder, cand)

    def paste(self):
        if self.loc in (COMPUTER, TRASH) or not self.clip:
            return
        for src in self.clip:
            if not os.path.exists(src):
                continue
            dst = self.unique(self.loc, os.path.basename(src))
            try:
                if self.clip_cut:
                    shutil.move(src, dst)
                elif os.path.isdir(src):
                    shutil.copytree(src, dst, symlinks=True)
                else:
                    shutil.copy2(src, dst)
            except OSError as e:
                self.alert('This could not be pasted.', str(e))
                break
        if self.clip_cut:
            self.clip = []
        self.fill()

    def new_folder(self):
        if self.loc in (COMPUTER, TRASH):
            return
        try:
            os.mkdir(self.unique(self.loc, 'New folder'))
        except OSError as e:
            self.alert('The folder could not be made.', str(e))
        self.fill()

    def ask(self, title, initial, done):
        d = Gtk.Window(title=title, transient_for=self.win, modal=True, resizable=False)
        box = Gtk.Box(spacing=8, margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        e = Gtk.Entry(text=initial, width_chars=32)
        ok = Gtk.Button(label='OK')
        ok.add_css_class('suggested-action')
        box.append(e)
        box.append(ok)
        d.set_child(box)

        def go(*_):
            d.close()
            done(e.get_text().strip())
        ok.connect('clicked', go)
        e.connect('activate', go)
        d.present()
        stem = os.path.splitext(initial)[0]
        GLib.idle_add(lambda: (e.grab_focus(), e.select_region(0, len(stem)), False)[2])

    def rename(self):
        sel = self.selected()
        if len(sel) != 1 or self.loc == TRASH:
            return
        src = sel[0]

        def done(name):
            if not name or '/' in name or name == os.path.basename(src):
                return
            dst = os.path.join(os.path.dirname(src), name)
            if os.path.exists(dst):
                self.alert('There is already an item with that name.', name)
                return
            try:
                os.rename(src, dst)
            except OSError as e:
                self.alert('This could not be renamed.', str(e))
            self.fill()
        self.ask('Rename', os.path.basename(src), done)

    def delete(self):
        sel = self.selected()
        if not sel:
            return
        if self.loc == TRASH:
            msg, detail, btn = 'Delete permanently?', f'{len(sel)} item(s) will be gone for good.', 'Delete'
        else:
            msg, detail, btn = 'Move to the Trash?', ', '.join(os.path.basename(p) for p in sel[:3]) + (
                '…' if len(sel) > 3 else ''), 'Move to Trash'
        dlg = Gtk.AlertDialog(message=msg, detail=detail, buttons=[btn, 'Cancel'], default_button=1, cancel_button=1)

        def done(d, res):
            try:
                if d.choose_finish(res) != 0:
                    return
            except GLib.Error:
                return
            for p in sel:
                try:
                    if self.loc == TRASH:
                        info = os.path.join(TRASH, 'info', os.path.basename(p) + '.trashinfo')
                        shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
                        if os.path.exists(info):
                            os.remove(info)
                    else:
                        Gio.File.new_for_path(p).trash(None)
                except (OSError, GLib.Error) as e:
                    self.alert('This could not be deleted.', str(e))
                    break
            self.fill()
        dlg.choose(self.win, None, done)

    def restore(self):
        for p in self.selected():
            info = os.path.join(TRASH, 'info', os.path.basename(p) + '.trashinfo')
            try:
                orig = next(urllib.parse.unquote(line.split('=', 1)[1].strip()) for line in open(info)
                            if line.startswith('Path='))
                os.makedirs(os.path.dirname(orig), exist_ok=True)
                shutil.move(p, self.unique(os.path.dirname(orig), os.path.basename(orig)))
                os.remove(info)
            except (OSError, StopIteration) as e:
                self.alert('This could not be restored.', str(e))
        self.fill()

    def empty_trash(self):
        dlg = Gtk.AlertDialog(message='Empty the Trash?', detail='Everything in it will be gone for good.',
                              buttons=['Empty the Trash', 'Cancel'], default_button=1, cancel_button=1)

        def done(d, res):
            try:
                if d.choose_finish(res) != 0:
                    return
            except GLib.Error:
                return
            for sub in ('files', 'info'):
                folder = os.path.join(TRASH, sub)
                for n in os.listdir(folder) if os.path.isdir(folder) else []:
                    p = os.path.join(folder, n)
                    try:
                        shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
                    except OSError:
                        pass
            self.fill()
        dlg.choose(self.win, None, done)

    def properties(self):
        sel = self.selected() or ([self.loc] if self.loc not in (COMPUTER, TRASH) else [])
        if len(sel) != 1:
            return
        p = sel[0]
        try:
            st = os.stat(p)
        except OSError:
            return
        size = st.st_size
        if os.path.isdir(p):
            size = 0
            for r, _d, fs in os.walk(p):
                for f in fs:
                    try:
                        size += os.lstat(os.path.join(r, f)).st_size
                    except OSError:
                        pass
        when = lambda t: datetime.datetime.fromtimestamp(t).strftime('%d %B %Y, %H:%M')  # noqa: E731
        kind = 'File folder' if os.path.isdir(p) else Gio.content_type_get_description(Gio.content_type_guess(p, None)[0])
        self.alert(os.path.basename(p) or p, f'Type: {kind}\nLocation: {os.path.dirname(p)}\nSize: {human(size)}\n'
                                               f'Modified: {when(st.st_mtime)}\nCreated: {when(st.st_ctime)}')

    def alert(self, msg, detail=''):
        Gtk.AlertDialog(message=msg, detail=detail).show(self.win)

    def context_menu(self, gesture, _n, x, y):
        child = self.flow.get_child_at_pos(x, y)
        if child and not child.is_selected():
            self.flow.unselect_all()
            self.flow.select_child(child)
        elif not child:
            self.flow.unselect_all()
        menu = Gio.Menu()
        if child:
            if self.loc == TRASH:
                menu.append('Restore', 'win.ctx::restore')
                menu.append('Delete permanently', 'win.ctx::delete')
            else:
                menu.append('Open', 'win.ctx::open')
                menu.append('Cut', 'win.ctx::cut')
                menu.append('Copy', 'win.ctx::copy')
                menu.append('Rename', 'win.ctx::rename')
                menu.append('Move to Trash', 'win.ctx::delete')
                menu.append('Properties', 'win.ctx::props')
        elif self.loc not in (COMPUTER, TRASH):
            menu.append('Paste', 'win.ctx::paste')
            menu.append('New folder', 'win.ctx::newdir')
            menu.append('Refresh', 'win.ctx::refresh')
            menu.append('Properties', 'win.ctx::props')
        elif self.loc == TRASH:
            menu.append('Empty the Trash', 'win.ctx::empty')
        if not self.win.lookup_action('ctx'):
            act = Gio.SimpleAction.new('ctx', GLib.VariantType.new('s'))
            act.connect('activate', lambda _a, v: {
                'open': lambda: [self.open_item(p) for p in self.selected()[:1]], 'cut': lambda: self.copy(True),
                'copy': lambda: self.copy(False), 'rename': self.rename, 'delete': self.delete,
                'props': self.properties, 'paste': self.paste, 'newdir': self.new_folder, 'refresh': self.fill,
                'restore': self.restore, 'empty': self.empty_trash}[v.get_string()]())
            self.win.add_action(act)
        pop = Gtk.PopoverMenu(menu_model=menu, has_arrow=False)
        pop.set_parent(self.flow)
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = int(x), int(y), 1, 1
        pop.set_pointing_to(r)
        pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
        pop.popup()


if __name__ == '__main__':
    ex = Explorer()
    mwx7ui.App('org.mwx7.explorer', 'My Computer', 'computer', (900, 600), CSS, ex.build).run_main()
