"""Solitaire (native): Klondike, draw 1. Cards are drawn with cairo on green felt; drag with the mouse."""
import random
import sys

import cairo

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import GLib, Gtk  # noqa: E402
from mwx7cards import CH, CW, card_rrect, draw_card, is_red, text  # noqa: E402

GAP, M, TAB_Y = 14, 14, 132
SW, SH = 7 * CW + 8 * GAP, 560
DOWN_STEP, UP_STEP = 8, 22
CSS = "window.mwx7-solitaire > box { background: #0e5a2e; }"

# A card is [suit, rank, face_up]; suits: 0 spade, 1 heart, 2 diamond, 3 club. Drawing lives in lib/mwx7cards.py.


def col_x(i):
    return M + i * (CW + GAP)


class Solitaire:
    def build(self, app, win):
        win.add_css_class('mwx7-solitaire')
        self.app = app
        self.timer = 0
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([('Game', [('New Game', 'new', lambda: self.new_game())])]))
        app.set_accels_for_action('app.new', ['F2'])
        self.area = Gtk.DrawingArea(content_width=SW, content_height=SH)
        self.area.set_draw_func(self.draw)
        drag = Gtk.GestureDrag(button=1)
        drag.connect('drag-begin', self.drag_begin)
        drag.connect('drag-update', self.drag_update)
        drag.connect('drag-end', self.drag_end)
        self.area.add_controller(drag)
        click = Gtk.GestureClick(button=1)
        click.connect('pressed', self.on_click)
        self.area.add_controller(click)
        root.append(self.area)
        self.new_game()
        return root

    def new_game(self):
        self.stop()
        deck = [[s, r, False] for s in range(4) for r in range(1, 14)]
        random.shuffle(deck)
        self.tab = [[] for _ in range(7)]
        for col in range(7):
            for _ in range(col + 1):
                self.tab[col].append(deck.pop())
            self.tab[col][-1][2] = True
        self.stock, self.waste, self.found = deck, [], [[] for _ in range(4)]
        self.score = self.secs = 0
        self.won = self.auto = False
        self.held = None  # (cards, source kind, source index, grab dx, grab dy)
        self.pos = (0, 0)
        self.area.queue_draw()

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def start_timer(self):
        if not self.timer and not self.won:
            self.timer = GLib.timeout_add(1000, self.tick)

    def tick(self):
        self.secs += 1
        self.area.queue_draw()
        return True

    # --- rules ---
    def can_tab(self, card, col):
        pile = self.tab[col]
        if not pile:
            return card[1] == 13
        top = pile[-1]
        return top[2] and is_red(top[0]) != is_red(card[0]) and top[1] == card[1] + 1

    def can_found(self, card, f):
        pile = self.found[f]
        return pile[-1][0] == card[0] and pile[-1][1] + 1 == card[1] if pile else card[1] == 1

    def tab_y(self, col, idx):
        y = TAB_Y
        for c in self.tab[col][:idx]:
            y += UP_STEP if c[2] else DOWN_STEP
        return y

    def move(self, cards, src, si, dest, di):
        """Moves the tail `cards` of a pile onto another and applies scoring and the auto-flip."""
        pile = {'waste': self.waste, 'found': self.found[si] if src == 'found' else None,
                'tab': self.tab[si] if src == 'tab' else None}[src]
        del pile[len(pile) - len(cards):]
        (self.found[di] if dest == 'found' else self.tab[di]).extend(cards)
        if src == 'waste':
            self.score += 10 if dest == 'found' else 5
        elif src == 'tab' and dest == 'found':
            self.score += 10
        elif src == 'found' and dest == 'tab':
            self.score = max(0, self.score - 15)
        if src == 'tab' and pile and not pile[-1][2]:
            pile[-1][2] = True
            self.score += 5
        self.start_timer()
        self.after_move()

    def draw_stock(self):
        if self.won or self.auto:
            return
        if self.stock:
            c = self.stock.pop()
            c[2] = True
            self.waste.append(c)
        elif self.waste:
            self.stock = self.waste[::-1]
            for c in self.stock:
                c[2] = False
            self.waste = []
            self.score = max(0, self.score - 100)
        self.start_timer()
        self.after_move()

    def after_move(self):
        if all(len(f) == 13 for f in self.found):
            self.won = True
            self.stop()
            self.app.set_title('Solitaire - You win!')
        elif not self.auto and all(c[2] for p in self.tab for c in p):
            # Everything is face up: the game can only be won from here, so finish it.
            self.auto, self.idle = True, 0
            GLib.timeout_add(70, self.auto_step)
        self.area.queue_draw()

    def auto_step(self):
        if self.won or not self.auto:
            return False
        for src, pile, si in [('waste', self.waste, 0)] + [('tab', p, i) for i, p in enumerate(self.tab)]:
            if pile:
                for f in range(4):
                    if self.can_found(pile[-1], f):
                        self.idle = 0
                        self.move([pile[-1]], src, si, 'found', f)
                        return True
        # Nothing fits on a foundation: turn the stock, but give up after one full pass without a move.
        self.idle += 1
        if self.idle > len(self.stock) + len(self.waste) + 1:
            self.auto = False
            return False
        if self.stock:
            c = self.stock.pop()
            c[2] = True
            self.waste.append(c)
        else:
            self.stock = self.waste[::-1]
            for c in self.stock:
                c[2] = False
            self.waste = []
        self.area.queue_draw()
        return True

    # --- hit testing ---
    def hit(self, x, y):
        """Returns (kind, index, card index) for the topmost thing under the point, or None."""
        if M <= y <= M + CH:
            if col_x(0) <= x <= col_x(0) + CW:
                return ('stock', 0, 0)
            if col_x(1) <= x <= col_x(1) + CW and self.waste:
                return ('waste', 0, len(self.waste) - 1)
            for f in range(4):
                if col_x(3 + f) <= x <= col_x(3 + f) + CW and self.found[f]:
                    return ('found', f, len(self.found[f]) - 1)
        for col in range(7):
            if col_x(col) <= x <= col_x(col) + CW:
                for idx in range(len(self.tab[col]) - 1, -1, -1):
                    top = self.tab_y(col, idx)
                    if top <= y <= top + CH:
                        return ('tab', col, idx) if self.tab[col][idx][2] else None
        return None

    # --- mouse ---
    def drag_begin(self, _g, x, y):
        if self.won or self.auto:
            return
        h = self.hit(x, y)
        self.held = None
        if not h:
            return
        kind, i, idx = h
        if kind == 'stock':
            return self.draw_stock()
        if kind == 'tab':
            cards, ox, oy = self.tab[i][idx:], col_x(i), self.tab_y(i, idx)
        elif kind == 'waste':
            cards, ox, oy = [self.waste[-1]], col_x(1), M
        else:
            cards, ox, oy = [self.found[i][-1]], col_x(3 + i), M
        self.held = (cards, kind, i, x - ox, y - oy)
        self.start = (x, y)
        self.pos = (x, y)

    def drag_update(self, _g, dx, dy):
        if self.held:
            self.pos = (self.start[0] + dx, self.start[1] + dy)
            self.area.queue_draw()

    def drag_end(self, _g, dx, dy):
        if not self.held:
            return
        cards, kind, si, gx, gy = self.held
        self.held = None
        if abs(dx) + abs(dy) > 3:
            cx = self.start[0] + dx - gx + CW / 2
            cy = self.start[1] + dy - gy + CH / 2
            # Nearest valid pile to the dragged card's centre.
            if len(cards) == 1 and M - 10 <= cy <= M + CH + 10:
                for f in range(4):
                    if col_x(3 + f) - GAP / 2 <= cx <= col_x(3 + f) + CW + GAP / 2 and self.can_found(cards[0], f):
                        if not (kind == 'found' and si == f):
                            return self.move(cards, kind, si, 'found', f)
            if cy > M + CH:
                for col in range(7):
                    if col_x(col) - GAP / 2 <= cx <= col_x(col) + CW + GAP / 2 and self.can_tab(cards[0], col):
                        if not (kind == 'tab' and si == col):
                            return self.move(cards, kind, si, 'tab', col)
        self.area.queue_draw()

    def on_click(self, _g, n, x, y):
        if self.won:
            return self.new_game()
        if n != 2 or self.auto:
            return
        h = self.hit(x, y)
        if not h or h[0] not in ('waste', 'tab', 'found'):
            return
        kind, i, idx = h
        pile = self.waste if kind == 'waste' else self.found[i] if kind == 'found' else self.tab[i]
        if idx != len(pile) - 1:
            return
        for f in range(4):
            if kind != 'found' and self.can_found(pile[-1], f):
                return self.move([pile[-1]], kind, i, 'found', f)

    # --- drawing ---
    def slot(self, cr, x, y, label=None):
        card_rrect(cr, x, y)
        cr.set_source_rgba(0, 0, 0, 0.22)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.3)
        cr.set_line_width(1.5)
        cr.stroke()
        if label:
            cr.set_source_rgba(1, 1, 1, 0.35)
            text(cr, label, x + CW / 2 - 8, y + CH / 2 + 8, 24)

    def draw(self, _a, cr, w, h):
        g = cairo.RadialGradient(w / 2, h / 2, 40, w / 2, h / 2, max(w, h) * 0.75)
        g.add_color_stop_rgb(0, 0.12, 0.45, 0.24)
        g.add_color_stop_rgb(1, 0.04, 0.27, 0.13)
        cr.set_source(g)
        cr.paint()
        self.slot(cr, col_x(0), M, '↻')
        self.slot(cr, col_x(1), M)
        for f in range(4):
            self.slot(cr, col_x(3 + f), M, ['♠', '♥', '♦', '♣'][f])
        for col in range(7):
            self.slot(cr, col_x(col), TAB_Y)
        held = {id(c) for c in self.held[0]} if self.held else set()
        if self.stock:
            draw_card(cr, [0, 1, False], col_x(0), M)
        if self.waste:
            below = [c for c in self.waste if id(c) not in held]
            if below:
                draw_card(cr, below[-1], col_x(1), M)
        for f in range(4):
            for c in [c for c in self.found[f] if id(c) not in held][-1:]:
                draw_card(cr, c, col_x(3 + f), M)
        for col in range(7):
            for idx, c in enumerate(self.tab[col]):
                if id(c) not in held:
                    draw_card(cr, c, col_x(col), self.tab_y(col, idx))
        if self.held:
            cards, _k, _i, gx, gy = self.held
            for k, c in enumerate(cards):
                draw_card(cr, c, self.pos[0] - gx, self.pos[1] - gy + k * UP_STEP)
        cr.set_source_rgba(1, 1, 1, 0.9)
        text(cr, f'Score: {self.score}', 14, h - 12, 13)
        text(cr, f'Time: {self.secs // 60}:{self.secs % 60:02d}', 130, h - 12, 13)
        if self.won:
            cr.set_source_rgba(0, 0, 0, 0.45)
            cr.paint()
            cr.set_source_rgb(1, 1, 1)
            cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(40)
            e = cr.text_extents('You win!')
            cr.move_to(w / 2 - e.width / 2, h / 2)
            cr.show_text('You win!')
            text(cr, 'Click anywhere for a new game', w / 2 - 105, h / 2 + 34, 15)


if __name__ == '__main__':
    game = Solitaire()
    mwx7ui.App('org.mwx7.solitaire', 'Solitaire', 'solitaire', (SW, SH), CSS, game.build, resizable=False).run_main()
