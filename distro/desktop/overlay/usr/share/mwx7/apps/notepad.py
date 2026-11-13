"""Notepad (native): plain text files, as in the concept and Windows: File, Edit, Format, View; asks before losing work."""
import os
import sys
import time

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gio, GLib, Gtk, Pango  # noqa: E402

CSS = """
window.mwx7-notepad textview, window.mwx7-notepad textview text { font-family: "DejaVu Sans Mono", monospace;
  font-size: 11pt; color: #111; background: #ffffff; }
window.mwx7-notepad textview { padding: 4px 6px; }
.np-status { padding: 2px 10px; font-size: 11px; color: #4a5f7d; border-top: 1px solid #d5dfec; background: #f6f8fb; }
"""


class Notepad:
    def __init__(self):
        self.path = None
        self.dirty = False
        self.closing_ok = False

    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-notepad')
        app.on_open = lambda files: self.guard(lambda: self.load(files[0].get_path()))
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('File', [('New', 'new', lambda: self.guard(self.new)), ('Open…', 'open', lambda: self.guard(self.open)),
                      ('Save', 'save', self.save), ('Save As…', 'saveas', self.save_as), None,
                      ('Exit', 'exit', win.close)]),
            ('Edit', [('Undo', 'undo', lambda: self.buf.undo()), ('Redo', 'redo', lambda: self.buf.redo()), None,
                      ('Cut', 'cut', lambda: self.view.emit('cut-clipboard')),
                      ('Copy', 'copy', lambda: self.view.emit('copy-clipboard')),
                      ('Paste', 'paste', lambda: self.view.emit('paste-clipboard')),
                      ('Delete', 'delete', lambda: self.buf.delete_selection(True, True)), None,
                      ('Find…', 'find', lambda: self.find_dialog(False)), ('Replace…', 'replace', lambda: self.find_dialog(True)),
                      None,
                      ('Select All', 'selectall', lambda: self.buf.select_range(*self.buf.get_bounds())),
                      ('Time/Date', 'timedate', lambda: self.buf.insert_at_cursor(time.strftime('%H:%M %d/%m/%Y')))]),
            ('Format', [('Word Wrap', 'wrap', self.toggle_wrap), ('Font…', 'font', self.choose_font)]),
            ('View', [('Status Bar', 'statusbar', lambda: self.status.set_visible(not self.status.get_visible()))]),
            ('Help', [('About Notepad', 'about', lambda: Gio.Subprocess.new(
                ['/usr/share/mwx7/bin/mwx7-app', 'about'], Gio.SubprocessFlags.NONE))]),
        ]))
        self.buf = Gtk.TextBuffer(enable_undo=True)
        self.buf.connect('changed', self.on_changed)
        self.buf.connect('notify::cursor-position', lambda *_: self.update_status())
        self.view = Gtk.TextView(buffer=self.buf, wrap_mode=Gtk.WrapMode.WORD_CHAR, monospace=True)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.view)
        root.append(scroll)
        self.status = Gtk.Label(xalign=1)
        self.status.add_css_class('np-status')
        root.append(self.status)
        self.font = Gtk.CssProvider()
        mwx7ui.Gtk.StyleContext.add_provider_for_display(win.get_display(), self.font,
                                                         Gtk.STYLE_PROVIDER_PRIORITY_USER + 3)
        win.connect('close-request', self.on_close)
        if app.files:
            GLib.idle_add(lambda: self.load(app.files[0].get_path()) and False)
        else:
            self.retitle()
        self.update_status()
        GLib.idle_add(lambda: self.view.grab_focus() and False)
        return root

    # ---- state ----------------------------------------------------------------------------------------------------
    def name(self):
        return os.path.basename(self.path) if self.path else 'Untitled'

    def retitle(self):
        self.app.set_title(f'{"*" if self.dirty else ""}{self.name()} - Notepad')

    def on_changed(self, *_):
        if not self.dirty:
            self.dirty = True
            self.retitle()
        self.update_status()

    def update_status(self):
        it = self.buf.get_iter_at_mark(self.buf.get_insert())
        self.status.set_label(f'Ln {it.get_line() + 1}, Col {it.get_line_offset() + 1}')

    def toggle_wrap(self):
        on = self.view.get_wrap_mode() != Gtk.WrapMode.NONE
        self.view.set_wrap_mode(Gtk.WrapMode.NONE if on else Gtk.WrapMode.WORD_CHAR)

    def choose_font(self):
        dlg = Gtk.FontDialog(title='Font')

        def done(d, res):
            try:
                desc = d.choose_font_finish(res)
            except GLib.Error:
                return
            size = desc.get_size() / Pango.SCALE or 11
            weight = int(desc.get_weight())
            style = 'italic' if desc.get_style() == Pango.Style.ITALIC else 'normal'
            self.font.load_from_data((f'window.mwx7-notepad textview, window.mwx7-notepad textview text {{ '
                                      f'font-family: "{desc.get_family()}"; font-size: {size}pt; '
                                      f'font-weight: {weight}; font-style: {style}; }}').encode())
        dlg.choose_font(self.win, None, None, done)

    # ---- find and replace, as Notepad's dialogs ----
    def find_next(self, text, case, backwards=False):
        flags = Gtk.TextSearchFlags.TEXT_ONLY | (0 if case else Gtk.TextSearchFlags.CASE_INSENSITIVE)
        ins, bound = self.buf.get_selection_bounds() or (self.buf.get_iter_at_mark(self.buf.get_insert()),) * 2
        if backwards:
            hit = ins.backward_search(text, flags, None) or self.buf.get_end_iter().backward_search(text, flags, None)
        else:
            hit = bound.forward_search(text, flags, None) or self.buf.get_start_iter().forward_search(text, flags, None)
        if not hit:
            return False
        self.buf.select_range(hit[0], hit[1])
        self.view.scroll_to_iter(hit[0], 0.2, False, 0, 0)
        return True

    def find_dialog(self, replace):
        d = mwx7ui.dialog(self.win, 'Replace' if replace else 'Find', 'search')
        grid = Gtk.Grid(row_spacing=8, column_spacing=8, margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        what = Gtk.Entry(width_chars=26)
        sel = self.buf.get_selection_bounds()
        if sel:
            what.set_text(self.buf.get_text(sel[0], sel[1], False)[:80])
        grid.attach(Gtk.Label(label='Find what:', xalign=0), 0, 0, 1, 1)
        grid.attach(what, 1, 0, 1, 1)
        with_ = Gtk.Entry(width_chars=26)
        if replace:
            grid.attach(Gtk.Label(label='Replace with:', xalign=0), 0, 1, 1, 1)
            grid.attach(with_, 1, 1, 1, 1)
        case = Gtk.CheckButton(label='Match case')
        grid.attach(case, 0, 2, 2, 1)
        status = Gtk.Label(xalign=0)
        grid.attach(status, 0, 3, 2, 1)
        btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        nxt = Gtk.Button(label='Find Next')
        nxt.add_css_class('suggested-action')
        btns.append(nxt)

        def find(*_):
            t = what.get_text()
            if t:
                status.set_label('' if self.find_next(t, case.get_active()) else f'Cannot find "{t}"')
        nxt.connect('clicked', find)
        what.connect('activate', find)
        if replace:
            one, every = Gtk.Button(label='Replace'), Gtk.Button(label='Replace All')

            def rep(*_):
                t = what.get_text()
                b = self.buf.get_selection_bounds()
                if t and b and (self.buf.get_text(b[0], b[1], False) == t if case.get_active()
                                else self.buf.get_text(b[0], b[1], False).lower() == t.lower()):
                    self.buf.delete(b[0], b[1])
                    self.buf.insert_at_cursor(with_.get_text())
                find()

            def rep_all(*_):
                t = what.get_text()
                if not t:
                    return
                self.buf.place_cursor(self.buf.get_start_iter())
                n = 0
                self.buf.begin_user_action()
                while self.find_next(t, case.get_active()):
                    b = self.buf.get_selection_bounds()
                    if n and b[0].get_offset() < last:
                        break
                    self.buf.delete(b[0], b[1])
                    self.buf.insert_at_cursor(with_.get_text())
                    last = self.buf.get_iter_at_mark(self.buf.get_insert()).get_offset()
                    n += 1
                self.buf.end_user_action()
                status.set_label(f'Replaced {n} time{"s" if n != 1 else ""}.')
            one.connect('clicked', rep)
            every.connect('clicked', rep_all)
            btns.append(one)
            btns.append(every)
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_: d.close())
        btns.append(cancel)
        grid.attach(btns, 2, 0, 1, 4)
        d.set_child(grid)
        d.present()

    # ---- files ----------------------------------------------------------------------------------------------------
    def new(self):
        self.buf.set_text('')
        self.path, self.dirty = None, False
        self.retitle()

    def load(self, path):
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError as e:
            self.alert(f'Notepad cannot open {os.path.basename(path)}.', e.strerror or str(e))
            return False
        self.buf.begin_irreversible_action()
        self.buf.set_text(text)
        self.buf.end_irreversible_action()
        self.buf.place_cursor(self.buf.get_start_iter())
        self.path, self.dirty = path, False
        self.retitle()
        mwx7ui.remember(path)
        return True

    def write(self, path):
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.buf.get_text(*self.buf.get_bounds(), True))
        except OSError as e:
            self.alert(f'Notepad cannot save {os.path.basename(path)}.', e.strerror or str(e))
            return False
        mwx7ui.remember(path)
        self.path, self.dirty = path, False
        self.retitle()
        return True

    def documents(self):
        d = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or os.path.expanduser('~')
        return Gio.File.new_for_path(d)

    def text_filters(self):
        f = Gtk.FileFilter(name='Text Documents')
        f.add_mime_type('text/plain')
        f.add_suffix('txt')
        a = Gtk.FileFilter(name='All Files')
        a.add_pattern('*')
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        store.append(a)
        return store

    def open(self):
        dlg = Gtk.FileDialog(title='Open', initial_folder=self.documents(), filters=self.text_filters())

        def done(d, res):
            try:
                self.load(d.open_finish(res).get_path())
            except GLib.Error:
                pass
        dlg.open(self.win, None, done)

    def save(self, then=None):
        if self.path:
            if self.write(self.path) and then:
                then()
        else:
            self.save_as(then)

    def save_as(self, then=None):
        dlg = Gtk.FileDialog(title='Save As', initial_name=(self.name() if self.path else 'Untitled.txt'),
                             initial_folder=(Gio.File.new_for_path(os.path.dirname(self.path)) if self.path
                                             else self.documents()), filters=self.text_filters())

        def done(d, res):
            try:
                path = d.save_finish(res).get_path()
            except GLib.Error:
                return
            if self.write(path) and then:
                then()
        dlg.save(self.win, None, done)

    # ---- unsaved work ---------------------------------------------------------------------------------------------
    def guard(self, then):
        """Runs `then` once unsaved changes are saved or let go, as Notepad asks: Save, Don't Save, Cancel."""
        if not self.dirty:
            then()
            return
        dlg = Gtk.AlertDialog(message='Notepad', detail=f'Do you want to save changes to {self.name()}?',
                              buttons=['Save', 'Don’t Save', 'Cancel'], default_button=0, cancel_button=2)

        def done(d, res):
            try:
                choice = d.choose_finish(res)
            except GLib.Error:
                return
            if choice == 0:
                self.save(then)
            elif choice == 1:
                then()
        dlg.choose(self.win, None, done)

    def on_close(self, *_):
        if self.closing_ok or not self.dirty:
            return False

        def go():
            self.closing_ok = True
            self.win.close()
        self.guard(go)
        return True

    def alert(self, msg, detail):
        Gtk.AlertDialog(message=msg, detail=detail).show(self.win)


if __name__ == '__main__':
    pad = Notepad()
    mwx7ui.App('org.mwx7.notepad', 'Notepad', 'notepad', (640, 480), CSS, pad.build).run_main()
