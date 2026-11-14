"""Run Windows programs (native): what happens when a .exe or .msi is double-clicked. MWX 7 does not run Windows programs
itself; Bottles (a Flatpak, built on Wine) does. This small window says so kindly and offers the way on: open the file with
Bottles when it is installed, otherwise get Bottles from Get Apps, and always "Look for a Linux version" of the program (found
through the product name inside the file, or its file name). Nothing is ever run from here without a click."""
import os
import shutil
import subprocess
import sys
import urllib.parse

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7pe  # noqa: E402
import mwx7ui  # noqa: E402
from mwx7ui import Gtk  # noqa: E402

BOTTLES = 'com.usebottles.bottles'
APP = '/usr/share/mwx7/bin/mwx7-app'
CSS = """
window.mwx7-winrun > box { background: #f4f7fc; }
.wr-head { font-size: 16px; font-weight: 700; color: #1c2530; }
.wr-file { color: #1e3f66; font-weight: 600; }
.wr-body { color: #2b3a4d; }
.wr-hint { color: #55657a; font-size: 12px; }
.wr-bar { background: linear-gradient(180deg, #f3f6fb, #dde6f2); border-top: 1px solid #c3d1e4; padding: 10px 14px; }
window.mwx7-winrun button { min-height: 24px; padding: 0 16px; border-radius: 3px; color: #1c2530; border: 1px solid #8b9db5;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
  background: linear-gradient(180deg, #f6f9fd 0%, #e6edf6 49%, #d6e1ee 50%, #e3ebf5 100%); }
window.mwx7-winrun button:hover { border-color: #3c7fb1;
  background: linear-gradient(180deg, #eaf6fd 0%, #d9f0fc 49%, #bee6fd 50%, #a7d9f5 100%); }
window.mwx7-winrun button:active { background: linear-gradient(180deg, #c2e4f6 0%, #a9d9f2 49%, #90cbeb 50%, #a4d5ef 100%); }
window.mwx7-winrun button.suggested { border-color: #2c6d9e; font-weight: 700; }
"""


def bottles_installed():
    """Bottles as a Flatpak (the usual way here), or a native `bottles` command."""
    try:
        if subprocess.run(['flatpak', 'info', BOTTLES], capture_output=True, timeout=10).returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return shutil.which('bottles') is not None


def open_with_bottles(path):
    # Bottles takes the file as its argument and asks which bottle to run it in (it declares the same file types itself).
    if shutil.which('flatpak'):
        cmd = ['flatpak', 'run', BOTTLES, path]
    else:
        cmd = ['bottles', path]
    subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def store(link):
    """Opens Get Apps on a page: store:app/<flatpak id> or store:search/<text> (see Store.on_open in store.py)."""
    subprocess.Popen([APP, 'store', link], start_new_session=True)


class WinRun:
    def build(self, app, win):
        self.win = win
        win.add_css_class('mwx7-winrun')
        files = [f.get_path() for f in app.files if f.get_path()]
        self.path = files[0] if files else ''
        self.name = mwx7pe.program_name(self.path) if self.path else ''
        self.has_bottles = bottles_installed()
        win.set_default_size(460, -1)
        win.set_resizable(False)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top = Gtk.Box(spacing=14, margin_start=18, margin_end=18, margin_top=18, margin_bottom=14)
        top.append(mwx7ui.icon('exe', 56))
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        head = Gtk.Label(label='This is a Windows program', xalign=0)
        head.add_css_class('wr-head')
        col.append(head)
        fname = Gtk.Label(label=os.path.basename(self.path) or 'No file chosen', xalign=0, ellipsize=3, max_width_chars=40)
        fname.add_css_class('wr-file')
        col.append(fname)
        if self.has_bottles:
            text = 'MWX 7 runs Windows programs with Bottles. It will ask which bottle to use, and keeps this program tidy in its own.'
        else:
            text = 'MWX 7 needs a helper called Bottles to run Windows programs, and it is free in Get Apps.'
        body = Gtk.Label(label=text, wrap=True, xalign=0, max_width_chars=44)
        body.add_css_class('wr-body')
        col.append(body)
        if self.name:
            hint = Gtk.Label(label=f'Many programs also have a Linux version. We can look for “{self.name}”.', wrap=True,
                             xalign=0, max_width_chars=44, margin_top=4)
            hint.add_css_class('wr-hint')
            col.append(hint)
        top.append(col)
        root.append(top)

        bar = Gtk.Box(spacing=8, halign=Gtk.Align.FILL)
        bar.add_css_class('wr-bar')
        look = Gtk.Button(label='Look for a Linux version', sensitive=bool(self.name))
        look.connect('clicked', lambda *_: self.after(lambda: store('store:search/' + urllib.parse.quote(self.name))))
        bar.append(look)
        bar.append(Gtk.Box(hexpand=True))
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_: win.close())
        if self.has_bottles:
            go = Gtk.Button(label='Open with Bottles', sensitive=bool(self.path))
            go.connect('clicked', lambda *_: self.after(lambda: open_with_bottles(self.path)))
        else:
            go = Gtk.Button(label='Get Bottles')
            go.connect('clicked', lambda *_: self.after(lambda: store('store:app/' + BOTTLES)))
        go.add_css_class('suggested')
        bar.append(go)
        bar.append(cancel)
        root.append(bar)
        return root

    def after(self, fn):
        fn()
        self.win.close()


if __name__ == '__main__':
    mwx7ui.App('org.mwx7.winrun', 'Run Windows programs', 'exe', (460, 200), CSS, WinRun().build, resizable=False).run_main()
