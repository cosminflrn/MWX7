"""Card drawing shared by MWX 7's card games (Solitaire, FreeCell, Spider, Hearts): original suit glyphs and cards in
cairo, plus the felt, empty-slot and banner helpers. Cards are [suit, rank, face_up]; suits 0 spade, 1 heart, 2 diamond,
3 club; rank 1 (ace) to 13 (king)."""
import math

import cairo

CW, CH = 70, 98
RED = (0.78, 0.1, 0.12)
BLACK = (0.1, 0.12, 0.16)
RANKS = ['', 'A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
SUIT_CHARS = ['\u2660', '\u2665', '\u2666', '\u2663']


def is_red(suit):
    return suit in (1, 2)


def suit_path(cr, suit, cx, cy, s):
    """Original suit glyphs built from arcs and curves, s = half-size."""
    if suit == 1:  # heart
        cr.move_to(cx, cy + s)
        cr.curve_to(cx - s * 1.6, cy - s * 0.1, cx - s * 0.9, cy - s * 1.2, cx, cy - s * 0.4)
        cr.curve_to(cx + s * 0.9, cy - s * 1.2, cx + s * 1.6, cy - s * 0.1, cx, cy + s)
    elif suit == 2:  # diamond
        cr.move_to(cx, cy - s * 1.1)
        cr.line_to(cx + s * 0.8, cy)
        cr.line_to(cx, cy + s * 1.1)
        cr.line_to(cx - s * 0.8, cy)
    else:
        if suit == 0:  # spade: a heart upside down plus a stem
            cr.move_to(cx, cy - s)
            cr.curve_to(cx - s * 1.6, cy + s * 0.1, cx - s * 0.9, cy + s * 1.2, cx, cy + s * 0.4)
            cr.curve_to(cx + s * 0.9, cy + s * 1.2, cx + s * 1.6, cy + s * 0.1, cx, cy - s)
        else:  # club: three discs
            for dx, dy in ((0, -0.5), (-0.55, 0.3), (0.55, 0.3)):
                cr.new_sub_path()
                cr.arc(cx + dx * s, cy + dy * s, s * 0.52, 0, 2 * math.pi)
        cr.close_path()
        cr.move_to(cx, cy + s * 0.2)
        cr.line_to(cx + s * 0.35, cy + s)
        cr.line_to(cx - s * 0.35, cy + s)
    cr.close_path()
    cr.fill()


def card_rrect(cr, x, y, w=CW, h=CH, r=6):
    cr.new_sub_path()
    for cx, cy, a in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        cr.arc(cx, cy, r, math.radians(a), math.radians(a + 90))
    cr.close_path()


def text(cr, s, x, y, size, bold=True):
    cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    cr.move_to(x, y)
    cr.show_text(s)


def draw_card(cr, card, x, y):
    suit, rank, up = card
    card_rrect(cr, x + 1.5, y + 2, CW, CH)  # soft shadow
    cr.set_source_rgba(0, 0, 0, 0.25)
    cr.fill()
    card_rrect(cr, x, y)
    if not up:
        cr.set_source_rgb(0.95, 0.97, 1)
        cr.fill()
        card_rrect(cr, x + 4, y + 4, CW - 8, CH - 8, 3)
        g = cairo.LinearGradient(x, y, x + CW, y + CH)
        g.add_color_stop_rgb(0, 0.35, 0.62, 0.95)
        g.add_color_stop_rgb(1, 0.1, 0.3, 0.7)
        cr.set_source(g)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.4)
        cr.set_line_width(1)
        cr.stroke()
        cr.save()
        card_rrect(cr, x + 4, y + 4, CW - 8, CH - 8, 3)
        cr.clip()
        cr.set_source_rgba(1, 1, 1, 0.18)  # diamond lattice
        for k in range(-CH, CW + CH, 12):
            cr.move_to(x + k, y)
            cr.line_to(x + k + CH, y + CH)
            cr.move_to(x + k + CH, y)
            cr.line_to(x + k, y + CH)
        cr.stroke()
        cr.restore()
        card_rrect(cr, x, y)
        cr.set_source_rgb(0.55, 0.6, 0.68)
        cr.set_line_width(1)
        cr.stroke()
        return
    cr.set_source_rgb(1, 1, 1)
    cr.fill_preserve()
    cr.set_source_rgb(0.62, 0.66, 0.72)
    cr.set_line_width(1)
    cr.stroke()
    col = RED if is_red(suit) else BLACK
    cr.set_source_rgb(*col)
    for bx, by, flip in ((x + 4, y + 4, False), (x + CW - 4, y + CH - 4, True)):
        cr.save()
        cr.translate(bx, by)
        if flip:
            cr.rotate(math.pi)
        text(cr, RANKS[rank], 0, 13, 14)
        suit_path(cr, suit, 6, 22, 5)
        cr.restore()
    if rank > 10:  # court cards: a big suit mark and letter
        suit_path(cr, suit, x + CW / 2, y + CH / 2 - 10, 14)
        cr.set_font_size(26)
        e = cr.text_extents(RANKS[rank])
        text(cr, RANKS[rank], x + CW / 2 - e.width / 2 - e.x_bearing, y + CH / 2 + 28, 26)
    elif rank == 1:
        suit_path(cr, suit, x + CW / 2, y + CH / 2, 20)
    else:
        pips = {2: [(1, 0), (1, 6)], 3: [(1, 0), (1, 3), (1, 6)], 4: [(0, 0), (2, 0), (0, 6), (2, 6)],
                5: [(0, 0), (2, 0), (1, 3), (0, 6), (2, 6)], 6: [(0, 0), (2, 0), (0, 3), (2, 3), (0, 6), (2, 6)],
                7: [(0, 0), (2, 0), (1, 1.5), (0, 3), (2, 3), (0, 6), (2, 6)],
                8: [(0, 0), (2, 0), (1, 1.5), (0, 3), (2, 3), (1, 4.5), (0, 6), (2, 6)],
                9: [(0, 0), (2, 0), (0, 2), (2, 2), (1, 3), (0, 4), (2, 4), (0, 6), (2, 6)],
                10: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2), (0, 4), (2, 4), (1, 5), (0, 6), (2, 6)]}[rank]
        for px, py in pips:
            suit_path(cr, suit, x + 20 + px * 15, y + 20 + py * 9.7, 6)


