"""Mines (native): Minesweeper with glossy Windows 7 blue tiles, drawn with cairo in one widget."""
import math
import random
import sys

import cairo

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import GLib, Gtk  # noqa: E402

LEVELS = {'beginner': (9, 9, 10, 'Beginner'), 'intermediate': (16, 16, 40, 'Intermediate'), 'expert': (30, 16, 99, 'Expert')}
CELL, PAD, HEAD = 24, 10, 44
NUM_COLORS = [None, (0.1, 0.3, 0.85), (0.1, 0.5, 0.15), (0.85, 0.15, 0.15), (0.1, 0.1, 0.5), (0.55, 0.1, 0.1),
              (0.0, 0.5, 0.5), (0.1, 0.1, 0.1), (0.4, 0.4, 0.4)]
CSS = """
window.mwx7-mines > box { background: linear-gradient(180deg, #dbe6f3 0%, #c3d3e8 100%); }
"""


def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    for cx, cy, a in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        cr.arc(cx, cy, r, math.radians(a), math.radians(a + 90))
    cr.close_path()


def glossy(cr, x, y, w, h, top, bottom, line):
    """A Windows 7 glass button: dark rim, light top half, deeper bottom half."""
    rrect(cr, x, y, w, h, 3)
    cr.set_source_rgb(*line)
    cr.fill()
    g = cairo.LinearGradient(0, y, 0, y + h)
    g.add_color_stop_rgb(0, *top)
    g.add_color_stop_rgb(0.5, *top)
    g.add_color_stop_rgb(0.51, *bottom)
    g.add_color_stop_rgb(1, *bottom)
    rrect(cr, x + 1, y + 1, w - 2, h - 2, 2)
    cr.set_source(g)
    cr.fill()


def centered(cr, text, cx, cy, size, bold=True):
    cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    e = cr.text_extents(text)
    cr.move_to(cx - e.width / 2 - e.x_bearing, cy - e.height / 2 - e.y_bearing)
    cr.show_text(text)


