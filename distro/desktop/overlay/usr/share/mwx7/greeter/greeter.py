#!/usr/bin/env python3
"""MWX 7 logon screen. Talks to greetd over its socket ($GREETD_SOCK): name → password → start the desktop session.
Runs full screen inside cage; when the logon succeeds it exits and greetd starts the session."""
import json
import os
import pwd
import socket
import struct
import subprocess
import threading
import time

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SHARE = '/usr/share/mwx7'
SESSION = ['/usr/local/bin/mwx7-session']
LAST_USER = os.path.expanduser('~/last-user')
LIVE = os.path.exists('/usr/local/bin/mwx7-install')  # the greeter's own home (/var/lib/greetd)


def people():
    """Accounts a person can log in to: regular user ids with a real shell."""
    out = []
    for p in pwd.getpwall():
        if 1000 <= p.pw_uid < 60000 and not p.pw_shell.endswith(('nologin', 'false')):
            out.append((p.pw_name, (p.pw_gecos or '').split(',')[0].strip() or p.pw_name.capitalize()))
    return out


class Greetd:
    """One request, one answer; both are a 4-byte length in native byte order followed by JSON."""

    def __init__(self):
        self.s = socket.socket(socket.AF_UNIX)
        self.s.connect(os.environ['GREETD_SOCK'])

    def ask(self, **msg):
        data = json.dumps(msg).encode()
        self.s.sendall(struct.pack('=I', len(data)) + data)
        size = struct.unpack('=I', self._read(4))[0]
        return json.loads(self._read(size))

    def _read(self, n):
        buf = b''
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError('greetd closed the connection')
            buf += chunk
        return buf


def log_in(username, password):
    """Returns None when the session is about to start, otherwise the reason it did not."""
    try:
        g = Greetd()
        r = g.ask(type='create_session', username=username)
        while r.get('type') == 'auth_message':
            kind = r.get('auth_message_type')
            # Questions get the password; notices just get acknowledged.
            r = g.ask(type='post_auth_message_response', response=password if kind in ('secret', 'visible') else None)
        if r.get('type') == 'success':
            r = g.ask(type='start_session', cmd=SESSION, env=[])
            if r.get('type') == 'success':
                return None
        g.ask(type='cancel_session')
        if r.get('error_type') == 'auth_error':
            return 'The password is incorrect. Please try again.'
        return r.get('description') or 'Logging in did not work. Please try again.'
    except (OSError, KeyError, ValueError) as e:
        return f'The logon service is not answering ({e}).'


