"""Photos (native): the concept's Windows 7-style Photo Viewer for your Pictures folder (and MWX 7's sample photos):
previous/next, actual size, rotate, slideshow, delete to Trash. Opens a picture given to it, with its folder around it."""
import os
import re
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk  # noqa: E402
import gi  # noqa: E402

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf  # noqa: E402

IMAGES = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.svg')
SAMPLES = '/usr/share/mwx7/web/media/pictures'
CSS = """
window.mwx7-photos > box { background: #1a2333; }
.ph-stage { background: radial-gradient(circle at 50% 40%, #2b3a52, #121a28 70%); }
.ph-name { padding: 3px 12px; border-radius: 999px; background: rgba(255,255,255,.75); color: #243a57; }
.ph-empty { color: rgba(255,255,255,.8); font-size: 14px; }
.ph-bar { padding: 8px 14px; border-top: 1px solid rgba(255,255,255,.35);
  background: linear-gradient(180deg, rgba(40,55,78,.95), rgba(18,28,44,.95) 50%, rgba(8,14,26,.98) 51%, rgba(22,34,52,.98)); }
.ph-bar button { color: #eef3f9; background: none; border: none; box-shadow: none; border-radius: 4px; padding: 6px; }
.ph-bar button:hover { background: linear-gradient(180deg, rgba(255,255,255,.28), rgba(255,255,255,.08)); box-shadow: inset 0 0 0 1px rgba(255,255,255,.35); }
.ph-bar button.ph-show { min-width: 48px; min-height: 48px; padding: 0; border-radius: 999px; border: 1px solid #0b2a52;
  background: radial-gradient(circle at 50% 30%, #9ad3ff, #2f86e0 55%, #0d4f9c);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.6), 0 0 12px rgba(60,150,255,.45); }
.ph-bar button.ph-del:hover { background: linear-gradient(180deg, #ff9a8f, #d23b33); }
.ph-count { color: #b8c8de; margin-right: 6px; }
window.ph-slideshow { background: #000000; }
"""


def pictures_dir():
    return GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) or os.path.expanduser('~/Pictures')


