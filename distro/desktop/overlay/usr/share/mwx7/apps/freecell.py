"""FreeCell (native): the classic eight-column game with numbered deals (Microsoft's shuffle, so game numbers match),
four free cells, the supermove limit, auto-move of safe cards to the foundations, undo and statistics."""
import random
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7cards as mc  # noqa: E402
import mwx7ui  # noqa: E402
from mwx7cards import CH, CW, draw_card, is_red, text  # noqa: E402
from mwx7ui import GLib, Gtk  # noqa: E402

GAP, M, TAB_Y = 14, 14, 132
SW, SH = 8 * CW + 9 * GAP, 640
CSS = "window.mwx7-freecell > box { background: #0e5a2e; }"
STATS = {'won': 0, 'lost': 0, 'streak': 0, 'best_win': 0, 'best_lose': 0}
SUIT_OF_MS = [3, 2, 1, 0]  # Microsoft numbers suits club, diamond, heart, spade; ours are spade, heart, diamond, club


def col_x(i):
    return M + i * (CW + GAP)


def deal(number):
    """Microsoft's FreeCell shuffle: the same game number gives the same deal as the original."""
    seed = number
    cards = list(range(52))
    cols = [[] for _ in range(8)]
    for i in range(52):
        seed = (seed * 214013 + 2531011) & 0xFFFFFFFF
        j = ((seed >> 16) & 0x7FFF) % (52 - i)
        c = cards[j]
        cards[j] = cards[51 - i]
        cols[i % 8].append((SUIT_OF_MS[c % 4], c // 4 + 1, True))
    return cols


class FreeCell:
    def build(self, app, win):
        win.add_css_class('mwx7-freecell')
        self.app, self.win = app, win
        self.stats = mc.load_json('freecell-stats', STATS)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('Game', [('New Game', 'new', lambda: self.new_game()), ('Select Game...', 'select', self.select),
                      ('Restart Game', 'restart', lambda: self.new_game(self.number)), None,
                      ('Undo', 'undo', self.undo), None, ('Statistics...', 'stats', self.show_stats), None,
                      ('Exit', 'quit', app.quit)])]))
        app.set_accels_for_action('app.new', ['F2'])
        app.set_accels_for_action('app.undo', ['<Ctrl>z'])
        win.connect('close-request', lambda *_a: self.record_loss())
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
        self.number = 0
        self.moves = 0
        self.counted = True
        self.new_game()
        return root

    # --- games and statistics ---
    def new_game(self, number=None):
        self.record_loss()
        self.number = number or random.randint(1, 1000000)
        self.cols = deal(self.number)
        self.free = [None] * 4
        self.found = [[] for _ in range(4)]
        self.moves = 0
        self.undo_stack = []
        self.over = None  # None, 'won' or 'stuck'
        self.counted = False
        self.held = None
        self.auto_on = False
        self.app.set_title(f'FreeCell - Game #{self.number}')
        self.area.queue_draw()

    def select(self):
        mc.ask_number(self.win, 'freecell', 'Select Game', 'Game number (1 - 1000000):', self.number,
                      lambda n: self.new_game(max(1, min(1000000, n))))

    def record_loss(self):
        """Leaving a started game unsolved counts as a loss, as in the original. Returns False (close-request: let it close)."""
        if self.moves and not self.counted:
            self.finish(False)
        return False

    def finish(self, won):
        self.counted = True
        s = self.stats
        if won:
            s['won'] += 1
            s['streak'] = max(0, s['streak']) + 1
            s['best_win'] = max(s['best_win'], s['streak'])
        else:
            s['lost'] += 1
            s['streak'] = min(0, s['streak']) - 1
            s['best_lose'] = max(s['best_lose'], -s['streak'])
        mc.save_json('freecell-stats', s)

    def show_stats(self):
        s = self.stats
        total = s['won'] + s['lost']
        pct = round(100 * s['won'] / total) if total else 0
        cur = f"{abs(s['streak'])} {'wins' if s['streak'] > 0 else 'losses'}" if s['streak'] else '0'

        def reset():
            self.stats.update(STATS)
            mc.save_json('freecell-stats', self.stats)
        mc.message(self.win, 'freecell', 'FreeCell Statistics',
                   [f'Games played: {total}', f"Won: {s['won']} ({pct}%)", f"Lost: {s['lost']}", f'Current streak: {cur}',
                    f"Longest winning streak: {s['best_win']}", f"Longest losing streak: {s['best_lose']}"],
                   [('Reset', reset)])

    # --- rules ---
    def snapshot(self):
        return (list(self.free), [list(f) for f in self.found], [list(c) for c in self.cols], self.moves)

    def undo(self):
        if self.undo_stack and self.over != 'won':
            self.auto_on = False
            self.free, self.found, self.cols, self.moves = self.undo_stack.pop()
            self.over = None
            self.area.queue_draw()

    def can_found(self, card):
        return len(self.found[card[0]]) + 1 == card[1]

    def can_stack(self, card, col):
        pile = self.cols[col]
        return not pile or (is_red(pile[-1][0]) != is_red(card[0]) and pile[-1][1] == card[1] + 1)

    def max_move(self, dest_empty):
        """Supermove limit: (free cells + 1) * 2^(empty columns), the destination not counting if it is empty."""
        free = sum(1 for c in self.free if c is None)
        empty = sum(1 for c in self.cols if not c) - (1 if dest_empty else 0)
        return (free + 1) * (2 ** max(0, empty))

    def run_from(self, col):
        """Index where the properly alternating, descending run at the bottom of a column starts."""
        pile = self.cols[col]
        i = len(pile) - 1
        while i > 0 and is_red(pile[i - 1][0]) != is_red(pile[i][0]) and pile[i - 1][1] == pile[i][1] + 1:
            i -= 1
        return i

    def commit(self):
        """A player move was made: afterwards the safe cards fly home one by one, then the game may be over."""
        self.moves += 1
        self.auto_on = True
        GLib.timeout_add(110, self.auto_step)
        self.check_end()
        self.area.queue_draw()

    def safe(self, card):
        """Safe to send home: no card still on the tableau could need it as a base (the usual auto-play rule)."""
        if card[1] <= 2:
            return True
        opp = (1, 2) if card[0] in (0, 3) else (0, 3)
        return all(len(self.found[o]) >= card[1] - 1 for o in opp)

    def auto_step(self):
        if not self.auto_on or self.over:
            return False
        sources = [('free', i, c) for i, c in enumerate(self.free) if c] + \
                  [('col', i, p[-1]) for i, p in enumerate(self.cols) if p]
        for kind, i, c in sources:
            if self.can_found(c) and self.safe(c):
                if kind == 'free':
                    self.free[i] = None
                else:
                    self.cols[i].pop()
                self.found[c[0]].append(c)
                self.check_end()
                self.area.queue_draw()
                return True
        self.auto_on = False
        return False

    def check_end(self):
        if all(len(f) == 13 for f in self.found):
            self.over = 'won'
            if not self.counted:
                self.finish(True)
            return
        if None in self.free or any(not c for c in self.cols):
            return
        tops = list(self.free) + [p[-1] for p in self.cols]
        for c in tops:
            if self.can_found(c) or any(self.can_stack(c, j) for j in range(8)):
                return
        self.over = 'stuck'
        if not self.counted:
            self.finish(False)

    def move_to(self, cards, src, si, dest, di):
        """Applies a validated move of `cards` (the tail of a column, or one card) and records undo."""
        self.undo_stack.append(self.snapshot())
        if src == 'free':
            self.free[si] = None
        else:
            del self.cols[si][len(self.cols[si]) - len(cards):]
        if dest == 'free':
            self.free[di] = cards[0]
        elif dest == 'found':
            self.found[cards[0][0]].append(cards[0])
        else:
            self.cols[di].extend(cards)
        self.commit()

    # --- hit testing ---
    def step(self, col):
        n = len(self.cols[col])
        return 26 if n < 2 else min(26.0, (SH - TAB_Y - CH - 30) / (n - 1))

    def card_y(self, col, idx):
        return TAB_Y + idx * self.step(col)

    def hit(self, x, y):
        if M <= y <= M + CH:
            for i in range(4):
                if col_x(i) <= x <= col_x(i) + CW and self.free[i]:
                    return ('free', i, 0)
        for col in range(8):
            if col_x(col) <= x <= col_x(col) + CW:
                for idx in range(len(self.cols[col]) - 1, -1, -1):
                    top = self.card_y(col, idx)
                    if top <= y <= top + (CH if idx == len(self.cols[col]) - 1 else self.step(col)):
                        return ('col', col, idx)
        return None

    # --- mouse ---
    def drag_begin(self, _g, x, y):
        self.held = None
        if self.over:
            return
        h = self.hit(x, y)
        if not h:
            return
        kind, i, idx = h
        if kind == 'free':
            cards, ox, oy = [self.free[i]], col_x(i), M
        else:
            if idx < self.run_from(i):
                return
            cards, ox, oy = self.cols[i][idx:], col_x(i), self.card_y(i, idx)
        self.held = (cards, kind, i, x - ox, y - oy)
        self.start = self.pos = (x, y)

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
            if cy < M + CH + 10:
                for i in range(8):
                    if col_x(i) - GAP / 2 <= cx <= col_x(i) + CW + GAP / 2 and len(cards) == 1:
                        if i < 4 and self.free[i] is None and not (kind == 'free' and si == i):
                            return self.move_to(cards, kind, si, 'free', i)
                        if i >= 4 and self.can_found(cards[0]):
                            return self.move_to(cards, kind, si, 'found', 0)
            else:
                for col in range(8):
                    if col_x(col) - GAP / 2 <= cx <= col_x(col) + CW + GAP / 2 and not (kind == 'col' and si == col):
                        if self.can_stack(cards[0], col) and len(cards) <= self.max_move(not self.cols[col]):
                            return self.move_to(cards, kind, si, 'col', col)
        self.area.queue_draw()

    def on_click(self, _g, n, x, y):
        if self.over == 'won':
            return self.new_game()
        if n != 2 or self.over:
            return
        h = self.hit(x, y)
        if not h:
            return
        kind, i, idx = h
        if kind == 'col' and idx != len(self.cols[i]) - 1:
            return
        card = self.free[i] if kind == 'free' else self.cols[i][-1]
        if self.can_found(card):
            return self.move_to([card], kind, i, 'found', 0)
        if kind == 'col' and None in self.free:
            return self.move_to([card], 'col', i, 'free', self.free.index(None))

    # --- drawing ---
    def draw(self, _a, cr, w, h):
        mc.felt(cr, w, h)
        for i in range(4):
            mc.slot(cr, col_x(i), M)
            mc.slot(cr, col_x(4 + i), M, mc.SUIT_CHARS[i])
        for col in range(8):
            mc.slot(cr, col_x(col), TAB_Y)
        held = {id(c) for c in self.held[0]} if self.held else set()
        for i, c in enumerate(self.free):
            if c and id(c) not in held:
                draw_card(cr, c, col_x(i), M)
        for f in range(4):
            if self.found[f]:
                draw_card(cr, self.found[f][-1], col_x(4 + f), M)
        for col in range(8):
            for idx, c in enumerate(self.cols[col]):
                if id(c) not in held:
                    draw_card(cr, c, col_x(col), self.card_y(col, idx))
        if self.held:
            cards, _k, _i, gx, gy = self.held
            for k, c in enumerate(cards):
                draw_card(cr, c, self.pos[0] - gx, self.pos[1] - gy + k * 26)
        cr.set_source_rgba(1, 1, 1, 0.9)
        text(cr, f'Game #{self.number}', 14, h - 12, 13)
        text(cr, f'Moves: {self.moves}', 160, h - 12, 13)
        if self.over == 'won':
            mc.banner(cr, w, h, 'You win!', 'Click anywhere for a new game')
        elif self.over == 'stuck':
            mc.banner(cr, w, h, 'No more moves', 'Undo (Ctrl+Z) or press F2 for a new game')


if __name__ == '__main__':
    game = FreeCell()
    mwx7ui.App('org.mwx7.freecell', 'FreeCell', 'freecell', (SW, SH), CSS, game.build, resizable=False).run_main()
