"""Paint (native): the concept's Windows 7-style Paint: a ribbon of tools (select, pencil, brush, eraser, fill, colour
picker, text, magnifier), shapes (line, rectangle, rounded rectangle, ellipse), sizes, two colours from a palette or
any colour, undo/redo, and PNG/JPEG/BMP files. Left button paints with colour 1, right button with colour 2."""
import math
import os
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk  # noqa: E402
import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf  # noqa: E402

PALETTE = ['#000000', '#7f7f7f', '#880015', '#ed1c24', '#ff7f27', '#fff200', '#22b14c', '#00a2e8', '#3f48cc', '#a349a4',
           '#ffffff', '#c3c3c3', '#b97a57', '#ffaec9', '#ffc90e', '#efe4b0', '#b5e61d', '#99d9ea', '#7092be', '#c8bfe7']
TOOLS = [('select', 'edit-select-all-symbolic', 'Select'), ('pencil', 'document-edit-symbolic', 'Pencil'),
         ('brush', 'applications-graphics-symbolic', 'Brush'), ('eraser', 'edit-clear-symbolic', 'Eraser'),
         ('fill', 'color-select-symbolic', 'Fill with color'), ('picker', 'color-picker-symbolic', 'Color picker'),
         ('text', 'insert-text-symbolic', 'Text'), ('magnifier', 'zoom-in-symbolic', 'Magnifier')]
SHAPES = [('line', 'Line'), ('rect', 'Rectangle'), ('round', 'Rounded rectangle'), ('ellipse', 'Oval')]
SIZES = [1, 3, 5, 8]
CSS = """
window.mwx7-paint > box { background: #ffffff; }
.pt-ribbon { padding: 6px 8px 4px; border-bottom: 1px solid #b6c6da;
  background: linear-gradient(180deg, #fbfdff 0%, #eef4fb 60%, #dfe9f5 100%); }
.pt-group { padding: 0 8px; border-right: 1px solid #c8d5e6; }
.pt-group-label { font-size: 10px; color: #5a6f8d; margin-top: 2px; }
.pt-ribbon button { min-width: 26px; min-height: 26px; padding: 2px; border-radius: 3px; border: 1px solid transparent;
  background: none; box-shadow: none; color: #1c3150; }
.pt-ribbon button:hover { border-color: #a8c6ec; background: linear-gradient(180deg, #f4f9ff, #dbeafc); }
.pt-ribbon button.on { border-color: #6e9fd8; background: linear-gradient(180deg, #e2efff, #bcd7f6); }
button.pt-swatch { min-width: 18px; min-height: 18px; padding: 0; border: 1px solid #8a9bb2; border-radius: 1px; }
button.pt-big { min-width: 34px; min-height: 34px; padding: 0; border: 1px solid #8a9bb2; border-radius: 2px; }
.pt-size-line { background: #1c3150; }
.pt-canvas-bg { background: #c9d6e8; }
.pt-status { padding: 2px 10px; font-size: 11px; color: #4a5f7d; border-top: 1px solid #d5dfec; background: #f0f4fa; }
"""


def rgba(hexc):
    c = Gdk.RGBA()
    c.parse(hexc)
    return c


