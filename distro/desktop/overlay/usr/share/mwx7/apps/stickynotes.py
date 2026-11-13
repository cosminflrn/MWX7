"""Sticky Notes (native): a window per note, in six colours, kept between sign-ins (unlike the concept, which forgets
them on reload: on a real PC a note is meant to stay)."""
import json
import os
import sys
import uuid

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

STORE = os.path.join(GLib.get_user_data_dir(), 'mwx7', 'notes.json')
COLORS = {  # paper, head, edge, ink
    'yellow': ('#fff7a8', '#f1d95b', '#c9ae2f', '#3a3414'), 'blue': ('#cfe8fb', '#9ccbf0', '#6aa5d4', '#17324d'),
    'green': ('#d4f2c4', '#a4dc8b', '#74b45a', '#1d3b14'), 'pink': ('#fbd3e2', '#f1a2c0', '#cf7898', '#4a1a2d'),
    'purple': ('#e2d4f6', '#c1a4e8', '#9577c4', '#2f1d4a'), 'white': ('#fbfbfb', '#dcdfe4', '#aeb4be', '#262a31'),
}
CSS = ''.join(f"""
window.sn-{c}, window.sn-{c} textview, window.sn-{c} textview text {{ background: {p}; color: {i}; }}
window.sn-{c} .sn-head {{ background: linear-gradient(180deg, shade({h}, 1.12), {h}); border-bottom: 1px solid {e}; }}
window.sn-{c} .sn-head button {{ color: {i}; }}
window.sn-{c} .sn-head button:hover {{ background: rgba(255,255,255,.45); border-color: {e}; }}
""" for c, (p, h, e, i) in COLORS.items()) + """
window.sn { border-radius: 0; box-shadow: 0 6px 18px rgba(0,0,0,.35); }
.sn-head { min-height: 26px; padding: 0 4px; }
.sn-head button { min-width: 20px; min-height: 20px; padding: 0; border: 1px solid transparent; border-radius: 4px;
  background: none; box-shadow: none; opacity: .75; }
.sn-head button:hover { opacity: 1; }
window.sn textview { padding: 10px 12px; font-family: "Comic Neue", "Selawik", cursive; font-size: 13pt; }
"""


def has_text(text):
    return bool(text and text.strip())


