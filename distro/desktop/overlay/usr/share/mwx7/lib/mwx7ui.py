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
        w = self.win = Gtk.ApplicationWindow(application=self, title=self.title)
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
        """menus: [(label, [(item label, action name, callback) | None for a separator, ...]), ...]"""
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
        return Gtk.PopoverMenuBar.new_from_model(model)

    def run_main(self):
        return self.run(sys.argv)