class Greeter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.mwx7.greeter')
        self.users = people()
        self.user = None

    def do_activate(self):
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(HERE, 'greeter.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = Gtk.ApplicationWindow(application=self)
        win.add_css_class('greeter')
        win.set_decorated(False)

        overlay = Gtk.Overlay()
        back = Gtk.Picture.new_for_filename(os.path.join(SHARE, 'wallpaper.jpg'))
        back.set_content_fit(Gtk.ContentFit.COVER)
        overlay.set_child(back)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        col.set_halign(Gtk.Align.CENTER)
        col.set_valign(Gtk.Align.CENTER)
        self.avatar = Gtk.Picture()
        self.avatar.set_size_request(112, 112)
        frame = Gtk.Box()
        frame.add_css_class('avatar')
        frame.set_halign(Gtk.Align.CENTER)
        frame.append(self.avatar)
        col.append(frame)
        self.name = Gtk.Label()
        self.name.add_css_class('name')
        col.append(self.name)

        row = Gtk.Box(spacing=6)
        row.set_halign(Gtk.Align.CENTER)
        self.password = Gtk.PasswordEntry()
        self.password.set_property('placeholder-text', 'Password')
        self.password.set_show_peek_icon(False)
        self.password.set_size_request(230, -1)
        self.password.connect('activate', self.on_go)
        row.append(self.password)
        self.go = Gtk.Button(label='→')
        self.go.add_css_class('go')
        self.go.set_tooltip_text('Log on')
        self.go.connect('clicked', self.on_go)
        row.append(self.go)
        col.append(row)
        self.message = Gtk.Label()
        self.message.add_css_class('message')
        col.append(self.message)

        # More than one account: small pictures to switch between them.
        if len(self.users) > 1:
            others = Gtk.Box(spacing=14)
            others.set_halign(Gtk.Align.CENTER)
            others.set_margin_top(18)
            for login, full in self.users:
                b = Gtk.Button()
                b.add_css_class('other')
                v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                v.append(self.picture_of(login, 48))
                v.append(Gtk.Label(label=full))
                b.set_child(v)
                b.connect('clicked', lambda *_a, u=(login, full): self.choose(u))
                others.append(b)
            col.append(others)
        overlay.add_overlay(col)

        brand = Gtk.Label(label='MWX 7')
        brand.add_css_class('brand')
        brand.set_halign(Gtk.Align.CENTER)
        brand.set_valign(Gtk.Align.END)
        brand.set_margin_bottom(28)
        overlay.add_overlay(brand)

        power = Gtk.Box(spacing=8)
        power.set_halign(Gtk.Align.END)
        power.set_valign(Gtk.Align.END)
        power.set_margin_end(24)
        power.set_margin_bottom(20)
        for label, icon, cmd in (('Restart', 'logoff', ['systemctl', 'reboot']),
                                 ('Shut Down', 'shutdown', ['systemctl', 'poweroff'])):
            b = Gtk.Button()
            b.add_css_class('power')
            b.set_tooltip_text(label)
            img = Gtk.Image.new_from_file(os.path.join(SHARE, 'icons', icon + '.png'))
            img.set_pixel_size(28)
            b.set_child(img)
            b.connect('clicked', lambda *_a, c=cmd: subprocess.Popen(c))
            power.append(b)
        overlay.add_overlay(power)

        self.clock = Gtk.Label()
        self.clock.add_css_class('clock')
        self.clock.set_halign(Gtk.Align.START)
        self.clock.set_valign(Gtk.Align.END)
        self.clock.set_margin_start(28)
        self.clock.set_margin_bottom(22)
        overlay.add_overlay(self.clock)
        self.tick()
        GLib.timeout_add_seconds(10, self.tick)

        win.set_child(overlay)
        last = open(LAST_USER).read().strip() if os.path.exists(LAST_USER) else ''
        self.choose(next((u for u in self.users if u[0] == last), self.users[0] if self.users else ('root', 'root')))
        win.fullscreen()
        win.present()
        self.password.grab_focus()

    def picture_of(self, login, size):
        # A picture the person chose (same place other Linux desktops use), else MWX 7's default.
        own = f'/var/lib/AccountsService/icons/{login}'
        path = own if os.path.exists(own) else os.path.join(SHARE, 'avatars', '03-guitar.jpg')
        pic = Gtk.Picture()
        try:
            pic.set_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, False))
        except GLib.Error:
            pass
        pic.set_size_request(size, size)
        return pic

    def choose(self, user):
        self.user = user
        self.name.set_label(user[1])
        try:
            own = f'/var/lib/AccountsService/icons/{user[0]}'
            path = own if os.path.exists(own) else os.path.join(SHARE, 'avatars', '03-guitar.jpg')
            self.avatar.set_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 112, 112, False))
        except GLib.Error:
            pass
        # On the live medium, say what the password is: nobody chose it.
        self.message.set_label('Live session: the password is mwx7' if user[0] == 'mwx' and LIVE else '')
        self.password.set_text('')
        self.password.grab_focus()

    def tick(self):
        self.clock.set_label(time.strftime('%H:%M\n%A, %-d %B'))
        return True

    def on_go(self, *_):
        password = self.password.get_text()
        if not password or not self.go.get_sensitive():
            return
        self.go.set_sensitive(False)
        self.password.set_sensitive(False)
        self.message.set_label('Welcome')
        login = self.user[0]

        def work():
            problem = log_in(login, password)
            GLib.idle_add(self.done, login, problem)
        threading.Thread(target=work, daemon=True).start()

    def done(self, login, problem):
        if problem is None:
            try:
                with open(LAST_USER, 'w') as f:
                    f.write(login)
            except OSError:
                pass
            self.quit()
            return False
        self.message.set_label(problem)
        self.go.set_sensitive(True)
        self.password.set_sensitive(True)
        self.password.set_text('')
        self.password.grab_focus()
        return False


if __name__ == '__main__':
    Greeter().run(None)