def list_images(folder):
    try:
        return sorted((os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(IMAGES)),
                      key=lambda p: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', p)])
    except OSError:
        return []


class Photos:
    def __init__(self):
        self.pics, self.index, self.rot, self.actual = [], -1, 0, False
        self.pixbuf = None

    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-photos')
        app.on_open = lambda files: self.open_path(files[0].get_path())
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('File', [('Open Pictures Folder', 'folder', lambda: Gio.AppInfo.launch_default_for_uri(
                Gio.File.new_for_path(pictures_dir()).get_uri(), None)), None,
                ('Move to Trash', 'trash', self.remove)]),
            ('View', [('Slideshow', 'slideshow', self.slideshow), ('Fit to Window / Actual Size', 'zoom', self.toggle_zoom),
                      None, ('Rotate Counterclockwise', 'rotl', lambda: self.rotate(90)),
                      ('Rotate Clockwise', 'rotr', lambda: self.rotate(-90))]),
        ]))
        stage = Gtk.Overlay(vexpand=True)
        stage.add_css_class('ph-stage')
        self.scroll = Gtk.ScrolledWindow()
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.SCALE_DOWN, can_shrink=True)
        self.picture.set_margin_top(20)
        self.picture.set_margin_bottom(20)
        self.picture.set_margin_start(20)
        self.picture.set_margin_end(20)
        self.scroll.set_child(self.picture)
        stage.set_child(self.scroll)
        self.name = Gtk.Label(halign=Gtk.Align.CENTER, valign=Gtk.Align.START, margin_top=10, visible=False)
        self.name.add_css_class('ph-name')
        stage.add_overlay(self.name)
        self.empty = Gtk.Label(label='No pictures yet.\nPut photos in your Pictures folder.',
                               justify=Gtk.Justification.CENTER, visible=False)
        self.empty.add_css_class('ph-empty')
        stage.add_overlay(self.empty)
        hover = Gtk.EventControllerMotion()
        hover.connect('enter', lambda *_: self.name.set_visible(bool(self.pics)))
        hover.connect('leave', lambda *_: self.name.set_visible(False))
        stage.add_controller(hover)
        root.append(stage)

        bar = Gtk.CenterBox()
        bar.add_css_class('ph-bar')
        left = Gtk.Box(spacing=4)
        self.count = Gtk.Label()
        self.count.add_css_class('ph-count')
        left.append(self.count)
        left.append(self.button('go-previous-symbolic', 'Previous', lambda *_: self.step(-1)))
        self.zoom_btn = self.button('zoom-original-symbolic', 'Actual size', lambda *_: self.toggle_zoom())
        left.append(self.zoom_btn)
        show = self.button('media-playback-start-symbolic', 'Play slideshow', lambda *_: self.slideshow())
        show.add_css_class('ph-show')
        right = Gtk.Box(spacing=4)
        right.append(self.button('object-rotate-left-symbolic', 'Rotate counterclockwise', lambda *_: self.rotate(90)))
        right.append(self.button('object-rotate-right-symbolic', 'Rotate clockwise', lambda *_: self.rotate(-90)))
        right.append(self.button('go-next-symbolic', 'Next', lambda *_: self.step(1)))
        right.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        d = self.button('user-trash-symbolic', 'Delete', lambda *_: self.remove())
        d.add_css_class('ph-del')
        right.append(d)
        bar.set_start_widget(left)
        bar.set_center_widget(show)
        bar.set_end_widget(right)
        root.append(bar)

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

    def open_path(self, path):
        mwx7ui.remember(path)
        self.pics = list_images(os.path.dirname(path)) or [path]
        self.show(self.pics.index(path) if path in self.pics else 0)
        return False

    def show(self, i):
        self.empty.set_visible(not self.pics)
        if not self.pics:
            self.index = -1
            self.picture.set_paintable(None)
            self.count.set_label('')
            self.app.set_title('Photos')
            return
        self.index = i % len(self.pics)
        self.rot = 0
        path = self.pics[self.index]
        try:
            self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(path).apply_embedded_orientation()
        except GLib.Error:
            self.pixbuf = None
        self.paint()
        name = os.path.basename(path)
        self.name.set_label(name)
        self.count.set_label(f'{self.index + 1} of {len(self.pics)}')
        self.app.set_title(f'{name} - Photos')

    def paint(self):
        if not self.pixbuf:
            self.picture.set_paintable(None)
            return
        pb = self.pixbuf.rotate_simple(GdkPixbuf.PixbufRotation(self.rot % 360)) if self.rot % 360 else self.pixbuf
        self.picture.set_paintable(Gdk.Texture.new_for_pixbuf(pb))

    def step(self, d):
        if self.pics:
            self.show(self.index + d)

    def rotate(self, deg):
        self.rot = (self.rot + deg) % 360
        self.paint()

    def toggle_zoom(self):
        self.actual = not self.actual
        self.picture.set_can_shrink(not self.actual)
        self.zoom_btn.set_icon_name('zoom-fit-best-symbolic' if self.actual else 'zoom-original-symbolic')
        self.zoom_btn.set_tooltip_text('Fit to window' if self.actual else 'Actual size')

    def remove(self):
        if self.index < 0:
            return
        path = self.pics[self.index]
        if path.startswith(SAMPLES):
            Gtk.AlertDialog(message='This is one of MWX 7’s sample photos.',
                            detail='Sample photos can’t be deleted.').show(self.win)
            return
        dlg = Gtk.AlertDialog(message='Move this picture to the Trash?', detail=os.path.basename(path),
                              buttons=['Move to Trash', 'Cancel'], default_button=1, cancel_button=1)

        def done(d, res):
            try:
                if d.choose_finish(res) != 0:
                    return
                Gio.File.new_for_path(path).trash(None)
            except GLib.Error:
                return
            self.pics.remove(path)
            self.show(min(self.index, len(self.pics) - 1) if self.pics else -1)
        dlg.choose(self.win, None, done)

    def slideshow(self):
        """Full screen, a picture every four seconds; a click ends it."""
        if not self.pics:
            return
        w = Gtk.Window(transient_for=self.win)
        w.add_css_class('ph-slideshow')
        pic = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN)
        w.set_child(pic)
        state = {'i': self.index}

        def load():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(self.pics[state['i'] % len(self.pics)]).apply_embedded_orientation()
                pic.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
            except GLib.Error:
                pass

        def advance():
            state['i'] += 1
            load()
            return True
        timer = GLib.timeout_add_seconds(4, advance)

        def end(*_):
            GLib.source_remove(timer)
            w.destroy()
            self.show(state['i'])
        click = Gtk.GestureClick()
        click.connect('pressed', end)
        w.add_controller(click)
        load()
        w.fullscreen()
        w.present()


if __name__ == '__main__':
    photos = Photos()
    mwx7ui.App('org.mwx7.photos', 'Photos', 'photos', (860, 620), CSS, photos.build).run_main()
