"""Settings -> Display: the arrangement view. Rectangles for the screens, dragged to say where each one sits (Windows 7's
"Identify / drag the monitors" box). Pure drawing and geometry; Settings applies the result (wlr-randr, wayfire.ini).

Screens are dicts {name, label, x, y, w, h} in the compositor's logical pixels (mode size / scale, swapped when rotated).
"""
import math

import cairo
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk  # noqa: E402

SNAP = 36  # logical pixels within which an edge snaps to a neighbour's edge


def logical_size(o):
    """Width and height of a screen in the layout: its current mode over its scale, swapped when rotated 90/270."""
    mode = next((m for m in o.get('modes', []) if m.get('current')), None) or (o.get('modes') or [{}])[0]
    try:
        scale = float(o.get('scale') or 1) or 1.0
    except (TypeError, ValueError):
        scale = 1.0
    w, h = int(mode.get('width') or 1920), int(mode.get('height') or 1080)
    if str(o.get('transform') or 'normal') in ('90', '270', 'flipped-90', 'flipped-270'):
        w, h = h, w
    return max(1, round(w / scale)), max(1, round(h / scale))


def position_of(o):
    p = o.get('position')
    if isinstance(p, dict):
        try:
            return int(p.get('x', 0)), int(p.get('y', 0))
        except (TypeError, ValueError):
            pass
    return 0, 0


def overlaps(a, b):
    return a['x'] < b['x'] + b['w'] and b['x'] < a['x'] + a['w'] and a['y'] < b['y'] + b['h'] and b['y'] < a['y'] + a['h']


def touches(a, b):
    """Edge to edge with some length in common (a corner touch does not count: the pointer could not cross)."""
    if a['x'] + a['w'] == b['x'] or b['x'] + b['w'] == a['x']:
        return a['y'] < b['y'] + b['h'] and b['y'] < a['y'] + a['h']
    if a['y'] + a['h'] == b['y'] or b['y'] + b['h'] == a['y']:
        return a['x'] < b['x'] + b['w'] and b['x'] < a['x'] + a['w']
    return False


def settle(r, others):
    """Where a dropped screen ends up: where it is if it touches a neighbour without overlapping any, else the nearest spot
    beside one of them (right, left, below or above, keeping its other coordinate)."""
    if not others:
        return r['x'], r['y']
    if not any(overlaps(r, o) for o in others) and any(touches(r, o) for o in others):
        return r['x'], r['y']
    best = None
    for o in others:
        for x, y in ((o['x'] + o['w'], r['y']), (o['x'] - r['w'], r['y']), (r['x'], o['y'] + o['h']), (r['x'], o['y'] - r['h'])):
            # keep the shared stretch of edge: clamp the free coordinate so the two share some length
            if x in (o['x'] + o['w'], o['x'] - r['w']):
                y = min(max(y, o['y'] - r['h'] + 1), o['y'] + o['h'] - 1)
            else:
                x = min(max(x, o['x'] - r['w'] + 1), o['x'] + o['w'] - 1)
            cand = dict(r, x=x, y=y)
            if any(overlaps(cand, p) for p in others):
                continue
            d = math.hypot(x - r['x'], y - r['y'])
            if best is None or d < best[0]:
                best = (d, x, y)
    return (best[1], best[2]) if best else (r['x'], r['y'])


def snap(r, others):
    """While dragging: pull an edge onto a neighbour's near edge, and line up tops, bottoms, lefts and rights."""
    for o in others:
        for mine, theirs in ((r['x'], o['x'] + o['w']), (r['x'] + r['w'], o['x']), (r['x'], o['x']), (r['x'] + r['w'], o['x'] + o['w'])):
            if abs(mine - theirs) <= SNAP:
                r['x'] += theirs - mine
                break
        for mine, theirs in ((r['y'], o['y'] + o['h']), (r['y'] + r['h'], o['y']), (r['y'], o['y']), (r['y'] + r['h'], o['y'] + o['h'])):
            if abs(mine - theirs) <= SNAP:
                r['y'] += theirs - mine
                break


def normalize(rects):
    """Shift everything so the top-left screen sits at 0,0 (the layout has no use for a negative origin)."""
    if rects:
        mx, my = min(r['x'] for r in rects), min(r['y'] for r in rects)
        for r in rects:
            r['x'] -= mx
            r['y'] -= my


