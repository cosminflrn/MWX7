"""Paint (native): the concept's Windows 7-style Paint: a ribbon of tools (select, pencil, brush, eraser, fill, colour
picker, text, magnifier), shapes (line, arrow, rectangle, rounded rectangle, oval; outline and/or fill), sizes, two
colours from a palette or any colour, a text tool that stays editable until it is put down, rectangular selections
(move, cut/copy/paste, delete, crop), zoom (Ctrl+wheel, slider, fit), undo/redo, Resize and Skew, and PNG/JPEG/BMP
files. Left button paints with colour 1, right button with colour 2."""
import math
import os
import re
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk  # noqa: E402
import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version('GdkPixbuf', '2.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import GdkPixbuf, Pango, PangoCairo  # noqa: E402

PALETTE = ['#000000', '#7f7f7f', '#880015', '#ed1c24', '#ff7f27', '#fff200', '#22b14c', '#00a2e8', '#3f48cc', '#a349a4',
           '#ffffff', '#c3c3c3', '#b97a57', '#ffaec9', '#ffc90e', '#efe4b0', '#b5e61d', '#99d9ea', '#7092be', '#c8bfe7']
TOOLS = [('select', 'Select'), ('pencil', 'Pencil'), ('brush', 'Brush'), ('eraser', 'Eraser'), ('fill', 'Fill with color'),
         ('picker', 'Color picker'), ('text', 'Text'), ('magnifier', 'Magnifier')]
SHAPES = [('line', 'Line'), ('arrow', 'Arrow'), ('rect', 'Rectangle'), ('round', 'Rounded rectangle'), ('ellipse', 'Oval')]
SIZES = [1, 3, 5, 8]
ZOOM_MIN, ZOOM_MAX = 0.1, 16.0
# Undo/redo keep whole-image copies; this caps what they may hold together (a 4000 x 3000 image is 48 MB per step).
HISTORY_BYTES = 256 * 1024 * 1024
HISTORY_STEPS = 100
MAX_PIXELS = 64_000_000
CSS = """
window.mwx7-paint > box { background: #ffffff; }
.pt-ribbon { padding: 6px 8px 4px; background: linear-gradient(180deg, #fbfdff 0%, #eef4fb 60%, #dfe9f5 100%); }
.pt-ribbon-scroll { border-bottom: 1px solid #b6c6da; }
.pt-group { padding: 0 8px; border-right: 1px solid #c8d5e6; }
.pt-group-label { font-size: 10px; color: #5a6f8d; margin-top: 2px; }
.pt-cap { font-size: 10px; color: #1c3150; }
.pt-ribbon button { min-width: 26px; min-height: 26px; padding: 2px; border-radius: 3px; border: 1px solid transparent;
  background: none; box-shadow: none; color: #1c3150; }
.pt-ribbon button:hover { border-color: #a8c6ec; background: linear-gradient(180deg, #f4f9ff, #dbeafc); }
.pt-ribbon button.on, .pt-ribbon button:checked { border-color: #6e9fd8; background: linear-gradient(180deg, #e2efff, #bcd7f6); }
.pt-ribbon button:disabled { opacity: 0.4; }
.pt-ribbon button.pt-tall { padding: 2px 4px; }
.pt-ribbon dropdown button, .pt-ribbon dropdown button:hover { min-height: 22px; padding: 0 4px; }
.pt-ribbon spinbutton { min-height: 22px; }
.pt-ribbon button.pt-tog { font-weight: bold; min-width: 24px; }
.pt-ribbon button.pt-tog-i { font-style: italic; }
button.pt-swatch { min-width: 18px; min-height: 18px; padding: 0; border: 1px solid #8a9bb2; border-radius: 1px; }
button.pt-big { min-width: 34px; min-height: 34px; padding: 0; border: 1px solid #8a9bb2; border-radius: 2px; }
.pt-size-line { background: #1c3150; }
.pt-canvas-bg { background: #c9d6e8; }
.pt-status { padding: 2px 10px; font-size: 11px; color: #4a5f7d; border-top: 1px solid #d5dfec; background: #f0f4fa; }
.pt-status button { min-height: 16px; min-width: 16px; padding: 0 5px; font-size: 11px; border-radius: 3px;
  border: 1px solid transparent; background: none; box-shadow: none; color: #1c3150; }
.pt-status button:hover { border-color: #a8c6ec; background: linear-gradient(180deg, #f4f9ff, #dbeafc); }
.pt-status scale { min-width: 120px; }
"""
TEXT_CSS = """
.mwx7-paint textview.pt-text-edit, .mwx7-paint textview.pt-text-edit text { background: transparent; color: %(color)s;
  font-family: '%(family)s'; font-size: %(px)dpx; font-weight: %(weight)s; font-style: %(style)s; padding: 0; margin: 0; }
.mwx7-paint textview.pt-text-edit { outline: 1px dashed #3a78d0; outline-offset: 3px; caret-color: %(color)s; }
"""


def rgba(hexc):
    c = Gdk.RGBA()
    c.parse(hexc)
    return c


def hexof(c):
    return '#%02x%02x%02x' % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))


def cost(s):
    return s.get_width() * s.get_height() * 4


