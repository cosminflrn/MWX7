"""MWX 7 Snipping Tool (GTK 4): the web concept's Snip on the real screen. New captures a rectangle you drag, a window
you click or the whole screen (grim + slurp); Save writes a PNG to Pictures, Copy puts it on the clipboard."""
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

sys.path.insert(0, '/usr/share/mwx7/settings')
import settings as base  # noqa: E402  (the Aero title bar, the window colour and the shared look)

MODES = [('rect', 'Rectangular Snip'), ('window', 'Window Snip'), ('full', 'Full-screen Snip')]
CSS = """
window.mwx7-snip .snip-bar { padding: 6px 8px; border-bottom: 1px solid #d5dfec;
  background: linear-gradient(to bottom, #fbfdff, #e9f0f9); }
window.mwx7-snip .snip-bar button { padding: 3px 10px; min-height: 0; border-radius: 4px; border: 1px solid transparent;
  background: none; box-shadow: none; color: #1c3150; }
window.mwx7-snip .snip-bar button:hover { border-color: #a8c6ec; background: linear-gradient(to bottom, #f4f9ff, #dbeafc); }
window.mwx7-snip .snip-bar button:disabled { opacity: .45; }
window.mwx7-snip .snip-stage { background: #eef2f7; }
window.mwx7-snip .snip-empty { color: #5a6f8d; }
window.mwx7-snip .snip-empty-title { font-weight: 700; font-size: 15px; color: #1c3150; }
window.mwx7-snip .snip-foot { padding: 4px 10px; font-size: 12px; color: #4a5f7d; border-top: 1px solid #d5dfec;
  background: #f6f8fb; }
"""


def wayfire_windows():
    """Where each visible window is, for Window Snip (slurp offers them as rectangles to click)."""
    path = os.environ.get('WAYFIRE_SOCKET') or '/tmp/wayfire-wayland-1.socket'
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(3)
        s.connect(path)
        msg = json.dumps({'method': 'window-rules/list-views', 'data': {}}).encode()
        s.sendall(struct.pack('<I', len(msg)) + msg)
        n = struct.unpack('<I', s.recv(4))[0]
        buf = b''
        while len(buf) < n:
            buf += s.recv(n - len(buf))
        views = json.loads(buf)
    except (OSError, ValueError, struct.error):
        return []
    out = []
    for v in views:
        g = v.get('geometry') or {}
        if v.get('role') == 'toplevel' and v.get('mapped', True) and not v.get('minimized') and g.get('width'):
            out.append(f"{g['x']},{g['y']} {g['width']}x{g['height']}")
    return out


