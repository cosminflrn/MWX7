"""Spider Solitaire (native): two decks, one, two or four suits, a deal row from the stock, finished K-to-A runs leave for
the foundation, unlimited undo and a hint."""
import random
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7cards as mc  # noqa: E402
import mwx7ui  # noqa: E402
from mwx7cards import CH, CW, draw_card, slot, text  # noqa: E402
from mwx7ui import GLib, Gtk  # noqa: E402

GAP, M, TAB_Y = 10, 10, 132
SW, SH = 10 * CW + 11 * GAP, 640
DOWN_STEP, UP_STEP = 8, 22
CSS = "window.mwx7-spider > box { background: #0e5a2e; }"
LEVELS = [(1, 'One Suit (Easy)'), (2, 'Two Suits (Medium)'), (4, 'Four Suits (Difficult)')]

# A card is (suit, rank, face_up) with suit 0 spade, 1 heart, 2 diamond, 3 club; tuples are replaced, never edited.


def col_x(i):
    return M + i * (CW + GAP)


class Spider:
    def build(self, app, win):
        win.add_css_class('mwx7-spider')
        self.app, self.win = app, win
        self.prefs = mc.load_json('spider-settings', {'suits': 1})
        if self.prefs['suits'] not in (1, 2, 4):
            self.prefs['suits'] = 1
        self.menus()
        app.set_accels_for_action('app.new', ['F2'])
        app.set_accels_for_action('app.undo', ['<Ctrl>z'])
        app.set_accels_for_action('app.hint', ['<Ctrl>h'])
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
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
        self.hint_timer = 0
        self.new_game()
        return root

    def menus(self):
        """Rebuilt when the difficulty changes so that the current level carries a bullet."""
        levels = [(('• ' if n == self.prefs['suits'] else '    ') + label, f'suits{n}', lambda n=n: self.set_suits(n))
                  for n, label in LEVELS]
        self.app.menubar([
            ('Game', [('New Game', 'new', lambda: self.new_game()), ('Restart Game', 'restart', lambda: self.new_game(True)),
                      None, ('Undo', 'undo', self.undo), ('Hint', 'hint', self.hint), None, ('Exit', 'quit', self.app.quit)]),
            ('Difficulty', levels)])

    def set_suits(self, n):
        self.prefs['suits'] = n
        mc.save_json('spider-settings', self.prefs)
        self.menus()
        self.new_game()

    # --- games ---
    def new_game(self, same=False):
        if not same:
            n = self.prefs['suits']
            suits = {1: [0], 2: [0, 1], 4: [0, 1, 2, 3]}[n]
            deck = [(suits[k % n], r, False) for k in range(8) for r in range(1, 14)]
            random.shuffle(deck)
            self.first = list(deck)
        deck = list(self.first)
        self.cols = [[] for _ in range(10)]
        for col in range(10):
            for _ in range(6 if col < 4 else 5):
                self.cols[col].append(deck.pop())
            s, r, _u = self.cols[col][-1]
            self.cols[col][-1] = (s, r, True)
        self.stock = deck
        self.found = []  # suits of the finished runs
        self.score, self.moves = 500, 0
        self.undo_stack = []
        self.won = False
        self.held = None
        self.hint_cells = None
        self.app.set_title('Spider Solitaire')
        self.area.queue_draw()

    def snapshot(self):
        return ([list(c) for c in self.cols], list(self.stock), list(self.found), self.score, self.moves)

    def undo(self):
        if self.undo_stack and not self.won:
            self.cols, self.stock, self.found, self.score, self.moves = self.undo_stack.pop()
            self.hint_cells = None
            self.area.queue_draw()

    # --- rules ---
    def run_start(self, col):
        """Index where the same-suit descending face-up run at the bottom of a column starts."""
        pile = self.cols[col]
        i = len(pile) - 1
        while i > 0 and pile[i - 1][2] and pile[i - 1][0] == pile[i][0] and pile[i - 1][1] == pile[i][1] + 1:
            i -= 1
        return i

    def can_drop(self, card, col):
        pile = self.cols[col]
        return not pile or pile[-1][1] == card[1] + 1

    def settle(self, col):
        """After a change to a column: flip the new top card and send a finished K..A run to the foundation."""
        pile = self.cols[col]
        if len(pile) >= 13:
            run = pile[-13:]
            if all(c[0] == run[0][0] and c[1] == 13 - k for k, c in enumerate(run)):
                del pile[-13:]
                self.found.append(run[0][0])
                self.score += 100
        if pile and not pile[-1][2]:
            pile[-1] = (pile[-1][0], pile[-1][1], True)
        if len(self.found) == 8:
            self.won = True
            self.app.set_title('Spider Solitaire - You win!')

    def move(self, src, idx, dest):
        self.undo_stack.append(self.snapshot())
        run = self.cols[src][idx:]
        del self.cols[src][idx:]
        self.cols[dest].extend(run)
        self.score -= 1
        self.moves += 1
        self.settle(src)
        self.settle(dest)
        self.hint_cells = None
        self.area.queue_draw()

    def deal_row(self):
        if not self.stock or self.won:
            return
        if any(not c for c in self.cols):
            self.app.set_title('Spider Solitaire - Fill every empty column first')
            GLib.timeout_add(2500, lambda: (self.app.set_title('Spider Solitaire'), False)[1])
            return
        self.undo_stack.append(self.snapshot())
        for col in range(10):
            s, r, _u = self.stock.pop()
            self.cols[col].append((s, r, True))
        self.moves += 1
        self.score -= 1
        for col in range(10):
            self.settle(col)
        self.hint_cells = None
        self.area.queue_draw()

    def best_dest(self, src, idx):
        """Where a run would best go: onto the same suit, else any matching card, else an empty column."""
        card = self.cols[src][idx]
        best, score = None, 0
        for d in range(10):
            pile = self.cols[d]
            if d == src or not self.can_drop(card, d):
                continue
            s = 3 if pile and pile[-1][0] == card[0] else 2 if pile else 1
            if s > score:
                best, score = d, s
        return best, score

    def hint(self):
        """Highlights a useful move (preferring same-suit joins and ones that turn a card up), else the stock."""
        best, top = None, 0
        for src in range(10):
            if not self.cols[src]:
                continue
            lo = self.run_start(src)
            for idx in range(lo, len(self.cols[src])):
                pile = self.cols[src]
                if idx > 0 and pile[idx - 1][2] and pile[idx - 1][0] == pile[idx][0] and pile[idx - 1][1] == pile[idx][1] + 1:
                    continue  # would break a run that is already joined
                d, s = self.best_dest(src, idx)
                if d is None:
                    continue
                if s == 1 and idx == 0:
                    continue  # an empty column to another: pointless
                s += 2 if idx > 0 and not pile[idx - 1][2] else 0
                s += (len(pile) - idx) * 0.01
                if s > top:
                    best, top = (src, idx, d), s
        if best:
            self.hint_cells = ('move', *best)
        elif self.stock:
            self.hint_cells = ('stock',)
        else:
            self.hint_cells = ('none',)
        if self.hint_timer:
            GLib.source_remove(self.hint_timer)
        self.hint_timer = GLib.timeout_add(2500, self.clear_hint)
        self.area.queue_draw()

    def clear_hint(self):
        self.hint_cells, self.hint_timer = None, 0
        self.area.queue_draw()
        return False

    # --- geometry ---
    def ys(self, col):
        """Top y of every card in a column, squeezed when a long column would run off the table."""
        pile = self.cols[col]
        need = sum(UP_STEP if c[2] else DOWN_STEP for c in pile[:-1])
        room = SH - TAB_Y - CH - 30
        f = min(1.0, room / need) if need else 1.0
        out, y = [], TAB_Y
        for c in pile:
            out.append(y)
            y += (UP_STEP if c[2] else DOWN_STEP) * f
        return out

    def hit(self, x, y):
        if M <= y <= M + CH and col_x(0) <= x <= col_x(0) + CW and self.stock:
            return ('stock', 0, 0)
        for col in range(10):
            if col_x(col) <= x <= col_x(col) + CW:
                ys = self.ys(col)
                for idx in range(len(ys) - 1, -1, -1):
                    if ys[idx] <= y <= ys[idx] + CH:
                        return ('col', col, idx)
        return None

    # --- mouse ---
    def drag_begin(self, _g, x, y):
        self.held = None
        if self.won:
            return
        h = self.hit(x, y)
        if not h:
            return
        kind, i, idx = h
        if kind == 'stock':
            return self.deal_row()
        if not self.cols[i][idx][2] or idx < self.run_start(i):
            return
        self.held = (i, idx, x - col_x(i), y - self.ys(i)[idx])
        self.start = self.pos = (x, y)

    def drag_update(self, _g, dx, dy):
        if self.held:
            self.pos = (self.start[0] + dx, self.start[1] + dy)
            self.area.queue_draw()

    def drag_end(self, _g, dx, dy):
        if not self.held:
            return
        src, idx, gx, _gy = self.held
        self.held = None
        if abs(dx) + abs(dy) > 3:
            cx = self.start[0] + dx - gx + CW / 2
            for col in range(10):
                if col != src and col_x(col) - GAP / 2 <= cx <= col_x(col) + CW + GAP / 2 and self.can_drop(self.cols[src][idx], col):
                    return self.move(src, idx, col)
        self.area.queue_draw()

    def on_click(self, _g, n, x, y):
        if self.won:
            return self.new_game()
        if n != 2:
            return
        h = self.hit(x, y)
        if h and h[0] == 'col':
            _k, i, idx = h
            if self.cols[i][idx][2] and idx >= self.run_start(i):
                d, _s = self.best_dest(i, idx)
                if d is not None:
                    self.move(i, idx, d)

    # --- drawing ---
    def draw(self, _a, cr, w, h):
        mc.felt(cr, w, h)
        slot(cr, col_x(0), M, '↻')
        slot(cr, col_x(3), M, '\u2660')
        for col in range(10):
            slot(cr, col_x(col), TAB_Y)
        for k in range(len(self.stock) // 10):  # remaining deal rows, fanned like a stack
            draw_card(cr, (0, 1, False), col_x(0) + k * 5, M)
        for k, suit in enumerate(self.found):
            draw_card(cr, (suit, 13, True), col_x(3) + k * 26, M)
        hold = self.held
        for col in range(10):
            for idx, (c, y) in enumerate(zip(self.cols[col], self.ys(col))):
                if hold and col == hold[0] and idx >= hold[1]:
                    continue
                draw_card(cr, c, col_x(col), y)
        if hold:
            src, idx, gx, gy = hold
            for k, c in enumerate(self.cols[src][idx:]):
                draw_card(cr, c, self.pos[0] - gx, self.pos[1] - gy + k * UP_STEP)
        self.draw_hint(cr)
        cr.set_source_rgba(1, 1, 1, 0.9)
        text(cr, f'Score: {self.score}', 14, h - 12, 13)
        text(cr, f'Moves: {self.moves}', 130, h - 12, 13)
        text(cr, f'Runs: {len(self.found)}/8', 250, h - 12, 13)
        if self.hint_cells == ('none',):
            text(cr, 'No moves left: try Undo', 380, h - 12, 13)
        if self.won:
            mc.banner(cr, w, h, 'You win!', 'Click anywhere for a new game')

    def draw_hint(self, cr):
        if not self.hint_cells:
            return
        boxes = []
        if self.hint_cells[0] == 'stock':
            boxes.append((col_x(0), M, CH))
        elif self.hint_cells[0] == 'move':
            _k, src, idx, dest = self.hint_cells
            boxes.append((col_x(src), self.ys(src)[idx], CH + (len(self.cols[src]) - 1 - idx) * UP_STEP))
            ys = self.ys(dest)
            boxes.append((col_x(dest), ys[-1] if ys else TAB_Y, CH))
        for x, y, hh in boxes:
            mc.card_rrect(cr, x - 2, y - 2, CW + 4, hh + 4, 7)
            cr.set_source_rgba(1, 0.9, 0.3, 0.95)
            cr.set_line_width(3)
            cr.stroke()


if __name__ == '__main__':
    game = Spider()
    mwx7ui.App('org.mwx7.spider', 'Spider Solitaire', 'spider', (SW, SH), CSS, game.build, resizable=False).run_main()
