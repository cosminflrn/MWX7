"""Notepad (native): plain text files, as in the concept and Windows: File, Edit, Format, View; asks before losing work."""
import json
import os
import sys
import time

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

SESSION = os.path.join(GLib.get_user_data_dir(), 'mwx7', 'notepad-session.json')
EOLS = {'\n': 'Unix (LF)', '\r\n': 'Windows (CRLF)', '\r': 'Macintosh (CR)'}
BOMS = {'UTF-8 BOM': b'\xef\xbb\xbf', 'UTF-16 LE': b'\xff\xfe', 'UTF-16 BE': b'\xfe\xff'}
CODECS = {'UTF-8': 'utf-8', 'UTF-8 BOM': 'utf-8', 'UTF-16 LE': 'utf-16-le', 'UTF-16 BE': 'utf-16-be', 'Latin-1': 'latin-1'}
BASE_PT = 11

CSS = """
window.mwx7-notepad textview, window.mwx7-notepad textview text { font-family: "DejaVu Sans Mono", monospace;
  font-size: 11pt; color: #111; background: #ffffff; }
window.mwx7-notepad textview { padding: 4px 6px; }
.np-status { font-size: 11px; color: #4a5f7d; border-top: 1px solid #d5dfec; background: #f6f8fb; }
.np-status label { padding: 2px 10px; }
.np-status .np-sep { border-left: 1px solid #d5dfec; }
.np-tab { padding: 0 0 0 2px; }
.np-tab button { min-width: 16px; min-height: 16px; padding: 0; margin-left: 4px; border-radius: 3px; background: none; box-shadow: none;
  opacity: .6; }
.np-tab button:hover { opacity: 1; background: rgba(0,0,0,.08); }
.np-tab .np-dot { color: #2b6cb0; font-size: 10px; }
"""


def decode(data):
    """(text with \\n line ends, encoding name, original line ending). UTF-8 / UTF-16 by BOM, else UTF-8, else Latin-1 (which
    accepts any byte, so a legacy file always opens rather than showing replacement characters)."""
    if data.startswith(b'\xef\xbb\xbf'):
        enc, text = 'UTF-8 BOM', data[3:].decode('utf-8', 'replace')
    elif data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        enc = 'UTF-16 LE' if data[:2] == b'\xff\xfe' else 'UTF-16 BE'
        text = data[2:].decode(CODECS[enc], 'replace')
    else:
        try:
            enc, text = 'UTF-8', data.decode('utf-8')
        except UnicodeDecodeError:
            enc, text = 'Latin-1', data.decode('latin-1')
    crlf = text.count('\r\n')
    lf, cr = text.count('\n') - crlf, text.count('\r') - crlf
    eol = max((lf, '\n'), (crlf, '\r\n'), (cr, '\r'))[1] if (lf or crlf or cr) else '\n'
    return text.replace('\r\n', '\n').replace('\r', '\n'), enc, eol


def encode(text, enc, eol):
    """Inverse of decode. Returns (bytes, encoding actually used): Latin-1 falls back to UTF-8 for characters it lacks."""
    text = text.replace('\n', eol)
    try:
        body = text.encode(CODECS[enc])
    except UnicodeEncodeError:
        enc, body = 'UTF-8', text.encode('utf-8')
    return BOMS.get(enc, b'') + body, enc


class Doc:
    """One tab: its own buffer, view, file and encoding."""
    def __init__(self):
        self.path, self.dirty, self.loading = None, False, False
        self.enc, self.eol = 'UTF-8', '\n'
        self.buf = Gtk.TextBuffer(enable_undo=True)
        self.view = Gtk.TextView(buffer=self.buf, monospace=True)
        self.scroll = Gtk.ScrolledWindow(vexpand=True)
        self.scroll.set_child(self.view)
        self.title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, width_chars=8, max_width_chars=22)
        self.dot = Gtk.Label(label='●', visible=False)
        self.dot.add_css_class('np-dot')
        self.close = Gtk.Button(icon_name='window-close-symbolic', tooltip_text='Close tab (Ctrl+W)', focusable=False)
        self.tab = Gtk.Box(spacing=0)
        self.tab.add_css_class('np-tab')
        for w in (self.title, self.dot, self.close):
            self.tab.append(w)

    def name(self):
        return os.path.basename(self.path) if self.path else 'Untitled'

    def text(self):
        return self.buf.get_text(*self.buf.get_bounds(), True)

    def set_text(self, text):
        self.loading = True
        self.buf.begin_irreversible_action()
        self.buf.set_text(text)
        self.buf.end_irreversible_action()
        self.buf.place_cursor(self.buf.get_start_iter())
        self.loading = False

    def refresh_tab(self):
        self.title.set_label(self.name())
        self.title.set_tooltip_text(self.path or None)
        self.dot.set_visible(self.dirty)