class Snip(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.mwx7.snip')
        GLib.set_prgname('org.mwx7.snip')
        self.mode = 'rect'
        self.file = None

    def do_activate(self):
        if self.get_windows():
            self.get_windows()[0].present()
            return
        display = Gdk.Display.get_default()
        css = Gtk.CssProvider()
        css.load_from_path('/usr/share/mwx7/settings/settings.css')
        Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        own = Gtk.CssProvider()
        own.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(display, own, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        rgb, intensity = base.glass_now()
        a = base.glass_alpha(intensity)
        tint = Gtk.CssProvider()
        tint.load_from_data((base.titlebar_css('headerbar.mwx7-titlebar', rgb, a) +
                             base.titlebar_css('window.mwx7-settings:backdrop headerbar.mwx7-titlebar', rgb, a, False) +
                             'window.mwx7-settings { background: transparent; }\n'
                             'window.mwx7-settings > box { background: #ffffff; }\n').encode())
        Gtk.StyleContext.add_provider_for_display(display, tint, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)

        w = self.win = Gtk.ApplicationWindow(application=self, title='Snipping Tool')
        w.set_default_size(560, 420)
        w.add_css_class('mwx7-settings')
        w.add_css_class('mwx7-snip')
        w.set_titlebar(base.Settings.titlebar(w, 'Snipping Tool', 'snip'))

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bar = Gtk.Box(spacing=4)
        bar.add_css_class('snip-bar')
        self.new_btn = self.tool('New', 'document-new-symbolic', lambda *_: self.capture())
        bar.append(self.new_btn)
        # The arrow next to New picks the kind of snip, as in the concept.
        mode_btn = Gtk.MenuButton()
        mode_btn.set_tooltip_text('Snip type')
        menu = Gio.Menu()
        for mid, label in MODES:
            menu.append(label, f'app.mode::{mid}')
        act = Gio.SimpleAction.new_stateful('mode', GLib.VariantType.new('s'), GLib.Variant('s', self.mode))
        act.connect('activate', lambda a, v: (a.set_state(v), setattr(self, 'mode', v.get_string()),
                                              self.say(f'{dict(MODES)[v.get_string()]}: click New to capture.')))
        self.add_action(act)
        mode_btn.set_menu_model(menu)
        bar.append(mode_btn)
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_start(4)
        sep.set_margin_end(4)
        bar.append(sep)
        self.save_btn = self.tool('Save', 'document-save-symbolic', lambda *_: self.save())
        self.copy_btn = self.tool('Copy', 'edit-copy-symbolic', lambda *_: self.copy())
        self.save_btn.set_sensitive(False)
        self.copy_btn.set_sensitive(False)
        bar.append(self.save_btn)
        bar.append(self.copy_btn)
        root.append(bar)

        self.stage = Gtk.Stack(vexpand=True)
        self.stage.add_css_class('snip-stage')
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        empty.add_css_class('snip-empty')
        pic = Gtk.Image.new_from_file('/usr/share/mwx7/icons/snip.png')
        pic.set_pixel_size(64)
        t = Gtk.Label(label='No snip yet')
        t.add_css_class('snip-empty-title')
        empty.append(pic)
        empty.append(t)
        empty.append(Gtk.Label(label='Click New and drag around what you want to capture.'))
        self.stage.add_named(empty, 'empty')
        self.picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN)
        self.picture.set_margin_top(10)
        self.picture.set_margin_bottom(10)
        self.picture.set_margin_start(10)
        self.picture.set_margin_end(10)
        self.stage.add_named(self.picture, 'shot')
        root.append(self.stage)
        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class('snip-foot')
        root.append(self.status)
        self.say('Click New to capture. The arrow picks rectangle, window or full screen.')
        w.set_child(root)
        w.present()

    def tool(self, label, icon, fn):
        b = Gtk.Button()
        box = Gtk.Box(spacing=5)
        box.append(Gtk.Image.new_from_icon_name(icon))
        box.append(Gtk.Label(label=label))
        b.set_child(box)
        b.connect('clicked', fn)
        return b

    def say(self, text):
        self.status.set_label(text)

    def capture(self):
        # Out of the way first, so the snip shows what is behind this window, then back with the result.
        self.win.set_visible(False)
        GLib.timeout_add(350, self.grab)

    def grab(self):
        out = os.path.join(tempfile.gettempdir(), f'mwx7-snip-{os.getuid()}.png')
        try:
            if self.mode == 'full':
                cmd = ['grim', out]
            else:
                area = subprocess.run(['slurp', '-d', '-b', '#1e64dc22', '-c', '#1e64dcff', '-w', '2']
                                      + (['-r'] if self.mode == 'window' else []),
                                      input='\n'.join(wayfire_windows()) if self.mode == 'window' else None,
                                      capture_output=True, text=True, timeout=120)
                if area.returncode != 0 or not area.stdout.strip():
                    self.win.set_visible(True)
                    self.say('No snip taken.')
                    return False
                cmd = ['grim', '-g', area.stdout.strip(), out]
            subprocess.run(cmd, check=True, timeout=20, capture_output=True)
        except (OSError, subprocess.SubprocessError) as e:
            self.win.set_visible(True)
            self.say(f'The snip did not work ({e.__class__.__name__}).')
            return False
        self.file = out
        self.picture.set_file(Gio.File.new_for_path(out))
        self.stage.set_visible_child_name('shot')
        self.save_btn.set_sensitive(True)
        self.copy_btn.set_sensitive(True)
        self.win.set_visible(True)
        self.win.present()
        self.say('Snip taken. Save it as a picture or copy it.')
        return False

    def save(self):
        pics = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) or os.path.expanduser('~/Pictures')
        os.makedirs(pics, exist_ok=True)
        dlg = Gtk.FileDialog(title='Save Snip', initial_name=time.strftime('Snip %Y-%m-%d %H-%M-%S.png'),
                             initial_folder=Gio.File.new_for_path(pics))

        def done(d, res):
            try:
                dest = d.save_finish(res)
            except GLib.Error:
                return
            with open(self.file, 'rb') as src, open(dest.get_path(), 'wb') as f:
                f.write(src.read())
            self.say(f'Saved as {os.path.basename(dest.get_path())}.')
        dlg.save(self.win, None, done)

    def copy(self):
        try:
            with open(self.file, 'rb') as f:
                subprocess.run(['wl-copy', '--type', 'image/png'], stdin=f, timeout=5)
            self.say('Copied. Paste it into Paint, a document or a chat.')
        except (OSError, subprocess.SubprocessError):
            self.say('Copying did not work.')


if __name__ == '__main__':
    Snip().run(None)
