"""Hearts (native): you against three simple computer players. Pass three cards (left, right, across, none), avoid hearts
and the Queen of Spades, shoot the moon by taking everything; the game ends when someone reaches 100 and the lowest wins."""
import random
import sys

import cairo

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7cards as mc  # noqa: E402
import mwx7ui  # noqa: E402
from mwx7cards import CH, CW, draw_card, text  # noqa: E402
from mwx7ui import GLib, Gtk  # noqa: E402

W, H = 760, 620
CSS = "window.mwx7-hearts > box { background: #0e5a2e; }"
NAMES = ['You', 'West', 'North', 'East']  # seats run clockwise from the bottom
PASS_NAMES = ['left', 'right', 'across', None]
SUIT_ORDER = {3: 0, 2: 1, 0: 2, 1: 3}  # clubs, diamonds, spades, hearts: alternating colours in the hand
HAND_Y = H - CH - 40
CX, CY = W / 2, 292
LIMIT = 100
# A card is (suit, rank, True); suits 0 spade, 1 heart, 2 diamond, 3 club, rank 1..13 with the ace high here (rank 1 -> 14).


def key(c):
    return (SUIT_ORDER[c[0]], 14 if c[1] == 1 else c[1])


def high(c):
    return 14 if c[1] == 1 else c[1]


def points(c):
    return 13 if (c[0] == 0 and c[1] == 12) else 1 if c[0] == 1 else 0