def felt(cr, w, h):
    g = cairo.RadialGradient(w / 2, h / 2, 40, w / 2, h / 2, max(w, h) * 0.75)
    g.add_color_stop_rgb(0, 0.12, 0.45, 0.24)
    g.add_color_stop_rgb(1, 0.04, 0.27, 0.13)
    cr.set_source(g)
    cr.paint()


def slot(cr, x, y, label=None):
    """An empty pile outline, optionally with a faint hint glyph."""
    card_rrect(cr, x, y)
    cr.set_source_rgba(0, 0, 0, 0.22)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 0.3)
    cr.set_line_width(1.5)
    cr.stroke()
    if label:
        cr.set_source_rgba(1, 1, 1, 0.35)
        cr.set_font_size(24)
        e = cr.text_extents(label)
        text(cr, label, x + CW / 2 - e.width / 2 - e.x_bearing, y + CH / 2 + 8, 24)


def centered(cr, s, cx, y, size):
    cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(size)
    e = cr.text_extents(s)
    cr.move_to(cx - e.width / 2 - e.x_bearing, y)
    cr.show_text(s)


def banner(cr, w, h, title, sub):
    """Dims the table and shows a headline, for won / game over."""
    cr.set_source_rgba(0, 0, 0, 0.5)
    cr.paint()
    cr.set_source_rgb(1, 1, 1)
    centered(cr, title, w / 2, h / 2, 40)
    centered(cr, sub, w / 2, h / 2 + 34, 15)


# --- persistence and small dialogs shared by the games (they import mwx7ui first, so Gtk is available) ---
def _store(name):
    import os

    from gi.repository import GLib
    d = os.path.join(GLib.get_user_config_dir(), 'mwx7')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name + '.json')


def load_json(name, default):
    import json
    try:
        with open(_store(name)) as f:
            data = json.load(f)
        return {**default, **data} if isinstance(data, dict) else dict(default)
    except (OSError, ValueError):
        return dict(default)


def save_json(name, data):
    import json
    try:
        with open(_store(name), 'w') as f:
            json.dump(data, f)
    except OSError:
        pass  # statistics are a nicety: a read-only home must not break the game


def message(win, game_id, title, lines, buttons=()):
    """A small Aero dialog: lines of text and buttons [(label, callback)] plus Close."""
    import mwx7ui
    from mwx7ui import Gtk
    w = mwx7ui.dialog(win, title, game_id)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=14, margin_bottom=14, margin_start=18, margin_end=18)
    for ln in lines:
        box.append(Gtk.Label(label=ln, xalign=0))
    row = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=8)
    for label, fn in list(buttons) + [('Close', None)]:
        b = Gtk.Button(label=label)
        b.connect('clicked', lambda _b, f=fn: (f and f(), w.destroy()))
        row.append(b)
    box.append(row)
    w.set_child(box)
    w.present()
    return w


def ask_number(win, game_id, title, prompt, initial, on_ok):
    import mwx7ui
    from mwx7ui import Gtk
    w = mwx7ui.dialog(win, title, game_id)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=14, margin_bottom=14, margin_start=18, margin_end=18)
    box.append(Gtk.Label(label=prompt, xalign=0))
    entry = Gtk.Entry(text=str(initial))
    box.append(entry)
    row = Gtk.Box(spacing=8, halign=Gtk.Align.END)

    def ok(*_a):
        try:
            n = int(entry.get_text().strip())
        except ValueError:
            return
        w.destroy()
        on_ok(n)
    entry.connect('activate', ok)
    for label, fn in (('OK', ok), ('Cancel', lambda *_a: w.destroy())):
        b = Gtk.Button(label=label)
        b.connect('clicked', fn)
        row.append(b)
    box.append(row)
    w.set_child(box)
    w.present()
    return w
