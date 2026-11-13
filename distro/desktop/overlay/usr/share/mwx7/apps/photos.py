"""Photos (native): the concept's Windows 7-style Photo Viewer for your Pictures folder (and MWX 7's sample photos):
previous/next (arrows, Home/End), zoom (wheel, fit / 100%, double-click) and pan by dragging, rotate (saved to the file:
lossless for JPEG when jpegtran is installed), slideshow with a fade, file info (with the date taken from EXIF when Pillow or
GExiv2 is there), crop with Save as copy, and Delete to the Trash with Undo. Opens a picture given to it, with its folder
around it."""
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk  # noqa: E402
import gi  # noqa: E402

gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Gsk', '4.0')
gi.require_version('Graphene', '1.0')
from gi.repository import GdkPixbuf, Graphene, Gsk  # noqa: E402

IMAGES = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.svg')
SAMPLES = '/usr/share/mwx7/web/media/pictures'
TRASH = os.path.join(GLib.get_user_data_dir(), 'Trash')
CSS = """
window.mwx7-photos > box { background: #1a2333; }
.ph-stage { background: radial-gradient(circle at 50% 40%, #2b3a52, #121a28 70%); }
.ph-name { padding: 3px 12px; border-radius: 999px; background: rgba(255,255,255,.75); color: #243a57; }
.ph-empty { color: rgba(255,255,255,.8); font-size: 14px; }
.ph-bar { padding: 8px 14px; border-top: 1px solid rgba(255,255,255,.35);
  background: linear-gradient(180deg, rgba(40,55,78,.95), rgba(18,28,44,.95) 50%, rgba(8,14,26,.98) 51%, rgba(22,34,52,.98)); }
.ph-bar button { color: #eef3f9; background: none; border: none; box-shadow: none; border-radius: 4px; padding: 6px; }
.ph-bar button:hover { background: linear-gradient(180deg, rgba(255,255,255,.28), rgba(255,255,255,.08)); box-shadow: inset 0 0 0 1px rgba(255,255,255,.35); }
.ph-bar button:checked { background: linear-gradient(180deg, rgba(120,190,255,.45), rgba(60,130,220,.25)); box-shadow: inset 0 0 0 1px rgba(160,210,255,.6); }
.ph-bar button.ph-show { min-width: 48px; min-height: 48px; padding: 0; border-radius: 999px; border: 1px solid #0b2a52;
  background: radial-gradient(circle at 50% 30%, #9ad3ff, #2f86e0 55%, #0d4f9c);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.6), 0 0 12px rgba(60,150,255,.45); }
.ph-bar button.ph-del:hover { background: linear-gradient(180deg, #ff9a8f, #d23b33); }
.ph-count { color: #b8c8de; margin-right: 6px; }
.ph-zoom { color: #b8c8de; min-width: 38px; }
.ph-bar separator { background: rgba(255,255,255,.22); min-width: 1px; margin: 8px 6px; }
window.ph-slideshow { background: #000000; }
.ph-info { min-width: 250px; padding: 14px 16px; background: rgba(12,20,34,.88); border-left: 1px solid rgba(255,255,255,.18); }
.ph-info-title { color: #ffffff; font-weight: 700; font-size: 14px; margin-bottom: 8px; }
.ph-info-k { color: #8fa6c4; font-size: 11px; margin-top: 8px; } .ph-info-v { color: #eef3f9; font-size: 12px; }
.ph-pill { padding: 5px 8px 5px 14px; border-radius: 999px; background: rgba(255,255,255,.88); color: #243a57; }
.ph-pill button { min-height: 0; padding: 3px 10px; border-radius: 999px; font-size: 12px; }
.ph-toast { padding: 6px 8px 6px 16px; border-radius: 999px; background: rgba(12,20,34,.92); color: #ffffff;
  border: 1px solid rgba(255,255,255,.25); }
.ph-toast button { min-height: 0; padding: 3px 12px; border-radius: 999px; font-size: 12px; color: #9ad3ff; background: none;
  border: none; box-shadow: none; font-weight: 700; }
.ph-toast button:hover { background: rgba(255,255,255,.15); }
"""


def pictures_dir():
    return GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) or os.path.expanduser('~/Pictures')


