"""Welcome (native): the concept's tour, shown at an account's first sign-in and kept in the Start menu."""
import subprocess
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gtk  # noqa: E402

SLIDES = [
    ('Welcome to MWX 7', 'A dream desktop that blends the best of Windows XP, Windows 7 and macOS, on your own PC.',
     [('Always up to date', 'Settings → Updates brings new versions; security fixes install by themselves.')],
     ['orb']),
    ('Your desktop', 'Everything is a click away, and every window is easy to find.',
     [('Dock', 'Your apps at the bottom; icons grow as you point at them.'),
      ('Start', 'All programs and instant search in one menu.'),
      ('Overview', 'The button in the top bar lays every window out at once.'),
      ('Aero Peek', 'Point at a running app in the dock to preview its windows.')],
     ['computer', 'browser', 'mediaplayer', 'photos', 'settings']),
    ('Files and apps', 'The essentials are all here, and they work together.',
     [('My Computer', 'Browse folders and drives.'), ('Internet', 'Google Chrome, framed in glass like every window.'),
      ('Media Player', 'Listen to Bach, recorded on a real piano.'), ('Photo Viewer', 'Flip through your pictures.')],
     ['computer', 'browser', 'mediaplayer', 'photos']),
    ('Make it yours', 'Open Settings to change how MWX 7 looks.',
     [('Wallpapers', 'Meadows, mountains and more.'), ('Window Color', 'Tint the glass and set its intensity.'),
      ('Widgets', 'Clock, calendar, meters and weather, right on the desktop.')],
     ['settings', 'paint']),
]
CSS = """
window.mwx7-welcome > box { background: #ffffff; }
.wl-art { background: radial-gradient(circle at 50% 35%, #e6f2ff, #bcd8f6 55%, #8fb7e6); }
.wl-title { font-size: 24px; font-weight: 300; color: #1c3150; }
.wl-lead { color: #3c5272; }
.wl-pt-h { font-weight: 700; color: #1c3150; }
.wl-pt { color: #4a5f7d; }
.wl-foot { padding: 10px 16px; border-top: 1px solid #d5dfec; background: #f6f8fb; }
button.wl-dot { min-width: 10px; min-height: 10px; padding: 0; border-radius: 999px; background: #c6d4e6; border: none;
  box-shadow: none; }
button.wl-dot.on { background: #2a72d6; }
"""


def build(app, win):
    win.add_css_class('mwx7-welcome')
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=260, vexpand=True)
    for i, (title, lead, points, art) in enumerate(SLIDES):
        page = Gtk.Box()
        pic = Gtk.Box(halign=Gtk.Align.FILL, spacing=14)
        pic.add_css_class('wl-art')
        pic.set_size_request(280, -1)
        inner = Gtk.FlowBox(max_children_per_line=2 if len(art) > 1 else 1, valign=Gtk.Align.CENTER,
                            halign=Gtk.Align.CENTER, selection_mode=Gtk.SelectionMode.NONE, hexpand=True,
                            row_spacing=14, column_spacing=14)
        for a in art:
            inner.append(mwx7ui.icon(a, 128 if len(art) == 1 else 64))
        pic.append(inner)
        page.append(pic)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=28, margin_start=26, margin_end=26,
                       hexpand=True)
        t = Gtk.Label(label=title, xalign=0)
        t.add_css_class('wl-title')
        text.append(t)
        ld = Gtk.Label(label=lead, xalign=0, wrap=True)
        ld.add_css_class('wl-lead')
        text.append(ld)
        for h, d in points:
            hl = Gtk.Label(label=h, xalign=0, margin_top=6)
            hl.add_css_class('wl-pt-h')
            dl = Gtk.Label(label=d, xalign=0, wrap=True)
            dl.add_css_class('wl-pt')
            text.append(hl)
            text.append(dl)
        page.append(text)
        stack.add_named(page, str(i))
    root.append(stack)

    foot = Gtk.CenterBox()
    foot.add_css_class('wl-foot')
    back = Gtk.Button(label='Back')
    nxt = Gtk.Button(label='Next')
    nxt.add_css_class('suggested-action')
    dots_box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
    dots = []
    state = {'i': 0}

    def go(i):
        state['i'] = i
        stack.set_visible_child_name(str(i))
        back.set_sensitive(i > 0)
        nxt.set_label('Get started' if i == len(SLIDES) - 1 else 'Next')
        for j, d in enumerate(dots):
            (d.add_css_class if j == i else d.remove_css_class)('on')

    for i in range(len(SLIDES)):
        d = Gtk.Button(tooltip_text=SLIDES[i][0], focusable=False)
        d.add_css_class('wl-dot')
        d.connect('clicked', lambda _b, i=i: go(i))
        dots.append(d)
        dots_box.append(d)
    back.connect('clicked', lambda *_: go(state['i'] - 1))

    def forward(*_):
        if state['i'] == len(SLIDES) - 1:
            win.close()
        else:
            go(state['i'] + 1)
    nxt.connect('clicked', forward)
    left = Gtk.Box(spacing=8)
    settings = Gtk.Button(label='Open Settings')
    settings.connect('clicked', lambda *_: subprocess.Popen(['/usr/share/mwx7/settings/mwx7-settings'],
                                                             start_new_session=True))
    left.append(settings)
    right = Gtk.Box(spacing=8)
    right.append(back)
    right.append(nxt)
    foot.set_start_widget(left)
    foot.set_center_widget(dots_box)
    foot.set_end_widget(right)
    root.append(foot)
    go(0)
    return root


if __name__ == '__main__':
    mwx7ui.App('org.mwx7.welcome', 'Welcome', 'about', (720, 480), CSS, build, resizable=False).run_main()
