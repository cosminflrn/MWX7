"""Reader (native): MWX 7's PDF viewer. Continuous scrolling, zoom (fit width / fit page / + / - / Ctrl+wheel), a thumbnails
sidebar, find with highlighted matches, print, and it remembers the last page and zoom of each file. Poppler (through GObject
introspection) does the drawing; pages are drawn only while they are on screen (plus one either side), by a worker thread that
has its own copy of the document, so scrolling never waits for a page. Opens a file given to it (mwx7-app reader file.pdf)."""
import json
import os
import sys
import threading
import time
from bisect import bisect_right
from collections import OrderedDict

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk  # noqa: E402
import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version('Poppler', '0.18')
from gi.repository import Poppler  # noqa: E402

CONFIG = os.path.join(GLib.get_user_config_dir(), 'mwx7', 'reader.json')
REMEMBERED_FILES = 300
GAP, MARGIN = 14, 16  # between pages / around the stack, in pixels
THUMB_W, THUMB_H, THUMB_ROW = 104, 134, 164
PX_PER_PT = 96 / 72  # 100% = a point is 1/72 inch drawn at 96 dpi, as on a Windows desktop
ZOOMS = (0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 3.0, 4.0, 6.0, 8.0)
PAGE_CACHE_BYTES = 192 * 1024 * 1024
THUMB_CACHE = 500

CSS = """
window.mwx7-reader > box { background: #e9eef5; }
.rd-bar { padding: 5px 8px; background: linear-gradient(180deg, #f6faff, #dce8f6); border-bottom: 1px solid #a9c1de; }
.rd-bar button, .rd-find button { min-height: 24px; min-width: 24px; padding: 2px 6px; border-radius: 3px; background: none;
  border: 1px solid transparent; box-shadow: none; color: #1c3150; }
.rd-bar button:hover, .rd-find button:hover { background: linear-gradient(180deg, #f4f9ff, #d6e7fa); border-color: #9bbbe3; }
.rd-bar button:checked { background: linear-gradient(180deg, #cfe3fa, #aecdf2); border-color: #6d9ad0; }
.rd-bar button:disabled { opacity: .45; }
.rd-bar separator { background: #b5c7de; min-width: 1px; margin: 3px 5px; }
.rd-bar entry { min-height: 24px; border-radius: 3px; border: 1px solid #8ea8c9; background: #ffffff; padding: 0 4px; }
.rd-of, .rd-zoom { color: #3b4f6b; }
.rd-zoom { min-width: 44px; }
.rd-find { padding: 5px 8px; background: linear-gradient(180deg, #fffdf3, #f6efc8); border-bottom: 1px solid #d9cd8c; }
.rd-find entry { min-height: 24px; border-radius: 3px; border: 1px solid #b9ab62; background: #ffffff; }
.rd-count { color: #5b5222; margin: 0 6px; }
.rd-stage { background: #98a3b3; }
.rd-side { background: linear-gradient(90deg, #f3f8fd, #e3edf8); border-right: 1px solid #b7cae2; }
.rd-empty { color: #3b4f6b; font-size: 14px; }
.rd-empty button { padding: 6px 18px; }
"""


def load_config():
    try:
        with open(CONFIG) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, 'w') as f:
            json.dump(cfg, f)
    except OSError:
        pass


def open_document(path, password=None):
    return Poppler.Document.new_from_file(Gio.File.new_for_path(path).get_uri(), password)


class Renderer(threading.Thread):
    """Draws pages off the main thread. Poppler documents are not shared between threads, so it opens its own. The main
    thread replaces the whole job list whenever the view changes (jobs: (kind, page, px_w, px_h, scale_factor)), so what
    has scrolled away is never drawn."""

    def __init__(self, path, password, gen, deliver):
        super().__init__(daemon=True)
        self.path, self.password, self.gen, self.deliver = path, password, gen, deliver
        self.cv = threading.Condition()
        self.jobs, self.busy, self.stop = [], None, False

    def set_jobs(self, jobs):
        with self.cv:
            self.jobs = jobs
            self.cv.notify()

    def quit(self):
        with self.cv:
            self.stop = True
            self.cv.notify()

    def run(self):
        try:
            doc = open_document(self.path, self.password)
        except GLib.Error:
            return
        while True:
            with self.cv:
                while not self.jobs and not self.stop:
                    self.cv.wait()
                if self.stop:
                    return
                job = self.jobs.pop(0)
                self.busy = job
            kind, n, pw, ph, sf = job
            try:
                page = doc.get_page(n)
                w, h = page.get_size()
                surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, int(pw * sf)), max(1, int(ph * sf)))
                cr = cairo.Context(surf)
                cr.set_source_rgb(1, 1, 1)
                cr.paint()
                cr.scale(surf.get_width() / w, surf.get_height() / h)
                page.render(cr)
                surf.flush()
                surf.set_device_scale(sf, sf)
            except Exception:  # noqa: BLE001 - a bad page must not stop the others
                surf = None
            with self.cv:
                self.busy = None
            GLib.idle_add(self.deliver, self.gen, job, surf)