def list_images(folder):
    try:
        return sorted((os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(IMAGES)),
                      key=lambda p: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', p)])
    except OSError:
        return []


def human(n):
    for unit in ('bytes', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:,} bytes' if unit == 'bytes' else f'{n:.1f} {unit}'
        n /= 1024


def date_taken(path):
    """The EXIF date the picture was taken, when Pillow or GExiv2 happens to be installed; None otherwise (no new
    dependency: the row is simply left out)."""
    raw = None
    try:
        from PIL import Image  # noqa: PLC0415
        with Image.open(path) as im:
            ex = im.getexif()
            raw = ex.get_ifd(0x8769).get(36867) or ex.get(306)
    except Exception:  # noqa: BLE001 (no Pillow, or no EXIF in this file)
        pass
    if not raw:
        try:
            gi.require_version('GExiv2', '0.10')
            from gi.repository import GExiv2  # noqa: PLC0415
            md = GExiv2.Metadata()
            md.open_path(path)
            raw = md.try_get_tag_string('Exif.Photo.DateTimeOriginal') or md.try_get_tag_string('Exif.Image.DateTime')
        except Exception:  # noqa: BLE001
            return None
    try:
        return datetime.strptime(str(raw).strip(), '%Y:%m:%d %H:%M:%S').strftime('%-d %B %Y, %H:%M')
    except ValueError:
        return None


def rgba(r, g, b, a=1.0):
    c = Gdk.RGBA()
    c.red, c.green, c.blue, c.alpha = r, g, b, a
    return c


def trashed_name_of(orig):
    """After Gio trashed `orig`: the name it got in the Trash (the newest .trashinfo that points back at it)."""
    info_dir, best = os.path.join(TRASH, 'info'), (0, None)
    try:
        for n in os.listdir(info_dir):
            fp = os.path.join(info_dir, n)
            for line in open(fp, errors='replace'):
                if line.startswith('Path=') and urllib.parse.unquote(line[5:].strip()) == orig:
                    best = max(best, (os.path.getmtime(fp), n[:-len('.trashinfo')]))
    except OSError:
        pass
    return best[1]


class Viewer(Gtk.Widget):
    """The picture: zoom with the wheel (around the pointer), drag to pan, double-click toggles fit / 100%; in crop mode the
    drag edits the crop rectangle instead. It draws straight from a texture, so zooming never re-decodes anything."""
    __gtype_name__ = 'MwxPhotosViewer'
    MARGIN, MIN_SIDE = 20, 8

    def __init__(self):
        super().__init__(hexpand=True, vexpand=True)
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.pixbuf = self.texture = None
        self.iw = self.ih = 0
        self.fit, self.scale, self.ox, self.oy = True, 1.0, 0.0, 0.0
        self.crop_mode, self.crop = False, None  # crop: [left, top, right, bottom] in picture pixels
        self.on_zoom = self.on_crop = None
        self.px = self.py = 0.0
        self._pct, self._drag = None, None
        drag = Gtk.GestureDrag(button=1)
        drag.connect('drag-begin', self.drag_begin)
        drag.connect('drag-update', self.drag_update)
        drag.connect('drag-end', lambda *_: setattr(self, '_drag', None))
        self.add_controller(drag)
        click = Gtk.GestureClick(button=1)
        click.connect('pressed', lambda g, n, x, y: n == 2 and not self.crop_mode and self.toggle(x, y))
        self.add_controller(click)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', lambda c, dx, dy: self.zoom_at(1.15 ** -dy, self.px, self.py) or True)
        self.add_controller(scroll)
        motion = Gtk.EventControllerMotion()
        motion.connect('motion', self.moved)
        self.add_controller(motion)

    # ---- geometry ----------------------------------------------------------------------------------------------------
    def fit_scale(self):
        if not self.iw:
            return 1.0
        w, h = max(1, self.get_width() - 2 * self.MARGIN), max(1, self.get_height() - 2 * self.MARGIN)
        return min(1.0, w / self.iw, h / self.ih)

    def cur_scale(self):
        return self.fit_scale() if self.fit else self.scale

    def origin(self):
        s = self.cur_scale()
        return (self.get_width() / 2 + self.ox - self.iw * s / 2, self.get_height() / 2 + self.oy - self.ih * s / 2)

    def clamp(self):
        s = self.cur_scale()
        mx, my = max(0.0, (self.iw * s - self.get_width()) / 2), max(0.0, (self.ih * s - self.get_height()) / 2)
        self.ox, self.oy = max(-mx, min(mx, self.ox)), max(-my, min(my, self.oy))

    def pannable(self):
        s = self.cur_scale()
        return self.iw * s > self.get_width() or self.ih * s > self.get_height()

    def update_cursor(self):
        self.set_cursor_from_name('crosshair' if self.crop_mode else 'grab' if self.pannable() else None)

    def moved(self, _c, x, y):
        self.px, self.py = x, y

    # ---- what is shown -----------------------------------------------------------------------------------------------
    def set_pixbuf(self, pb):
        self.pixbuf = pb
        self.texture = Gdk.Texture.new_for_pixbuf(pb) if pb else None
        self.iw, self.ih = (pb.get_width(), pb.get_height()) if pb else (0, 0)
        self.fit, self.ox, self.oy = True, 0.0, 0.0
        self.set_crop_mode(False)
        self.update_cursor()
        self.queue_draw()

    def percent(self):
        return round(self.cur_scale() * 100) if self.iw else 0

    # ---- zoom --------------------------------------------------------------------------------------------------------
    def zoom_at(self, factor, x, y):
        if not self.iw:
            return
        s0 = self.cur_scale()
        s1 = max(0.02, min(32.0, s0 * factor))
        cx, cy = self.get_width() / 2, self.get_height() / 2
        ix, iy = (x - cx - self.ox) / s0 + self.iw / 2, (y - cy - self.oy) / s0 + self.ih / 2  # the picture point under the pointer
        self.scale, self.fit = s1, False
        self.ox, self.oy = x - cx - (ix - self.iw / 2) * s1, y - cy - (iy - self.ih / 2) * s1
        if abs(s1 - self.fit_scale()) < 0.003:
            self.fit, self.ox, self.oy = True, 0.0, 0.0
        self.clamp()
        self.update_cursor()
        self.queue_draw()

    def set_fit(self):
        self.fit, self.ox, self.oy = True, 0.0, 0.0
        self.update_cursor()
        self.queue_draw()

    def set_actual(self, x=None, y=None):
        x = self.get_width() / 2 if x is None else x
        y = self.get_height() / 2 if y is None else y
        self.zoom_at(1.0 / max(self.cur_scale(), 1e-6), x, y)
        self.fit = False  # at "100%" even when the picture is smaller than the window

    def toggle(self, x=None, y=None):
        if self.fit and self.fit_scale() < 0.999:
            self.set_actual(x, y)
        else:
            self.set_fit()

    # ---- crop --------------------------------------------------------------------------------------------------------
    def set_crop_mode(self, on):
        self.crop_mode = bool(on and self.iw)
        if self.crop_mode:
            self.crop = [self.iw * .1, self.ih * .1, self.iw * .9, self.ih * .9]
        else:
            self.crop = None
        self.update_cursor()
        self.queue_draw()
        if self.on_crop:
            self.on_crop()

    def crop_screen(self):
        x, y = self.origin()
        s = self.cur_scale()
        l, t, r, b = self.crop
        return x + l * s, y + t * s, x + r * s, y + b * s

    def hit(self, sx, sy):
        """Which part of the crop rectangle is under the pointer: a handle ('l', 'tr'...), 'move', or None."""
        l, t, r, b = self.crop_screen()
        near = 9
        xs = [(c, v) for c, v in (('l', l), ('r', r), ('', (l + r) / 2)) if abs(sx - v) <= near]
        ys = [(c, v) for c, v in (('t', t), ('b', b), ('', (t + b) / 2)) if abs(sy - v) <= near]
        if xs and ys and (xs[0][0] or ys[0][0]):
            return xs[0][0] + ys[0][0]
        return 'move' if l < sx < r and t < sy < b else None

    def drag_begin(self, _g, x, y):
        if self.crop_mode:
            sx, sy = x, y
            ox, oy = self.origin()
            s = self.cur_scale()
            ip = (max(0.0, min(self.iw, (sx - ox) / s)), max(0.0, min(self.ih, (sy - oy) / s)))
            self._drag = {'mode': self.hit(sx, sy) or 'new', 'rect': list(self.crop), 'start': ip}
        else:
            self._drag = {'mode': 'pan', 'ox': self.ox, 'oy': self.oy}

    def drag_update(self, _g, dx, dy):
        d = self._drag
        if not d:
            return
        if d['mode'] == 'pan':
            if self.pannable():
                self.ox, self.oy = d['ox'] + dx, d['oy'] + dy
                self.clamp()
                self.queue_draw()
            return
        s = self.cur_scale()
        dx, dy = dx / s, dy / s
        l, t, r, b = d['rect']
        iw, ih, m = self.iw, self.ih, self.MIN_SIDE
        mode = d['mode']
        if mode == 'new':
            x0, y0 = d['start']
            x1, y1 = max(0.0, min(iw, x0 + dx)), max(0.0, min(ih, y0 + dy))
            l, r, t, b = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        elif mode == 'move':
            w, h = r - l, b - t
            l = max(0.0, min(iw - w, l + dx))
            t = max(0.0, min(ih - h, t + dy))
            r, b = l + w, t + h
        else:
            if 'l' in mode:
                l = max(0.0, min(r - m, l + dx))
            if 'r' in mode:
                r = min(float(iw), max(l + m, r + dx))
            if 't' in mode:
                t = max(0.0, min(b - m, t + dy))
            if 'b' in mode:
                b = min(float(ih), max(t + m, b + dy))
        self.crop = [l, t, r, b]
        self.queue_draw()
        if self.on_crop:
            self.on_crop()

    def crop_box(self):
        """The crop as whole picture pixels (x, y, width, height), at least 1 × 1."""
        l, t, r, b = (round(v) for v in self.crop)
        l, t = max(0, min(self.iw - 1, l)), max(0, min(self.ih - 1, t))
        return l, t, max(1, min(self.iw, r) - l), max(1, min(self.ih, b) - t)

    # ---- drawing -----------------------------------------------------------------------------------------------------
    def do_snapshot(self, snap):
        if not self.texture:
            return
        w, h = self.get_width(), self.get_height()
        s = self.cur_scale()
        x, y = self.origin()
        x, y = round(x), round(y)
        flt = Gsk.ScalingFilter.TRILINEAR if s < 1 else Gsk.ScalingFilter.NEAREST if s >= 3 else Gsk.ScalingFilter.LINEAR
        snap.append_scaled_texture(self.texture, flt, Graphene.Rect().init(x, y, self.iw * s, self.ih * s))
        if self.crop_mode and self.crop:
            l, t, r, b = (round(v) for v in self.crop_screen())  # whole pixels: no light seams around the shade
            shade = rgba(0, 0, 0, .55)
            for rx, ry, rw, rh in ((0, 0, w, t), (0, b, w, h - b), (0, t, l, b - t), (r, t, w - r, b - t)):
                if rw > 0 and rh > 0:
                    snap.append_color(shade, Graphene.Rect().init(rx, ry, rw, rh))
            white, faint = rgba(1, 1, 1, .95), rgba(1, 1, 1, .35)
            for k in (1, 2):  # rule of thirds
                snap.append_color(faint, Graphene.Rect().init(l + (r - l) * k / 3, t, 1, b - t))
                snap.append_color(faint, Graphene.Rect().init(l, t + (b - t) * k / 3, r - l, 1))
            for rx, ry, rw, rh in ((l, t, r - l, 1), (l, b - 1, r - l, 1), (l, t, 1, b - t), (r - 1, t, 1, b - t)):
                snap.append_color(white, Graphene.Rect().init(rx, ry, rw, rh))
            for hx in (l, (l + r) / 2, r):
                for hy in (t, (t + b) / 2, b):
                    if (hx, hy) != ((l + r) / 2, (t + b) / 2):
                        snap.append_color(white, Graphene.Rect().init(hx - 3, hy - 3, 7, 7))
        pct = self.percent()
        if pct != self._pct:
            self._pct = pct
            if self.on_zoom:
                GLib.idle_add(lambda: self.on_zoom() and False)


class Photos:
    def __init__(self):
        self.pics, self.index, self.rot, self.orient = [], -1, 0, 1
        self.pixbuf = None
        self.trashed, self.consented, self.declined = [], set(), set()
        self.toast_timer = 0

    # ---- window ------------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-photos')
        app.on_open = lambda files: self.open_path(files[0].get_path())
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('File', [('Open Pictures Folder', 'folder', lambda: Gio.AppInfo.launch_default_for_uri(
                Gio.File.new_for_path(pictures_dir()).get_uri(), None)),
                ('Save Cropped Copy…', 'savecopy', self.crop_save), None,
                ('Move to Trash', 'trash', self.remove), ('Undo Move to Trash', 'undotrash', self.undo_delete)]),
            ('View', [('Slideshow', 'slideshow', self.slideshow), None,
                      ('Fit to Window', 'fit', lambda: self.viewer.set_fit()),
                      ('Actual Size', 'actual', lambda: self.viewer.set_actual()),
                      ('Zoom In', 'zoomin', lambda: self.zoom_step(1.25)), ('Zoom Out', 'zoomout', lambda: self.zoom_step(0.8)),
                      None, ('File Info', 'info', self.toggle_info)]),
            ('Edit', [('Rotate Counterclockwise', 'rotl', lambda: self.rotate(90)),
                      ('Rotate Clockwise', 'rotr', lambda: self.rotate(-90)), None, ('Crop', 'crop', self.toggle_crop)]),
        ]))
        for action, accels in (('slideshow', ['F11']), ('fit', ['<Ctrl>0']), ('actual', ['<Ctrl>1']),
                               ('zoomin', ['<Ctrl>plus', '<Ctrl>equal']), ('zoomout', ['<Ctrl>minus']),
                               ('info', ['<Ctrl>i']), ('rotl', ['<Ctrl>comma']), ('rotr', ['<Ctrl>period']),
                               ('crop', ['<Ctrl>k']), ('undotrash', ['<Ctrl>z']), ('savecopy', ['<Ctrl>s'])):
            app.set_accels_for_action('app.' + action, accels)

        stage = Gtk.Overlay(vexpand=True)
        stage.add_css_class('ph-stage')
        self.viewer = Viewer()
        self.viewer.on_zoom = self.zoom_changed
        self.viewer.on_crop = self.crop_changed
        stage.set_child(self.viewer)
        self.name = Gtk.Label(halign=Gtk.Align.CENTER, valign=Gtk.Align.START, margin_top=10, visible=False, can_target=False)
        self.name.add_css_class('ph-name')
        stage.add_overlay(self.name)
        self.empty = Gtk.Label(label='No pictures yet.\nPut photos in your Pictures folder.',
                               justify=Gtk.Justification.CENTER, visible=False, can_target=False)
        self.empty.add_css_class('ph-empty')
        stage.add_overlay(self.empty)

        # Crop tool: a pill with the size and the two ways out.
        self.cropbar = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, valign=Gtk.Align.START, margin_top=10, visible=False)
        self.cropbar.add_css_class('ph-pill')
        self.cropsize = Gtk.Label()
        self.cropbar.append(self.cropsize)
        save = Gtk.Button(label='Save as copy…', focusable=False)
        save.connect('clicked', lambda *_: self.crop_save())
        cancel = Gtk.Button(label='Cancel', focusable=False)
        cancel.connect('clicked', lambda *_: self.toggle_crop())
        self.cropbar.append(save)
        self.cropbar.append(cancel)
        stage.add_overlay(self.cropbar)

        self.toast = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER, valign=Gtk.Align.END, margin_bottom=14, visible=False)
        self.toast.add_css_class('ph-toast')
        self.toast_label = Gtk.Label()
        self.toast_btn = Gtk.Button(label='Undo', focusable=False)
        self.toast_btn.connect('clicked', lambda *_: self.toast_action and self.toast_action())
        self.toast.append(self.toast_label)
        self.toast.append(self.toast_btn)
        self.toast_action = None
        stage.add_overlay(self.toast)

        hover = Gtk.EventControllerMotion()
        hover.connect('enter', lambda *_: self.name.set_visible(bool(self.pics) and not self.viewer.crop_mode))
        hover.connect('leave', lambda *_: self.name.set_visible(False))
        stage.add_controller(hover)

        self.info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.info.add_css_class('ph-info')
        self.reveal = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT, reveal_child=False)
        self.reveal.set_child(self.info)
        middle = Gtk.Box(vexpand=True)
        middle.append(stage)
        stage.set_hexpand(True)
        middle.append(self.reveal)
        root.append(middle)

        bar = Gtk.CenterBox()
        bar.add_css_class('ph-bar')
        left = Gtk.Box(spacing=4)
        self.count = Gtk.Label()
        self.count.add_css_class('ph-count')
        self.zoom_lbl = Gtk.Label(xalign=1)
        self.zoom_lbl.add_css_class('ph-zoom')
        left.append(self.count)
        left.append(self.zoom_lbl)
        self.zoom_btn = self.button('zoom-original-symbolic', 'Fit to window / actual size', lambda *_: self.viewer.toggle())
        left.append(self.zoom_btn)
        self.info_btn = Gtk.ToggleButton(icon_name='dialog-information-symbolic', tooltip_text='File info', focusable=False,
                                         valign=Gtk.Align.CENTER)
        self.info_btn.connect('toggled', lambda b: self.reveal.set_reveal_child(b.get_active()) or self.update_info())
        left.append(self.info_btn)
        self.crop_btn = Gtk.ToggleButton(label='Crop', tooltip_text='Crop', focusable=False, valign=Gtk.Align.CENTER)
        self.crop_btn.connect('toggled', lambda b: self.set_crop(b.get_active()))
        left.append(self.crop_btn)
        show = self.button('media-playback-start-symbolic', 'Play slideshow', lambda *_: self.slideshow())
        show.add_css_class('ph-show')
        # Previous and next flank the slideshow button, as in Windows Photo Viewer, instead of sitting on opposite sides.
        mid = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        mid.append(self.button('go-previous-symbolic', 'Previous', lambda *_: self.step(-1)))
        mid.append(show)
        mid.append(self.button('go-next-symbolic', 'Next', lambda *_: self.step(1)))
        right = Gtk.Box(spacing=4)
        right.append(self.button('object-rotate-left-symbolic', 'Rotate counterclockwise', lambda *_: self.rotate(90)))
        right.append(self.button('object-rotate-right-symbolic', 'Rotate clockwise', lambda *_: self.rotate(-90)))
        right.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        d = self.button('user-trash-symbolic', 'Delete', lambda *_: self.remove())
        d.add_css_class('ph-del')
        right.append(d)
        bar.set_start_widget(left)
        bar.set_center_widget(mid)
        bar.set_end_widget(right)
        root.append(bar)

        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.on_key)
        win.add_controller(keys)

        if app.files:
            GLib.idle_add(lambda: self.open_path(app.files[0].get_path()) and False)
        else:
            self.pics = list_images(pictures_dir()) or list_images(SAMPLES)
            self.show(0 if self.pics else -1)
        return root

    def button(self, icon, tip, fn):
        b = Gtk.Button(icon_name=icon, tooltip_text=tip, focusable=False, valign=Gtk.Align.CENTER)
        b.connect('clicked', fn)
        return b

    def on_key(self, _c, keyval, _code, state):
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        name = Gdk.keyval_name(keyval) or ''
        if name in ('Left', 'Page_Up'):
            self.step(-1)
        elif name in ('Right', 'Page_Down'):
            self.step(1)
        elif name == 'Home':
            self.show(0)
        elif name == 'End':
            self.show(len(self.pics) - 1)
        elif name == 'Delete':
            self.remove()
        elif name in ('plus', 'equal', 'KP_Add'):
            self.zoom_step(1.25)
        elif name in ('minus', 'KP_Subtract'):
            self.zoom_step(0.8)
        elif name == 'Escape' and self.viewer.crop_mode:
            self.set_crop(False)
        else:
            return False
        return True

    def zoom_step(self, f):
        self.viewer.zoom_at(f, self.viewer.get_width() / 2, self.viewer.get_height() / 2)

    def zoom_changed(self):
        self.zoom_lbl.set_label(f'{self.viewer.percent()}%' if self.pics else '')
        self.zoom_btn.set_icon_name('zoom-original-symbolic' if self.viewer.fit else 'zoom-fit-best-symbolic')
        self.zoom_btn.set_tooltip_text('Actual size' if self.viewer.fit else 'Fit to window')

    # ---- pictures ----------------------------------------------------------------------------------------------------
    def open_path(self, path):
        mwx7ui.remember(path)
        self.pics = list_images(os.path.dirname(path)) or [path]
        self.show(self.pics.index(path) if path in self.pics else 0)
        return False

    def show(self, i):
        self.empty.set_visible(not self.pics)
        if not self.pics:
            self.index = -1
            self.viewer.set_pixbuf(None)
            self.count.set_label('')
            self.zoom_lbl.set_label('')
            self.app.set_title('Photos')
            self.update_info()
            return
        self.index = i % len(self.pics)
        self.rot, self.orient = 0, 1
        path = self.pics[self.index]
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(path)
            self.orient = int(pb.get_option('orientation') or 1)
            self.pixbuf = pb.apply_embedded_orientation()
        except (GLib.Error, ValueError):
            self.pixbuf = None
        self.crop_btn.set_active(False)
        self.paint()
        name = os.path.basename(path)
        self.name.set_label(name)
        self.count.set_label(f'{self.index + 1} of {len(self.pics)}')
        self.app.set_title(f'{name} - Photos')
        self.update_info()

    def paint(self):
        if not self.pixbuf:
            self.viewer.set_pixbuf(None)
            return
        pb = self.pixbuf.rotate_simple(GdkPixbuf.PixbufRotation(self.rot % 360)) if self.rot % 360 else self.pixbuf
        self.viewer.set_pixbuf(pb)
        self.zoom_changed()

    def step(self, d):
        if self.pics:
            self.show(self.index + d)

    # ---- rotate: saved to the file ------------------------------------------------------------------------------------
    def rotate(self, deg):
        if self.index < 0 or not self.pixbuf:
            return
        self.rot = (self.rot + deg) % 360
        self.paint()
        self.persist_rotation()

    def persist_rotation(self):
        """Writes the turned picture back: lossless for JPEG with jpegtran (when no EXIF orientation tag is in the way);
        otherwise a JPEG is re-encoded, after asking once; PNG/BMP/TIFF are lossless to re-encode. Other formats only turn
        on screen."""
        path, cw = self.pics[self.index], (-self.rot) % 360
        ext = os.path.splitext(path)[1].lower()
        if not cw or not os.access(path, os.W_OK):
            return
        if ext in ('.jpg', '.jpeg'):
            if self.orient == 1 and shutil.which('jpegtran') and self.lossless(path, cw):
                return self.reload(path)
            if path in self.declined:
                return
            if path in self.consented:
                return self.reencode(path)
            dlg = Gtk.AlertDialog(
                message='Save the rotated picture?',
                detail='This computer has no lossless JPEG rotation tool (jpegtran), or the picture carries a camera '
                       'orientation tag. Saving re-compresses it (a small loss of quality) and may drop details such as '
                       'the date taken.',
                buttons=['Re-save rotated', 'Only turn the view'], default_button=1, cancel_button=1)

            def done(d, res):
                try:
                    ok = d.choose_finish(res) == 0
                except GLib.Error:
                    ok = False
                (self.consented if ok else self.declined).add(path)
                if ok:
                    self.reencode(path)
            dlg.choose(self.win, None, done)
        elif ext in ('.png', '.bmp', '.tif', '.tiff'):
            self.reencode(path)

    def lossless(self, path, cw):
        tmp = path + '.mwx7-tmp'
        try:
            subprocess.run(['jpegtran', '-perfect', '-copy', 'all', '-rotate', str(cw), '-outfile', tmp, path],
                           check=True, capture_output=True, timeout=120)
            self.replace_keep_time(tmp, path)
            return True
        except (OSError, subprocess.SubprocessError):
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    @staticmethod
    def replace_keep_time(tmp, path):
        st = os.stat(path)
        os.replace(tmp, path)
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))

    def reencode(self, path):
        ext, tmp = os.path.splitext(path)[1].lower(), path + '.mwx7-tmp'
        fmt = {'.jpg': 'jpeg', '.jpeg': 'jpeg', '.png': 'png', '.bmp': 'bmp', '.tif': 'tiff', '.tiff': 'tiff'}[ext]
        try:
            pb = self.pixbuf.rotate_simple(GdkPixbuf.PixbufRotation(self.rot % 360))
            if fmt == 'jpeg':
                pb.savev(tmp, fmt, ['quality'], ['93'])
            else:
                pb.savev(tmp, fmt, [], [])
            self.replace_keep_time(tmp, path)
        except (GLib.Error, OSError) as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return self.alert('The rotated picture could not be saved.', str(e))
        self.reload(path)

    def reload(self, path):
        if path in self.pics:
            self.show(self.pics.index(path))

    def alert(self, msg, detail=''):
        Gtk.AlertDialog(message=msg, detail=detail).show(self.win)

    # ---- info panel --------------------------------------------------------------------------------------------------
    def toggle_info(self):
        self.info_btn.set_active(not self.info_btn.get_active())

    def update_info(self):
        if not self.reveal.get_reveal_child():
            return
        while (c := self.info.get_first_child()):
            self.info.remove(c)
        title = Gtk.Label(label='File info', xalign=0)
        title.add_css_class('ph-info-title')
        self.info.append(title)
        if self.index < 0:
            return
        path = self.pics[self.index]
        rows = [('Name', os.path.basename(path))]
        try:
            st = os.stat(path)
            kind = Gio.content_type_get_description(Gio.content_type_guess(path, None)[0])
            rows.append(('Type', kind))
            rows.append(('Size', f'{human(st.st_size)}  ({st.st_size:,} bytes)' if st.st_size >= 1024 else human(st.st_size)))
            if self.pixbuf:
                rows.append(('Dimensions', f'{self.pixbuf.get_width()} × {self.pixbuf.get_height()} pixels'))
            taken = date_taken(path)
            if taken:
                rows.append(('Date taken', taken))
            rows.append(('Modified', datetime.fromtimestamp(st.st_mtime).strftime('%-d %B %Y, %H:%M')))
        except OSError:
            pass
        rows.append(('Folder', os.path.dirname(path)))
        for k, v in rows:
            kl, vl = Gtk.Label(label=k, xalign=0), Gtk.Label(label=v, xalign=0, wrap=True, wrap_mode=2, selectable=True,
                                                             max_width_chars=28)
            kl.add_css_class('ph-info-k')
            vl.add_css_class('ph-info-v')
            self.info.append(kl)
            self.info.append(vl)

    # ---- crop --------------------------------------------------------------------------------------------------------
    def toggle_crop(self):
        self.crop_btn.set_active(not self.crop_btn.get_active())

    def set_crop(self, on):
        if on and not self.pixbuf:
            return self.crop_btn.set_active(False)
        if on == self.viewer.crop_mode:
            return
        self.viewer.set_crop_mode(on)
        self.cropbar.set_visible(self.viewer.crop_mode)
        self.name.set_visible(False)

    def crop_changed(self):
        if self.viewer.crop_mode and self.viewer.crop:
            _x, _y, w, h = self.viewer.crop_box()
            self.cropsize.set_label(f'Crop  {w} × {h}')
        elif self.crop_btn.get_active():
            self.crop_btn.set_active(False)
        self.cropbar.set_visible(self.viewer.crop_mode)

    def crop_save(self):
        if not self.viewer.crop_mode or not self.viewer.pixbuf:
            return self.show_toast('Choose Crop first, then Save as copy.')
        x, y, w, h = self.viewer.crop_box()
        sub = self.viewer.pixbuf.new_subpixbuf(x, y, w, h).copy()
        src = self.pics[self.index]
        stem, ext = os.path.splitext(os.path.basename(src))
        dlg = mwx7ui.FileDialog(title='Save as copy', initial_folder=Gio.File.new_for_path(os.path.dirname(src)),
                                initial_name=f'{stem} - cropped{ext if ext.lower() in IMAGES else ".png"}')

        def done(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            dest = f.get_path()
            e = os.path.splitext(dest)[1].lower()
            fmt = {'.jpg': 'jpeg', '.jpeg': 'jpeg', '.png': 'png', '.bmp': 'bmp', '.tif': 'tiff', '.tiff': 'tiff'}.get(e)
            if not fmt:
                dest, fmt = dest + '.png', 'png'
            try:
                sub.savev(dest, fmt, ['quality'], ['93']) if fmt == 'jpeg' else sub.savev(dest, fmt, [], [])
            except GLib.Error as err:
                return self.alert('The copy could not be saved.', str(err))
            cur = self.pics[self.index]
            if os.path.dirname(dest) == os.path.dirname(cur):
                self.pics = list_images(os.path.dirname(cur))
                self.index = self.pics.index(cur) if cur in self.pics else 0
                self.count.set_label(f'{self.index + 1} of {len(self.pics)}')
            self.set_crop(False)
            self.crop_btn.set_active(False)
            self.show_toast(f'Saved {os.path.basename(dest)}')
        dlg.save(self.win, None, done)

    # ---- delete / undo -----------------------------------------------------------------------------------------------
    def show_toast(self, text, action=None, label='Undo', secs=8):
        self.toast_label.set_label(text)
        self.toast_btn.set_label(label)
        self.toast_btn.set_visible(bool(action))
        self.toast_action = action
        self.toast.set_visible(True)
        if self.toast_timer:
            GLib.source_remove(self.toast_timer)
        self.toast_timer = GLib.timeout_add_seconds(secs, self.hide_toast)

    def hide_toast(self):
        self.toast_timer = 0
        self.toast.set_visible(False)
        return False

    def remove(self):
        if self.index < 0:
            return
        path = self.pics[self.index]
        if path.startswith(SAMPLES):
            return self.alert('This is one of MWX 7’s sample photos.', 'Sample photos can’t be deleted.')
        try:
            Gio.File.new_for_path(path).trash(None)
        except GLib.Error as e:
            return self.alert('This picture could not be moved to the Trash.', e.message)
        self.trashed.append((path, trashed_name_of(path)))
        i = self.index
        self.pics.remove(path)
        self.show(min(i, len(self.pics) - 1) if self.pics else -1)
        self.show_toast(f'“{os.path.basename(path)}” moved to the Trash', self.undo_delete)

    def undo_delete(self):
        if not self.trashed:
            return
        path, name = self.trashed.pop()
        info = os.path.join(TRASH, 'info', f'{name}.trashinfo')
        src = os.path.join(TRASH, 'files', name or '')
        try:
            if not name or not os.path.lexists(src):
                raise OSError('It is no longer in the Trash.')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            dest, n = path, 1
            while os.path.lexists(dest):  # something new took its name meanwhile
                dest = f'{os.path.splitext(path)[0]} ({n}){os.path.splitext(path)[1]}'
                n += 1
            shutil.move(src, dest)
            if os.path.exists(info):
                os.remove(info)
        except OSError as e:
            return self.alert('This could not be undone.', str(e))
        folder = os.path.dirname(dest)
        if self.pics and os.path.dirname(self.pics[0]) != folder:
            self.pics = []
        self.pics = list_images(folder)
        self.show(self.pics.index(dest) if dest in self.pics else 0)
        self.hide_toast()
        self.show_toast(f'Restored “{os.path.basename(dest)}”')

    # ---- slideshow ---------------------------------------------------------------------------------------------------
    def slideshow(self):
        """Full screen, a picture every four seconds with a fade between them; a click or Esc ends it, the arrows move on."""
        if not self.pics:
            return
        try:
            fade = mwx7ui.base.ini_get('mwx7-animate', 'level', 'full') != 'off'
        except Exception:  # noqa: BLE001
            fade = True
        w = Gtk.Window(transient_for=self.win)
        w.add_css_class('ph-slideshow')
        top = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN)
        under = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, opacity=0.0, can_target=False)
        ov = Gtk.Overlay()
        ov.set_child(top)
        ov.add_overlay(under)
        w.set_child(ov)
        st = {'i': self.index, 'timer': 0, 'tick': 0, 'paused': False}

        def texture():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(self.pics[st['i'] % len(self.pics)]).apply_embedded_orientation()
                return Gdk.Texture.new_for_pixbuf(pb)
            except GLib.Error:
                return None

        def settle():
            if st['tick']:
                w.remove_tick_callback(st['tick'])
                st['tick'] = 0
                top.set_paintable(under.get_paintable())
                under.set_opacity(0.0)

        def go(delta):
            settle()
            st['i'] += delta
            tex = texture()
            if not fade or not top.get_paintable():
                top.set_paintable(tex)
                return
            under.set_paintable(tex)
            t0 = [None]

            def tick(wd, clock):
                now = clock.get_frame_time()
                t0[0] = t0[0] or now
                t = min(1.0, (now - t0[0]) / 700000)
                under.set_opacity(t * t * (3 - 2 * t))  # smoothstep
                if t >= 1.0:
                    st['tick'] = 0
                    top.set_paintable(under.get_paintable())
                    under.set_opacity(0.0)
                    return False
                return True
            st['tick'] = w.add_tick_callback(tick)

        def auto():
            if not st['paused']:
                go(1)
            return True

        def restart():
            if st['timer']:
                GLib.source_remove(st['timer'])
            st['timer'] = GLib.timeout_add_seconds(4, auto)

        def end(*_):
            settle()
            if st['timer']:
                GLib.source_remove(st['timer'])
                st['timer'] = 0
            w.destroy()
            self.show(st['i'])

        def key(_c, keyval, _code, _state):
            name = Gdk.keyval_name(keyval)
            if name == 'Escape':
                end()
            elif name in ('Right', 'Down', 'Page_Down'):
                go(1)
                restart()
            elif name in ('Left', 'Up', 'Page_Up'):
                go(-1)
                restart()
            elif name == 'space':
                st['paused'] = not st['paused']
            else:
                return False
            return True
        click = Gtk.GestureClick()
        click.connect('pressed', end)
        w.add_controller(click)
        kc = Gtk.EventControllerKey()
        kc.connect('key-pressed', key)
        w.add_controller(kc)
        top.set_paintable(texture())
        restart()
        w.fullscreen()
        w.present()


if __name__ == '__main__':
    photos = Photos()
    mwx7ui.App('org.mwx7.photos', 'Photos', 'photos', (860, 620), CSS, photos.build).run_main()