class Paint:
    def __init__(self):
        self.w, self.h = 800, 560
        self.surface = self.blank(self.w, self.h)
        self.undo_stack, self.redo_stack = [], []
        self.tool, self.shape, self.size = 'pencil', None, 3
        self.prev_tool = ('pencil', None)
        self.outline, self.fill = True, False
        self.color1, self.color2 = rgba('#000000'), rgba('#ffffff')
        self.zoom = 1.0
        self.path, self.dirty = None, False
        self.drag = None
        self.sel = None          # (x, y, w, h) on the canvas
        self.clip = None         # a cairo surface: the copied selection
        self.floating = None     # (surface, x, y): a pasted or moved selection not yet put down
        self.tv = None           # the live text box (a Gtk.TextView over the canvas) until it is committed
        self.tx = None           # (x, y) of that text box on the canvas
        self.font_family, self.font_px, self.bold, self.italic = 'Sans', 24, False, False
        self.ptr = None          # last pointer position over the canvas (widget px), the anchor for Ctrl+wheel zoom
        self.zsync = False

    @staticmethod
    def blank(w, h, color=None):
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(s)
        if color is None:
            cr.set_source_rgb(1, 1, 1)
        else:
            cr.set_source_rgb(color.red, color.green, color.blue)
        cr.paint()
        return s

    # ---- UI -------------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-paint')
        self.text_css = mwx7ui.css('', 5)
        app.on_open = lambda files: self.guard(lambda: self.load(files[0].get_path()))
        actions = [
            ('File', [('New', 'new', lambda: self.guard(self.new), '<Control>n'),
                      ('Open…', 'open', lambda: self.guard(self.open), '<Control>o'),
                      ('Save', 'save', self.save, '<Control>s'), ('Save As…', 'saveas', self.save_as, '<Control><Shift>s'),
                      None, ('Exit', 'exit', win.close, None)]),
            ('Edit', [('Undo', 'undo', self.undo, '<Control>z'), ('Redo', 'redo', self.redo, '<Control>y'), None,
                      ('Cut', 'cut', self.cut, '<Control>x'), ('Copy', 'copy', self.copy, '<Control>c'),
                      ('Paste', 'paste', self.paste, '<Control>v'), ('Delete', 'delete', self.delete_sel, 'Delete'),
                      None, ('Select All', 'selectall', self.select_all, '<Control>a'),
                      ('Crop to Selection', 'crop', self.crop, '<Control><Shift>x')]),
            ('Image', [('Resize and Skew…', 'resize', self.resize_dialog, '<Control>e'),
                       ('Rotate Right', 'rotr', lambda: self.rotate(90), None), ('Rotate Left', 'rotl', lambda: self.rotate(-90), None),
                       ('Flip Horizontal', 'fliph', lambda: self.flip(True), None),
                       ('Flip Vertical', 'flipv', lambda: self.flip(False), None),
                       None, ('Canvas Size…', 'canvas', self.canvas_dialog, None)]),
            ('View', [('Zoom In', 'zin', lambda: self.zoom_at(self.zoom * 1.25), '<Control>plus'),
                      ('Zoom Out', 'zout', lambda: self.zoom_at(self.zoom / 1.25), '<Control>minus'),
                      ('100%', 'z100', lambda: self.zoom_at(1.0), '<Control>0'),
                      ('Fit to Window', 'zfit', self.fit, '<Control>9')]),
        ]
        menus = []
        for label, items in actions:
            menus.append((label, [None if it is None else it[:3] for it in items]))
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar(menus))
        for _label, items in actions:
            for it in items:
                if it and it[3]:
                    app.set_accels_for_action('app.' + it[1], [it[3]])
        app.set_accels_for_action('app.zin', ['<Control>plus', '<Control>equal', '<Control>KP_Add'])
        app.set_accels_for_action('app.zout', ['<Control>minus', '<Control>KP_Subtract'])
        rb = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC, vscrollbar_policy=Gtk.PolicyType.NEVER,
                                propagate_natural_height=True)
        rb.add_css_class('pt-ribbon-scroll')
        rb.set_child(self.ribbon())
        root.append(rb)
        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self.draw)
        self.area.set_halign(Gtk.Align.START)
        self.area.set_valign(Gtk.Align.START)
        self.resize_area()
        for button in (1, 3):
            g = Gtk.GestureDrag(button=button)
            g.connect('drag-begin', self.on_begin, button)
            g.connect('drag-update', self.on_update, button)
            g.connect('drag-end', self.on_end, button)
            self.area.add_controller(g)
        motion = Gtk.EventControllerMotion()
        motion.connect('motion', self.on_motion)
        self.area.add_controller(motion)
        # The text box is laid over the canvas, so the canvas and the box scroll and zoom as one.
        self.overlay = Gtk.Overlay(halign=Gtk.Align.START, valign=Gtk.Align.START, margin_top=6, margin_start=6,
                                   margin_end=6, margin_bottom=6)
        self.overlay.set_child(self.area)
        bg = Gtk.Box()
        bg.add_css_class('pt-canvas-bg')
        bg.append(self.overlay)
        self.sc = Gtk.ScrolledWindow(vexpand=True)
        self.sc.set_child(bg)
        wheel = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        wheel.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        wheel.connect('scroll', self.on_wheel)
        self.sc.add_controller(wheel)
        root.append(self.sc)
        root.append(self.statusbar())
        win.connect('close-request', self.on_close)
        self.closing_ok = False
        if app.files:
            GLib.idle_add(lambda: self.load(app.files[0].get_path()) and False)
        self.retitle()
        self.set_zoom(1.0)
        return root

    def statusbar(self):
        bar = Gtk.Box(spacing=2)
        bar.add_css_class('pt-status')
        self.status = Gtk.Label(xalign=0, hexpand=True, label=f'{self.w} × {self.h}px')
        bar.append(self.status)
        for text, tip, fn in (('Fit', 'Fit to window', self.fit), ('100%', 'Actual size', lambda: self.zoom_at(1.0)),
                              ('−', 'Zoom out', lambda: self.zoom_at(self.zoom / 1.25))):
            b = Gtk.Button(label=text, tooltip_text=tip, focusable=False)
            b.connect('clicked', lambda _b, f=fn: f())
            bar.append(b)
        self.zscale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, math.log2(ZOOM_MIN), math.log2(ZOOM_MAX), 0.02)
        self.zscale.set_draw_value(False)
        self.zscale.set_focusable(False)
        self.zscale.connect('value-changed', lambda s: None if self.zsync else self.zoom_at(2 ** s.get_value()))
        bar.append(self.zscale)
        plus = Gtk.Button(label='+', tooltip_text='Zoom in', focusable=False)
        plus.connect('clicked', lambda _b: self.zoom_at(self.zoom * 1.25))
        bar.append(plus)
        self.zlabel = Gtk.Label(label='100%', width_chars=5, xalign=1)
        bar.append(self.zlabel)
        return bar

    def group(self, label, child):
        g = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        g.add_css_class('pt-group')
        # Centred in the room above the caption, so every group's label sits on one baseline.
        child.set_vexpand(True)
        child.set_valign(Gtk.Align.CENTER)
        g.append(child)
        lab = Gtk.Label(label=label)
        lab.add_css_class('pt-group-label')
        g.append(lab)
        return g

    def ibtn(self, icon, tip, fn, size=18, caption=None, toggle=False):
        """A ribbon button with one of MWX 7's drawn glyphs (and a caption beneath it for the big ones)."""
        b = Gtk.ToggleButton(focusable=False, tooltip_text=tip) if toggle else Gtk.Button(focusable=False, tooltip_text=tip)
        da = Gtk.DrawingArea(content_width=size, content_height=size)
        da.set_draw_func(self.tool_icon, icon)
        if caption:
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            v.append(da)
            v.append(Gtk.Label(label=caption, css_classes=['pt-cap']))
            b.set_child(v)
            b.add_css_class('pt-tall')
        else:
            b.set_child(da)
        if fn:
            b.connect('clicked', lambda _b: fn())
        return b

    def ribbon(self):
        r = Gtk.Box(vexpand=False, valign=Gtk.Align.START)
        r.add_css_class('pt-ribbon')
        self.tool_btns = {}
        # Edit: clipboard and history
        g = Gtk.Grid(row_spacing=2, column_spacing=2)
        paste = self.ibtn('paste', 'Paste (Ctrl+V)', self.paste, 24, 'Paste')
        paste.set_vexpand(True)
        g.attach(paste, 0, 0, 1, 2)
        for i, (icon, tip, fn) in enumerate((('cut', 'Cut (Ctrl+X)', self.cut), ('copy', 'Copy (Ctrl+C)', self.copy),
                                              ('undo', 'Undo (Ctrl+Z)', self.undo), ('redo', 'Redo (Ctrl+Y)', self.redo))):
            g.attach(self.ibtn(icon, tip, fn), 1 + i // 2, i % 2, 1, 1)
        r.append(self.group('Edit', g))
        # Image
        g = Gtk.Grid(row_spacing=2, column_spacing=2)
        for i, (icon, tip, fn) in enumerate((('crop', 'Crop to selection', self.crop), ('resize', 'Resize and skew…', self.resize_dialog),
                                              ('rotate', 'Rotate right', lambda: self.rotate(90)),
                                              ('flip', 'Flip horizontal', lambda: self.flip(True)))):
            g.attach(self.ibtn(icon, tip, fn), i % 2, i // 2, 1, 1)
        r.append(self.group('Image', g))
        # Tools
        grid = Gtk.Grid(row_spacing=2, column_spacing=2)
        for i, (tid, tip) in enumerate(TOOLS):
            b = self.ibtn(tid, tip, lambda t=tid: self.set_tool(t))
            self.tool_btns[tid] = b
            grid.attach(b, i % 4, i // 4, 1, 1)
        r.append(self.group('Tools', grid))
        # Shapes and whether they are outlined, filled, or both
        sh = Gtk.Box(spacing=6)
        shapes = Gtk.Grid(row_spacing=2, column_spacing=2)
        for i, (sid, tip) in enumerate(SHAPES):
            b = self.ibtn('shape:' + sid, tip, lambda s=sid: self.set_tool('shape', s))
            self.tool_btns['shape:' + sid] = b
            shapes.attach(b, i % 3, i // 3, 1, 1)
        sh.append(shapes)
        opts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        self.out_btn = self.ibtn('outline', 'Outline (colour 1)', lambda: self.set_shape_style('outline'), toggle=True)
        self.fill_btn = self.ibtn('solid', 'Fill (colour 2, or colour 1 without an outline)',
                                  lambda: self.set_shape_style('fill'), toggle=True)
        opts.append(self.out_btn)
        opts.append(self.fill_btn)
        sh.append(opts)
        r.append(self.group('Shapes', sh))
        # Size
        sizes = Gtk.Grid(row_spacing=2, column_spacing=2)
        self.size_btns = {}
        for i, s in enumerate(SIZES):
            b = Gtk.Button(focusable=False, tooltip_text=f'{s}px')
            line = Gtk.Box(valign=Gtk.Align.CENTER)
            line.add_css_class('pt-size-line')
            line.set_size_request(22, s)
            b.set_child(line)
            b.connect('clicked', lambda _b, s=s: self.set_size(s))
            self.size_btns[s] = b
            sizes.attach(b, i % 2, i // 2, 1, 1)
        r.append(self.group('Size', sizes))
        # Text options: shown with the text tool
        fams = sorted({f.get_name() for f in PangoCairo.font_map_get_default().list_families()}, key=str.lower)
        if 'Selawik' in fams:
            self.font_family = 'Selawik'
        elif fams and self.font_family not in fams:
            self.font_family = fams[0]
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.font_dd = Gtk.DropDown.new_from_strings(fams or ['Sans'])
        self.font_dd.set_size_request(140, -1)
        self.font_dd.set_focusable(False)
        if self.font_family in fams:
            self.font_dd.set_selected(fams.index(self.font_family))
        self.font_dd.connect('notify::selected', lambda dd, _p: self.set_font(family=dd.get_selected_item().get_string()))
        tb.append(self.font_dd)
        row = Gtk.Box(spacing=3)
        self.px_spin = Gtk.SpinButton.new_with_range(6, 300, 1)
        self.px_spin.set_value(self.font_px)
        self.px_spin.set_focusable(False)
        self.px_spin.set_tooltip_text('Font size (px)')
        self.px_spin.connect('value-changed', lambda s: self.set_font(px=int(s.get_value())))
        row.append(self.px_spin)
        self.bold_btn = Gtk.ToggleButton(label='B', focusable=False, tooltip_text='Bold', css_classes=['pt-tog'])
        self.bold_btn.connect('toggled', lambda b: self.set_font(bold=b.get_active()))
        self.ital_btn = Gtk.ToggleButton(label='I', focusable=False, tooltip_text='Italic', css_classes=['pt-tog', 'pt-tog-i'])
        self.ital_btn.connect('toggled', lambda b: self.set_font(italic=b.get_active()))
        row.append(self.bold_btn)
        row.append(self.ital_btn)
        tb.append(row)
        self.text_group = self.group('Text', tb)
        r.append(self.text_group)
        # Colours
        cols = Gtk.Box(spacing=8)
        self.big = []
        for n in (1, 2):
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            b = Gtk.Button(focusable=False, tooltip_text=f'Color {n}')
            b.add_css_class('pt-big')
            da = Gtk.DrawingArea(content_width=30, content_height=30)
            da.set_draw_func(lambda _a, cr, w, h, n=n: self.paint_swatch(cr, w, h, self.color1 if n == 1 else self.color2))
            b.set_child(da)
            b.connect('clicked', lambda _b, n=n: self.choose_color(n))
            self.big.append(da)
            v.append(b)
            v.append(Gtk.Label(label=f'Color {n}', css_classes=['pt-group-label']))
            cols.append(v)
        pal = Gtk.Grid(row_spacing=2, column_spacing=2, valign=Gtk.Align.CENTER)
        for i, c in enumerate(PALETTE):
            b = Gtk.Button(focusable=False, tooltip_text=c)
            b.add_css_class('pt-swatch')
            da = Gtk.DrawingArea(content_width=14, content_height=14)
            da.set_draw_func(lambda _a, cr, w, h, c=c: self.paint_swatch(cr, w, h, rgba(c)))
            b.set_child(da)
            b.connect('clicked', lambda _b, c=c: self.set_color(1, rgba(c)))
            right = Gtk.GestureClick(button=3)
            right.connect('pressed', lambda *_a, c=c: self.set_color(2, rgba(c)))
            b.add_controller(right)
            pal.attach(b, i % 10, i // 10, 1, 1)
        cols.append(pal)
        edit = Gtk.Button(tooltip_text='Edit colors', focusable=False, valign=Gtk.Align.CENTER)
        wheel = Gtk.DrawingArea(content_width=24, content_height=24)

        def rainbow(_a, cr, w, h):
            for i in range(12):
                c = Gdk.RGBA()
                c.parse(f'hsl({i * 30}, 85%, 55%)')
                cr.set_source_rgb(c.red, c.green, c.blue)
                cr.move_to(w / 2, h / 2)
                cr.arc(w / 2, h / 2, w / 2 - 1, math.radians(i * 30), math.radians(i * 30 + 31))
                cr.close_path()
                cr.fill()
        wheel.set_draw_func(rainbow)
        edit.set_child(wheel)
        edit.connect('clicked', lambda *_: self.choose_color(1))
        cols.append(edit)
        r.append(self.group('Colors', cols))
        self.set_shape_style('outline', init=True)
        self.set_tool('pencil')
        self.set_size(3)
        self.set_font()
        return r

    @staticmethod
    def paint_swatch(cr, w, h, c):
        cr.set_source_rgba(c.red, c.green, c.blue, c.alpha)
        cr.rectangle(0, 0, w, h)
        cr.fill()

    @staticmethod
    def tool_icon(_a, cr, w, h, tid):
        """MWX 7's own small glyphs (drawn, so every button has one whatever the icon theme holds), on an 18 px grid."""
        cr.scale(w / 18, h / 18)
        ink = (0.11, 0.19, 0.31)
        blue = (0.18, 0.45, 0.85)
        cr.set_line_width(1.4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_source_rgb(*ink)

        def fill_stroke(fill):
            cr.set_source_rgb(*fill)
            cr.fill_preserve()
            cr.set_source_rgb(*ink)
            cr.stroke()
        if tid.startswith('shape:'):
            Paint.trace_static(cr, tid[6:], 2, 3, 16, 15)
            cr.stroke()
            return
        if tid == 'select':
            cr.set_dash([2.5, 2])
            cr.rectangle(2.5, 3.5, 13, 11)
            cr.stroke()
        elif tid == 'pencil':
            cr.move_to(4, 14); cr.line_to(13, 5); cr.line_to(15, 7); cr.line_to(6, 16); cr.close_path()
            fill_stroke((0.98, 0.78, 0.25))
            cr.move_to(4, 14); cr.line_to(3, 17); cr.line_to(6, 16); cr.fill()
        elif tid == 'brush':
            cr.move_to(14.5, 3); cr.line_to(8.5, 10); cr.stroke()
            cr.set_source_rgb(*blue)
            cr.move_to(8, 10); cr.curve_to(4, 10, 5, 15, 2.5, 16); cr.curve_to(7, 16.5, 10.5, 14, 9.5, 11); cr.close_path(); cr.fill()
        elif tid == 'eraser':
            cr.move_to(3, 12); cr.line_to(10, 5); cr.line_to(15, 10); cr.line_to(10, 15); cr.line_to(6, 15); cr.close_path()
            fill_stroke((0.96, 0.62, 0.72))
            cr.move_to(6.5, 8.5); cr.line_to(11.5, 13.5); cr.stroke()
        elif tid == 'fill':
            cr.move_to(3, 9); cr.line_to(9, 3); cr.line_to(15, 9); cr.line_to(9, 15); cr.close_path()
            fill_stroke((0.85, 0.92, 1))
            cr.set_source_rgb(*blue); cr.arc(15.5, 14, 1.8, 0, 2 * math.pi); cr.fill()
        elif tid == 'picker':
            cr.move_to(3, 16); cr.line_to(10, 9); cr.stroke()
            cr.set_line_width(3); cr.move_to(10.5, 8.5); cr.line_to(14.5, 4.5); cr.stroke()
        elif tid == 'text':
            cr.select_font_face('Selawik', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(15); cr.move_to(3, 15); cr.show_text('A')
        elif tid == 'magnifier':
            cr.arc(8, 8, 5, 0, 2 * math.pi); cr.stroke()
            cr.set_line_width(2.4); cr.move_to(11.5, 11.5); cr.line_to(16, 16); cr.stroke()
        elif tid == 'paste':
            cr.rectangle(3, 3.5, 12, 13); fill_stroke((0.93, 0.80, 0.55))
            cr.rectangle(6, 2, 6, 3.5); fill_stroke((0.75, 0.78, 0.84))
            cr.rectangle(6.5, 8, 8, 8.5); fill_stroke((1, 1, 1))
        elif tid == 'cut':
            cr.move_to(6, 2); cr.line_to(11, 11); cr.move_to(12, 2); cr.line_to(7, 11); cr.stroke()
            cr.set_source_rgb(*blue)
            cr.arc(6.5, 14, 2.3, 0, 2 * math.pi); cr.stroke(); cr.arc(11.5, 14, 2.3, 0, 2 * math.pi); cr.stroke()
        elif tid == 'copy':
            cr.rectangle(2.5, 2.5, 9, 10); fill_stroke((1, 1, 1))
            cr.rectangle(6.5, 6.5, 9, 10); fill_stroke((0.85, 0.92, 1))
        elif tid in ('undo', 'redo'):
            if tid == 'redo':
                cr.translate(18, 0); cr.scale(-1, 1)
            cr.move_to(3, 7.5); cr.line_to(7.5, 3); cr.line_to(7.5, 12); cr.close_path(); cr.fill()
            cr.set_line_width(2)
            cr.move_to(7, 7.5); cr.curve_to(14, 5, 16.5, 11, 12, 14.5); cr.stroke()
        elif tid == 'crop':
            cr.move_to(5, 1.5); cr.line_to(5, 13); cr.line_to(16.5, 13)
            cr.move_to(1.5, 5); cr.line_to(13, 5); cr.line_to(13, 16.5); cr.stroke()
        elif tid == 'resize':
            cr.rectangle(2.5, 7.5, 8, 8); cr.stroke()
            cr.set_source_rgb(*blue)
            cr.set_dash([2, 1.5]); cr.rectangle(2.5, 2.5, 13, 13); cr.stroke()
            cr.set_dash([]); cr.move_to(11, 7); cr.line_to(15, 3); cr.stroke()
        elif tid == 'rotate':
            cr.arc(9, 9, 5.5, math.radians(-60), math.radians(200)); cr.stroke()
            cr.move_to(1.5, 8); cr.line_to(6, 8); cr.line_to(4, 12); cr.close_path(); cr.fill()
        elif tid == 'flip':
            cr.move_to(2, 3); cr.line_to(8, 9); cr.line_to(2, 15); cr.close_path(); cr.stroke()
            cr.set_source_rgb(*blue)
            cr.move_to(16, 3); cr.line_to(10, 9); cr.line_to(16, 15); cr.close_path(); cr.fill()
        elif tid == 'outline':
            cr.set_line_width(1.8); cr.rectangle(3, 4, 12, 10); cr.stroke()
        elif tid == 'solid':
            cr.set_source_rgb(*blue); cr.rectangle(3, 4, 12, 10); cr.fill()

    # ---- shapes ---------------------------------------------------------------------------------------------------
    @staticmethod
    def trace_static(cr, shape, x0, y0, x1, y1):
        """Adds the path of a shape. An arrow is a line with a closed head."""
        x, y, w, h = min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)
        if shape == 'line':
            cr.move_to(x0, y0)
            cr.line_to(x1, y1)
        elif shape == 'arrow':
            dist = math.hypot(x1 - x0, y1 - y0)
            if dist < 1:
                return
            ux, uy = (x1 - x0) / dist, (y1 - y0) / dist
            head = min(dist, max(9, cr.get_line_width() * 4.5))
            bx, by = x1 - ux * head, y1 - uy * head
            cr.move_to(x0, y0)
            cr.line_to(bx, by)
            cr.stroke()
            half = head * 0.45
            cr.move_to(x1, y1)
            cr.line_to(bx - uy * half, by + ux * half)
            cr.line_to(bx + uy * half, by - ux * half)
            cr.close_path()
            cr.fill_preserve()
        elif shape == 'rect':
            cr.rectangle(x, y, w, h)
        elif shape == 'round':
            r = min(12, min(w, h) * 0.3)
            cr.new_sub_path()
            cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
            cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
            cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
            cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
            cr.close_path()
        elif shape == 'ellipse' and w > 0 and h > 0:
            cr.save()
            cr.translate(x + w / 2, y + h / 2)
            cr.scale(w / 2, h / 2)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()

    def paint_shape(self, cr, shape, p0, p1, c1, c2, width):
        """Draws a finished or in-progress shape with the current outline/fill choice: outline in c1, fill in c2 (or c1
        when there is no outline). Lines and arrows are always c1. Shared by the preview and the final stroke, so
        what you see while dragging is what lands."""
        off = 0.5 if width % 2 else 0
        x0, y0, x1, y1 = (round(v) + off for v in (*p0, *p1))
        cr.set_line_width(width)
        cr.set_line_join(cairo.LINE_JOIN_MITER if shape == 'rect' else cairo.LINE_JOIN_ROUND)
        cr.set_line_cap(cairo.LINE_CAP_ROUND if shape in ('line', 'arrow') else cairo.LINE_CAP_BUTT)
        if shape in ('line', 'arrow'):
            cr.set_source_rgb(c1.red, c1.green, c1.blue)
            self.trace_static(cr, shape, x0, y0, x1, y1)
            cr.stroke()
            return
        self.trace_static(cr, shape, x0, y0, x1, y1)
        if self.fill:
            f = c2 if self.outline else c1
            cr.set_source_rgb(f.red, f.green, f.blue)
            cr.fill_preserve() if self.outline else cr.fill()
        if self.outline:
            cr.set_source_rgb(c1.red, c1.green, c1.blue)
            cr.stroke()

    def set_shape_style(self, which, init=False):
        if not init:
            if which == 'outline':
                self.outline = not self.outline
            else:
                self.fill = not self.fill
            if not (self.outline or self.fill):
                self.outline = True
        for b, on in ((self.out_btn, self.outline), (self.fill_btn, self.fill)):
            if b.get_active() != on:
                b.set_active(on)

    # ---- tool state -----------------------------------------------------------------------------------------------
    def set_tool(self, tool, shape=None):
        self.put_down()
        if tool in ('picker', 'magnifier') and self.tool not in ('picker', 'magnifier'):
            self.prev_tool = (self.tool, self.shape)
        self.tool, self.shape = tool, shape
        if tool != 'select':
            self.sel = None
        for k, b in self.tool_btns.items():
            on = k == (f'shape:{shape}' if tool == 'shape' else tool)
            (b.add_css_class if on else b.remove_css_class)('on')
        self.text_group.set_visible(tool == 'text')
        if hasattr(self, 'area'):
            cursor = {'select': 'default', 'text': 'text', 'magnifier': 'zoom-in'}.get(tool, 'crosshair')
            self.area.set_cursor(Gdk.Cursor.new_from_name(cursor))
            self.area.queue_draw()

    def set_size(self, s):
        self.size = s
        for k, b in self.size_btns.items():
            (b.add_css_class if k == s else b.remove_css_class)('on')

    def set_color(self, n, c):
        if n == 1:
            self.color1 = c
            if self.tv is not None:
                self.tx = (*self.tx[:2], c)
                self.style_text()
        else:
            self.color2 = c
        for da in self.big:
            da.queue_draw()

    def choose_color(self, n):
        dlg = Gtk.ColorDialog(title='Edit Colors', with_alpha=False)

        def done(d, res):
            try:
                self.set_color(n, d.choose_rgba_finish(res))
            except GLib.Error:
                pass
        dlg.choose_rgba(self.win, self.color1 if n == 1 else self.color2, None, done)

    def retitle(self):
        name = os.path.basename(self.path) if self.path else 'Untitled'
        self.app.set_title(f'{"*" if self.dirty else ""}{name} - Paint')

    def touched(self):
        if not self.dirty:
            self.dirty = True
            self.retitle()

    # ---- view / zoom ----------------------------------------------------------------------------------------------
    def resize_area(self):
        self.area.set_content_width(max(1, int(self.w * self.zoom)))
        self.area.set_content_height(max(1, int(self.h * self.zoom)))

    def set_zoom(self, z):
        # Stay within what the toolkit can lay out (a 8000 px canvas at 16x would be far past it).
        z = min(z, 30000 / max(self.w, self.h, 1))
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, z))
        self.resize_area()
        self.area.queue_draw()
        self.zsync = True
        self.zscale.set_value(math.log2(self.zoom))
        self.zsync = False
        self.zlabel.set_label(f'{round(self.zoom * 100)}%')
        self.style_text()

    def zoom_at(self, z, anchor=None):
        """Zooms keeping the image point under the pointer (or the view's centre) where it is."""
        old = self.zoom
        ha, va = self.sc.get_hadjustment(), self.sc.get_vadjustment()
        if anchor is None:
            anchor = self.ptr
        if anchor is not None:
            ax, ay = anchor
            vx, vy = ax + 6 - ha.get_value(), ay + 6 - va.get_value()
        else:
            vx, vy = ha.get_page_size() / 2, va.get_page_size() / 2
            ax, ay = ha.get_value() + vx - 6, va.get_value() + vy - 6
        ix, iy = ax / old, ay / old
        self.set_zoom(z)
        if self.zoom == old:
            return
        # Wait for the new canvas size to be laid out, or the scroll position would be clamped to the old one.
        GLib.timeout_add(30, lambda: (ha.set_value(ix * self.zoom + 6 - vx), va.set_value(iy * self.zoom + 6 - vy), False)[2])

    def fit(self):
        vw, vh = self.sc.get_width() - 24, self.sc.get_height() - 24
        if vw > 0 and vh > 0:
            self.zoom_at(min(vw / self.w, vh / self.h), anchor=(0, 0))
            GLib.timeout_add(40, lambda: (self.sc.get_hadjustment().set_value(0), self.sc.get_vadjustment().set_value(0), False)[2])

    def on_wheel(self, ctl, _dx, dy):
        if not ctl.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            return False
        self.zoom_at(self.zoom * (1.15 ** (-dy)))
        return True

    def on_motion(self, _c, x, y):
        self.ptr = (x, y)
        self.status.set_label(f'{int(x / self.zoom)}, {int(y / self.zoom)}px    {self.w} × {self.h}px')

    def draw(self, _a, cr, _w, _h):
        cr.scale(self.zoom, self.zoom)
        cr.set_source_surface(self.surface, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST if self.zoom > 1 else cairo.FILTER_GOOD)
        cr.paint()
        if self.floating:
            s, x, y = self.floating
            cr.set_source_surface(s, x, y)
            cr.get_source().set_filter(cairo.FILTER_NEAREST if self.zoom > 1 else cairo.FILTER_GOOD)
            cr.paint()
        d = self.drag
        if d and d.get('preview'):
            d['preview'](cr)
        if self.sel:
            x, y, w, h = self.sel
            cr.set_line_width(1 / self.zoom)
            cr.set_dash([4 / self.zoom, 3 / self.zoom])
            cr.set_source_rgb(0.1, 0.35, 0.8)
            cr.rectangle(x + 0.5 / self.zoom, y + 0.5 / self.zoom, w, h)
            cr.stroke()

    # ---- history --------------------------------------------------------------------------------------------------
    def snapshot(self):
        copy = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.w, self.h)
        cr = cairo.Context(copy)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_surface(self.surface, 0, 0)
        cr.paint()
        self.undo_stack.append(copy)
        self.redo_stack.clear()
        self.trim_history()

    def trim_history(self):
        """Drops the oldest steps past the step limit or the memory budget (the newest step always stays)."""
        del self.undo_stack[:-HISTORY_STEPS]
        total = sum(map(cost, self.undo_stack)) + sum(map(cost, self.redo_stack)) + cost(self.surface)
        while total > HISTORY_BYTES and (len(self.undo_stack) > 1 or self.redo_stack):
            gone = self.undo_stack.pop(0) if len(self.undo_stack) > 1 else self.redo_stack.pop(0)
            total -= cost(gone)

    def replace(self, surface):
        self.surface = surface
        self.w, self.h = surface.get_width(), surface.get_height()
        self.resize_area()
        self.area.queue_draw()

    def undo(self):
        if self.in_text():
            self.tv.get_buffer().undo()
            return
        self.put_down()
        if self.undo_stack:
            self.redo_stack.append(self.surface)
            self.sel = None
            self.replace(self.undo_stack.pop())
            self.touched()

    def redo(self):
        if self.in_text():
            self.tv.get_buffer().redo()
            return
        self.put_down()
        if self.redo_stack:
            self.undo_stack.append(self.surface)
            self.sel = None
            self.replace(self.redo_stack.pop())
            self.trim_history()
            self.touched()

    # ---- painting -------------------------------------------------------------------------------------------------
    def color_for(self, button):
        return self.color1 if button == 1 else self.color2

    def stroke_seg(self, x0, y0, x1, y1, color, width, square=False):
        cr = cairo.Context(self.surface)
        cr.set_antialias(cairo.ANTIALIAS_NONE if square or width <= 1 else cairo.ANTIALIAS_DEFAULT)
        cr.set_source_rgba(color.red, color.green, color.blue, 1)
        cr.set_line_width(width)
        cr.set_line_cap(cairo.LINE_CAP_SQUARE if square else cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        off = 0.5 if width % 2 else 0
        cr.move_to(x0 + off, y0 + off)
        cr.line_to(x1 + off, y1 + off)
        cr.stroke()

    def on_begin(self, g, x, y, button):
        cx, cy = x / self.zoom, y / self.zoom
        t = self.tool
        had_text = self.tv is not None
        if had_text:
            self.commit_text()
        if t == 'magnifier':
            self.zoom_at(self.zoom * (2 if button == 1 else 0.5), anchor=(x, y))
            return
        if t == 'picker':
            self.set_color(1 if button == 1 else 2, self.pixel(int(cx), int(cy)))
            # Like Paint: pick once, then go back to what you were doing.
            self.set_tool(*self.prev_tool)
            return
        if t == 'fill':
            self.snapshot()
            self.flood(int(cx), int(cy), self.color_for(button))
            self.touched()
            self.area.queue_draw()
            return
        if t == 'text':
            self.start_text(int(cx), int(cy), self.color_for(button))
            return
        if t == 'select':
            if self.sel and self.inside(cx, cy):
                self.lift()
                s, fx, fy = self.floating
                self.drag = {'move': (cx - fx, cy - fy)}
                return
            self.put_down()
            self.sel = None
            self.drag = {'sel': (cx, cy)}
            self.area.queue_draw()
            return
        self.snapshot()
        self.touched()
        color = self.color_for(button) if t != 'eraser' else self.color2
        other = self.color2 if button == 1 else self.color1
        self.drag = {'x0': cx, 'y0': cy, 'last': (cx, cy), 'color': color, 'other': other}
        if t in ('pencil', 'brush', 'eraser'):
            self.paint_free(cx, cy)

    def width_for(self):
        return {'pencil': 1, 'brush': self.size * 2, 'eraser': self.size * 3}.get(self.tool, self.size)

    def paint_free(self, cx, cy):
        d = self.drag
        lx, ly = d['last']
        if self.tool == 'pencil':
            self.stroke_seg(int(lx), int(ly), int(cx), int(cy), d['color'], 1, square=True)
        else:
            self.stroke_seg(lx, ly, cx, cy, d['color'], self.width_for(), square=self.tool == 'eraser')
        d['last'] = (cx, cy)
        self.area.queue_draw()

    def on_update(self, g, dx, dy, button):
        ok, sx, sy = g.get_start_point()
        if not ok or not self.drag:
            return
        cx, cy = (sx + dx) / self.zoom, (sy + dy) / self.zoom
        d = self.drag
        if 'move' in d:
            ox, oy = d['move']
            s, _x, _y = self.floating
            self.floating = (s, int(cx - ox), int(cy - oy))
            self.sel = (self.floating[1], self.floating[2], s.get_width(), s.get_height())
            self.area.queue_draw()
            return
        if 'sel' in d:
            x0, y0 = d['sel']
            x1, y1 = max(0, min(self.w, cx)), max(0, min(self.h, cy))
            self.sel = (int(min(x0, x1)), int(min(y0, y1)), int(abs(x1 - x0)), int(abs(y1 - y0)))
            self.status.set_label(f'Selection {self.sel[2]} × {self.sel[3]}px    {self.w} × {self.h}px')
            self.area.queue_draw()
            return
        if self.tool in ('pencil', 'brush', 'eraser'):
            self.paint_free(cx, cy)
        elif self.tool == 'shape':
            x0, y0, color, other, w = d['x0'], d['y0'], d['color'], d['other'], self.size
            shape = self.shape
            d['preview'] = lambda cr, x1=cx, y1=cy: self.paint_shape(cr, shape, (x0, y0), (x1, y1), color, other, w)
            d['end'] = (cx, cy)
            self.area.queue_draw()

    def on_end(self, g, dx, dy, button):
        d, self.drag = self.drag, None
        if not d:
            return
        if self.tool == 'shape' and 'end' in d:
            cr = cairo.Context(self.surface)
            self.paint_shape(cr, self.shape, (d['x0'], d['y0']), d['end'], d['color'], d['other'], self.size)
        if 'sel' in d and self.sel and (self.sel[2] < 2 or self.sel[3] < 2):
            self.sel = None
        self.area.queue_draw()

    # ---- pixels ---------------------------------------------------------------------------------------------------
    def pixel(self, x, y):
        self.surface.flush()
        data, stride = self.surface.get_data(), self.surface.get_stride()
        x, y = max(0, min(self.w - 1, x)), max(0, min(self.h - 1, y))
        i = y * stride + x * 4
        b, g, r = data[i], data[i + 1], data[i + 2]
        c = Gdk.RGBA()
        c.red, c.green, c.blue, c.alpha = r / 255, g / 255, b / 255, 1
        return c

    _ZERO_RUN = re.compile(rb'\x00+')

    def flood(self, x, y, color):
        """Scanline flood fill (exact colour match, 4-connected, as Paint does).

        Pure Python visits one pixel at a time far too slowly for a big canvas, so each row is turned into a
        one-byte-per-pixel "differs from the seed colour" mask with big-integer XOR/OR (all in C), and the runs of
        matching pixels are found with a regex. Python then only walks runs, not pixels: a blank 4000 x 3000 image
        is 3000 runs, so the fill finishes in well under a second."""
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        self.surface.flush()
        buf = self.surface.get_data()
        stride, w, h = self.surface.get_stride(), self.w, self.h
        new = bytes((round(color.blue * 255), round(color.green * 255), round(color.red * 255), 255))
        at = y * stride + x * 4
        old = bytes(buf[at:at + 4])
        if old == new:
            return
        patt = int.from_bytes(old * w, 'little')
        zero_run = self._ZERO_RUN
        rows = {}   # y -> (run starts, run ends, visited flags); built the first time a row is reached

        def runs_of(ry):
            r = rows.get(ry)
            if r is None:
                base = ry * stride
                x_ = (int.from_bytes(buf[base:base + w * 4], 'little') ^ patt).to_bytes(w * 4, 'little')
                m = (int.from_bytes(x_[0::4], 'little') | int.from_bytes(x_[1::4], 'little') |
                     int.from_bytes(x_[2::4], 'little') | int.from_bytes(x_[3::4], 'little')).to_bytes(w, 'little')
                spans = [mt.span() for mt in zero_run.finditer(m)]
                r = rows[ry] = ([s for s, _e in spans], [e for _s, e in spans], bytearray(len(spans)))
            return r

        def run_at(ry, rx):
            starts, ends, _seen = runs_of(ry)
            lo, hi = 0, len(starts)
            while lo < hi:
                mid = (lo + hi) // 2
                if ends[mid] <= rx:
                    lo = mid + 1
                else:
                    hi = mid
            return lo if lo < len(starts) and starts[lo] <= rx else -1

        first = run_at(y, x)
        stack = [(y, first)]
        runs_of(y)[2][first] = 1
        while stack:
            ry, i = stack.pop()
            starts, ends, _s = runs_of(ry)
            s, e = starts[i], ends[i]
            buf[ry * stride + s * 4: ry * stride + e * 4] = new * (e - s)
            for ny in (ry - 1, ry + 1):
                if not 0 <= ny < h:
                    continue
                ns, ne, seen = runs_of(ny)
                # First run in the next row that ends after our start, then every one that starts before our end.
                lo, hi = 0, len(ns)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if ne[mid] <= s:
                        lo = mid + 1
                    else:
                        hi = mid
                j = lo
                while j < len(ns) and ns[j] < e:
                    if not seen[j]:
                        seen[j] = 1
                        stack.append((ny, j))
                    j += 1
        self.surface.mark_dirty()

    # ---- text -----------------------------------------------------------------------------------------------------
    def in_text(self):
        return self.tv is not None and self.win.get_focus() is self.tv

    def font_desc(self):
        d = Pango.FontDescription()
        d.set_family(self.font_family)
        d.set_absolute_size(self.font_px * Pango.SCALE)
        d.set_weight(Pango.Weight.BOLD if self.bold else Pango.Weight.NORMAL)
        d.set_style(Pango.Style.ITALIC if self.italic else Pango.Style.NORMAL)
        return d

    def set_font(self, family=None, px=None, bold=None, italic=None):
        if family is not None:
            self.font_family = family
        if px is not None:
            self.font_px = px
        if bold is not None:
            self.bold = bold
        if italic is not None:
            self.italic = italic
        self.style_text()

    def style_text(self):
        """The text box looks like what will be drawn: same family, weight, colour, and size at the current zoom."""
        color = self.tx[2] if self.tv is not None and self.tx else self.color1
        self.text_css.load_from_data((TEXT_CSS % {
            'color': hexof(color), 'family': self.font_family.replace("'", ''), 'px': max(1, round(self.font_px * self.zoom)),
            'weight': 'bold' if self.bold else 'normal', 'style': 'italic' if self.italic else 'normal'}).encode())
        if self.tv is not None:
            self.tv.set_margin_start(int(self.tx[0] * self.zoom))
            self.tv.set_margin_top(int(self.tx[1] * self.zoom))
            self.fit_text()

    def fit_text(self):
        """Sizes the box to its text: a GtkTextView in an overlay keeps its first size instead of growing as you type."""
        buf = self.tv.get_buffer()
        d = self.font_desc()
        d.set_absolute_size(max(1, self.font_px * self.zoom) * Pango.SCALE)
        lay = self.tv.create_pango_layout(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False) + ' ')
        lay.set_font_description(d)
        w, h = lay.get_pixel_size()
        self.tv.set_size_request(max(24, w + 6), max(10, h))

    def start_text(self, x, y, color):
        """Puts an editable text box on the canvas. Nothing is drawn until it is committed (click elsewhere, Escape,
        Ctrl+Enter, or switch tool), so the text can be retyped and restyled meanwhile."""
        self.commit_text()
        tv = Gtk.TextView(wrap_mode=Gtk.WrapMode.NONE, halign=Gtk.Align.START, valign=Gtk.Align.START, accepts_tab=False,
                          left_margin=0, right_margin=0, top_margin=0, bottom_margin=0)
        tv.add_css_class('pt-text-edit')
        tv.get_buffer().connect('changed', lambda _b: self.tv is tv and self.fit_text())
        keys = Gtk.EventControllerKey()

        def key(_c, keyval, _code, state):
            if keyval == Gdk.KEY_Escape or (keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and state & Gdk.ModifierType.CONTROL_MASK):
                GLib.idle_add(lambda: self.commit_text() and False)
                return True
            return False
        keys.connect('key-pressed', key)
        tv.add_controller(keys)
        self.tv, self.tx = tv, (x, y, color)
        self.overlay.add_overlay(tv)
        self.style_text()
        tv.grab_focus()

    def close_text(self):
        if self.tv is not None:
            self.overlay.remove_overlay(self.tv)
            self.tv = None
            self.tx = None
            self.style_text()

    def commit_text(self):
        """Draws the text box's text onto the image (one undo step) and removes the box."""
        tv = self.tv
        if tv is None:
            return
        buf = tv.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        x, y, color = self.tx
        self.close_text()
        if not text.strip():
            return
        self.snapshot()
        cr = cairo.Context(self.surface)
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(self.font_desc())
        layout.set_text(text, -1)
        cr.set_source_rgba(color.red, color.green, color.blue, 1)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)
        self.surface.flush()
        self.touched()
        self.area.queue_draw()

    # ---- selection ------------------------------------------------------------------------------------------------
    def inside(self, cx, cy):
        x, y, w, h = self.sel
        return x <= cx <= x + w and y <= cy <= y + h

    def cut_out(self, sel, clear):
        x, y, w, h = sel
        part = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, w), max(1, h))
        cr = cairo.Context(part)
        cr.set_source_surface(self.surface, -x, -y)
        cr.paint()
        if clear:
            cr2 = cairo.Context(self.surface)
            c = self.color2
            cr2.set_source_rgba(c.red, c.green, c.blue, 1)
            cr2.rectangle(x, y, w, h)
            cr2.fill()
        return part

    def lift(self):
        if not self.floating and self.sel:
            self.snapshot()
            self.floating = (self.cut_out(self.sel, True), self.sel[0], self.sel[1])
            self.touched()

    def put_down(self):
        """Settles whatever is still loose: a text box becomes pixels, a moved or pasted selection is dropped in place."""
        self.commit_text()
        if self.floating:
            s, x, y = self.floating
            cr = cairo.Context(self.surface)
            cr.set_source_surface(s, x, y)
            cr.paint()
            self.floating = None
            if hasattr(self, 'area'):
                self.area.queue_draw()

    def select_all(self):
        if self.in_text():
            b = self.tv.get_buffer()
            b.select_range(b.get_start_iter(), b.get_end_iter())
            return
        self.set_tool('select')
        self.sel = (0, 0, self.w, self.h)
        self.area.queue_draw()

    def copy(self):
        if self.in_text():
            self.tv.get_buffer().copy_clipboard(self.win.get_clipboard())
            return
        if self.floating:
            self.clip = self.floating[0]
        elif self.sel:
            self.clip = self.cut_out(self.sel, False)
        else:
            return
        self.win.get_clipboard().set(Gdk.Texture.new_for_pixbuf(
            Gdk.pixbuf_get_from_surface(self.clip, 0, 0, self.clip.get_width(), self.clip.get_height())))

    def cut(self):
        if self.in_text():
            self.tv.get_buffer().cut_clipboard(self.win.get_clipboard(), True)
            return
        if self.sel:
            self.copy()
            self.delete_sel()

    def delete_sel(self):
        if self.in_text():
            self.tv.get_buffer().delete_selection(True, True)
            return
        if not (self.floating or self.sel):
            return
        if self.floating:
            self.floating = None
        else:
            self.snapshot()
            self.cut_out(self.sel, True)
        self.sel = None
        self.touched()
        self.area.queue_draw()

    def paste(self):
        if self.in_text():
            self.tv.get_buffer().paste_clipboard(self.win.get_clipboard(), None, True)
            return

        def got(cb, res):
            try:
                tex = cb.read_texture_finish(res)
            except GLib.Error:
                tex = None
            surf = None
            if tex:
                pb = Gdk.pixbuf_get_from_texture(tex)
                surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, pb.get_width(), pb.get_height())
                cr = cairo.Context(surf)
                Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
                cr.paint()
            surf = surf or self.clip
            if not surf:
                return
            self.paste_surface(surf)
        self.win.get_clipboard().read_texture_async(None, got)

    def paste_surface(self, surf):
        """Drops an image on the canvas as a selection at the top-left of what you can see; the canvas grows to hold
        it, as Paint offers to."""
        self.set_tool('select')
        self.snapshot()
        pw, ph = surf.get_width(), surf.get_height()
        if (pw > self.w or ph > self.h) and max(pw, self.w) * max(ph, self.h) <= MAX_PIXELS:
            big = self.blank(max(pw, self.w), max(ph, self.h), self.color2)
            cr = cairo.Context(big)
            cr.set_source_surface(self.surface, 0, 0)
            cr.paint()
            self.replace(big)
        fx = max(0, min(self.w - 1, int(self.sc.get_hadjustment().get_value() / self.zoom)))
        fy = max(0, min(self.h - 1, int(self.sc.get_vadjustment().get_value() / self.zoom)))
        self.floating = (surf, fx, fy)
        self.sel = (fx, fy, pw, ph)
        self.touched()
        self.area.queue_draw()

    def crop(self):
        if not self.sel:
            return
        self.put_down()
        self.snapshot()
        part = self.cut_out(self.sel, False)
        self.sel = None
        self.replace(part)
        self.touched()

    # ---- image ----------------------------------------------------------------------------------------------------
    def rotate(self, deg):
        self.put_down()
        self.snapshot()
        w, h = self.w, self.h
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, h, w)
        cr = cairo.Context(s)
        if deg == 90:
            cr.translate(h, 0)
        else:
            cr.translate(0, w)
        cr.rotate(math.radians(deg))
        cr.set_source_surface(self.surface, 0, 0)
        cr.paint()
        self.sel = None
        self.replace(s)
        self.touched()

    def flip(self, horizontal):
        self.put_down()
        self.snapshot()
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.w, self.h)
        cr = cairo.Context(s)
        if horizontal:
            cr.translate(self.w, 0)
            cr.scale(-1, 1)
        else:
            cr.translate(0, self.h)
            cr.scale(1, -1)
        cr.set_source_surface(self.surface, 0, 0)
        cr.paint()
        self.replace(s)
        self.touched()

    def too_big(self, nw, nh):
        if nw * nh > MAX_PIXELS:
            Gtk.AlertDialog(message='That is too large for Paint.', detail=f'{nw} × {nh}px is over {MAX_PIXELS // 1_000_000} megapixels.').show(self.win)
            return True
        return False

    def resize_skew(self, nw, nh, skew_h=0.0, skew_v=0.0):
        """Scales the image to nw x nh, then skews it by the given angles (degrees). The corners a skew uncovers are
        filled with colour 2, like Paint's background."""
        self.put_down()
        if self.too_big(nw, nh):
            return False
        img = self.surface
        if (nw, nh) != (self.w, self.h):
            img = cairo.ImageSurface(cairo.FORMAT_ARGB32, nw, nh)
            cr = cairo.Context(img)
            cr.scale(nw / self.w, nh / self.h)
            cr.set_source_surface(self.surface, 0, 0)
            src = cr.get_source()
            src.set_filter(cairo.FILTER_BEST if nw < self.w or nh < self.h else cairo.FILTER_BILINEAR)
            src.set_extend(cairo.EXTEND_PAD)
            cr.rectangle(0, 0, self.w, self.h)
            cr.clip()
            cr.paint()
        tx, ty = math.tan(math.radians(skew_h)), math.tan(math.radians(skew_v))
        if abs(skew_h) > 0.001 or abs(skew_v) > 0.001:
            xs = [px + tx * py for px in (0, nw) for py in (0, nh)]
            ys = [py + ty * px for px in (0, nw) for py in (0, nh)]
            sw, sh = math.ceil(max(xs) - min(xs)), math.ceil(max(ys) - min(ys))
            if self.too_big(sw, sh):
                return False
            out = self.blank(sw, sh, self.color2)
            cr = cairo.Context(out)
            cr.transform(cairo.Matrix(xx=1, yx=ty, xy=tx, yy=1, x0=-min(xs), y0=-min(ys)))
            cr.set_source_surface(img, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_BILINEAR)
            cr.paint()
            img = out
        self.snapshot()
        self.sel = None
        self.replace(img)
        self.touched()
        return True

    def resize_dialog(self):
        d = mwx7ui.dialog(self.win, 'Resize and Skew', 'paint')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14, margin_start=16,
                      margin_end=16)
        grid = Gtk.Grid(row_spacing=8, column_spacing=10)
        pct = Gtk.CheckButton(label='Percentage', active=True)
        px = Gtk.CheckButton(label='Pixels', group=pct)
        unit = Gtk.Box(spacing=14)
        unit.append(pct)
        unit.append(px)
        keep = Gtk.CheckButton(label='Maintain aspect ratio', active=True)
        hv = Gtk.SpinButton.new_with_range(1, 1000, 1)
        vv = Gtk.SpinButton.new_with_range(1, 1000, 1)
        hv.set_value(100)
        vv.set_value(100)
        busy = [False]
        ow, oh = self.w, self.h

        def units(*_):
            busy[0] = True
            if pct.get_active():
                hv.set_range(1, 1000)
                vv.set_range(1, 1000)
                hv.set_value(100)
                vv.set_value(100)
            else:
                hv.set_range(1, 16000)
                vv.set_range(1, 16000)
                hv.set_value(ow)
                vv.set_value(oh)
            busy[0] = False
        pct.connect('toggled', units)

        def linked(src, dst, ratio):
            def f(*_):
                if busy[0] or not keep.get_active():
                    return
                busy[0] = True
                dst.set_value(max(1, round(src.get_value() * ratio)))
                busy[0] = False
            return f
        hv.connect('value-changed', lambda s: linked(hv, vv, 1 if pct.get_active() else oh / ow)())
        vv.connect('value-changed', lambda s: linked(vv, hv, 1 if pct.get_active() else ow / oh)())
        sh = Gtk.SpinButton.new_with_range(-89, 89, 1)
        sv = Gtk.SpinButton.new_with_range(-89, 89, 1)
        grid.attach(Gtk.Label(label='Resize', xalign=0, css_classes=['heading']), 0, 0, 1, 1)
        grid.attach(unit, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label='Horizontal', xalign=0), 0, 1, 1, 1)
        grid.attach(hv, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label='Vertical', xalign=0), 0, 2, 1, 1)
        grid.attach(vv, 1, 2, 1, 1)
        grid.attach(keep, 1, 3, 1, 1)
        grid.attach(Gtk.Label(label='Skew (degrees)', xalign=0, css_classes=['heading'], margin_top=6), 0, 4, 2, 1)
        grid.attach(Gtk.Label(label='Horizontal', xalign=0), 0, 5, 1, 1)
        grid.attach(sh, 1, 5, 1, 1)
        grid.attach(Gtk.Label(label='Vertical', xalign=0), 0, 6, 1, 1)
        grid.attach(sv, 1, 6, 1, 1)
        box.append(grid)
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label='Cancel')
        ok = Gtk.Button(label='OK')
        ok.add_css_class('suggested-action')
        btns.append(cancel)
        btns.append(ok)
        box.append(btns)

        def apply(*_):
            a, b = hv.get_value(), vv.get_value()
            nw, nh = (round(ow * a / 100), round(oh * b / 100)) if pct.get_active() else (int(a), int(b))
            d.close()
            self.resize_skew(max(1, nw), max(1, nh), sh.get_value(), sv.get_value())
        ok.connect('clicked', apply)
        cancel.connect('clicked', lambda *_: d.close())
        d.set_child(box)
        d.present()

    def canvas_dialog(self):
        d = mwx7ui.dialog(self.win, 'Canvas Size', 'paint')
        grid = Gtk.Grid(row_spacing=8, column_spacing=8, margin_top=14, margin_bottom=14, margin_start=16, margin_end=16)
        wv = Gtk.SpinButton.new_with_range(1, 8000, 1)
        hv = Gtk.SpinButton.new_with_range(1, 8000, 1)
        wv.set_value(self.w)
        hv.set_value(self.h)
        grid.attach(Gtk.Label(label='Width (px)', xalign=0), 0, 0, 1, 1)
        grid.attach(wv, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label='Height (px)', xalign=0), 0, 1, 1, 1)
        grid.attach(hv, 1, 1, 1, 1)
        ok = Gtk.Button(label='OK')
        ok.add_css_class('suggested-action')

        def apply(*_):
            nw, nh = int(wv.get_value()), int(hv.get_value())
            d.close()
            self.put_down()
            if self.too_big(nw, nh):
                return
            self.snapshot()
            s = self.blank(nw, nh)
            cr = cairo.Context(s)
            cr.set_source_surface(self.surface, 0, 0)
            cr.paint()
            self.replace(s)
            self.touched()
        ok.connect('clicked', apply)
        grid.attach(ok, 1, 2, 1, 1)
        d.set_child(grid)
        d.present()

    # ---- files ----------------------------------------------------------------------------------------------------
    def pictures(self):
        return Gio.File.new_for_path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
                                     or os.path.expanduser('~'))

    def filters(self):
        f = Gtk.FileFilter(name='Pictures')
        for m in ('image/png', 'image/jpeg', 'image/bmp', 'image/gif', 'image/webp', 'image/tiff'):
            f.add_mime_type(m)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        return store

    def new(self):
        self.put_down()
        self.sel = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.replace(self.blank(800, 560))
        self.path, self.dirty = None, False
        self.retitle()

    def load(self, path):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(path).apply_embedded_orientation()
        except GLib.Error as e:
            Gtk.AlertDialog(message=f'Paint cannot read {os.path.basename(path)}.', detail=e.message).show(self.win)
            return False
        self.close_text()
        s = self.blank(pb.get_width(), pb.get_height())
        cr = cairo.Context(s)
        Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
        cr.paint()
        self.sel, self.floating = None, None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.replace(s)
        self.path, self.dirty = path, False
        self.retitle()
        mwx7ui.remember(path)
        return True

    def write(self, path):
        self.put_down()
        ext = os.path.splitext(path)[1].lower()
        kind = {'.jpg': 'jpeg', '.jpeg': 'jpeg', '.bmp': 'bmp', '.tif': 'tiff', '.tiff': 'tiff'}.get(ext, 'png')
        if kind == 'png' and ext != '.png':
            path += '.png'
        try:
            pb = Gdk.pixbuf_get_from_surface(self.surface, 0, 0, self.w, self.h)
            if kind == 'jpeg':
                pb.savev(path, 'jpeg', ['quality'], ['92'])
            else:
                pb.savev(path, kind, [], [])
        except GLib.Error as e:
            Gtk.AlertDialog(message=f'Paint cannot save {os.path.basename(path)}.', detail=e.message).show(self.win)
            return False
        self.path, self.dirty = path, False
        self.retitle()
        mwx7ui.remember(path)
        return True

    def open(self):
        dlg = mwx7ui.FileDialog(title='Open', initial_folder=self.pictures(), filters=self.filters())

        def done(d, res):
            try:
                self.load(d.open_finish(res).get_path())
            except GLib.Error:
                pass
        dlg.open(self.win, None, done)

    def save(self, then=None):
        if self.path:
            if self.write(self.path) and then:
                then()
        else:
            self.save_as(then)

    def save_as(self, then=None):
        dlg = mwx7ui.FileDialog(title='Save As', initial_folder=self.pictures(),
                                initial_name=os.path.basename(self.path) if self.path else 'Untitled.png')

        def done(d, res):
            try:
                path = d.save_finish(res).get_path()
            except GLib.Error:
                return
            if self.write(path) and then:
                then()
        dlg.save(self.win, None, done)

    def guard(self, then):
        self.put_down()   # a text box still open counts as a change
        if not self.dirty:
            then()
            return
        name = os.path.basename(self.path) if self.path else 'Untitled'
        dlg = Gtk.AlertDialog(message='Paint', detail=f'Do you want to save changes to {name}?',
                              buttons=['Save', 'Don’t Save', 'Cancel'], default_button=0, cancel_button=2)

        def done(d, res):
            try:
                c = d.choose_finish(res)
            except GLib.Error:
                return
            if c == 0:
                self.save(then)
            elif c == 1:
                then()
        dlg.choose(self.win, None, done)

    def on_close(self, *_):
        self.put_down()
        if self.closing_ok or not self.dirty:
            return False

        def go():
            self.closing_ok = True
            self.win.close()
        self.guard(go)
        return True


if __name__ == '__main__':
    paint = Paint()
    mwx7ui.App('org.mwx7.paint', 'Paint', 'paint', (1100, 720), CSS, paint.build).run_main()