class Reader:
    def __init__(self):
        self.cfg = load_config()
        self.doc = self.path = self.password = None
        self.renderer, self.gen = None, 0
        self.sizes, self.ps, self.offsets, self.total = [], [], [], 0
        self.mode, self.zoom = 'width', 1.0  # mode: 'width' | 'page' | 'custom'
        self.cur = 0
        self.pending = None  # (page, fraction down it) to scroll to once the new layout exists
        self.cache, self.cache_bytes, self.thumbs = OrderedDict(), 0, OrderedDict()
        self.hits, self.order, self.cur_hit, self.query = {}, [], -1, ''
        self.search_id = self.relayout_id = self.save_id = self.sched_id = 0
        self.print_settings = self.page_setup = None
        self.quiet = False  # set while code (not the person) moves a control

    # ---- window ------------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-reader')
        app.on_open = lambda files: self.open_path(files[0].get_path())
        win.connect('close-request', lambda *_a: self.on_close() or False)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('File', [('Open…', 'open', self.open_dialog), ('Print…', 'print', self.print_doc)]),
            ('Edit', [('Find…', 'find', self.show_find), ('Find Next', 'findnext', lambda: self.step_hit(1)),
                      ('Find Previous', 'findprev', lambda: self.step_hit(-1))]),
            ('View', [('Thumbnails', 'thumbs', self.toggle_side), None,
                      ('Zoom In', 'zoomin', lambda: self.zoom_step(1)), ('Zoom Out', 'zoomout', lambda: self.zoom_step(-1)),
                      ('Actual Size', 'actual', lambda: self.set_zoom(1.0)), None,
                      ('Fit Width', 'fitwidth', lambda: self.set_mode('width')),
                      ('Fit Page', 'fitpage', lambda: self.set_mode('page'))]),
            ('Go', [('Previous Page', 'prev', lambda: self.goto(self.cur - 1)),
                    ('Next Page', 'next', lambda: self.goto(self.cur + 1)), None,
                    ('First Page', 'first', lambda: self.goto(0)), ('Last Page', 'last', lambda: self.goto(10 ** 9)),
                    ('Go to Page…', 'gopage', self.focus_page)]),
        ]))
        for action, accels in (('open', ['<Ctrl>o']), ('print', ['<Ctrl>p']), ('find', ['<Ctrl>f']), ('findnext', ['F3']),
                               ('findprev', ['<Shift>F3']), ('thumbs', ['F9']), ('zoomin', ['<Ctrl>plus', '<Ctrl>equal']),
                               ('zoomout', ['<Ctrl>minus']), ('actual', ['<Ctrl>1']), ('fitwidth', ['<Ctrl>0']),
                               ('fitpage', ['<Ctrl>9']), ('prev', ['<Alt>Up']), ('next', ['<Alt>Down']),
                               ('gopage', ['<Ctrl>g'])):
            app.set_accels_for_action('app.' + action, accels)

        root.append(self.build_toolbar())
        self.findbar = self.build_findbar()
        root.append(self.findbar)

        body = Gtk.Box(vexpand=True)
        self.side = Gtk.ScrolledWindow(width_request=146, hexpand=False, hscrollbar_policy=Gtk.PolicyType.NEVER, css_classes=['rd-side'])
        self.thumbarea = Gtk.DrawingArea(hexpand=False)
        self.thumbarea.set_draw_func(self.draw_thumbs)
        click = Gtk.GestureClick()
        click.connect('pressed', self.thumb_click)
        self.thumbarea.add_controller(click)
        self.side.set_child(self.thumbarea)
        self.side.get_vadjustment().connect('value-changed', lambda *_a: self.thumbarea.queue_draw())
        self.side.set_visible(bool(self.cfg.get('sidebar', False)))
        self.side_btn.set_active(self.side.get_visible())
        body.append(self.side)

        overlay = Gtk.Overlay(hexpand=True)
        self.scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True, css_classes=['rd-stage'])
        self.area = Gtk.DrawingArea(hexpand=True, focusable=True)
        self.area.set_draw_func(self.draw_pages)
        grab = Gtk.GestureClick()
        grab.connect('pressed', lambda *_a: self.area.grab_focus())
        self.area.add_controller(grab)
        self.scroll.set_child(self.area)
        wheel = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        wheel.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        wheel.connect('scroll', self.on_wheel)
        self.scroll.add_controller(wheel)
        self.vadj, self.hadj = self.scroll.get_vadjustment(), self.scroll.get_hadjustment()
        self.vadj.connect('value-changed', self.on_scrolled)
        self.vadj.connect('changed', self.on_extent)
        self.hadj.connect('changed', self.on_extent)
        overlay.set_child(self.scroll)

        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER,
                             valign=Gtk.Align.CENTER, css_classes=['rd-empty'])
        self.empty.append(Gtk.Label(label='Open a PDF to start reading.', justify=Gtk.Justification.CENTER, wrap=True))
        btn = Gtk.Button(label='Open…', halign=Gtk.Align.CENTER)
        btn.connect('clicked', lambda *_a: self.open_dialog())
        self.empty.append(btn)
        overlay.add_overlay(self.empty)
        body.append(overlay)
        root.append(body)
        self.sync_controls()
        if app.files:
            GLib.idle_add(self.open_first)
        return root

    def open_first(self):
        self.open_path(self.app.files[0].get_path())
        return False

    def tool(self, icon_name, tip, fn, toggle=False):
        b = Gtk.ToggleButton() if toggle else Gtk.Button()
        b.set_icon_name(icon_name)
        b.set_tooltip_text(tip)
        b.set_focusable(False)
        b.connect('toggled' if toggle else 'clicked', lambda *_a: fn())
        return b

    def build_toolbar(self):
        bar = Gtk.Box(spacing=2, css_classes=['rd-bar'])
        self.side_btn = self.tool('view-list-symbolic', 'Thumbnails', lambda: self.toggle_side(True), toggle=True)
        bar.append(self.side_btn)
        bar.append(Gtk.Separator())
        bar.append(self.tool('document-open-symbolic', 'Open…', self.open_dialog))
        self.print_btn = self.tool('document-print-symbolic', 'Print…', self.print_doc)
        bar.append(self.print_btn)
        bar.append(Gtk.Separator())
        self.prev_btn = self.tool('go-up-symbolic', 'Previous page', lambda: self.goto(self.cur - 1))
        self.next_btn = self.tool('go-down-symbolic', 'Next page', lambda: self.goto(self.cur + 1))
        self.pageentry = Gtk.Entry(width_chars=4, max_width_chars=5, xalign=0.5, valign=Gtk.Align.CENTER)
        self.pageentry.connect('activate', self.page_entered)
        focus = Gtk.EventControllerFocus()
        focus.connect('leave', lambda *_a: self.show_page_number())
        self.pageentry.add_controller(focus)
        self.of_label = Gtk.Label(label='/ –', css_classes=['rd-of'], margin_start=4, margin_end=4)
        for w in (self.prev_btn, self.pageentry, self.of_label, self.next_btn, Gtk.Separator()):
            bar.append(w)
        self.out_btn = self.tool('zoom-out-symbolic', 'Zoom out', lambda: self.zoom_step(-1))
        self.in_btn = self.tool('zoom-in-symbolic', 'Zoom in', lambda: self.zoom_step(1))
        self.zoom_label = Gtk.Label(label='100%', css_classes=['rd-zoom'])
        self.width_btn = self.tool('view-fullscreen-symbolic', 'Fit width', lambda: self.fit_toggled('width'), toggle=True)
        self.page_btn = self.tool('zoom-fit-best-symbolic', 'Fit page', lambda: self.fit_toggled('page'), toggle=True)
        for w in (self.out_btn, self.zoom_label, self.in_btn, self.width_btn, self.page_btn):
            bar.append(w)
        bar.append(Gtk.Box(hexpand=True))
        self.find_btn = self.tool('edit-find-symbolic', 'Find (Ctrl+F)', self.show_find)
        bar.append(self.find_btn)
        return bar

    def build_findbar(self):
        bar = Gtk.Box(spacing=4, css_classes=['rd-find'], visible=False)
        self.entry = Gtk.SearchEntry(placeholder_text='Find in document', width_chars=30)
        self.entry.connect('search-changed', lambda e: self.start_search(e.get_text()))
        self.entry.connect('activate', lambda *_a: self.step_hit(1))
        self.entry.connect('stop-search', lambda *_a: self.hide_find())
        self.count = Gtk.Label(css_classes=['rd-count'])
        for w in (self.entry, self.tool('go-up-symbolic', 'Previous match', lambda: self.step_hit(-1)),
                  self.tool('go-down-symbolic', 'Next match', lambda: self.step_hit(1)), self.count,
                  Gtk.Box(hexpand=True), self.tool('window-close-symbolic', 'Close', self.hide_find)):
            bar.append(w)
        return bar

    # ---- opening -----------------------------------------------------------------------------------------------------
    def open_dialog(self):
        flt = Gtk.FileFilter(name='PDF documents')
        flt.add_mime_type('application/pdf')
        flt.add_suffix('pdf')
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        folder = Gio.File.new_for_path(os.path.dirname(self.path)) if self.path else None
        dlg = mwx7ui.FileDialog(title='Open', initial_folder=folder, filters=store)

        def done(d, res):
            try:
                self.open_path(d.open_finish(res).get_path())
            except GLib.Error:
                pass
        dlg.open(self.win, None, done)

    def open_path(self, path, password=None):
        path = os.path.abspath(path)
        try:
            doc = open_document(path, password)
        except GLib.Error as e:
            if e.matches(Poppler.error_quark(), Poppler.Error.ENCRYPTED):
                self.ask_password(path, retry=password is not None)
            else:
                self.fail(path, e.message)
            return False
        n = doc.get_n_pages()
        if n < 1:
            self.fail(path, 'This document has no pages.')
            return False
        self.save_position()
        self.close_doc()
        self.doc, self.path, self.password = doc, path, password
        self.sizes = [doc.get_page(i).get_size() for i in range(n)]
        mwx7ui.remember(path)
        self.gen += 1
        self.renderer = Renderer(path, password, self.gen, self.rendered)
        self.renderer.start()
        remembered = (self.cfg.get('files') or {}).get(path, {})
        z = remembered.get('zoom', 'width')
        self.mode, self.zoom = (z, 1.0) if z in ('width', 'page') else ('custom', min(8.0, max(0.1, float(z or 1))))
        page = min(max(int(remembered.get('page', 0) or 0), 0), n - 1)
        self.cur, self.pending, self.ps, self.offsets = page, (page, 0.0), [], []
        self.empty.set_visible(False)
        self.app.set_title(f'{os.path.basename(path)} - Reader')
        self.relayout(force=True)
        if self.entry.get_text():
            self.start_search(self.entry.get_text())
        self.sync_controls()
        self.area.grab_focus()
        GLib.timeout_add(120, self.sync_thumb_later)
        return True

    def fail(self, path, message):
        Gtk.AlertDialog(message=f'Could not open {os.path.basename(path)}', detail=message).show(self.win)

    def ask_password(self, path, retry):
        dlg = mwx7ui.dialog(self.win, 'Password required', 'reader')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=16, margin_start=18,
                      margin_end=18)
        box.append(Gtk.Label(label=('That password did not work. ' if retry else '') +
                             f'{os.path.basename(path)} is protected.\nType its password to open it.', xalign=0))
        pw = Gtk.PasswordEntry(show_peek_icon=True, width_chars=28)
        box.append(pw)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        ok = Gtk.Button(label='Open', css_classes=['suggested-action'], width_request=80)
        cancel = Gtk.Button(label='Cancel', width_request=80)
        row.append(ok)
        row.append(cancel)
        box.append(row)

        def go(*_a):
            text = pw.get_text()
            dlg.destroy()
            self.open_path(path, text)
        ok.connect('clicked', go)
        pw.connect('activate', go)
        cancel.connect('clicked', lambda *_a: dlg.destroy())
        dlg.set_child(box)
        dlg.present()
        pw.grab_focus()

    def close_doc(self):
        if self.renderer:
            self.renderer.quit()
        self.renderer = None
        self.cache.clear()
        self.thumbs.clear()
        self.cache_bytes = 0
        self.doc = None
        self.hits, self.order, self.cur_hit = {}, [], -1
        self.search_id += 1

    def on_close(self):
        self.save_position()
        self.close_doc()

    # ---- remembered settings -----------------------------------------------------------------------------------------
    def save_position(self):
        if self.save_id:
            GLib.source_remove(self.save_id)
            self.save_id = 0
        if not self.doc:
            return False
        files = self.cfg.setdefault('files', {})
        files.pop(self.path, None)  # re-inserted last: the oldest entries are the ones dropped
        files[self.path] = {'page': self.cur, 'zoom': self.mode if self.mode != 'custom' else round(self.zoom, 3)}
        while len(files) > REMEMBERED_FILES:
            files.pop(next(iter(files)))
        self.cfg['sidebar'] = self.side.get_visible()
        save_config(self.cfg)
        return False

    def save_soon(self):
        if self.save_id:
            GLib.source_remove(self.save_id)
        self.save_id = GLib.timeout_add(1200, self.save_position)

    # ---- layout ------------------------------------------------------------------------------------------------------
    def view_size(self):
        w, h = self.hadj.get_page_size(), self.vadj.get_page_size()
        return (w or 640), (h or 480)

    def fit_zoom(self, mode):
        vw, vh = self.view_size()
        widest = self.sizes[0][0]  # the first page sets the width: the zoom must not change as other pages scroll by
        z = (vw - 2 * MARGIN) / (widest * PX_PER_PT)
        if mode == 'page':
            _pw, ph = self.sizes[min(self.cur, len(self.sizes) - 1)]
            z = min(z, (vh - 2 * GAP) / (ph * PX_PER_PT))
        return min(8.0, max(0.1, z))

    def relayout(self, force=False):
        if not self.doc:
            return
        zoom = self.fit_zoom(self.mode) if self.mode != 'custom' else self.zoom
        if not force and abs(zoom - self.zoom) < 1e-4 and self.ps:
            return
        if self.pending is None and self.ps:  # keep the same spot on the same page while the pages change size
            top = self.vadj.get_value()
            p = max(0, bisect_right(self.offsets, top) - 1)
            self.pending = (p, (top - self.offsets[p]) / max(1, self.ps[p][1]))
        self.zoom = zoom
        s = zoom * PX_PER_PT
        self.ps = [(max(1, round(w * s)), max(1, round(h * s))) for w, h in self.sizes]
        self.offsets, y = [], MARGIN
        for _w, h in self.ps:
            self.offsets.append(y)
            y += h + GAP
        self.total = y - GAP + MARGIN
        self.area.set_content_width(max(w for w, _h in self.ps) + 2 * MARGIN)
        self.area.set_content_height(self.total)
        self.area.queue_draw()
        self.sync_controls()
        GLib.timeout_add(40, self.apply_pending)

    def apply_pending(self):
        if self.pending and self.offsets:
            p, f = self.pending
            p = min(max(p, 0), len(self.ps) - 1)
            value = self.offsets[p] + f * self.ps[p][1] - (GAP if f == 0 else 0)
            self.vadj.set_value(min(max(0, value), max(0, self.vadj.get_upper() - self.vadj.get_page_size())))
            # A page wider than the window (a landscape page among portrait ones) starts centred, not at its left edge.
            self.hadj.set_value(max(0, (self.hadj.get_upper() - self.hadj.get_page_size()) / 2))
            self.pending = None
            self.update_current()
        return False

    def on_extent(self, *_a):
        """The viewport changed size (window resized, or the layout just caught up): refit if a fit mode is on."""
        if self.relayout_id or not self.doc or self.mode == 'custom':
            return

        def later():
            self.relayout_id = 0
            self.relayout()
            return False
        self.relayout_id = GLib.idle_add(later)

    def on_scrolled(self, *_a):
        self.update_current()
        self.area.queue_draw()

    def update_current(self):
        if not self.offsets:
            return
        probe = self.vadj.get_value() + self.vadj.get_page_size() * 0.3
        cur = max(0, min(len(self.ps) - 1, bisect_right(self.offsets, probe) - 1))
        if cur != self.cur:
            self.cur = cur
            self.page_changed()

    def page_changed(self):
        self.show_page_number()
        self.thumbarea.queue_draw()
        self.sync_thumb_scroll()
        self.save_soon()
        if self.mode == 'page':
            self.relayout()

    def goto(self, n):
        if not self.doc or not self.offsets:
            return
        n = min(max(n, 0), len(self.ps) - 1)
        self.pending = (n, 0.0)
        self.apply_pending()
        if n != self.cur:
            self.cur = n
            self.page_changed()

    # ---- zoom --------------------------------------------------------------------------------------------------------
    def set_zoom(self, z):
        if not self.doc:
            return
        self.mode, self.zoom = 'custom', min(8.0, max(0.1, z))
        self.relayout(force=True)
        self.save_soon()

    def zoom_step(self, d):
        if not self.doc:
            return
        z = self.zoom
        if d > 0:
            z = next((c for c in ZOOMS if c > z * 1.01), ZOOMS[-1])
        else:
            z = next((c for c in reversed(ZOOMS) if c < z / 1.01), ZOOMS[0])
        self.set_zoom(z)

    def set_mode(self, mode):
        if not self.doc:
            return
        self.mode = mode
        self.relayout(force=True)
        self.save_soon()

    def fit_toggled(self, mode):
        if not self.quiet:
            self.set_mode(mode)

    def on_wheel(self, ctrl, _dx, dy):
        if not ctrl.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            return False
        self.zoom_step(-1 if dy > 0 else 1)
        return True

    # ---- drawing the pages -------------------------------------------------------------------------------------------
    def visible_pages(self):
        if not self.offsets:
            return []
        top = self.vadj.get_value()
        bottom = top + self.vadj.get_page_size()
        first = max(0, bisect_right(self.offsets, top) - 1)
        out = []
        for i in range(first, len(self.ps)):
            if self.offsets[i] > bottom:
                break
            if self.offsets[i] + self.ps[i][1] >= top:
                out.append(i)
        return out

    def draw_pages(self, _area, cr, width, _height):
        s = self.zoom * PX_PER_PT
        for i in self.visible_pages():
            pw, ph = self.ps[i]
            x, y = (width - pw) / 2, self.offsets[i]
            cr.set_source_rgba(0, 0, 0, 0.18)
            cr.rectangle(x + 2, y + 3, pw, ph)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(x, y, pw, ph)
            cr.fill()
            entry = self.cache.get(i)
            if entry:
                self.cache.move_to_end(i)
                surf = entry[2]
                sx, sy = surf.get_device_scale()
                cr.save()
                cr.translate(x, y)
                # A page drawn for another zoom still shows (scaled) until the new one lands.
                cr.scale(pw / (surf.get_width() / sx), ph / (surf.get_height() / sy))
                cr.set_source_surface(surf, 0, 0)
                cr.get_source().set_filter(cairo.FILTER_GOOD)
                cr.paint()
                cr.restore()
            for k, (x1, y1, x2, y2) in enumerate(self.hits.get(i, ())):
                current = self.cur_hit >= 0 and self.order[self.cur_hit] == (i, k)
                cr.set_source_rgba(1, 0.55, 0.05, 0.55) if current else cr.set_source_rgba(1, 0.9, 0.1, 0.45)
                cr.rectangle(x + x1 * s, y + y1 * s, (x2 - x1) * s, (y2 - y1) * s)
                cr.fill()
            cr.set_source_rgba(0, 0, 0, 0.35)
            cr.set_line_width(1)
            cr.rectangle(x + 0.5, y + 0.5, pw - 1, ph - 1)
            cr.stroke()
        self.schedule()

    def draw_thumbs(self, _area, cr, width, _height):
        if not self.doc:
            return
        adj = self.side.get_vadjustment()
        top, bottom = adj.get_value(), adj.get_value() + adj.get_page_size()
        cr.select_font_face('sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(12)
        for i in range(max(0, int(top // THUMB_ROW)), min(len(self.sizes), int(bottom // THUMB_ROW) + 1)):
            y0 = i * THUMB_ROW
            if i == self.cur:
                cr.set_source_rgba(0.45, 0.65, 0.92, 0.35)
                cr.rectangle(6, y0 + 2, width - 12, THUMB_ROW - 4)
                cr.fill()
                cr.set_source_rgba(0.35, 0.58, 0.88, 0.9)
                cr.set_line_width(1)
                cr.rectangle(6.5, y0 + 2.5, width - 13, THUMB_ROW - 5)
                cr.stroke()
            tw, th = self.thumb_size(i)
            x, y = (width - tw) / 2, y0 + 8 + (THUMB_H - th) / 2
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(x, y, tw, th)
            cr.fill()
            entry = self.thumbs.get(i)
            if entry:
                self.thumbs.move_to_end(i)
                cr.set_source_surface(entry[2], x, y)
                cr.paint()
            cr.set_source_rgba(0, 0, 0, 0.4)
            cr.set_line_width(1)
            cr.rectangle(x + 0.5, y + 0.5, tw - 1, th - 1)
            cr.stroke()
            cr.set_source_rgb(0.17, 0.25, 0.37)
            label = str(i + 1)
            cr.move_to((width - cr.text_extents(label).x_advance) / 2, y0 + THUMB_ROW - 8)
            cr.show_text(label)
        self.schedule()

    def thumb_size(self, i):
        w, h = self.sizes[i]
        k = min(THUMB_W / w, THUMB_H / h)
        return max(1, round(w * k)), max(1, round(h * k))

    def thumb_click(self, _gesture, _n, _x, y):
        if self.doc and int(y // THUMB_ROW) < len(self.sizes):
            self.goto(int(y // THUMB_ROW))

    def sync_thumb_later(self):
        self.sync_thumb_scroll()
        return False

    def sync_thumb_scroll(self):
        if not self.side.get_visible() or not self.doc:
            return
        adj = self.side.get_vadjustment()
        top, bottom = self.cur * THUMB_ROW, (self.cur + 1) * THUMB_ROW
        if top < adj.get_value():
            adj.set_value(top)
        elif bottom > adj.get_value() + adj.get_page_size():
            adj.set_value(bottom - adj.get_page_size())

    # ---- the worker's jobs -------------------------------------------------------------------------------------------
    def schedule(self):
        """At most once per frame: tell the worker what the screen needs now, nearest the middle of the view first."""
        if not self.sched_id:
            self.sched_id = GLib.idle_add(self.schedule_now)

    def schedule_now(self):
        self.sched_id = 0
        if not self.doc or not self.renderer or not self.offsets:
            return False
        sf = self.area.get_scale_factor()
        busy = self.renderer.busy
        mid = self.vadj.get_value() + self.vadj.get_page_size() / 2
        vis = self.visible_pages()
        want = set(vis)
        if vis:
            want |= {max(0, vis[0] - 1), min(len(self.ps) - 1, vis[-1] + 1)}
        jobs = []
        for i in sorted(want, key=lambda i: abs(self.offsets[i] + self.ps[i][1] / 2 - mid)):
            pw, ph = self.ps[i]
            entry = self.cache.get(i)
            if (entry is None or entry[:2] != (pw, ph)) and not (busy and busy[:4] == ('p', i, pw, ph)):
                jobs.append(('p', i, pw, ph, sf))
        if self.side.get_visible():
            adj = self.side.get_vadjustment()
            lo, hi = int(adj.get_value() // THUMB_ROW), int((adj.get_value() + adj.get_page_size()) // THUMB_ROW) + 1
            for i in range(max(0, lo), min(len(self.sizes), hi + 1)):
                tw, th = self.thumb_size(i)
                if i not in self.thumbs and not (busy and busy[:2] == ('t', i)):
                    jobs.append(('t', i, tw, th, 1))
        self.renderer.set_jobs(jobs)
        return False

    def rendered(self, gen, job, surf):
        if gen != self.gen or surf is None:
            return False
        kind, i, pw, ph, _sf = job
        if kind == 't':
            self.thumbs[i] = (pw, ph, surf)
            while len(self.thumbs) > THUMB_CACHE:
                self.thumbs.popitem(last=False)
            self.thumbarea.queue_draw()
            return False
        old = self.cache.pop(i, None)
        if old:
            self.cache_bytes -= old[2].get_width() * old[2].get_height() * 4
        self.cache[i] = (pw, ph, surf)
        self.cache_bytes += surf.get_width() * surf.get_height() * 4
        keep = set(self.visible_pages())
        for k in list(self.cache):
            if self.cache_bytes <= PAGE_CACHE_BYTES:
                break
            if k not in keep and k != i:
                gone = self.cache.pop(k)
                self.cache_bytes -= gone[2].get_width() * gone[2].get_height() * 4
        self.area.queue_draw()
        self.schedule()  # the worker may have idled while this page was in flight
        return False

    # ---- controls ----------------------------------------------------------------------------------------------------
    def toggle_side(self, from_button=False):
        show = self.side_btn.get_active() if from_button else not self.side.get_visible()
        self.side.set_visible(show)
        self.quiet = True
        self.side_btn.set_active(show)
        self.quiet = False
        self.cfg['sidebar'] = show
        if self.doc:
            self.thumbarea.set_content_height(len(self.sizes) * THUMB_ROW)
            GLib.timeout_add(60, self.sync_thumb_later)  # once the sidebar has its size
            self.schedule()
        save_config(self.cfg)

    def sync_controls(self):
        has = bool(self.doc)
        self.quiet = True
        for b in (self.prev_btn, self.next_btn, self.in_btn, self.out_btn, self.width_btn, self.page_btn, self.print_btn,
                  self.find_btn):
            b.set_sensitive(has)
        self.pageentry.set_sensitive(has)
        self.width_btn.set_active(has and self.mode == 'width')
        self.page_btn.set_active(has and self.mode == 'page')
        self.quiet = False
        self.zoom_label.set_label(f'{round(self.zoom * 100)}%' if has else '')
        self.of_label.set_label(f'/ {len(self.sizes)}' if has else '/ –')
        if has:
            self.thumbarea.set_content_height(len(self.sizes) * THUMB_ROW)
        self.show_page_number()

    def show_page_number(self):
        self.pageentry.set_text(str(self.cur + 1) if self.doc else '')

    def page_entered(self, entry):
        try:
            self.goto(int(entry.get_text().strip()) - 1)
        except ValueError:
            self.show_page_number()
        self.area.grab_focus()

    def focus_page(self):
        if self.doc:
            self.pageentry.grab_focus()
            self.pageentry.select_region(0, -1)

    # ---- find --------------------------------------------------------------------------------------------------------
    def show_find(self):
        if not self.doc:
            return
        self.findbar.set_visible(True)
        self.entry.grab_focus()
        self.entry.select_region(0, -1)

    def hide_find(self):
        self.findbar.set_visible(False)
        self.hits, self.order, self.cur_hit = {}, [], -1
        self.search_id += 1
        self.area.queue_draw()
        self.area.grab_focus()

    def start_search(self, text):
        self.search_id += 1
        sid = self.search_id
        self.query = text
        self.hits, self.order, self.cur_hit = {}, [], -1
        self.count.set_label('')
        self.area.queue_draw()
        if not text or not self.doc:
            return
        state = {'page': 0, 'chosen': False}
        doc = self.doc

        def chunk():
            # Pages in small slices (about 8 ms) so typing and scrolling stay smooth while a long document is searched.
            if sid != self.search_id or doc is not self.doc:
                return False
            t0 = time.monotonic()
            n = len(self.sizes)
            while state['page'] < n and time.monotonic() - t0 < 0.008:
                i = state['page']
                state['page'] += 1
                rects = doc.get_page(i).find_text(text)
                if rects:
                    h = self.sizes[i][1]
                    # Poppler gives PDF points from the bottom-left corner; the view counts down from the top.
                    self.hits[i] = [(r.x1, h - r.y2, r.x2, h - r.y1) for r in rects]
                    self.order += [(i, k) for k in range(len(rects))]
            done = state['page'] >= n
            if not state['chosen'] and self.order and (done or self.order[-1][0] >= self.cur):
                state['chosen'] = True
                self.cur_hit = next((j for j, (p, _k) in enumerate(self.order) if p >= self.cur), 0)
                self.reveal_hit()
            self.update_count(done)
            self.area.queue_draw()
            return not done
        GLib.idle_add(chunk)

    def update_count(self, done):
        if self.order:
            where = f'{self.cur_hit + 1} of ' if self.cur_hit >= 0 else ''
            self.count.set_label(f'{where}{len(self.order)}{"" if done else "…"} found')
        else:
            self.count.set_label('No matches' if done else 'Searching…')

    def step_hit(self, d):
        if not self.order:
            if not self.findbar.get_visible():
                self.show_find()
            return
        self.cur_hit = (self.cur_hit + d) % len(self.order)
        self.reveal_hit()
        self.update_count(True)
        self.area.queue_draw()

    def reveal_hit(self):
        if self.cur_hit < 0:
            return
        i, k = self.order[self.cur_hit]
        s = self.zoom * PX_PER_PT
        _x1, y1, _x2, y2 = self.hits[i][k]
        top, page = self.offsets[i] + y1 * s, self.vadj.get_page_size()
        if top < self.vadj.get_value() + 30 or self.offsets[i] + y2 * s > self.vadj.get_value() + page - 30:
            self.vadj.set_value(max(0, top - page / 3))

    # ---- print -------------------------------------------------------------------------------------------------------
    def print_doc(self, export=None):
        """File > Print: GTK's own dialog (printers, page range, preview), every page scaled to fit inside the margins. `export`
        prints to that PDF without a dialog (used by checks)."""
        if not self.doc:
            return None
        doc = self.doc
        op = Gtk.PrintOperation(job_name=os.path.basename(self.path), n_pages=doc.get_n_pages(), embed_page_setup=True,
                                allow_async=export is None)
        op.set_unit(Gtk.Unit.POINTS)
        if self.page_setup:
            op.set_default_page_setup(self.page_setup)
        if self.print_settings:
            op.set_print_settings(self.print_settings)
        if export:
            op.set_export_filename(export)

        def request(_op, _ctx, n, setup):
            w, h = doc.get_page(n).get_size()  # a landscape page prints on landscape paper
            setup.set_orientation(Gtk.PageOrientation.LANDSCAPE if w > h else Gtk.PageOrientation.PORTRAIT)

        def draw(_op, ctx, n):
            page = doc.get_page(n)
            pw, ph = page.get_size()
            cr = ctx.get_cairo_context()
            w, h = ctx.get_width(), ctx.get_height()
            s = min(w / pw, h / ph)
            cr.translate((w - pw * s) / 2, (h - ph * s) / 2)
            cr.scale(s, s)
            page.render_for_printing(cr)

        def finished(_op, result):
            if result == Gtk.PrintOperationResult.APPLY:
                self.print_settings = _op.get_print_settings()
            self.page_setup = _op.get_default_page_setup()
        op.connect('request-page-setup', request)
        op.connect('draw-page', draw)
        op.connect('done', finished)
        try:
            op.run(Gtk.PrintOperationAction.EXPORT if export else Gtk.PrintOperationAction.PRINT_DIALOG, self.win)
        except GLib.Error as e:
            Gtk.AlertDialog(message='Could not print', detail=e.message).show(self.win)
        return op


if __name__ == '__main__':
    reader = Reader()
    mwx7ui.App('org.mwx7.reader', 'Reader', 'reader', (900, 700), CSS, reader.build).run_main()
