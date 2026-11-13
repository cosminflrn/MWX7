"""About MWX 7 (native): the concept's About window with this PC's real processor, memory and disk."""
import os
import shutil
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gtk  # noqa: E402

WHATS_NEW = [
    'Smoother: the status bar no longer keeps a processor core busy',
    'Real apps: My Computer, Notepad, Paint, Photos, Media Player, Calculator, Task Manager, Sticky Notes, Snipping Tool',
    'Aero Peek with window thumbnails, Aero Shake, Full Screen into the top bar',
    'Start menu with your most-used programs, jump lists in the dock',
    'Drag icons and gadgets anywhere; Aurora and Dusk themes; Night light',
    'Startup and log-off sounds; network and volume flyouts',
]
CSS = """
window.mwx7-about > box { background: radial-gradient(circle at 50% 0%, #e8f2ff, #ffffff 60%); }
.about-name { font-size: 30px; font-weight: 700; color: #1c3150; }
.about-seven { color: #2a72d6; font-weight: 300; }
.about-tag { color: #4a5f7d; }
.about-key { color: #5a6f8d; }
.about-val { color: #1c3150; }
.about-small { font-size: 11px; color: #7a8696; }
"""


def cpu():
    try:
        for line in open('/proc/cpuinfo'):
            if line.startswith('model name'):
                name = line.split(':', 1)[1]
                for junk in ('(R)', '(TM)', '(tm)', ' CPU', ' Processor'):
                    name = name.replace(junk, '')
                return ' '.join(name.split()) + f' ({os.cpu_count()} threads)'
    except OSError:
        pass
    return f'{os.cpu_count()} threads'


def memory():
    try:
        for line in open('/proc/meminfo'):
            if line.startswith('MemTotal'):
                return f'{int(line.split()[1]) / 1048576:.1f} GB'
    except OSError:
        pass
    return 'Unknown'


def build(app, win):
    win.add_css_class('mwx7-about')
    try:
        version = open('/usr/share/mwx7/version').read().strip()
    except OSError:
        version = ''
    d = shutil.disk_usage('/')
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=14, margin_bottom=12,
                  margin_start=22, margin_end=22)
    box.append(mwx7ui.icon('orb', 84))
    name = Gtk.Label(use_markup=True, label='MWX <span weight="light" foreground="#2a72d6">7</span>')
    name.add_css_class('about-name')
    box.append(name)
    tag = Gtk.Label(label='The dream desktop.')
    tag.add_css_class('about-tag')
    box.append(tag)
    grid = Gtk.Grid(column_spacing=12, row_spacing=3, halign=Gtk.Align.CENTER, margin_top=10)
    rows = [('Version', f'{version or "?"} “Luna”'), ('Processor', cpu()), ('Memory', memory()),
            ('Storage', f'{d.free / 1e9:.0f} GB free of {d.total / 1e9:.0f} GB'), ('Built by', 'Cosmin & Claude')]
    for i, (k, v) in enumerate(rows):
        kl = Gtk.Label(label=k, xalign=1)
        kl.add_css_class('about-key')
        vl = Gtk.Label(label=v, xalign=0, wrap=True, max_width_chars=34)
        vl.add_css_class('about-val')
        grid.attach(kl, 0, i, 1, 1)
        grid.attach(vl, 1, i, 1, 1)
    box.append(grid)
    new = Gtk.Expander(label=f'What’s new in {version or "this version"}', halign=Gtk.Align.CENTER, margin_top=8)
    lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=4)
    for t in WHATS_NEW:
        lst.append(Gtk.Label(label='• ' + t, xalign=0, wrap=True, max_width_chars=48))
    new.set_child(lst)
    box.append(new)
    small = Gtk.Label(label='Icons: Crystal Clear (LGPL, Everaldo Coelho) · Font: Selawik (OFL) · '
                            'Photos: Pexels · Sounds: FluidR3 (MIT)', wrap=True, justify=Gtk.Justification.CENTER,
                      max_width_chars=52, vexpand=True, valign=Gtk.Align.END)
    small.add_css_class('about-small')
    box.append(small)
    return box


if __name__ == '__main__':
    mwx7ui.App('org.mwx7.about', 'About MWX 7', 'about', (420, 540), CSS, build, resizable=False).run_main()
