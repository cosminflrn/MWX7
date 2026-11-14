#!/usr/bin/env python3
"""MWX 7 Repair screen (boot menu -> Repair MWX 7). Runs full screen in cage as root, started by bin/mwx7-repair from a
copy in /boot/mwx7-recovery, so it works even when /usr/share/mwx7 is damaged. Mouse only: no typing, so no keyboard
layout can get in the way. Two choices, each running install.py's reinstall(): Repair (keeps accounts, files, apps and
settings) and Reset to factory (after a second, explicit confirmation). install.py restarts the PC when it is done."""
import json
import os
import subprocess
import sys
import threading

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, 'install.py')
SHARE = '/usr/share/mwx7'  # only decoration comes from here: the screen works without it
SHOWN = '/run/mwx7-repair-shown'  # tells bin/mwx7-repair that this screen made it to the display


def restart(*_):
    subprocess.Popen(['systemctl', 'reboot'])


class Repair(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.mwx7.repair')

    def do_activate(self):
        css = Gtk.CssProvider()
        try:
            css.load_from_path(os.path.join(HERE, 'oobe.css'))
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except (GLib.Error, AttributeError):
            pass  # plain GTK look rather than no screen at all
        self.win = Gtk.ApplicationWindow(application=self, title='Repair MWX 7')
        self.win.add_css_class('oobe')
        self.win.fullscreen()
        overlay = Gtk.Overlay()
        wall = os.path.join(SHARE, 'wallpaper.jpg')
        if os.path.exists(wall):
            back = Gtk.Picture.new_for_filename(wall)
            back.set_content_fit(Gtk.ContentFit.COVER)
            overlay.set_child(back)
        else:
            overlay.set_child(Gtk.Box())
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class('card')
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        card.set_size_request(640, 380)
        top = Gtk.Box(spacing=12)
        orb = os.path.join(SHARE, 'icons', 'orb.png')
        if os.path.exists(orb):
            img = Gtk.Image.new_from_file(orb)
            img.set_pixel_size(40)
            top.append(img)
        self.title = Gtk.Label(xalign=0, hexpand=True)
        self.title.add_css_class('title')
        top.append(self.title)
        card.append(top)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, vexpand=True)
        card.append(self.body)
        overlay.add_overlay(card)
        self.win.set_child(overlay)
        self.win.present()
        try:
            open(SHOWN, 'w').close()
        except OSError:
            pass
        self.choose()

    # ---- pages --------------------------------------------------------------------------------------------------
    def page(self, title):
        self.title.set_label(title)
        while (c := self.body.get_first_child()) is not None:
            self.body.remove(c)

    def text(self, s, css='text'):
        lab = Gtk.Label(label=s, xalign=0, wrap=True)
        lab.add_css_class(css)
        self.body.append(lab)
        return lab

    def button(self, label, cb, primary=False):
        b = Gtk.Button(label=label)
        if primary:
            b.add_css_class('primary')
        b.connect('clicked', cb)
        return b

    def buttons(self, *btns):
        row = Gtk.Box(spacing=10, halign=Gtk.Align.END, valign=Gtk.Align.END, vexpand=True)
        row.add_css_class('bottom')
        for b in btns:
            row.append(b)
        self.body.append(row)

    def choose(self, *_):
        self.page('Repair MWX 7')
        self.text('MWX 7 did not start the way it should. Choose what to do. Nothing happens until you click.')
        for label, note, cb in (
                ('Repair, keeping my files', 'Puts MWX 7 itself back in order. Your accounts, files, apps and settings stay.',
                 lambda *_: self.start(True)),
                ('Reset to factory', 'Starts again as new. Everything on this PC is deleted first (you will be asked to confirm).',
                 self.confirm_reset)):
            b = Gtk.Button()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t = Gtk.Label(label=label, xalign=0)
            t.add_css_class('disk-title')
            n = Gtk.Label(label=note, xalign=0, wrap=True)
            n.add_css_class('hint')
            box.append(t)
            box.append(n)
            b.set_child(box)
            b.add_css_class('disk')
            b.connect('clicked', cb)
            self.body.append(b)
        self.buttons(self.button('Restart', restart))

    def confirm_reset(self, *_):
        self.page('Delete everything?')
        lab = self.text('Reset to factory deletes all accounts, files, apps and settings on this PC. This cannot be undone.',
                        'refusal')
        lab.set_wrap(True)
        self.text('If you only want MWX 7 to work again, go back and choose Repair.')
        self.buttons(self.button('Back', self.choose, True), self.button('Delete everything and reset', lambda *_: self.start(False)))

    def start(self, keep):
        self.page('Repairing MWX 7' if keep else 'Resetting MWX 7')
        self.text("This takes a while. Don't turn off your PC. It restarts by itself when it is done.")
        self.step = self.text('Getting ready', 'status')
        self.bar = Gtk.ProgressBar()
        self.body.append(self.bar)
        threading.Thread(target=self.work, args=(keep,), daemon=True).start()

    def work(self, keep):
        error = 'Something went wrong.'
        try:
            p = subprocess.Popen([sys.executable, INSTALL, 'reinstall', 'keep' if keep else 'clean'], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                kind, _, rest = line.strip().partition(' ')
                if kind == 'STEP':
                    GLib.idle_add(self.step.set_label, rest + '…')
                elif kind == 'PROGRESS' and rest.isdigit():
                    GLib.idle_add(self.bar.set_fraction, int(rest) / 100)
                elif kind == 'ERROR':
                    error = rest
            if p.wait() == 0:
                GLib.idle_add(self.step.set_label, 'Restarting…')
                return  # install.py restarts the PC itself
        except OSError as e:
            error = str(e)
        GLib.idle_add(self.failed, error)

    def failed(self, error):
        self.page('That did not work')
        self.text(error, 'refusal')
        self.text('Nothing was changed. You can try again, or restart and start MWX 7 as usual.')
        self.buttons(self.button('Restart', restart), self.button('Back', self.choose, True))


if __name__ == '__main__':
    sys.exit(Repair().run(None))