class Notes(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.mwx7.stickynotes')
        GLib.set_prgname('org.mwx7.stickynotes')
        self.notes = {}
        self.save_id = 0

    def do_activate(self):
        if self.notes:
            # Started again (Start menu, dock): a new note, as Win7 does.
            self.add_note({})
            return
        p = Gtk.CssProvider()
        p.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        try:
            saved = json.load(open(STORE))
        except (OSError, ValueError):
            saved = []
        # Empty notes left in the file by older versions are dropped.
        for n in [n for n in saved if has_text(n.get('text'))] or [{}]:
            self.add_note(n)

    def add_note(self, data, color=None):
        nid = data.get('id') or uuid.uuid4().hex
        color = color or data.get('color') if (color or data.get('color')) in COLORS else 'yellow'
        w = Gtk.ApplicationWindow(application=self, title='Sticky Notes')
        w.set_default_size(data.get('w', 260), data.get('h', 250))
        w.add_css_class('sn')
        w.add_css_class('sn-' + color)
        head = Gtk.CenterBox()
        head.add_css_class('sn-head')
        add = Gtk.Button(icon_name='list-add-symbolic', tooltip_text='New note', focusable=False)
        add.connect('clicked', lambda *_: self.add_note({}, self.notes[nid]['color']))
        close = Gtk.Button(icon_name='window-close-symbolic', tooltip_text='Delete note', focusable=False)
        head.set_start_widget(add)
        head.set_end_widget(close)
        handle = Gtk.WindowHandle()
        handle.set_child(head)
        w.set_titlebar(handle)
        buf = Gtk.TextBuffer()
        buf.set_text(data.get('text', ''))
        view = Gtk.TextView(buffer=buf, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sc = Gtk.ScrolledWindow()
        sc.set_child(view)
        w.set_child(sc)
        self.notes[nid] = {'win': w, 'buf': buf, 'color': color}
        buf.connect('changed', lambda *_: (self.retitle(nid), self.schedule_save()))
        close.connect('clicked', lambda *_: self.delete(nid))
        w.connect('close-request', lambda *_: (self.on_close(nid), False)[1])
        # Right-click: the colours, as in the concept.
        menu = Gio.Menu()
        for c in COLORS:
            menu.append(c.title(), f'win.color::{c}')
        act = Gio.SimpleAction.new('color', GLib.VariantType.new('s'))
        act.connect('activate', lambda _a, v: self.recolor(nid, v.get_string()))
        w.add_action(act)
        pop = Gtk.PopoverMenu(menu_model=menu, has_arrow=False)
        pop.set_parent(sc)
        click = Gtk.GestureClick(button=3)

        def pressed(_g, _n, x, y):
            r = Gdk.Rectangle()
            r.x, r.y, r.width, r.height = int(x), int(y), 1, 1
            pop.set_pointing_to(r)
            pop.popup()
        click.connect('pressed', pressed)
        view.add_controller(click)
        self.retitle(nid)
        w.present()
        GLib.idle_add(lambda: view.grab_focus() and False)
        self.schedule_save()

    def on_close(self, nid):
        # A note closed while empty is gone, not kept as a blank note for the next sign-in.
        n = self.notes.get(nid)
        if n and not has_text(n['buf'].get_text(*n['buf'].get_bounds(), False)):
            self.notes.pop(nid, None)
        self.save()

    def retitle(self, nid):
        n = self.notes[nid]
        first = n['buf'].get_text(*n['buf'].get_bounds(), False).strip().split('\n')[0][:28]
        n['win'].set_title(f'{first} — Sticky Notes' if first else 'Sticky Notes')

    def recolor(self, nid, color):
        n = self.notes[nid]
        n['win'].remove_css_class('sn-' + n['color'])
        n['color'] = color
        n['win'].add_css_class('sn-' + color)
        self.schedule_save()

    def delete(self, nid):
        n = self.notes[nid]

        def drop():
            self.notes.pop(nid, None)
            self.save()
            n['win'].destroy()
        if not n['buf'].get_text(*n['buf'].get_bounds(), False).strip():
            drop()
            return
        dlg = Gtk.AlertDialog(message='Delete this note?', detail='It will be permanently deleted.',
                              buttons=['Delete', 'Cancel'], default_button=1, cancel_button=1)

        def done(d, res):
            try:
                if d.choose_finish(res) == 0:
                    drop()
            except GLib.Error:
                pass
        dlg.choose(n['win'], None, done)

    def schedule_save(self):
        if self.save_id:
            GLib.source_remove(self.save_id)
        self.save_id = GLib.timeout_add(600, lambda: (self.save(), False)[1])

    def save(self):
        self.save_id = 0
        out = []
        for nid, n in self.notes.items():
            if not has_text(n['buf'].get_text(*n['buf'].get_bounds(), False)):
                continue  # never persist an empty note
            out.append({'id': nid, 'color': n['color'], 'text': n['buf'].get_text(*n['buf'].get_bounds(), False),
                        'w': n['win'].get_width() or 260, 'h': n['win'].get_height() or 250})
        try:
            os.makedirs(os.path.dirname(STORE), exist_ok=True)
            tmp = STORE + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(out, f)
            os.replace(tmp, STORE)
        except OSError:
            pass


if __name__ == '__main__':
    if '--if-any' in sys.argv:
        # Sign-in autostart: only bring notes back when there is something written on one.
        try:
            if not any(isinstance(n, dict) and has_text(n.get('text')) for n in json.load(open(STORE))):
                sys.exit(0)
        except (OSError, ValueError, TypeError):
            sys.exit(0)
        sys.argv.remove('--if-any')
    Notes().run(sys.argv)