class Arrange(Gtk.DrawingArea):
    """Draws the screens scaled to fit and lets the person drag them. `on_select(name)` on a click, `on_moved()` after a
    drop (positions already settled and normalized)."""

    def __init__(self, rects, primary, on_select=None, on_moved=None, height=210):
        super().__init__(hexpand=True)
        self.set_content_height(height)
        self.set_size_request(320, height)
        self.rects, self.primary, self.selected = rects, primary, (rects[0]['name'] if rects else '')
        self.on_select, self.on_moved = on_select, on_moved
        self.drag, self.scale, self.origin = None, 1.0, (0, 0)
        self.set_draw_func(self.draw)
        g = Gtk.GestureDrag(button=1)
        g.connect('drag-begin', self.begin)
        g.connect('drag-update', self.update)
        g.connect('drag-end', self.end)
        self.add_controller(g)

    def fit(self, W, H):
        """Scale and offset that put the bounding box of all screens (plus room to move) in the widget."""
        if not self.rects:
            return
        bw = max(r['x'] + r['w'] for r in self.rects) - min(r['x'] for r in self.rects)
        bh = max(r['y'] + r['h'] for r in self.rects) - min(r['y'] for r in self.rects)
        # Room to drag a screen to the other side: the box is laid out as if one more screen fitted around it.
        span_w, span_h = bw + max(r['w'] for r in self.rects) / 2, bh + max(r['h'] for r in self.rects) / 2
        self.scale = min((W - 24) / span_w, (H - 24) / span_h, 0.2)
        mx, my = min(r['x'] for r in self.rects), min(r['y'] for r in self.rects)
        self.origin = ((W - bw * self.scale) / 2 - mx * self.scale, (H - bh * self.scale) / 2 - my * self.scale)

    def box(self, r):
        s, (ox, oy) = self.scale, self.origin
        return ox + r['x'] * s, oy + r['y'] * s, r['w'] * s, r['h'] * s

    def draw(self, _area, cr, W, H):
        cr.set_source_rgb(0.914, 0.933, 0.965)
        cr.rectangle(0, 0, W, H)
        cr.fill()
        cr.set_source_rgb(0.72, 0.78, 0.88)
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, W - 1, H - 1)
        cr.stroke()
        if self.drag is None:
            self.fit(W, H)  # frozen while dragging so the screens do not slide under the pointer
        for i, r in enumerate(self.rects):
            x, y, w, h = self.box(r)
            sel = r['name'] == self.selected
            cr.rectangle(x, y, w, h)
            from_rgb, to_rgb = ((0.20, 0.45, 0.85), (0.10, 0.28, 0.62)) if sel else ((0.40, 0.55, 0.78), (0.28, 0.40, 0.62))
            grad = cairo.LinearGradient(0, y, 0, y + h)
            grad.add_color_stop_rgb(0, *from_rgb)
            grad.add_color_stop_rgb(1, *to_rgb)
            cr.set_source(grad)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 1) if sel else cr.set_source_rgba(1, 1, 1, 0.55)
            cr.set_line_width(2 if sel else 1)
            cr.stroke()
            if r['name'] == self.primary:  # the bar along the top and the dock along the bottom, in miniature
                cr.set_source_rgba(1, 1, 1, 0.35)
                cr.rectangle(x + 1, y + 1, w - 2, max(3, h * 0.07))
                cr.fill()
                cr.rectangle(x + w * 0.3, y + h - max(3, h * 0.07) - 1, w * 0.4, max(3, h * 0.07))
                cr.fill()
            cr.select_font_face('Selawik', 0, 1)
            cr.set_source_rgb(1, 1, 1)
            cr.set_font_size(min(34, max(14, h * 0.4)))
            num = str(i + 1)
            ext = cr.text_extents(num)
            cr.move_to(x + (w - ext.width) / 2 - ext.x_bearing, y + (h + ext.height) / 2 - 2)
            cr.show_text(num)
            cr.select_font_face('Selawik', 0, 0)
            cr.set_font_size(11)
            line = f"{r['name']}  {r['w']}×{r['h']}" + ('  ★' if r['name'] == self.primary else '')
            ext = cr.text_extents(line)
            if ext.width < w - 6:
                cr.set_source_rgba(1, 1, 1, 0.9)
                cr.move_to(x + (w - ext.width) / 2 - ext.x_bearing, y + h - 8)
                cr.show_text(line)

    def hit(self, px, py):
        for r in reversed(self.rects):
            x, y, w, h = self.box(r)
            if x <= px <= x + w and y <= py <= y + h:
                return r
        return None

    def begin(self, _g, px, py):
        r = self.hit(px, py)
        self.drag = None
        if r is None:
            return
        self.selected = r['name']
        if self.on_select:
            self.on_select(r['name'])
        self.drag = (r, r['x'], r['y'])
        self.queue_draw()

    def update(self, _g, dx, dy):
        if self.drag is None:
            return
        r, x0, y0 = self.drag
        r['x'], r['y'] = x0 + round(dx / self.scale), y0 + round(dy / self.scale)
        snap(r, [o for o in self.rects if o is not r])
        self.queue_draw()

    def end(self, _g, _dx, _dy):
        if self.drag is None:
            return
        r = self.drag[0]
        self.drag = None
        r['x'], r['y'] = settle(r, [o for o in self.rects if o is not r])
        normalize(self.rects)
        self.queue_draw()
        if self.on_moved:
            self.on_moved()