class Notepad:
    def __init__(self):
        self.docs = []
        self.wrap = True
        self.zoom = 100
        self.font = None  # (family, size pt, weight, style) once chosen in Format > Font
        self.session_id = 0
        self.recent = []

    # the current tab, under the names the menus and the find dialog use
    @property
    def doc(self):
        i = self.nb.get_current_page()
        return self.docs[i] if 0 <= i < len(self.docs) else None

    @property
    def buf(self):
        return self.doc.buf

    @property
    def view(self):
        return self.doc.view

    # ---- window ---------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-notepad')
        app.on_open = lambda files: self.open_paths([f.get_path() for f in files])
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.nb = Gtk.Notebook(scrollable=True, vexpand=True)
        self.nb.connect('switch-page', lambda _n, _p, _i: GLib.idle_add(self.on_switch))
        plus = Gtk.Button(icon_name='tab-new-symbolic', tooltip_text='New tab (Ctrl+T)', has_frame=False, focusable=False)
        plus.connect('clicked', lambda *_: self.new_tab())
        self.nb.set_action_widget(plus, Gtk.PackType.END)
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        # Capture: the text view would otherwise take the drop first.
        drop.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        drop.connect('drop', lambda _t, fl, *_: self.open_paths([f.get_path() for f in fl.get_files()]))
        self.nb.add_controller(drop)
        root.append(self.nb)
        bar = Gtk.Box()
        bar.add_css_class('np-status')
        self.st = {}
        for key, expand in (('pos', True), ('zoom', False), ('eol', False), ('enc', False)):
            lab = Gtk.Label(xalign=0 if expand else 1, hexpand=expand)
            if not expand:
                lab.add_css_class('np-sep')
            self.st[key] = lab
            bar.append(lab)
        self.status = bar
        root.append(bar)
        self.font_css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(win.get_display(), self.font_css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 5)
        win.connect('close-request', self.on_close)
        # Restore last time's tabs first, then whatever was asked for (a file opened with Notepad).
        self.restore_session()
        self.apply_font()
        self.build_menu()
        if app.files:
            self.open_paths([f.get_path() for f in app.files])
        if not self.docs:
            self.new_tab()
        return root

    def build_menu(self):
        self.recent = self.recent_files()
        recent_items = [(f'{i + 1}  {os.path.basename(p)}', f'recent{i}', lambda i=i: self.open_paths([self.recent[i]]))
                        for i, p in enumerate(self.recent)]
        self.app.menubar([
            ('File', [('New Tab', 'new', self.new_tab), ('Open…', 'open', self.open),
                      ('Save', 'save', self.save), ('Save As…', 'saveas', self.save_as), None] + (
                recent_items + [None] if recent_items else []) + [
                      ('Close Tab', 'closetab', lambda: self.close_doc(self.doc)), ('Exit', 'exit', self.win.close)]),
            ('Edit', [('Undo', 'undo', lambda: self.buf.undo()), ('Redo', 'redo', lambda: self.buf.redo()), None,
                      ('Cut', 'cut', lambda: self.view.emit('cut-clipboard')),
                      ('Copy', 'copy', lambda: self.view.emit('copy-clipboard')),
                      ('Paste', 'paste', lambda: self.view.emit('paste-clipboard')),
                      ('Delete', 'delete', lambda: self.buf.delete_selection(True, True)), None,
                      ('Find…', 'find', lambda: self.find_dialog(False)), ('Replace…', 'replace', lambda: self.find_dialog(True)),
                      ('Go To Line…', 'gotoline', self.goto_dialog), None,
                      ('Select All', 'selectall', lambda: self.buf.select_range(*self.buf.get_bounds())),
                      ('Time/Date', 'timedate', lambda: self.buf.insert_at_cursor(time.strftime('%H:%M %d/%m/%Y')))]),
            ('Format', [(('✓ ' if self.wrap else '') + 'Word Wrap', 'wrap', self.toggle_wrap), ('Font…', 'font', self.choose_font)]),
            ('View', [('Zoom In', 'zoomin', lambda: self.set_zoom(self.zoom + 10)),
                      ('Zoom Out', 'zoomout', lambda: self.set_zoom(self.zoom - 10)),
                      ('Restore Default Zoom', 'zoomreset', lambda: self.set_zoom(100)), None,
                      ('Status Bar', 'statusbar', lambda: self.status.set_visible(not self.status.get_visible()))]),
            ('Help', [('About Notepad', 'about', lambda: Gio.Subprocess.new(
                ['/usr/share/mwx7/bin/mwx7-app', 'about'], Gio.SubprocessFlags.NONE))]),
        ])
        # Shortcuts are fine on the distro (CLAUDE.md rule 0 is for the browser build).
        for name, keys in (('new', ['<Ctrl>t', '<Ctrl>n']), ('open', ['<Ctrl>o']), ('save', ['<Ctrl>s']),
                           ('saveas', ['<Ctrl><Shift>s']), ('closetab', ['<Ctrl>w']), ('find', ['<Ctrl>f']),
                           ('replace', ['<Ctrl>h']), ('gotoline', ['<Ctrl>g']),
                           ('zoomin', ['<Ctrl>plus', '<Ctrl>equal', '<Ctrl>KP_Add']),
                           ('zoomout', ['<Ctrl>minus', '<Ctrl>KP_Subtract']), ('zoomreset', ['<Ctrl>0', '<Ctrl>KP_0'])):
            self.app.set_accels_for_action('app.' + name, keys)

    def recent_files(self):
        """The files this app remembered (mwx7ui.remember), newest first."""
        try:
            me = GLib.get_prgname()
            items = [i for i in Gtk.RecentManager.get_default().get_items()
                     if i.has_application(me) and i.get_uri().startswith('file://') and i.exists()]
            items.sort(key=lambda i: i.get_modified().to_unix() if i.get_modified() else 0, reverse=True)
            return [Gio.File.new_for_uri(i.get_uri()).get_path() for i in items[:8]]
        except (GLib.Error, TypeError, AttributeError):
            return []

    # ---- tabs -----------------------------------------------------------------------------------------------------
    def new_tab(self, doc=None):
        doc = doc if isinstance(doc, Doc) else Doc()
        doc.buf.connect('changed', lambda *_: self.on_changed(doc))
        doc.buf.connect('notify::cursor-position', lambda *_: self.update_status())
        doc.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR if self.wrap else Gtk.WrapMode.NONE)
        doc.close.connect('clicked', lambda *_: self.close_doc(doc))
        mid = Gtk.GestureClick(button=2)
        mid.connect('pressed', lambda *_: self.close_doc(doc))
        doc.tab.add_controller(mid)
        doc.refresh_tab()
        self.docs.append(doc)
        self.nb.append_page(doc.scroll, doc.tab)
        self.nb.set_tab_reorderable(doc.scroll, True)
        self.nb.set_current_page(len(self.docs) - 1)
        GLib.idle_add(lambda: doc.view.grab_focus() and False)
        self.on_switch()
        return doc

    def on_switch(self):
        # Tabs can be dragged into another order: keep self.docs in step with the notebook.
        self.docs.sort(key=lambda d: self.nb.page_num(d.scroll))
        self.retitle()
        self.update_status()
        self.schedule_session()
        return False

    def close_doc(self, doc):
        if doc not in self.docs:
            return

        def go():
            self.nb.remove_page(self.nb.page_num(doc.scroll))
            self.docs.remove(doc)
            if not self.docs:
                self.win.close()
            else:
                self.on_switch()
        self.guard(doc, go)

    def open_paths(self, paths):
        for path in paths:
            if not path:
                continue
            same = next((d for d in self.docs if d.path == path), None)
            if same:
                self.nb.set_current_page(self.docs.index(same))
                continue
            cur = self.doc
            # An untouched Untitled tab is replaced, not left behind.
            blank = cur if cur and not cur.path and not cur.dirty and not cur.text() else None
            self.load(blank or Doc(), path)
        self.schedule_session()
        return True

    # ---- state ----------------------------------------------------------------------------------------------------
    def retitle(self):
        d = self.doc
        if d:
            self.app.set_title(f'{"*" if d.dirty else ""}{d.name()} - Notepad')

    def on_changed(self, doc):
        if not doc.loading and not doc.dirty:
            doc.dirty = True
            doc.refresh_tab()
            self.retitle()
        if doc is self.doc:
            self.update_status()
        self.schedule_session()

    def update_status(self):
        d = self.doc
        if not d:
            return
        it = d.buf.get_iter_at_mark(d.buf.get_insert())
        self.st['pos'].set_label(f'Ln {it.get_line() + 1}, Col {it.get_line_offset() + 1}')
        self.st['zoom'].set_label(f'{self.zoom}%')
        self.st['eol'].set_label(EOLS[d.eol])
        self.st['enc'].set_label(d.enc)

    def toggle_wrap(self):
        self.wrap = not self.wrap
        for d in self.docs:
            d.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR if self.wrap else Gtk.WrapMode.NONE)
        self.build_menu()
        self.schedule_session()

    def set_zoom(self, z):
        self.zoom = max(20, min(500, z))
        self.apply_font()
        self.update_status()
        self.schedule_session()

    def apply_font(self):
        fam, size, weight, style = self.font or (None, BASE_PT, 400, 'normal')
        face = f'font-family: "{fam}"; ' if fam else ''
        self.font_css.load_from_data((
            f'window.mwx7-notepad textview, window.mwx7-notepad textview text {{ {face}font-size: {size * self.zoom / 100:.1f}pt; '
            f'font-weight: {weight}; font-style: {style}; }}').encode())

    def choose_font(self):
        dlg = Gtk.FontDialog(title='Font')

        def done(d, res):
            try:
                desc = d.choose_font_finish(res)
            except GLib.Error:
                return
            self.font = (desc.get_family(), desc.get_size() / Pango.SCALE or BASE_PT, int(desc.get_weight()),
                         'italic' if desc.get_style() == Pango.Style.ITALIC else 'normal')
            self.apply_font()
        dlg.choose_font(self.win, None, None, done)

    def goto_dialog(self):
        d = mwx7ui.dialog(self.win, 'Go To Line', 'search')
        total = self.buf.get_line_count()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=14, margin_bottom=14, margin_start=14,
                      margin_end=14)
        box.append(Gtk.Label(label=f'Line number (1 - {total}):', xalign=0))
        entry = Gtk.Entry(input_purpose=Gtk.InputPurpose.DIGITS, width_chars=20)
        entry.set_text(str(self.buf.get_iter_at_mark(self.buf.get_insert()).get_line() + 1))
        box.append(entry)
        row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        ok, cancel = Gtk.Button(label='Go To'), Gtk.Button(label='Cancel')
        ok.add_css_class('suggested-action')
        row.append(ok)
        row.append(cancel)
        box.append(row)

        def go(*_):
            try:
                n = int(entry.get_text().strip())
            except ValueError:
                return
            it = self.buf.get_iter_at_line(max(0, min(total, n) - 1))
            it = it[1] if isinstance(it, tuple) else it
            self.buf.place_cursor(it)
            self.view.scroll_to_iter(it, 0.1, True, 0, 0.5)
            d.close()
            self.view.grab_focus()
        ok.connect('clicked', go)
        entry.connect('activate', go)
        cancel.connect('clicked', lambda *_: d.close())
        d.set_child(box)
        d.present()
        entry.grab_focus()
        entry.select_region(0, -1)

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
    def load(self, doc, path):
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except OSError as e:
            self.alert(f'Notepad cannot open {os.path.basename(path)}.', e.strerror or str(e))
            return False
        text, doc.enc, doc.eol = decode(data)
        doc.set_text(text)
        doc.path, doc.dirty = path, False
        if doc not in self.docs:
            self.new_tab(doc)
        doc.refresh_tab()
        self.retitle()
        self.update_status()
        mwx7ui.remember(path)
        GLib.idle_add(lambda: self.build_menu() and False)
        return True

    def write(self, doc, path):
        data, doc.enc = encode(doc.text(), doc.enc, doc.eol)
        try:
            with open(path, 'wb') as f:
                f.write(data)
        except OSError as e:
            self.alert(f'Notepad cannot save {os.path.basename(path)}.', e.strerror or str(e))
            return False
        mwx7ui.remember(path)
        doc.path, doc.dirty = path, False
        doc.refresh_tab()
        if doc is self.doc:
            self.retitle()
            self.update_status()
        self.schedule_session()
        GLib.idle_add(lambda: self.build_menu() and False)
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
        dlg = mwx7ui.FileDialog(title='Open', initial_folder=self.documents(), filters=self.text_filters())

        def done(d, res):
            try:
                self.open_paths([d.open_finish(res).get_path()])
            except GLib.Error:
                pass
        dlg.open(self.win, None, done)

    def save(self, then=None, doc=None):
        doc = doc or self.doc
        if doc.path:
            if self.write(doc, doc.path) and then:
                then()
        else:
            self.save_as(then, doc)

    def save_as(self, then=None, doc=None):
        doc = doc or self.doc
        dlg = mwx7ui.FileDialog(title='Save As', initial_name=(doc.name() if doc.path else 'Untitled.txt'),
                                initial_folder=(Gio.File.new_for_path(os.path.dirname(doc.path)) if doc.path
                                                else self.documents()), filters=self.text_filters())

        def done(d, res):
            try:
                path = d.save_finish(res).get_path()
            except GLib.Error:
                return
            if self.write(doc, path) and then:
                then()
        dlg.save(self.win, None, done)

    # ---- unsaved work ---------------------------------------------------------------------------------------------
    def guard(self, doc, then):
        """Runs `then` once the tab's unsaved changes are saved or let go, as Notepad asks: Save, Don't Save, Cancel."""
        if not doc.dirty:
            then()
            return
        self.nb.set_current_page(self.docs.index(doc))
        dlg = Gtk.AlertDialog(message='Notepad', detail=f'Do you want to save changes to {doc.name()}?',
                              buttons=['Save', 'Don’t Save', 'Cancel'], default_button=0, cancel_button=2)

        def done(d, res):
            try:
                choice = d.choose_finish(res)
            except GLib.Error:
                return
            if choice == 0:
                self.save(then, doc)
            elif choice == 1:
                then()
        dlg.choose(self.win, None, done)

    def on_close(self, *_):
        # Closing the window keeps every tab, unsaved text included, and brings them back next start (as Windows 11's
        # Notepad does), so nothing is asked here; closing a single tab does ask. Closing the last tab clears the session.
        self.save_session()
        return False

    def alert(self, msg, detail):
        Gtk.AlertDialog(message=msg, detail=detail).show(self.win)

    # ---- session: the open tabs come back next start --------------------------------------------------------------
    def schedule_session(self):
        if self.session_id:
            GLib.source_remove(self.session_id)
        self.session_id = GLib.timeout_add(1200, lambda: (self.save_session(), False)[1])

    def save_session(self):
        self.session_id = 0
        tabs = []
        for d in self.docs:
            if not d.path and not d.text():
                continue  # an empty Untitled is not worth restoring
            t = {'path': d.path, 'enc': d.enc, 'eol': d.eol, 'dirty': d.dirty,
                 'cursor': d.buf.get_iter_at_mark(d.buf.get_insert()).get_offset()}
            if d.dirty or not d.path:
                t['text'] = d.text()
            tabs.append(t)
        cur = self.docs.index(self.doc) if self.doc else 0
        try:
            os.makedirs(os.path.dirname(SESSION), exist_ok=True)
            with open(SESSION + '.tmp', 'w') as f:
                json.dump({'tabs': tabs, 'current': cur, 'wrap': self.wrap, 'zoom': self.zoom}, f)
            os.replace(SESSION + '.tmp', SESSION)
        except OSError:
            pass

    def restore_session(self):
        try:
            with open(SESSION) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        try:
            self.wrap, self.zoom = bool(data.get('wrap', True)), int(data.get('zoom', 100))
            for t in data.get('tabs', []):
                d = Doc()
                d.path, d.enc, d.eol = t.get('path'), t.get('enc', 'UTF-8'), t.get('eol', '\n')
                if 'text' in t:
                    d.set_text(t['text'])
                    d.dirty = bool(t.get('dirty'))
                elif d.path and os.path.exists(d.path):
                    with open(d.path, 'rb') as f:
                        text, d.enc, d.eol = decode(f.read())
                    d.set_text(text)
                else:
                    continue  # the file is gone and there is no unsaved text to bring back
                self.new_tab(d)
                d.buf.place_cursor(d.buf.get_iter_at_offset(int(t.get('cursor', 0))))
                d.refresh_tab()
            if self.docs:
                self.nb.set_current_page(max(0, min(len(self.docs) - 1, int(data.get('current', 0)))))
        except (OSError, ValueError, TypeError, AttributeError):
            pass


if __name__ == '__main__':
    pad = Notepad()
    mwx7ui.App('org.mwx7.notepad', 'Notepad', 'notepad', (720, 520), CSS, pad.build).run_main()