class Hearts:
    def build(self, app, win):
        win.add_css_class('mwx7-hearts')
        self.app, self.win = app, win
        app.menubar([('Game', [('New Game', 'new', lambda: self.new_game()), None, ('Exit', 'quit', app.quit)])])
        app.set_accels_for_action('app.new', ['F2'])
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.area = Gtk.DrawingArea(content_width=W, content_height=H)
        self.area.set_draw_func(self.draw)
        click = Gtk.GestureClick(button=1)
        click.connect('pressed', self.on_click)
        self.area.add_controller(click)
        root.append(self.area)
        self.gen = 0
        self.new_game()
        return root

    # --- flow ---
    def new_game(self):
        self.gen += 1
        self.totals = [0, 0, 0, 0]
        self.round = 0
        self.deal()
        self.app.set_title('Hearts')

    def deal(self):
        self.gen += 1
        deck = [(s, r, True) for s in range(4) for r in range(1, 14)]
        random.shuffle(deck)
        self.hands = [sorted(deck[i * 13:(i + 1) * 13], key=key) for i in range(4)]
        self.taken = [0, 0, 0, 0]
        self.trick, self.last_trick = [], []
        self.broken = False
        self.first = True
        self.sel = []
        self.moon = None
        self.turn = 0
        direction = PASS_NAMES[self.round % 4]
        self.phase = 'pass' if direction else 'play'
        if self.phase == 'play':
            self.start_play()
        self.area.queue_draw()

    def start_play(self):
        self.phase = 'play'
        self.turn = next(p for p in range(4) if (3, 2, True) in self.hands[p])  # the two of clubs leads
        self.schedule()

    def do_pass(self):
        shift = {'left': 1, 'right': 3, 'across': 2}[PASS_NAMES[self.round % 4]]
        out = [list(self.sel)] + [self.ai_pass(p) for p in range(1, 4)]
        for p in range(4):
            for c in out[p]:
                self.hands[p].remove(c)
        for p in range(4):
            self.hands[(p + shift) % 4].extend(out[p])
        for h in self.hands:
            h.sort(key=key)
        self.sel = []
        self.start_play()
        self.area.queue_draw()

    def ai_pass(self, p):
        """The three cards most likely to hurt: the queen of spades, high spades while it is unguarded, high hearts."""
        def danger(c):
            if c[0] == 0 and c[1] == 12:
                return 100
            if c[0] == 0 and c[1] in (1, 13):
                return 60
            return (20 if c[0] == 1 else 0) + high(c)
        return sorted(self.hands[p], key=danger, reverse=True)[:3]

    def schedule(self):
        """Lets the next computer player move after a short pause, so the play can be followed."""
        if self.phase != 'play' or len(self.trick) == 4 or self.turn == 0:
            return
        gen = self.gen
        GLib.timeout_add(550, lambda: self.ai_move(gen) and False)

    def ai_move(self, gen):
        if gen == self.gen and self.phase == 'play' and self.turn != 0 and len(self.trick) < 4:
            self.play(self.turn, self.ai_pick(self.turn))

    def play(self, p, card):
        self.hands[p].remove(card)
        self.trick.append((p, card))
        if card[0] == 1:
            self.broken = True
        if len(self.trick) == 4:
            gen = self.gen
            GLib.timeout_add(1000, lambda: self.finish_trick(gen) and False)
        else:
            self.turn = (p + 1) % 4
            self.schedule()
        self.area.queue_draw()

    def finish_trick(self, gen):
        if gen != self.gen:
            return
        lead = self.trick[0][1][0]
        winner = max((t for t in self.trick if t[1][0] == lead), key=lambda t: high(t[1]))[0]
        self.taken[winner] += sum(points(c) for _p, c in self.trick)
        self.last_trick, self.trick = self.trick, []
        self.first = False
        self.turn = winner
        if not self.hands[0]:
            self.end_round()
        else:
            self.schedule()
        self.area.queue_draw()

    def end_round(self):
        self.phase = 'roundend'
        gain = list(self.taken)
        if 26 in gain:  # shot the moon: the shooter scores nothing and everyone else 26
            self.moon = gain.index(26)
            gain = [0 if p == self.moon else 26 for p in range(4)]
        self.gain = gain
        self.totals = [t + g for t, g in zip(self.totals, gain)]
        if max(self.totals) >= LIMIT:
            self.phase = 'gameover'
            best = min(self.totals)
            self.winners = [p for p in range(4) if self.totals[p] == best]
            self.app.set_title('Hearts - Game over')

    # --- rules ---
    def legal(self, p):
        hand = self.hands[p]
        if not self.trick:
            if self.first:
                return [c for c in hand if c == (3, 2, True)]
            if not self.broken:
                return [c for c in hand if c[0] != 1] or list(hand)
            return list(hand)
        follow = [c for c in hand if c[0] == self.trick[0][1][0]]
        if follow:
            return follow
        if self.first:  # no points on the first trick unless there is no choice
            return [c for c in hand if points(c) == 0] or list(hand)
        return list(hand)

    def ai_pick(self, p):
        legal = self.legal(p)
        if not self.trick:
            # Lead low, and never a high spade while the queen is about.
            return min(legal, key=lambda c: high(c) + (20 if c[0] == 0 and high(c) >= 12 else 0) + (30 if c[0] == 1 else 0))
        lead = self.trick[0][1][0]
        if legal[0][0] != lead:  # void: shed the worst card
            queen = [c for c in legal if c[0] == 0 and c[1] == 12]
            if queen:
                return queen[0]
            hearts = [c for c in legal if c[0] == 1]
            return max(hearts or legal, key=high)
        win = max(high(c) for _p, c in self.trick if c[0] == lead)
        lower = [c for c in legal if high(c) < win]
        if lower:
            return max(lower, key=high)  # duck as high as is safe
        safe = [c for c in legal if not (c[0] == 0 and c[1] == 12)] or legal
        return max(safe, key=high) if len(self.trick) == 3 else min(safe, key=high)

    # --- mouse ---
    def hand_xs(self):
        n = len(self.hands[0])
        step = min(40.0, (W - 80 - CW) / (n - 1)) if n > 1 else 0
        x0 = (W - (CW + step * (n - 1))) / 2
        return [x0 + i * step for i in range(n)], step

    def card_at(self, x, y):
        xs, step = self.hand_xs()
        for i in range(len(xs) - 1, -1, -1):
            c = self.hands[0][i]
            top = HAND_Y - (18 if c in self.sel else 0)
            if top <= y <= top + CH and xs[i] <= x <= xs[i] + (CW if i == len(xs) - 1 else step):
                return c
        return None

    def on_click(self, _g, _n, x, y):
        if self.phase == 'gameover':
            return self.new_game()
        if self.phase == 'roundend':
            self.round += 1
            return self.deal()
        if self.phase == 'pass':
            if len(self.sel) == 3 and CX - 50 <= x <= CX + 50 and CY - 16 <= y <= CY + 16:
                return self.do_pass()
            c = self.card_at(x, y)
            if c in self.sel:
                self.sel.remove(c)
            elif c and len(self.sel) < 3:
                self.sel.append(c)
        elif self.phase == 'play' and self.turn == 0 and len(self.trick) < 4:
            c = self.card_at(x, y)
            if c and c in self.legal(0):
                self.play(0, c)
        self.area.queue_draw()

    # --- drawing ---
    def draw(self, _a, cr, w, h):
        mc.felt(cr, w, h)
        back = (0, 1, False)
        n = len(self.hands[2])
        for k in range(n):
            draw_card(cr, back, (W - (CW + 19 * (n - 1))) / 2 + k * 19, 14)
        for p, x in ((1, 14), (3, W - 14 - CW)):
            n = len(self.hands[p])
            for k in range(n):
                draw_card(cr, back, x, 120 + k * 19)
        xs, _step = self.hand_xs() if self.hands[0] else ([], 0)
        mine = self.legal(0) if self.phase == 'play' and self.turn == 0 and len(self.trick) < 4 else None
        for i, c in enumerate(self.hands[0]):
            y = HAND_Y - (18 if c in self.sel else 0)
            draw_card(cr, c, xs[i], y)
            if mine is not None and c not in mine:  # cards that may not be played now are dimmed
                mc.card_rrect(cr, xs[i], y)
                cr.set_source_rgba(0, 0, 0, 0.35)
                cr.fill()
        spots = {0: (CX - CW / 2, CY + 12), 1: (CX - CW / 2 - 84, CY - 48), 2: (CX - CW / 2, CY - 108), 3: (CX - CW / 2 + 84, CY - 48)}
        for p, c in self.trick:
            draw_card(cr, c, *spots[p])
        cr.set_source_rgba(1, 1, 1, 0.92)
        for p, (lx, ly, mid) in enumerate([(CX, H - 14, True), (14, 110, False), (CX, 142, True), (W - 14, 110, None)]):
            label = f'{NAMES[p]}: {self.totals[p]}' + (f'  (+{self.taken[p]})' if self.taken[p] else '')
            if mid:
                mc.centered(cr, label, lx, ly, 13)
            else:
                cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(13)
                width = cr.text_extents(label).x_advance
                text(cr, label, lx if mid is False else lx - width, ly, 13)
        if self.phase == 'pass':
            d = PASS_NAMES[self.round % 4]
            cr.set_source_rgba(1, 1, 1, 0.95)
            mc.centered(cr, f'Choose 3 cards to pass {d}', CX, CY - 40, 18)
            if len(self.sel) == 3:
                mc.card_rrect(cr, CX - 50, CY - 16, 100, 32, 6)
                cr.set_source_rgb(0.95, 0.97, 1)
                cr.fill()
                cr.set_source_rgb(0.1, 0.25, 0.5)
                mc.centered(cr, 'Pass', CX, CY + 6, 15)
        elif self.phase == 'play' and self.turn == 0 and len(self.trick) < 4:
            cr.set_source_rgba(1, 1, 1, 0.9)
            mc.centered(cr, 'Your turn', CX, CY + 135, 14)
        if self.phase in ('roundend', 'gameover'):
            self.draw_scores(cr)

    def draw_scores(self, cr):
        cr.set_source_rgba(0, 0, 0, 0.6)
        cr.paint()
        cr.set_source_rgb(1, 1, 1)
        if self.phase == 'gameover':
            who = ' and '.join('You' if p == 0 else NAMES[p] for p in self.winners)
            title = 'You win!' if self.winners == [0] else f'{who} win{"s" if len(self.winners) == 1 else ""}'
        else:
            title = 'Round over'
        mc.centered(cr, title, CX, 150, 36)
        if self.moon is not None:
            mc.centered(cr, f'{"You" if self.moon == 0 else NAMES[self.moon]} shot the moon!', CX, 184, 18)
        for p in range(4):
            y = 236 + p * 34
            text(cr, NAMES[p], CX - 150, y, 17)
            text(cr, f'+{self.gain[p]}', CX + 20, y, 17)
            text(cr, f'{self.totals[p]}', CX + 110, y, 17)
        text(cr, 'Round', CX + 10, 210, 13, False)
        text(cr, 'Total', CX + 100, 210, 13, False)
        mc.centered(cr, 'Click anywhere to ' + ('start a new game' if self.phase == 'gameover' else 'continue'), CX, 410, 15)


if __name__ == '__main__':
    game = Hearts()
    mwx7ui.App('org.mwx7.hearts', 'Hearts', 'hearts', (W, H), CSS, game.build, resizable=False).run_main()