class Paint:
    def __init__(self):
        self.w, self.h = 800, 560
        self.surface = self.blank(self.w, self.h)
        self.undo_stack, self.redo_stack = [], []
        self.tool, self.shape, self.size = 'pencil', None, 3
        self.color1, self.color2 = rgba('#000000'), rgba('#ffffff')
        self.zoom = 1.0
        self.path, self.dirty = None, False
        self.drag = None
        self.sel = None          # (x, y, w, h) on the canvas
        self.clip = None         # a cairo surface: the copied selection
        self.floating = None     # (surface, x, y): a pasted or moved selection not yet put down

    @staticmethod
    def blank(w, h):
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(s)
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        return s

    # ---- UI -------------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-paint')
        app.on_open = lambda files: self.guard(lambda: self.load(files[0].get_path()))
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('File', [('New', 'new', lambda: self.guard(self.new)), ('Open…', 'open', lambda: self.guard(self.open)),
                      ('Save', 'save', self.save), ('Save As…', 'saveas', self.save_as), None, ('Exit', 'exit', win.close)]),
            ('Edit', [('Undo', 'undo', self.undo), ('Redo', 'redo', self.redo), None, ('Cut', 'cut', self.cut),
                      ('Copy', 'copy', self.copy), ('Paste', 'paste', self.paste), ('Delete', 'delete', self.delete_sel),
                      None, ('Select All', 'selectall', self.select_all), ('Crop to Selection', 'crop', self.crop)]),
            ('Image', [('Rotate Right', 'rotr', lambda: self.rotate(90)), ('Rotate Left', 'rotl', lambda: self.rotate(-90)),
                       ('Flip Horizontal', 'fliph', lambda: self.flip(True)), ('Flip Vertical', 'flipv', lambda: self.flip(False)),
                       None, ('Canvas Size…', 'canvas', self.canvas_dialog)]),
            ('View', [('Zoom In', 'zin', lambda: self.set_zoom(self.zoom * 2)), ('Zoom Out', 'zout', lambda: self.set_zoom(self.zoom / 2)),
                      ('100%', 'z100', lambda: self.set_zoom(1))]),
        ]))
        root.append(self.ribbon())
        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self.draw)
        self.area.set_halign(Gtk.Align.START)
        self.area.set_valign(Gtk.Align.START)
        self.area.set_margin_top(6)
        self.area.set_margin_start(6)
        self.area.set_margin_end(6)
        self.area.set_margin_bottom(6)
        self.resize_area()
        for button in (1, 3):
            g = Gtk.GestureDrag(button=button)
            g.connect('drag-begin', self.on_begin, button)
            g.connect('drag-update', self.on_update, button)
            g.connect('drag-end', self.on_end, button)
            self.area.add_controller(g)
        motion = Gtk.EventControllerMotion()
        motion.connect('motion', lambda _c, x, y: self.status.set_label(
            f'{int(x / self.zoom)}, {int(y / self.zoom)}px    {self.w} × {self.h}px    {int(self.zoom * 100)}%'))
        self.area.add_controller(motion)
        bg = Gtk.Box()
        bg.add_css_class('pt-canvas-bg')
        bg.append(self.area)
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(bg)
        root.append(sc)
        self.status = Gtk.Label(xalign=0, label=f'{self.w} × {self.h}px')
        self.status.add_css_class('pt-status')
        root.append(self.status)
        win.connect('close-request', self.on_close)
        self.closing_ok = False
        if app.files:
            GLib.idle_add(lambda: self.load(app.files[0].get_path()) and False)
        self.retitle()
        return root

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

    def ribbon(self):
        r = Gtk.Box(vexpand=False, valign=Gtk.Align.START)
        r.add_css_class('pt-ribbon')
        self.tool_btns = {}
        grid = Gtk.Grid(row_spacing=2, column_spacing=2)
        for i, (tid, icon, tip) in enumerate(TOOLS):
            b = Gtk.Button(tooltip_text=tip, focusable=False)
            da = Gtk.DrawingArea(content_width=18, content_height=18)
            da.set_draw_func(self.tool_icon, tid)
            b.set_child(da)
            b.connect('clicked', lambda _b, t=tid: self.set_tool(t))
            self.tool_btns[tid] = b
            grid.attach(b, i % 4, i // 4, 1, 1)
        r.append(self.group('Tools', grid))
        shapes = Gtk.Grid(row_spacing=2, column_spacing=2)
        for i, (sid, tip) in enumerate(SHAPES):
            b = Gtk.Button(tooltip_text=tip, focusable=False)
            da = Gtk.DrawingArea(content_width=18, content_height=18)
            da.set_draw_func(self.shape_icon, sid)
            b.set_child(da)
            b.connect('clicked', lambda _b, s=sid: self.set_tool('shape', s))
            self.tool_btns['shape:' + sid] = b
            shapes.attach(b, i % 2, i // 2, 1, 1)
        r.append(self.group('Shapes', shapes))
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
        self.set_tool('pencil')
        self.set_size(3)
        return r

    @staticmethod
    def paint_swatch(cr, w, h, c):
        cr.set_source_rgba(c.red, c.green, c.blue, c.alpha)
        cr.rectangle(0, 0, w, h)
        cr.fill()

    @staticmethod
    def tool_icon(_a, cr, w, h, tid):
        """MWX 7's own small tool glyphs (drawn, so every tool has one whatever the icon theme holds)."""
        ink = (0.11, 0.19, 0.31)
        cr.set_line_width(1.4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_source_rgb(*ink)
        if tid == 'select':
            cr.set_dash([2.5, 2])
            cr.rectangle(2.5, 3.5, 13, 11)
            cr.stroke()
        elif tid == 'pencil':
            cr.move_to(4, 14); cr.line_to(13, 5); cr.line_to(15, 7); cr.line_to(6, 16); cr.close_path()
            cr.set_source_rgb(0.98, 0.78, 0.25); cr.fill_preserve(); cr.set_source_rgb(*ink); cr.stroke()
            cr.move_to(4, 14); cr.line_to(3, 17); cr.line_to(6, 16); cr.fill()
        elif tid == 'brush':
            cr.move_to(14.5, 3); cr.line_to(8.5, 10); cr.stroke()
            cr.set_source_rgb(0.18, 0.45, 0.85)
            cr.move_to(8, 10); cr.curve_to(4, 10, 5, 15, 2.5, 16); cr.curve_to(7, 16.5, 10.5, 14, 9.5, 11); cr.close_path(); cr.fill()
        elif tid == 'eraser':
            cr.move_to(3, 12); cr.line_to(10, 5); cr.line_to(15, 10); cr.line_to(10, 15); cr.line_to(6, 15); cr.close_path()
            cr.set_source_rgb(0.96, 0.62, 0.72); cr.fill_preserve(); cr.set_source_rgb(*ink); cr.stroke()
            cr.move_to(6.5, 8.5); cr.line_to(11.5, 13.5); cr.stroke()
        elif tid == 'fill':
            cr.move_to(3, 9); cr.line_to(9, 3); cr.line_to(15, 9); cr.line_to(9, 15); cr.close_path()
            cr.set_source_rgb(0.85, 0.92, 1); cr.fill_preserve(); cr.set_source_rgb(*ink); cr.stroke()
            cr.set_source_rgb(0.18, 0.45, 0.85); cr.arc(15.5, 14, 1.8, 0, 2 * math.pi); cr.fill()
        elif tid == 'picker':
            cr.move_to(3, 16); cr.line_to(10, 9); cr.stroke()
            cr.set_line_width(3); cr.move_to(10.5, 8.5); cr.line_to(14.5, 4.5); cr.stroke()
        elif tid == 'text':
            cr.select_font_face('Selawik', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(15); cr.move_to(3, 15); cr.show_text('A')
        elif tid == 'magnifier':
            cr.arc(8, 8, 5, 0, 2 * math.pi); cr.stroke()
            cr.set_line_width(2.4); cr.move_to(11.5, 11.5); cr.line_to(16, 16); cr.stroke()

    def shape_icon(self, _a, cr, w, h, sid):
        cr.set_source_rgb(0.11, 0.19, 0.31)
        cr.set_line_width(1.5)
        self.trace(cr, sid, 2, 3, w - 2, h - 3)
        cr.stroke()

    def set_tool(self, tool, shape=None):
        self.put_down()
        self.tool, self.shape = tool, shape
        if tool != 'select':
            self.sel = None
        for k, b in self.tool_btns.items():
            on = k == (f'shape:{shape}' if tool == 'shape' else tool)
            (b.add_css_class if on else b.remove_css_class)('on')
        if hasattr(self, 'area'):
            self.area.set_cursor(Gdk.Cursor.new_from_name('crosshair' if tool != 'select' else 'default'))
            self.area.queue_draw()

    def set_size(self, s):
        self.size = s
        for k, b in self.size_btns.items():
            (b.add_css_class if k == s else b.remove_css_class)('on')

    def set_color(self, n, c):
        if n == 1:
            self.color1 = c
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

    # ---- drawing --------------------------------------------------------------------------------------------------
    def resize_area(self):
        self.area.set_content_width(int(self.w * self.zoom))
        self.area.set_content_height(int(self.h * self.zoom))

    def set_zoom(self, z):
        self.zoom = max(0.25, min(8.0, z))
        self.resize_area()
        self.area.queue_draw()

    def draw(self, _a, cr, _w, _h):
        cr.scale(self.zoom, self.zoom)
        cr.set_source_surface(self.surface, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST if self.zoom > 1 else cairo.FILTER_GOOD)
        cr.paint()
        if self.floating:
            s, x, y = self.floating
            cr.set_source_surface(s, x, y)
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

    def snapshot(self):
        copy = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.w, self.h)
        cr = cairo.Context(copy)
        cr.set_source_surface(self.surface, 0, 0)
        cr.paint()
        self.undo_stack.append(copy)
        del self.undo_stack[:-30]
        self.redo_stack.clear()

    def replace(self, surface):
        self.surface = surface
        self.w, self.h = surface.get_width(), surface.get_height()
        self.resize_area()
        self.area.queue_draw()

    def undo(self):
        self.put_down()
        if self.undo_stack:
            self.redo_stack.append(self.surface)
            self.replace(self.undo_stack.pop())
            self.touched()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.surface)
            self.replace(self.redo_stack.pop())
            self.touched()

    def color_for(self, button):
        return self.color1 if button == 1 else self.color2

    def trace(self, cr, shape, x0, y0, x1, y1):
        x, y, w, h = min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)
        if shape == 'line':
            cr.move_to(x0, y0)
            cr.line_to(x1, y1)
        elif shape == 'rect':
            cr.rectangle(x, y, w, h)
        elif shape == 'round':
            r = min(10, w / 2, h / 2)
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
        if t == 'magnifier':
            self.set_zoom(self.zoom * (2 if button == 1 else 0.5))
            return
        if t == 'picker':
            self.set_color(1 if button == 1 else 2, self.pixel(int(cx), int(cy)))
            return
        if t == 'fill':
            self.snapshot()
            self.flood(int(cx), int(cy), self.color_for(button))
            self.touched()
            self.area.queue_draw()
            return
        if t == 'text':
            self.text_at(int(cx), int(cy), self.color_for(button))
            return
        if t == 'select':
            if self.floating or (self.sel and self.inside(cx, cy)):
                self.lift()
                s, fx, fy = self.floating
                self.drag = {'move': (cx - fx, cy - fy)}
                return
            self.put_down()
            self.sel = None
            self.drag = {'sel': (cx, cy)}
            return
        self.snapshot()
        self.touched()
        color = self.color_for(button) if t != 'eraser' else self.color2
        self.drag = {'x0': cx, 'y0': cy, 'last': (cx, cy), 'color': color}
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
            self.area.queue_draw()
            return
        if self.tool in ('pencil', 'brush', 'eraser'):
            self.paint_free(cx, cy)
        elif self.tool == 'shape':
            x0, y0, color, w = d['x0'], d['y0'], d['color'], self.size

            def preview(cr, x1=cx, y1=cy):
                cr.set_source_rgba(color.red, color.green, color.blue, 1)
                cr.set_line_width(w)
                self.trace(cr, self.shape, x0, y0, x1, y1)
                cr.stroke()
            d['preview'] = preview
            d['end'] = (cx, cy)
            self.area.queue_draw()

    def on_end(self, g, dx, dy, button):
        d, self.drag = self.drag, None
        if not d:
            return
        if self.tool == 'shape' and 'end' in d:
            cr = cairo.Context(self.surface)
            c = d['color']
            cr.set_source_rgba(c.red, c.green, c.blue, 1)
            cr.set_line_width(self.size)
            self.trace(cr, self.shape, d['x0'], d['y0'], *d['end'])
            cr.stroke()
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

    def flood(self, x, y, color):
        """Scanline flood fill on the raw pixels (exact colour match, as Paint does)."""
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        self.surface.flush()
        buf = self.surface.get_data()
        stride, w, h = self.surface.get_stride(), self.w, self.h
        new = bytes((int(color.blue * 255), int(color.green * 255), int(color.red * 255), 255))
        at = y * stride + x * 4
        old = bytes(buf[at:at + 4])
        if old == new:
            return
        stack = [(x, y)]
        while stack:
            px, py = stack.pop()
            row = py * stride
            lx = px
            while lx > 0 and buf[row + (lx - 1) * 4: row + lx * 4] == old:
                lx -= 1
            rx = px
            while rx < w and buf[row + rx * 4: row + rx * 4 + 4] == old:
                rx += 1
            if rx <= lx:
                continue
            buf[row + lx * 4: row + rx * 4] = new * (rx - lx)
            for ny in (py - 1, py + 1):
                if 0 <= ny < h:
                    nrow = ny * stride
                    i = lx
                    while i < rx:
                        if buf[nrow + i * 4: nrow + i * 4 + 4] == old:
                            stack.append((i, ny))
                            while i < rx and buf[nrow + i * 4: nrow + i * 4 + 4] == old:
                                i += 1
                        i += 1
        self.surface.mark_dirty()

    def text_at(self, x, y, color):
        pop = Gtk.Popover()
        entry = Gtk.Entry(placeholder_text='Type, then press the button', width_chars=24)
        ok = Gtk.Button(label='Put down')
        box = Gtk.Box(spacing=6)
        box.append(entry)
        box.append(ok)
        pop.set_child(box)
        pop.set_parent(self.area)
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = int(x * self.zoom), int(y * self.zoom), 1, 1
        pop.set_pointing_to(r)

        def put(*_):
            text = entry.get_text()
            pop.popdown()
            if not text:
                return
            self.snapshot()
            cr = cairo.Context(self.surface)
            cr.set_source_rgba(color.red, color.green, color.blue, 1)
            cr.select_font_face('Selawik')
            cr.set_font_size(10 + self.size * 3)
            cr.move_to(x, y + 10 + self.size * 3)
            cr.show_text(text)
            self.touched()
            self.area.queue_draw()
        ok.connect('clicked', put)
        entry.connect('activate', put)
        pop.popup()
        entry.grab_focus()

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
        if self.floating:
            s, x, y = self.floating
            cr = cairo.Context(self.surface)
            cr.set_source_surface(s, x, y)
            cr.paint()
            self.floating = None
            if hasattr(self, 'area'):
                self.area.queue_draw()

    def select_all(self):
        self.set_tool('select')
        self.sel = (0, 0, self.w, self.h)
        self.area.queue_draw()

    def copy(self):
        if self.floating:
            self.clip = self.floating[0]
        elif self.sel:
            self.clip = self.cut_out(self.sel, False)
        if self.clip:
            self.win.get_clipboard().set(Gdk.Texture.new_for_pixbuf(
                Gdk.pixbuf_get_from_surface(self.clip, 0, 0, self.clip.get_width(), self.clip.get_height())))

    def cut(self):
        self.copy()
        self.delete_sel()

    def delete_sel(self):
        if self.floating:
            self.floating = None
        elif self.sel:
            self.snapshot()
            self.cut_out(self.sel, True)
        self.sel = None
        self.touched()
        self.area.queue_draw()

    def paste(self):
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
            self.put_down()
            self.set_tool('select')
            self.snapshot()
            self.floating = (surf, 0, 0)
            self.sel = (0, 0, surf.get_width(), surf.get_height())
            self.touched()
            self.area.queue_draw()
        self.win.get_clipboard().read_texture_async(None, got)

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
        if self.closing_ok or not self.dirty:
            return False

        def go():
            self.closing_ok = True
            self.win.close()
        self.guard(go)
        return True


if __name__ == '__main__':
    paint = Paint()
    mwx7ui.App('org.mwx7.paint', 'Paint', 'paint', (1000, 700), CSS, paint.build).run_main()
