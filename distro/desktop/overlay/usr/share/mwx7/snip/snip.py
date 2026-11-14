"""MWX 7 Snipping Tool (GTK 4), after Windows 7's: a snip is taken (grim + slurp) and opens in an editor with a pen,
a highlighter, an eraser and crop; Copy puts the picture on the clipboard (wl-copy), Save writes a PNG.

  snip.py                          opens the tool
  snip.py --capture region|window|full [--delay N]
                                   snips at once (Print, Shift+Print, Alt+Print): a dragged rectangle, the focused window
                                   (from Wayfire's IPC) or the whole screen. N is 0-5 seconds.
  snip.py --open FILE              edits a picture
  snip.py --record                 starts a screen recording (see record.py; Shift+Super+R does it from the keyboard)

Every snip is also copied to the clipboard and announced in a notification, as Windows 7 did."""
import json
import math
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, '/usr/share/mwx7/lib')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwx7ui  # noqa: E402
from mwx7ui import FileDialog, Gdk, Gio, GLib, Gtk  # noqa: E402
import cairo  # noqa: E402

# (id, menu label): what the arrow next to New offers. 'pick' is the click-a-window kind; --capture window takes the
# focused one, since a key press has no pointer to click with.
MODES = [('region', 'Rectangular Snip'), ('pick', 'Window Snip'), ('full', 'Full-screen Snip')]
CLI_MODES = {'region': 'region', 'rect': 'region', 'window': 'focused', 'full': 'full'}
PEN_COLORS = [('Red', '#e02020'), ('Orange', '#f08a1c'), ('Green', '#2a9d3a'), ('Blue', '#1e64dc'),
              ('Purple', '#7b3fc4'), ('Black', '#111111')]
HIGHLIGHT = (1.0, 0.93, 0.0)
CSS = """
window.mwx7-snip .snip-bar { padding: 6px 8px; border-bottom: 1px solid #d5dfec;
  background: linear-gradient(to bottom, #fbfdff, #e9f0f9); }
window.mwx7-snip .snip-bar button { padding: 3px 9px; min-height: 0; border-radius: 4px; border: 1px solid transparent;
  background: none; box-shadow: none; color: #1c3150; }
window.mwx7-snip .snip-bar button:hover { border-color: #a8c6ec; background: linear-gradient(to bottom, #f4f9ff, #dbeafc); }
window.mwx7-snip .snip-bar button:checked { border-color: #7aa6dc; background: linear-gradient(to bottom, #dbeafc, #bcd6f6); }
window.mwx7-snip .snip-bar button:disabled { opacity: .45; }
window.mwx7-snip .snip-bar button.snip-swatch { padding: 0; min-width: 14px; min-height: 18px; border-radius: 9px;
  border: 1px solid #6c7f9c; margin: 0 1px; }
window.mwx7-snip .snip-bar button.snip-swatch:checked { border: 2px solid #1c3150; }
window.mwx7-snip .snip-bar.rec { border-top: 0; padding-top: 4px; }
window.mwx7-snip .snip-bar button.snip-record { color: #8f1410; font-weight: 600; }
window.mwx7-snip .snip-stage { background: #eef2f7; }
window.mwx7-snip .snip-empty { color: #5a6f8d; }
window.mwx7-snip .snip-empty-title { font-weight: 700; font-size: 15px; color: #1c3150; }
window.mwx7-snip .snip-foot { padding: 4px 10px; font-size: 12px; color: #4a5f7d; border-top: 1px solid #d5dfec;
  background: #f6f8fb; }
"""


def wayfire_views():
    """Wayfire's list of windows over its IPC socket (what the shell and Task Manager read too)."""
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
            chunk = s.recv(n - len(buf))
            if not chunk:
                break
            buf += chunk
        return json.loads(buf)
    except (OSError, ValueError, struct.error):
        return []