class Mines:
    def build(self, app, win):
        win.add_css_class('mwx7-mines')
        self.app = app
        self.timer = 0
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('Game', [('New Game', 'new', lambda: self.reset()), None,
                      ('Beginner', 'beginner', lambda: self.set_level('beginner')),
                      ('Intermediate', 'intermediate', lambda: self.set_level('intermediate')),
                      ('Expert', 'expert', lambda: self.set_level('expert'))]),
        ]))
        self.area = Gtk.DrawingArea(halign=Gtk.Align.CENTER, valign=Gtk.Align.START, margin_top=6, margin_bottom=6,
                                    margin_start=6, margin_end=6)
        self.area.set_draw_func(self.draw)
        for button, fn in ((1, self.on_left), (3, self.on_right)):
            g = Gtk.GestureClick(button=button)
            g.connect('pressed', fn)
            self.area.add_controller(g)
        root.append(self.area)
        app.set_accels_for_action('app.new', ['F2'])
        self.set_level('beginner')
        return root

    def set_level(self, level):
        self.cols, self.rows, self.total, _name = LEVELS[level]
        self.area.set_content_width(self.cols * CELL + PAD * 2)
        self.area.set_content_height(self.rows * CELL + PAD * 2 + HEAD)
        self.reset()

    def reset(self):
        self.stop()
        n = self.cols * self.rows
        self.mine, self.open, self.flag, self.num = [False] * n, [False] * n, [False] * n, [0] * n
        self.state, self.secs, self.flags, self.opened, self.hit = 'ready', 0, 0, 0, -1
        self.area.queue_draw()
        self.app.set_title('Mines')

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def tick(self):
        self.secs = min(999, self.secs + 1)
        self.area.queue_draw()
        return True

    def neighbours(self, i):
        x, y = i % self.cols, i // self.cols
        return [(y + dy) * self.cols + x + dx for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if (dx or dy) and 0 <= x + dx < self.cols and 0 <= y + dy < self.rows]

    def plant(self, safe):
        # The first click and its neighbours are never mines, so the first reveal always opens an area.
        avoid = {safe, *self.neighbours(safe)}
        pool = [i for i in range(self.cols * self.rows) if i not in avoid]
        for i in random.sample(pool, self.total):
            self.mine[i] = True
        for i in range(self.cols * self.rows):
            self.num[i] = sum(self.mine[j] for j in self.neighbours(i))

    def reveal(self, start):
        if self.open[start] or self.flag[start]:
            return
        if self.state == 'ready':
            self.plant(start)
            self.state = 'play'
            self.timer = GLib.timeout_add(1000, self.tick)
        if self.mine[start]:
            self.state, self.hit = 'lost', start
            self.app.set_title('Mines - Boom! Click the smiley to try again')
            self.stop()
            return
        stack = [start]
        self.open[start] = True
        while stack:
            i = stack.pop()
            self.opened += 1
            if self.num[i]:
                continue
            for j in self.neighbours(i):
                if not self.open[j] and not self.mine[j]:
                    if self.flag[j]:
                        self.flag[j] = False
                        self.flags -= 1
                    self.open[j] = True
                    stack.append(j)
        if self.opened == self.cols * self.rows - self.total:
            self.state = 'won'
            self.stop()
            self.flag = [f or m for f, m in zip(self.flag, self.mine)]
            self.flags = self.total
            self.app.set_title(f'Mines - You win! {self.secs} s')

    def cell_at(self, x, y):
        if x < PAD or y < PAD + HEAD:
            return -1
        cx, cy = int((x - PAD) // CELL), int((y - PAD - HEAD) // CELL)
        return cy * self.cols + cx if cx < self.cols and cy < self.rows else -1

    def on_left(self, _g, n, x, y):
        w = self.cols * CELL + PAD * 2
        if abs(x - w / 2) <= 16 and 6 <= y <= 38:
            return self.reset()
        i = self.cell_at(x, y)
        if i < 0 or self.state not in ('ready', 'play'):
            return
        # Double-click an opened number whose flags match it: open the rest around it (chord).
        if n == 2 and self.open[i] and self.num[i] and sum(self.flag[j] for j in self.neighbours(i)) == self.num[i]:
            for j in self.neighbours(i):
                if self.state == 'play':
                    self.reveal(j)
        else:
            self.reveal(i)
        self.area.queue_draw()

    def on_right(self, _g, _n, x, y):
        i = self.cell_at(x, y)
        if i >= 0 and self.state == 'play' and not self.open[i]:
            self.flag[i] = not self.flag[i]
            self.flags += 1 if self.flag[i] else -1
            self.area.queue_draw()

    # --- drawing ---
    def lcd(self, cr, x, y, value):
        rrect(cr, x, y, 50, 28, 3)
        cr.set_source_rgb(0.04, 0.07, 0.12)
        cr.fill()
        cr.set_source_rgb(0.3, 0.85, 1.0)
        cr.select_font_face('monospace', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        centered(cr, f'{max(-99, min(999, value)):03d}', x + 25, y + 14, 22)

    def flag_icon(self, cr, x, y):
        cr.set_source_rgb(0.17, 0.2, 0.25)
        cr.rectangle(x + 11, y + 5, 1.6, 13)
        cr.rectangle(x + 7, y + 17, 9, 2.4)
        cr.fill()
        cr.set_source_rgb(0.85, 0.1, 0.1)
        cr.move_to(x + 11, y + 5)
        cr.line_to(x + 5, y + 8.5)
        cr.line_to(x + 11, y + 12)
        cr.close_path()
        cr.fill()

    def mine_icon(self, cr, x, y):
        cx, cy = x + CELL / 2, y + CELL / 2
        cr.set_source_rgb(0.06, 0.08, 0.12)
        cr.set_line_width(1.7)
        for a in range(0, 180, 45):
            dx, dy = 7.5 * math.cos(math.radians(a)), 7.5 * math.sin(math.radians(a))
            cr.move_to(cx - dx, cy - dy)
            cr.line_to(cx + dx, cy + dy)
        cr.stroke()
        cr.arc(cx, cy, 5, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.arc(cx - 1.8, cy - 1.8, 1.4, 0, 2 * math.pi)
        cr.fill()

    def face(self, cr, fx, fy):
        cr.set_source_rgb(0.06, 0.13, 0.25)
        cr.set_line_width(2)
        if self.state == 'lost':
            for ex in (-5, 5):
                cr.move_to(fx + ex - 2.5, fy - 7.5)
                cr.line_to(fx + ex + 2.5, fy - 2.5)
                cr.move_to(fx + ex - 2.5, fy - 2.5)
                cr.line_to(fx + ex + 2.5, fy - 7.5)
            cr.stroke()
            cr.arc(fx, fy + 8, 5, math.pi, 2 * math.pi)
            cr.stroke()
            return
        if self.state == 'won':  # sunglasses
            for ex in (-9, 2):
                rrect(cr, fx + ex, fy - 7, 7, 5, 2)
            cr.fill()
        else:
            for ex in (-5, 5):
                cr.arc(fx + ex, fy - 4, 1.8, 0, 2 * math.pi)
                cr.fill()
        cr.arc(fx, fy + 1, 7, math.radians(25), math.radians(155))
        cr.stroke()

    def draw(self, _a, cr, w, h):
        glossy(cr, 2, 2, w - 4, HEAD - 6, (0.96, 0.98, 1), (0.84, 0.89, 0.95), (0.55, 0.64, 0.75))
        self.lcd(cr, PAD + 2, 8, self.total - self.flags)
        self.lcd(cr, w - PAD - 52, 8, self.secs)
        glossy(cr, w / 2 - 16, 6, 32, 32, (0.74, 0.9, 0.99), (0.4, 0.7, 0.93), (0.2, 0.4, 0.65))
        self.face(cr, w / 2, 22)
        lost = self.state == 'lost'
        for i in range(self.cols * self.rows):
            x, y = PAD + (i % self.cols) * CELL, PAD + HEAD + (i // self.cols) * CELL
            if self.open[i] or (lost and self.mine[i] and not self.flag[i]):
                cr.rectangle(x, y, CELL, CELL)
                cr.set_source_rgb(*((0.95, 0.3, 0.25) if i == self.hit else (0.9, 0.94, 0.98)))
                cr.fill_preserve()
                cr.set_source_rgb(0.7, 0.77, 0.86)
                cr.set_line_width(1)
                cr.stroke()
                if self.mine[i]:
                    self.mine_icon(cr, x, y)
                elif self.num[i]:
                    cr.set_source_rgb(*NUM_COLORS[self.num[i]])
                    centered(cr, str(self.num[i]), x + CELL / 2, y + CELL / 2, 15)
            else:
                glossy(cr, x + 0.5, y + 0.5, CELL - 1, CELL - 1, (0.66, 0.84, 0.98), (0.3, 0.6, 0.9), (0.18, 0.38, 0.62))
                if self.flag[i]:
                    self.flag_icon(cr, x, y)
                    if lost and not self.mine[i]:  # a wrong flag
                        cr.set_source_rgb(0.85, 0.1, 0.1)
                        cr.set_line_width(2)
                        cr.move_to(x + 4, y + 4)
                        cr.line_to(x + CELL - 4, y + CELL - 4)
                        cr.move_to(x + CELL - 4, y + 4)
                        cr.line_to(x + 4, y + CELL - 4)
                        cr.stroke()

if __name__ == '__main__':
    game = Mines()
    mwx7ui.App('org.mwx7.mines', 'Mines', 'mines', (200, 300), CSS, game.build, resizable=False).run_main()