def visible_toplevels(views):
    return [v for v in views if v.get('role') == 'toplevel' and v.get('mapped', True) and not v.get('minimized')
            and (v.get('geometry') or {}).get('width')]


def geometry(v):
    g = v['geometry']
    return f"{g['x']},{g['y']} {g['width']}x{g['height']}"


def focused_geometry(views):
    for v in visible_toplevels(views):
        if v.get('activated'):
            return geometry(v)
    return None


def seg_dist(p, a, b):
    """Distance from point p to the segment a-b: what the eraser tests marks with."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def rgb(hexcolor):
    return tuple(int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5))


def paint_strokes(cr, strokes):
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    for s in strokes:
        pts = s['pts']
        cr.save()
        if s['kind'] == 'hl':
            # Multiplied, so text under the marker stays readable, as with a real highlighter.
            cr.set_operator(cairo.OPERATOR_MULTIPLY)
            cr.set_line_cap(cairo.LINE_CAP_SQUARE)
        else:
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgb(*s['color'])
        cr.set_line_width(s['width'])
        cr.move_to(*pts[0])
        if len(pts) == 1:
            cr.line_to(pts[0][0] + 0.01, pts[0][1])
        for p in pts[1:]:
            cr.line_to(*p)
        cr.stroke()
        cr.restore()


class Snip(mwx7ui.App):
    def __init__(self):
        super().__init__('org.mwx7.snip', 'Snipping Tool', 'snip', (640, 460), CSS, lambda app, w: self.build_ui(w))
        # --capture and --open arrive as arguments, also when the tool is already running.
        self.set_flags(Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.mode, self.delay, self.tool_id = 'region', 0, 'pen'
        self.color, self.base, self.strokes, self.undo_stack = PEN_COLORS[0][1], None, [], []
        self.current, self.crop_rect, self.file, self.busy = None, None, None, False

    # ---- command line ------------------------------------------------------------------------------------------------
    def do_command_line(self, cl):
        argv = cl.get_arguments()[1:]
        capture, delay, open_file, i = None, None, None, 0
        while i < len(argv):
            a = argv[i]
            nxt = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith('--') else None
            if a == '--capture':
                capture = nxt or 'region'
            elif a == '--delay' and nxt is not None:
                delay = nxt
            elif a == '--open' and nxt is not None:
                open_file = nxt
            i += 2 if a in ('--capture', '--delay', '--open') and nxt is not None else 1
        if '--record' in argv:
            self.activate()
            self.record()
            return 0
        if capture is not None and capture not in CLI_MODES:
            cl.printerr(f'snip: unknown capture "{capture}" (region, window or full)\n')
            return 2
        try:
            secs = max(0, min(5, int(delay))) if delay is not None else None
        except ValueError:
            cl.printerr('snip: --delay takes a number of seconds, 0 to 5\n')
            return 2
        self.activate()
        if open_file:
            self.load(open_file)
        if capture:
            self.start(CLI_MODES[capture], self.delay if secs is None else secs)
        return 0

    # ---- window ------------------------------------------------------------------------------------------------------
    def build_ui(self, w):
        w.add_css_class('mwx7-snip')
        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class('snip-foot')
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(self.menubar([
            ('File', [('New Snip', 'new', self.new_snip), ('Save As...', 'save', self.save), ('Copy', 'copy', self.copy),
                      None, ('Exit', 'quit', lambda: self.win.close())]),
            ('Edit', [('Undo', 'undo', self.undo), ('Copy', 'copy2', self.copy)]),
            ('Tools', [('Pen', 'pen', lambda: self.pick_tool('pen')), ('Highlighter', 'hl', lambda: self.pick_tool('hl')),
                       ('Eraser', 'eraser', lambda: self.pick_tool('eraser')),
                       ('Crop', 'crop', lambda: self.pick_tool('crop'))]),
        ]))
        bar = Gtk.Box(spacing=3)
        bar.add_css_class('snip-bar')
        self.new_btn = self.button('New', 'document-new-symbolic', self.new_snip)
        bar.append(self.new_btn)
        mode_btn = Gtk.MenuButton(tooltip_text='Snip type')
        menu = Gio.Menu()
        for mid, label in MODES:
            menu.append(label, f'app.mode::{mid}')
        act = Gio.SimpleAction.new_stateful('mode', GLib.VariantType.new('s'), GLib.Variant('s', self.mode))
        act.connect('activate', self.on_mode)
        self.add_action(act)
        mode_btn.set_menu_model(menu)
        bar.append(mode_btn)
        # Delay 0-5 s before the snip, as Windows 7's Delay menu.
        self.delay_dd = Gtk.DropDown.new_from_strings(['No delay'] + [f'Delay {n} s' for n in range(1, 6)])
        self.delay_dd.set_tooltip_text('Wait before snipping')
        self.delay_dd.connect('notify::selected', lambda d, _p: setattr(self, 'delay', d.get_selected()))
        bar.append(self.delay_dd)
        bar.append(self.divider())
        self.tool_btns = {}
        first = None
        for tid, label, icon in (('pen', 'Pen', 'document-edit-symbolic'), ('hl', 'Highlighter', 'format-text-bold-symbolic'),
                                 ('eraser', 'Eraser', 'edit-clear-symbolic'), ('crop', 'Crop', 'edit-cut-symbolic')):
            b = Gtk.ToggleButton()
            b.set_child(self.label_box(label, icon))
            if first:
                b.set_group(first)
            first = first or b
            b.connect('toggled', lambda btn, t=tid: btn.get_active() and self.pick_tool(t))
            self.tool_btns[tid] = b
            bar.append(b)
        self.tool_btns['pen'].set_active(True)
        # Pen colours: a few swatches, and any colour from the dialog.
        self.swatches = Gtk.Box(spacing=0)
        sw_first = None
        for name, hexc in PEN_COLORS:
            b = Gtk.ToggleButton(tooltip_text=name)
            b.add_css_class('snip-swatch')
            mwx7ui.css(f'window.mwx7-snip button.snip-swatch.c{hexc[1:]} {{ background: {hexc}; }}', 5)
            b.add_css_class('c' + hexc[1:])
            if sw_first:
                b.set_group(sw_first)
            sw_first = sw_first or b
            b.connect('toggled', lambda btn, c=hexc: btn.get_active() and self.pick_color(c))
            self.swatches.append(b)
            if hexc == self.color:
                b.set_active(True)
        bar.append(self.swatches)
        custom = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(), tooltip_text='Other colour')
        custom.connect('notify::rgba', lambda b, _p: self.pick_color(b.get_rgba().to_string(), True))
        bar.append(custom)
        bar.append(self.divider())
        self.undo_btn = self.button('Undo', 'edit-undo-symbolic', self.undo)
        self.copy_btn = self.button('Copy', 'edit-copy-symbolic', self.copy)
        self.save_btn = self.button('Save', 'document-save-symbolic', self.save)
        for b in (self.undo_btn, self.copy_btn, self.save_btn):
            b.set_sensitive(False)
            bar.append(b)
        root.append(bar)
        root.append(self.record_bar())

        self.stage = Gtk.Stack(vexpand=True)
        self.stage.add_css_class('snip-stage')
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        empty.add_css_class('snip-empty')
        pic = Gtk.Image.new_from_file('/usr/share/mwx7/icons/snip.png')
        pic.set_pixel_size(64)
        t = Gtk.Label(label='No snip yet')
        t.add_css_class('snip-empty-title')
        for c in (pic, t, Gtk.Label(label='Click New and drag around what you want to capture, or press Print.')):
            empty.append(c)
        self.stage.add_named(empty, 'empty')
        self.area = Gtk.DrawingArea(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.area.set_margin_top(10)
        self.area.set_margin_bottom(10)
        self.area.set_margin_start(10)
        self.area.set_margin_end(10)
        self.area.set_draw_func(self.draw)
        drag = Gtk.GestureDrag(button=1)
        drag.connect('drag-begin', self.drag_begin)
        drag.connect('drag-update', self.drag_update)
        drag.connect('drag-end', self.drag_end)
        self.area.add_controller(drag)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_child(self.area)
        self.stage.add_named(scroll, 'shot')
        root.append(self.stage)
        root.append(self.status)
        self.say('Click New to snip, or press Print. The arrow picks rectangle, window or full screen.')
        return root

    def record_bar(self):
        """Record mode, as Windows 11's: what to film, which sound to take along, and the Record button."""
        import record  # the same module Shift+Super+R runs, so the saved choices are shared
        prefs = record.load_prefs()
        bar = Gtk.Box(spacing=6)
        bar.add_css_class('snip-bar')
        bar.add_css_class('rec')
        self.rec_area = Gtk.DropDown.new_from_strings(['Region', 'Full screen'])
        self.rec_area.set_selected(0 if prefs['mode'] == 'region' else 1)
        self.rec_area.set_tooltip_text('What to record')
        self.rec_audio = Gtk.DropDown.new_from_strings(['No audio', 'Microphone', 'System audio'])
        self.rec_audio.set_selected(['none', 'mic', 'system'].index(prefs['audio']))
        self.rec_audio.set_tooltip_text('Sound to record with the screen')
        btn = self.button('Record', 'media-record-symbolic', self.record)
        btn.add_css_class('snip-record')
        for c in (btn, self.rec_area, self.rec_audio):
            bar.append(c)
        hint = Gtk.Label(label='Shift+Super+R starts and stops', hexpand=True, xalign=1)
        hint.add_css_class('snip-empty')
        bar.append(hint)
        return bar

    def record(self):
        mode = 'region' if self.rec_area.get_selected() == 0 else 'full'
        audio = ['none', 'mic', 'system'][self.rec_audio.get_selected()]
        subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'record.py'), 'start',
                          '--' + mode, '--audio', audio], start_new_session=True, stdin=subprocess.DEVNULL)
        self.win.close()  # out of the picture; the pill takes over

    def divider(self):
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_start(4)
        sep.set_margin_end(4)
        return sep

    def label_box(self, label, icon):
        box = Gtk.Box(spacing=5)
        box.append(Gtk.Image.new_from_icon_name(icon))
        box.append(Gtk.Label(label=label))
        return box

    def button(self, label, icon, fn):
        b = Gtk.Button()
        b.set_child(self.label_box(label, icon))
        b.connect('clicked', lambda *_: fn())
        return b

    def say(self, text):
        self.status.set_label(text)

    def on_mode(self, action, value):
        action.set_state(value)
        self.mode = value.get_string()
        self.say(f'{dict(MODES)[self.mode]}: click New to capture.')

    def pick_tool(self, tid):
        self.tool_id = tid
        self.tool_btns[tid].set_active(True)
        if not hasattr(self, 'area'):  # the toolbar is still being built
            return
        self.area.set_cursor_from_name('cell' if tid == 'eraser' else 'crosshair')
        self.say({'pen': 'Pen: drag on the snip to draw.', 'hl': 'Highlighter: drag over text to mark it.',
                  'eraser': 'Eraser: drag over a pen or highlighter mark to remove it.',
                  'crop': 'Crop: drag the part of the snip to keep.'}[tid])

    def pick_color(self, color, custom=False):
        if custom:
            c = Gdk.RGBA()
            c.parse(color)
            color = '#%02x%02x%02x' % tuple(round(v * 255) for v in (c.red, c.green, c.blue))
        self.color = color
        if self.tool_id != 'pen':
            self.pick_tool('pen')

    # ---- capturing ---------------------------------------------------------------------------------------------------
    def new_snip(self):
        self.start(self.mode, self.delay)

    def start(self, mode, delay):
        if self.busy:
            return
        self.busy = True
        self.hold()
        # Out of the way first, so the snip shows what is behind this window, then back with the result.
        self.win.set_visible(False)
        GLib.timeout_add(350 + 1000 * delay, self.grab, mode)

    def finish_failed(self, text):
        self.win.set_visible(True)
        self.win.present()
        self.say(text)
        self.busy = False
        self.release()
        return False

    def grab(self, mode):
        out = os.path.join(tempfile.gettempdir(), f'mwx7-snip-{os.getuid()}-{int(time.time())}.png')
        try:
            if mode == 'full':
                cmd = ['grim', out]
            elif mode == 'focused':
                area = focused_geometry(wayfire_views())
                if not area:
                    return self.finish_failed('There is no window to snip.')
                cmd = ['grim', '-g', area, out]
            else:
                pick = mode == 'pick'
                area = subprocess.run(['slurp', '-d', '-b', '#1e64dc22', '-c', '#1e64dcff', '-w', '2'] + (['-r'] if pick else []),
                                      input='\n'.join(geometry(v) for v in visible_toplevels(wayfire_views())) if pick else None,
                                      capture_output=True, text=True, timeout=120)
                if area.returncode != 0 or not area.stdout.strip():
                    return self.finish_failed('No snip taken.')
                cmd = ['grim', '-g', area.stdout.strip(), out]
            subprocess.run(cmd, check=True, timeout=20, capture_output=True)
        except (OSError, subprocess.SubprocessError) as e:
            return self.finish_failed(f'The snip did not work ({e.__class__.__name__}).')
        self.busy = False
        self.release()
        self.load(out)
        # As in Windows 7, a snip is on the clipboard at once; the notification shows what was taken.
        if self.copy(quiet=True):
            subprocess.Popen(['notify-send', '-a', 'Snipping Tool', '-i', out, 'Screenshot copied',
                              'Paste it anywhere, or mark it up and save it in Snipping Tool.'],
                             stderr=subprocess.DEVNULL)
        return False

    def load(self, path):
        try:
            surf = cairo.ImageSurface.create_from_png(path)
        except (OSError, cairo.Error):
            self.say('That picture could not be opened.')
            return
        self.file, self.base, self.strokes, self.undo_stack = path, surf, [], []
        self.show_image()
        self.win.set_visible(True)
        self.win.present()
        self.say(f'Snip taken ({surf.get_width()} x {surf.get_height()}). Mark it up, then save or copy it.')

    def show_image(self):
        self.area.set_content_width(self.base.get_width())
        self.area.set_content_height(self.base.get_height())
        self.stage.set_visible_child_name('shot')
        for b in (self.save_btn, self.copy_btn):
            b.set_sensitive(True)
        self.undo_btn.set_sensitive(bool(self.undo_stack))
        self.area.queue_draw()

    # ---- editing -----------------------------------------------------------------------------------------------------
    def draw(self, _a, cr, _w, _h):
        if not self.base:
            return
        cr.set_source_surface(self.base, 0, 0)
        cr.paint()
        paint_strokes(cr, self.strokes + ([self.current] if self.current else []))
        if self.crop_rect:
            x, y, w, h = self.crop_rect
            cr.set_source_rgba(0, 0, 0, 0.45)
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.rectangle(0, 0, self.base.get_width(), self.base.get_height())
            cr.rectangle(x, y, w, h)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.set_dash([5, 4])
            cr.set_line_width(1)
            cr.rectangle(x + .5, y + .5, w, h)
            cr.stroke()

    def push_undo(self):
        self.undo_stack.append((self.base, list(self.strokes)))
        self.undo_btn.set_sensitive(True)

    def drag_begin(self, _g, x, y):
        if not self.base:
            return
        self.start_pt = (x, y)
        if self.tool_id in ('pen', 'hl'):
            hl = self.tool_id == 'hl'
            self.current = {'kind': self.tool_id, 'color': HIGHLIGHT if hl else rgb(self.color),
                            'width': 16 if hl else 3, 'pts': [(x, y)]}
        elif self.tool_id == 'eraser':
            self.erased = False
            self.erase_at(x, y)
        else:
            self.crop_rect = (x, y, 0, 0)
        self.area.queue_draw()

    def drag_update(self, _g, dx, dy):
        if not self.base:
            return
        x, y = self.start_pt[0] + dx, self.start_pt[1] + dy
        if self.current:
            self.current['pts'].append((x, y))
        elif self.tool_id == 'eraser':
            self.erase_at(x, y)
        elif self.crop_rect:
            x0, y0 = self.start_pt
            self.crop_rect = (min(x0, x), min(y0, y), abs(x - x0), abs(y - y0))
        self.area.queue_draw()

    def drag_end(self, _g, _dx, _dy):
        if not self.base:
            return
        if self.current:
            self.push_undo()
            self.strokes.append(self.current)
            self.current = None
        elif self.crop_rect:
            rect, self.crop_rect = self.crop_rect, None
            self.apply_crop(*rect)
        self.area.queue_draw()

    def erase_at(self, x, y):
        """Removes every mark the eraser touches, whole, as Windows 7's did."""
        keep = []
        for s in self.strokes:
            pts, reach = s['pts'], s['width'] / 2 + 6
            hit = any(seg_dist((x, y), pts[i], pts[min(i + 1, len(pts) - 1)]) <= reach for i in range(len(pts)))
            if hit and not self.erased:
                self.push_undo()
                self.erased = True
            if not hit:
                keep.append(s)
        self.strokes = keep

    def apply_crop(self, x, y, w, h):
        x, y, w, h = int(x), int(y), int(w), int(h)
        if w < 4 or h < 4:
            return
        self.push_undo()
        out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(out)
        cr.set_source_surface(self.render(), -x, -y)
        cr.paint()
        self.base, self.strokes = out, []
        self.show_image()
        self.say(f'Cropped to {w} x {h}.')

    def undo(self):
        if not self.undo_stack:
            return
        self.base, self.strokes = self.undo_stack.pop()
        self.show_image()

    def render(self):
        """The snip with its marks flattened into one picture."""
        out = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.base.get_width(), self.base.get_height())
        cr = cairo.Context(out)
        cr.set_source_surface(self.base, 0, 0)
        cr.paint()
        paint_strokes(cr, self.strokes)
        return out

    # ---- Copy and Save -----------------------------------------------------------------------------------------------
    def copy(self, quiet=False):
        if not self.base:
            return False
        path = os.path.join(tempfile.gettempdir(), f'mwx7-snip-{os.getuid()}-edit.png')
        try:
            self.render().write_to_png(path)
            with open(path, 'rb') as f:
                subprocess.run(['wl-copy', '--type', 'image/png'], stdin=f, timeout=5, check=True)
        except (OSError, subprocess.SubprocessError, cairo.Error):
            self.say('Copying did not work.')
            return False
        if not quiet:
            self.say('Copied. Paste it into Paint, a document or a chat.')
        return True

    def save(self):
        if not self.base:
            return
        pics = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) or os.path.expanduser('~/Pictures')
        os.makedirs(pics, exist_ok=True)
        dlg = FileDialog(title='Save As', initial_name=time.strftime('Snip %Y-%m-%d %H-%M-%S.png'),
                         initial_folder=Gio.File.new_for_path(pics))

        def done(d, res):
            try:
                dest = d.save_finish(res)
            except GLib.Error:
                return
            path = dest.get_path()
            if not path.lower().endswith('.png'):
                path += '.png'
            try:
                self.render().write_to_png(path)
            except (OSError, cairo.Error):
                self.say('The snip could not be saved there.')
                return
            self.say(f'Saved as {os.path.basename(path)}.')
        dlg.save(self.win, None, done)


if __name__ == '__main__':
    sys.exit(Snip().run(sys.argv))
