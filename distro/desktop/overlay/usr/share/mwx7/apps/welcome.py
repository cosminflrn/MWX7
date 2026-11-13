"""Welcome Center (native): the first-run tour, shown at an account's first sign-in and kept in the Start menu.

Eight pages, each with a large illustration drawn here with cairo (original art, no borrowed icons) and buttons that open
the real thing (a Settings page, Get Apps). The keyboard page reads the real bindings from Wayfire's config, so it can
never drift from what the session does. "Show at startup" is stored in ~/.config/mwx7/welcome.json; bin/mwx7-welcome
(autostarted from wayfire.ini) shows this at the first sign-in always, and at later ones only when that box is ticked."""
import configparser
import json
import math
import os
import subprocess
import sys

import cairo

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import GLib, Gtk  # noqa: E402
import gi  # noqa: E402

gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gdk, Pango, PangoCairo  # noqa: E402

SETTINGS = '/usr/share/mwx7/settings/mwx7-settings'
APP = '/usr/share/mwx7/bin/mwx7-app'
CONF = os.path.join(GLib.get_user_config_dir(), 'mwx7', 'welcome.json')
WF_INIS = ['/etc/mwx7/wayfire.ini', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'etc',
                                                 'mwx7', 'wayfire.ini')]
AW, AH = 480.0, 420.0  # the illustrations' own coordinate space; they are scaled to fill the art panel


# ---------------------------------------------------------------- settings file
def load_conf():
    try:
        with open(CONF) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_conf(**kw):
    data = load_conf()
    data.update(kw)
    try:
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF, 'w') as f:
            json.dump(data, f)
    except OSError:
        pass


# ---------------------------------------------------------------- real shortcuts
KEYNAMES = {'LEFT': '←', 'RIGHT': '→', 'UP': '↑', 'DOWN': '↓', 'TAB': 'Tab', 'SPACE': 'Space', 'ENTER': 'Enter',
            'ESC': 'Esc', 'PRINT': 'Print Screen'}
LABELS = {
    ('core', 'close_top_view'): 'Close the window',
    ('fast-switcher', 'activate'): 'Switch to the next window',
    ('fast-switcher', 'activate_backward'): 'Switch to the previous window',
    ('scale', 'toggle'): 'Overview: every window at once',
    ('grid', 'slot_l'): 'Snap window to the left half',
    ('grid', 'slot_r'): 'Snap window to the right half',
    ('grid', 'slot_c'): 'Fill the screen',
    ('command', 'binding_terminal'): 'Open a terminal',
    ('command', 'binding_lock'): 'Lock the screen',
    ('command', 'binding_clipboard'): 'Clipboard history',
    ('command', 'binding_search'): 'Search',
}


def pretty(binding):
    """'<super> <shift> KEY_V' -> 'Super + Shift + V'."""
    out = []
    for tok in binding.replace('\\#', '#').split():
        if tok.startswith('<') and tok.endswith('>'):
            out.append(tok[1:-1].capitalize() if tok != '<ctrl>' else 'Ctrl')
        elif tok.startswith('KEY_'):
            k = tok[4:]
            out.append(KEYNAMES.get(k, k.capitalize() if len(k) > 2 else k))
    return ' + '.join(out)


def real_shortcuts():
    """[(keys, what)] from wayfire.ini: the file the session itself runs on."""
    cp = configparser.ConfigParser(interpolation=None, strict=False, comment_prefixes=('#',), inline_comment_prefixes=None)
    for path in WF_INIS:
        try:
            if cp.read(path):
                break
        except configparser.Error:
            continue
    rows = []
    for (sec, key), label in LABELS.items():
        val = cp.get(sec, key, fallback='').strip()
        if val and val.lower() != 'disabled':
            rows.append((pretty(val), label))
    # Any other binding added later to [command] still shows, named after its key.
    for key, val in cp.items('command') if cp.has_section('command') else []:
        if key.startswith('binding_') and ('command', key) not in LABELS and val.strip():
            rows.append((pretty(val), key[8:].replace('_', ' ').capitalize()))
    if 'grp:win_space_toggle' in cp.get('input', 'xkb_options', fallback=''):
        rows.append(('Super + Space', 'Switch keyboard language'))
    return rows


# ---------------------------------------------------------------- drawing helpers
def rr(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


def rgba(cr, hexcol, a=1.0):
    h = hexcol.lstrip('#')
    cr.set_source_rgba(int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


def vgrad(x0, y0, y1, stops):
    g = cairo.LinearGradient(x0, y0, x0, y1)
    for off, col, a in stops:
        h = col.lstrip('#')
        g.add_color_stop_rgba(off, int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)
    return g


def text(cr, s, x, y, size=12, col='#ffffff', bold=False, align='l', a=1.0, shadow=False):
    """y is the text's vertical centre."""
    lay = PangoCairo.create_layout(cr)
    lay.set_font_description(Pango.FontDescription(('Selawik, Sans ' + ('Bold ' if bold else '') + str(size))))
    lay.set_text(s, -1)
    w, h = lay.get_pixel_size()
    ox = x - (w if align == 'r' else w / 2 if align == 'c' else 0)
    if shadow:
        cr.move_to(ox, y - h / 2 + 1)
        cr.set_source_rgba(0, 0, 0, .35)
        PangoCairo.show_layout(cr, lay)
    cr.move_to(ox, y - h / 2)
    rgba(cr, col, a)
    PangoCairo.show_layout(cr, lay)
    cr.new_path()
    return w


def text_w(cr, s, size, bold=False):
    lay = PangoCairo.create_layout(cr)
    lay.set_font_description(Pango.FontDescription(('Selawik, Sans ' + ('Bold ' if bold else '') + str(size))))
    lay.set_text(s, -1)
    return lay.get_pixel_size()[0]


def wallpaper(cr, w, h, theme='day'):
    """Meadow and hills under a bright sky: the art panel's backdrop (drawn full-bleed, not in the 480x420 space)."""
    sky = {'day': ('#2f7fd6', '#7db9ec', '#d6ecff'), 'dusk': ('#3a4aa8', '#b06aa8', '#ffc59a'),
           'mint': ('#1f9a9a', '#6fcfc0', '#e0fff0')}[theme]
    cr.set_source(vgrad(0, 0, h, [(0, sky[0], 1), (.55, sky[1], 1), (1, sky[2], 1)]))
    cr.paint()
    g = cairo.RadialGradient(w * .72, h * .3, 4, w * .72, h * .3, h * .55)
    g.add_color_stop_rgba(0, 1, 1, .9, .95)
    g.add_color_stop_rgba(.25, 1, 1, .8, .35)
    g.add_color_stop_rgba(1, 1, 1, .9, 0)
    cr.set_source(g)
    cr.paint()
    # soft clouds
    for cx, cy, s in ((.2, .2, 1.0), (.55, .12, .7), (.85, .42, .8)):
        for dx, dy, r in ((-26, 4, 16), (-8, -6, 22), (16, -2, 19), (36, 5, 13)):
            cr.arc(cx * w + dx * s, cy * h + dy * s, r * s, 0, 2 * math.pi)
        cr.set_source_rgba(1, 1, 1, .5)
        cr.fill()
    for base, amp, col, ph in ((.66, .05, ('#2f7d4a', '#1f5a3a'), 0), (.76, .06, ('#3f9d54', '#256b3c'), 2.2),
                               (.88, .05, ('#58b75a', '#2f8a46'), 4.1)):
        cr.move_to(0, h)
        for i in range(0, int(w) + 8, 8):
            cr.line_to(i, h * base + math.sin(i / w * 5 + ph) * h * amp)
        cr.line_to(w, h)
        cr.close_path()
        cr.set_source(vgrad(0, h * base - 20, h, [(0, col[0], 1), (1, col[1], 1)]))
        cr.fill()


def glass(cr, x, y, w, h, r=10, alpha=.38, dark=False):
    rr(cr, x, y, w, h, r)
    if dark:
        cr.set_source(vgrad(0, y, y + h, [(0, '#33475f', .78), (1, '#0f1b2c', .86)]))
    else:
        cr.set_source(vgrad(0, y, y + h, [(0, '#ffffff', alpha + .2), (1, '#cfe6ff', alpha)]))
    cr.fill_preserve()
    cr.set_line_width(1)
    cr.set_source_rgba(1, 1, 1, .7 if not dark else .25)
    cr.stroke()


def shadow(cr, x, y, w, h, r=12, n=7, a=.28):
    for i in range(n, 0, -1):
        rr(cr, x - i * 1.5, y - i * 1.5 + 6, w + i * 3, h + i * 3, r + i)
        cr.set_source_rgba(0, 0, 0, a / n * .55)
        cr.fill()


def orb(cr, cx, cy, r):
    g = cairo.RadialGradient(cx - r * .3, cy - r * .4, r * .1, cx, cy, r)
    g.add_color_stop_rgba(0, .55, .85, 1, 1)
    g.add_color_stop_rgba(.55, .1, .45, .85, 1)
    g.add_color_stop_rgba(1, .03, .2, .55, 1)
    cr.arc(cx, cy, r, 0, 2 * math.pi)
    cr.set_source(g)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, .75)
    cr.set_line_width(max(1, r / 14))
    cr.stroke()
    # the four-pane flag of the Start orb, drawn as four soft leaves of our own
    for i, col in enumerate(('#ff7b5c', '#7ad24f', '#5aa9ff', '#ffd23f')):
        ox, oy = (-1 if i % 2 == 0 else 1), (-1 if i < 2 else 1)
        cr.save()
        cr.translate(cx + ox * r * .24, cy + oy * r * .24)
        cr.rotate(ox * oy * .35)
        rr(cr, -r * .21, -r * .21, r * .42, r * .42, r * .12)
        rgba(cr, col, .95)
        cr.fill()
        cr.restore()
    cr.arc(cx, cy - r * .35, r * .72, math.pi * 1.1, math.pi * 1.9)
    cr.set_source_rgba(1, 1, 1, .22)
    cr.set_line_width(r * .5)
    cr.stroke()


def lights(cr, x, y, r=7):
    """Green, yellow, red: minimize, full screen, close (left to right)."""
    for i, (a, b) in enumerate((('#8be37a', '#1f9d3a'), ('#ffe27a', '#d99a10'), ('#ff9a8a', '#c4281c'))):
        cx = x + i * (r * 2 + 5)
        g = cairo.RadialGradient(cx - r * .3, cy := y - r * .3, 1, cx, y, r)
        h1, h2 = a.lstrip('#'), b.lstrip('#')
        g.add_color_stop_rgb(0, *[int(h1[j:j + 2], 16) / 255 for j in (0, 2, 4)])
        g.add_color_stop_rgb(1, *[int(h2[j:j + 2], 16) / 255 for j in (0, 2, 4)])
        cr.arc(cx, y, r, 0, 2 * math.pi)
        cr.set_source(g)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, .35)
        cr.set_line_width(.8)
        cr.stroke()
        cr.arc(cx, y - r * .35, r * .55, math.pi, 2 * math.pi)
        cr.set_source_rgba(1, 1, 1, .45)
        cr.fill()
    return [x + i * (r * 2 + 5) for i in range(3)]


def window(cr, x, y, w, h, title, body=True):
    shadow(cr, x, y, w, h, 10)
    glass(cr, x, y, w, h, 10, .45)
    text(cr, title, x + 14, y + 14, 10, '#12304f', True)
    xs = lights(cr, x + w - 56, y + 14, 6)
    if body:
        rr(cr, x + 6, y + 28, w - 12, h - 34, 4)
        cr.set_source_rgb(1, 1, 1)
        cr.fill()
    return xs


def tile(cr, x, y, s, kind, col='#3b82e0'):
    """An app icon drawn from shapes: a rounded glass tile with a simple glyph in white."""
    c2 = {'#3b82e0': '#1b4ea6', '#e0653b': '#a63a1b', '#3bb26a': '#1b7a41', '#e0b03b': '#a67a1b',
          '#8a5be0': '#5230a6', '#3bb8c8': '#1b7f8f', '#d9548a': '#a62a5c'}.get(col, '#1b4ea6')
    rr(cr, x, y, s, s, s * .22)
    cr.set_source(vgrad(0, y, y + s, [(0, col, 1), (1, c2, 1)]))
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, .8)
    cr.set_line_width(max(1, s / 40))
    cr.stroke()
    rr(cr, x + s * .06, y + s * .05, s * .88, s * .42, s * .18)
    cr.set_source_rgba(1, 1, 1, .25)
    cr.fill()
    cr.save()
    cr.translate(x + s / 2, y + s / 2)
    cr.scale(s / 100, s / 100)
    cr.set_source_rgb(1, 1, 1)
    cr.set_line_width(7)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if kind == 'folder':
        cr.move_to(-26, -14); cr.line_to(-8, -14); cr.line_to(-2, -22); cr.line_to(26, -22); cr.line_to(26, 24)
        cr.line_to(-26, 24); cr.close_path(); cr.fill()
    elif kind == 'globe':
        cr.arc(0, 0, 26, 0, 2 * math.pi); cr.stroke()
        cr.save(); cr.scale(.45, 1); cr.arc(0, 0, 26, 0, 2 * math.pi); cr.restore(); cr.stroke()
        cr.move_to(-26, 0); cr.line_to(26, 0); cr.stroke()
    elif kind == 'music':
        cr.arc(-10, 18, 9, 0, 2 * math.pi); cr.fill()
        cr.arc(16, 12, 9, 0, 2 * math.pi); cr.fill()
        cr.move_to(-2, 18); cr.line_to(-2, -22); cr.line_to(24, -28); cr.line_to(24, 12); cr.stroke()
    elif kind == 'photo':
        cr.arc(14, -12, 8, 0, 2 * math.pi); cr.fill()
        cr.move_to(-30, 26); cr.line_to(-8, -8); cr.line_to(6, 12); cr.line_to(14, 2); cr.line_to(30, 26); cr.close_path(); cr.fill()
    elif kind == 'gear':
        for i in range(8):
            cr.save(); cr.rotate(i * math.pi / 4); rr(cr, -6, -32, 12, 14, 3); cr.fill(); cr.restore()
        cr.arc(0, 0, 22, 0, 2 * math.pi); cr.set_line_width(10); cr.stroke()
    elif kind == 'bag':
        rr(cr, -24, -10, 48, 38, 6); cr.fill()
        cr.set_line_width(6); cr.arc(0, -10, 12, math.pi, 2 * math.pi); cr.stroke()
    elif kind == 'calc':
        for i in range(3):
            for j in range(3):
                rr(cr, -26 + i * 19, -26 + j * 19, 14, 14, 3); cr.fill()
    elif kind == 'pencil':
        cr.save(); cr.rotate(-.8); rr(cr, -8, -32, 16, 52, 3); cr.fill()
        cr.move_to(-8, 24); cr.line_to(0, 38); cr.line_to(8, 24); cr.close_path(); cr.fill(); cr.restore()
    elif kind == 'play':
        cr.move_to(-14, -24); cr.line_to(26, 0); cr.line_to(-14, 24); cr.close_path(); cr.fill()
    elif kind == 'chat':
        rr(cr, -28, -24, 56, 38, 12); cr.fill()
        cr.move_to(-12, 12); cr.line_to(-16, 30); cr.line_to(4, 14); cr.close_path(); cr.fill()
    elif kind == 'game':
        rr(cr, -30, -14, 60, 34, 16); cr.fill()
        cr.set_source_rgba(0, 0, 0, .35)
        cr.set_line_width(6); cr.move_to(-18, 3); cr.line_to(-6, 3); cr.move_to(-12, -3); cr.line_to(-12, 9); cr.stroke()
        cr.arc(14, 0, 4, 0, 2 * math.pi); cr.fill(); cr.arc(22, 8, 4, 0, 2 * math.pi); cr.fill()
    cr.restore()


def tag(cr, x, y, s, size=10, align='l', col='#12304f'):
    """A pill label with a white glass body, for the callouts."""
    cr.new_path()
    w = text_w(cr, s, size, True) + 18
    x0 = x if align == 'l' else x - w if align == 'r' else x - w / 2
    rr(cr, x0, y - 11, w, 22, 11)
    cr.set_source_rgba(1, 1, 1, .92)
    cr.fill_preserve()
    cr.set_source_rgba(.1, .3, .6, .5)
    cr.set_line_width(1)
    cr.stroke()
    text(cr, s, x0 + 9, y, size, col, True)
    return x0, w


def num(cr, x, y, n):
    cr.new_path()
    cr.arc(x, y, 10, 0, 2 * math.pi)
    cr.set_source(vgrad(0, y - 10, y + 10, [(0, '#ff9b52', 1), (1, '#e0551a', 1)]))
    cr.fill_preserve()
    cr.set_source_rgb(1, 1, 1)
    cr.set_line_width(1.5)
    cr.stroke()
    text(cr, str(n), x, y, 9, '#ffffff', True, 'c')


def leader(cr, x0, y0, x1, y1):
    cr.new_path()
    cr.move_to(x0, y0)
    cr.line_to(x1, y1)
    cr.set_source_rgba(1, 1, 1, .9)
    cr.set_line_width(2)
    cr.stroke()


def key(cr, x, y, w, label, size=12, h=38):
    rr(cr, x, y + 4, w, h, 8)
    cr.set_source_rgba(0, 0, 0, .3)
    cr.fill()
    rr(cr, x, y, w, h, 8)
    cr.set_source(vgrad(0, y, y + h, [(0, '#ffffff', 1), (1, '#d3dcea', 1)]))
    cr.fill_preserve()
    cr.set_source_rgba(.2, .3, .5, .6)
    cr.set_line_width(1)
    cr.stroke()
    text(cr, label, x + w / 2, y + h / 2 - 1, size, '#1c3150', True, 'c')


# ---------------------------------------------------------------- the eight illustrations (each fills 480x420)
def art_welcome(cr):
    for i in range(14):  # rays
        cr.save()
        cr.translate(240, 190)
        cr.rotate(i * math.pi / 7)
        cr.move_to(0, 0)
        cr.line_to(-14, -330)
        cr.line_to(14, -330)
        cr.close_path()
        cr.set_source_rgba(1, 1, 1, .08)
        cr.fill()
        cr.restore()
    shadow(cr, 160, 110, 160, 160, 80, 9, .35)
    orb(cr, 240, 190, 84)
    glass(cr, 80, 310, 320, 62, 16, .35)
    text(cr, 'MWX 7', 240, 332, 22, '#10335f', True, 'c')
    text(cr, 'the best of XP, 7 and macOS', 240, 356, 10, '#1c3f6f', False, 'c')
    for x, y, r in ((90, 80, 3), (400, 120, 4), (60, 210, 2.5), (420, 260, 3), (330, 60, 2.5)):  # sparkles
        for k in range(2):
            cr.save(); cr.translate(x, y); cr.rotate(k * math.pi / 4)
            cr.move_to(-r * 3, 0); cr.line_to(r * 3, 0); cr.move_to(0, -r * 3); cr.line_to(0, r * 3)
            cr.set_source_rgba(1, 1, 1, .9); cr.set_line_width(1.5); cr.stroke(); cr.restore()


def dock(cr, cx, y, kinds, cols, big=2, base=40):
    """A dock: icons grow towards the pointer (index `big`), on a glass shelf."""
    sizes = [base + max(0, 26 - abs(i - big) * 11) for i in range(len(kinds))]
    total = sum(sizes) + 10 * (len(sizes) - 1) + 28
    x = cx - total / 2
    glass(cr, x, y + 4, total, base + 22, 16, .3)
    px = x + 14
    for i, k in enumerate(kinds):
        s = sizes[i]
        tile(cr, px, y + base + 20 - s, s, k, cols[i])
        # reflection
        cr.save()
        cr.rectangle(px, y + base + 20, s, 8)
        cr.clip()
        cr.set_source_rgba(1, 1, 1, .12)
        cr.paint()
        cr.restore()
        if i == 0:
            cr.arc(px + s / 2, y + base + 26, 2.5, 0, 2 * math.pi)
            cr.set_source_rgba(1, 1, 1, .95)
            cr.fill()
        px += s + 10
    return x, total, sizes


def art_desktop(cr):
    glass(cr, 0, 0, 480, 22, 0, .1, True)
    orb(cr, 14, 11, 8)
    text(cr, 'Files   Edit   View', 34, 11, 8, '#ffffff', False)
    text(cr, '10:24', 462, 11, 8, '#ffffff', True, 'r')
    for i, (k, c, n) in enumerate((('folder', '#e0b03b', 'Files'), ('globe', '#3b82e0', 'Internet'), ('music', '#d9548a', 'Music'))):
        tile(cr, 22, 44 + i * 78, 44, k, c)
        text(cr, n, 44, 44 + i * 78 + 54, 8, '#ffffff', False, 'c', shadow=True)
    window(cr, 130, 56, 250, 170, 'Files')
    for i in range(4):
        rr(cr, 148, 100 + i * 26, 70 + (i % 3) * 30, 12, 4)
        cr.set_source_rgba(.2, .4, .8, .25 + .1 * i)
        cr.fill()
    for i in range(2):
        tile(cr, 290 + i * 40, 104, 30, ('folder', 'photo')[i], ('#e0b03b', '#3bb26a')[i])
    # desktop widget
    glass(cr, 392, 44, 76, 76, 14, .3, True)
    text(cr, '10:24', 430, 76, 14, '#ffffff', True, 'c')
    text(cr, 'Friday 13', 430, 98, 7, '#cfe3ff', False, 'c')
    kinds = ['folder', 'globe', 'music', 'photo', 'gear', 'bag']
    cols = ['#e0b03b', '#3b82e0', '#d9548a', '#3bb26a', '#8a5be0', '#e0653b']
    x, total, sizes = dock(cr, 240, 292, kinds, cols, big=2)
    num(cr, 240, 276, 1)
    tag(cr, 262, 276, 'Dock: icons grow as you point', 9)
    # Aero Peek bubble over the Internet icon
    bx = x + 14 + sizes[0] + 10 + sizes[1] / 2
    shadow(cr, bx - 58, 178, 116, 68, 8, 5)
    glass(cr, bx - 58, 178, 116, 68, 8, .5)
    rr(cr, bx - 52, 184, 104, 50, 4)
    cr.set_source(vgrad(0, 184, 234, [(0, '#bfe0ff', 1), (1, '#eaf6ff', 1)]))
    cr.fill()
    text(cr, 'Aero Peek', bx, 241, 7, '#12304f', True, 'c')
    num(cr, bx + 58, 180, 2)
    num(cr, 430, 44, 3)
    num(cr, 14, 11, 4)


def art_bar(cr):
    # the bar, enlarged
    shadow(cr, 12, 26, 456, 52, 14, 6)
    glass(cr, 12, 26, 456, 52, 14, .1, True)
    orb(cr, 44, 52, 19)
    xs = {'start': 44}
    # search
    cr.arc(104, 50, 8, 0, 2 * math.pi)
    cr.set_source_rgba(1, 1, 1, .95); cr.set_line_width(2.5); cr.stroke()
    cr.move_to(110, 56); cr.line_to(117, 63); cr.stroke()
    text(cr, 'Terminal  Files  Notes', 170, 52, 9, '#e7f1ff', False, 'l', .85)
    # clipboard
    rr(cr, 322, 41, 18, 22, 3); cr.set_source_rgba(1, 1, 1, .95); cr.set_line_width(2); cr.stroke()
    rr(cr, 327, 38, 8, 6, 2); cr.set_source_rgba(1, 1, 1, .95); cr.fill()
    # bell
    cr.move_to(372, 62); cr.curve_to(374, 58, 374, 56, 374, 50); cr.curve_to(374, 42, 394, 42, 394, 50)
    cr.curve_to(394, 56, 394, 58, 396, 62); cr.close_path(); cr.set_source_rgba(1, 1, 1, .95); cr.fill()
    cr.arc(384, 65, 3, 0, math.pi); cr.fill()
    cr.arc(394, 42, 7, 0, 2 * math.pi); cr.set_source_rgb(.9, .2, .15); cr.fill()
    text(cr, '2', 394, 42, 8, '#ffffff', True, 'c')
    text(cr, '10:24', 460, 46, 10, '#ffffff', True, 'r')
    text(cr, 'Fri 13 Nov', 460, 61, 7, '#cfe3ff', False, 'r')
    for n, x in ((1, 44), (2, 104), (3, 331), (4, 384), (5, 430)):
        num(cr, x, 94, n)
    # notification toast + clipboard flyout + calendar popup
    shadow(cr, 20, 128, 210, 60, 10, 5)
    glass(cr, 20, 128, 210, 60, 10, .5)
    tile(cr, 30, 138, 38, 'chat', '#3bb26a')
    text(cr, 'New message', 78, 148, 9, '#12304f', True)
    text(cr, 'Lunch at one?', 78, 166, 9, '#35506f')
    num(cr, 20, 128, 4)
    shadow(cr, 20, 212, 210, 130, 10, 5)
    glass(cr, 20, 212, 210, 130, 10, .5)
    text(cr, 'Clipboard', 34, 228, 9, '#12304f', True)
    for i, s in enumerate(('https://example.org/menu', 'Meeting at 14:30', 'Invoice #2041')):
        rr(cr, 30, 244 + i * 29, 190, 23, 5)
        cr.set_source_rgba(1, 1, 1, .8); cr.fill()
        text(cr, s, 40, 244 + i * 29 + 12, 8, '#27405f')
    num(cr, 20, 212, 3)
    shadow(cr, 262, 112, 196, 236, 10, 5)
    glass(cr, 262, 112, 196, 236, 10, .5)
    text(cr, 'November 2026', 360, 130, 10, '#12304f', True, 'c')
    for i, d in enumerate('MTWTFSS'):
        text(cr, d, 280 + i * 25, 154, 7, '#5a7090', True, 'c')
    for n in range(1, 31):
        i = (n + 6) % 7
        r_ = (n + 6) // 7
        x, y = 280 + i * 25, 176 + r_ * 24 - 24
        if n == 13:
            cr.arc(x, y, 11, 0, 2 * math.pi)
            cr.set_source(vgrad(0, y - 11, y + 11, [(0, '#5aa9ff', 1), (1, '#1f62c4', 1)])); cr.fill()
        text(cr, str(n), x, y, 8, '#ffffff' if n == 13 else '#27405f', n == 13, 'c')
    num(cr, 458, 112, 5)
    tag(cr, 240, 395, 'Click the clock for the calendar', 9, 'c')


def art_windows(cr):
    glass(cr, 0, 0, 480, 26, 0, .1, True)
    orb(cr, 14, 13, 9)
    text(cr, 'Notes', 34, 13, 9, '#ffffff', True)
    text(cr, 'File   Edit   View   Window   Help', 78, 13, 9, '#e7f1ff')
    text(cr, '10:24', 464, 13, 9, '#ffffff', True, 'r')
    tag(cr, 100, 48, 'Menu bar, always at the top', 9)
    num(cr, 30, 48, 4)
    shadow(cr, 40, 100, 400, 250, 12)
    glass(cr, 40, 100, 400, 250, 12, .5)
    text(cr, 'Notes', 62, 122, 11, '#12304f', True)
    xs = lights(cr, 346, 122, 11)
    rr(cr, 50, 144, 380, 196, 5)
    cr.set_source_rgb(1, 1, 1); cr.fill()
    for i in range(7):
        rr(cr, 68, 164 + i * 24, 220 - (i * 37) % 120, 8, 3)
        cr.set_source_rgba(.25, .4, .7, .25); cr.fill()
    for i, (lab, n) in enumerate((('Minimize', 1), ('Full screen', 2), ('Close', 3))):
        num(cr, xs[i], 92, n)
        x0, w = 70 + i * 120, 0
        num(cr, x0, 388, n)
        tag(cr, x0 + 14, 388, lab, 9)


def art_apps(cr):
    window(cr, 28, 40, 424, 330, 'Get Apps')
    rr(cr, 120, 78, 240, 24, 12)
    cr.set_source_rgb(.94, .96, 1); cr.fill_preserve(); cr.set_source_rgba(.4, .55, .8, .6); cr.set_line_width(1); cr.stroke()
    cr.arc(138, 90, 5, 0, 2 * math.pi); cr.set_source_rgba(.3, .4, .6, .9); cr.set_line_width(1.5); cr.stroke()
    text(cr, 'Search thousands of apps', 152, 90, 8, '#7a8aa5')
    cr.move_to(40, 116); cr.line_to(440, 116); cr.set_source_rgba(.6, .7, .85, .5); cr.set_line_width(1); cr.stroke()
    items = (('Videos', 'play', '#d9548a'), ('Chat', 'chat', '#3bb26a'), ('Music', 'music', '#8a5be0'),
             ('Photos', 'photo', '#e0653b'), ('Games', 'game', '#3bb8c8'), ('Notes', 'pencil', '#e0b03b'))
    for i, (n, k, c) in enumerate(items):
        x, y = 52 + (i % 3) * 132, 130 + (i // 3) * 112
        rr(cr, x - 8, y - 4, 124, 100, 8)
        cr.set_source_rgba(.9, .94, 1, .7); cr.fill()
        tile(cr, x + 4, y + 2, 44, k, c)
        text(cr, n, x + 56, y + 14, 9, '#12304f', True)
        text(cr, 'Free', x + 56, y + 32, 8, '#6a7f9c')
        rr(cr, x + 4, y + 60, 86, 22, 11)
        cr.set_source(vgrad(0, y + 60, y + 82, [(0, '#6fb4ff', 1), (1, '#2a72d6', 1)])); cr.fill()
        text(cr, 'Install' if i != 1 else 'Open', x + 47, y + 71, 9, '#ffffff', True, 'c')
    tag(cr, 240, 392, 'Apps from Flathub, installed in one click', 9, 'c')


def art_settings(cr):
    window(cr, 28, 40, 424, 330, 'Settings')
    cr.rectangle(34, 72, 112, 292)
    cr.set_source_rgba(.88, .93, 1, 1); cr.fill()
    for i, (n, k, c) in enumerate((('Wallpapers', 'photo', '#3b82e0'), ('Display', 'play', '#8a5be0'),
                                   ('Sound', 'music', '#d9548a'), ('Backup', 'folder', '#3bb26a'), ('Updates', 'gear', '#e0653b'))):
        y = 80 + i * 34
        if i == 0:
            rr(cr, 38, y - 4, 104, 28, 5)
            cr.set_source(vgrad(0, y - 4, y + 24, [(0, '#cfe5ff', 1), (1, '#a8cdf5', 1)])); cr.fill()
        tile(cr, 44, y, 20, k, c)
        text(cr, n, 72, y + 10, 9, '#12304f', i == 0)
    text(cr, 'Wallpapers', 164, 88, 12, '#12304f', True)
    for i, th in enumerate(('day', 'dusk', 'mint')):
        x = 164 + i * 94
        cr.save()
        rr(cr, x, 106, 84, 54, 5); cr.clip()
        cr.translate(x, 106); cr.scale(84 / 200, 54 / 130)
        wallpaper(cr, 200, 130, th)
        cr.restore()
        rr(cr, x, 106, 84, 54, 5)
        cr.set_source_rgba(.2, .4, .8, 1 if i == 0 else .35); cr.set_line_width(2.5 if i == 0 else 1); cr.stroke()
    num(cr, 164, 106, 1)
    text(cr, 'Animations', 164, 184, 11, '#12304f', True)
    segs = ('Full', 'Reduced', 'Off')
    for i, s in enumerate(segs):
        x = 164 + i * 86
        rr(cr, x, 198, 86, 26, 6)
        if i == 0:
            cr.set_source(vgrad(0, 198, 224, [(0, '#6fb4ff', 1), (1, '#2a72d6', 1)]))
        else:
            cr.set_source_rgb(.94, .96, 1)
        cr.fill_preserve(); cr.set_source_rgba(.3, .5, .8, .6); cr.set_line_width(1); cr.stroke()
        text(cr, s, x + 43, 211, 9, '#ffffff' if i == 0 else '#27405f', True, 'c')
    num(cr, 164, 198, 2)
    text(cr, 'Backup', 164, 252, 11, '#12304f', True)
    rr(cr, 164, 266, 266, 80, 8)
    cr.set_source_rgba(.92, .96, 1, 1); cr.fill_preserve(); cr.set_source_rgba(.4, .55, .8, .5); cr.stroke()
    rr(cr, 178, 282, 50, 38, 6)
    cr.set_source(vgrad(0, 282, 320, [(0, '#c9d3e2', 1), (1, '#7f8ea6', 1)])); cr.fill()
    cr.arc(214, 308, 3, 0, 2 * math.pi); cr.set_source_rgb(.3, 1, .4); cr.fill()
    text(cr, 'Your files, safe on a drive', 240, 290, 9, '#12304f', True)
    rr(cr, 240, 306, 176, 9, 4.5); cr.set_source_rgba(.6, .7, .85, .5); cr.fill()
    rr(cr, 240, 306, 120, 9, 4.5); cr.set_source(vgrad(0, 306, 315, [(0, '#8be37a', 1), (1, '#2fa84a', 1)])); cr.fill()
    text(cr, 'Last backup: today', 240, 328, 8, '#5a7090')
    num(cr, 164, 266, 3)


def art_updates(cr):
    # card with the update arrows
    shadow(cr, 70, 40, 340, 170, 16)
    glass(cr, 70, 40, 340, 170, 16, .5)
    cx, cy = 150, 125
    cr.arc(cx, cy, 44, 0, 2 * math.pi)
    cr.set_source(vgrad(0, cy - 44, cy + 44, [(0, '#8dc7ff', 1), (1, '#1f62c4', 1)])); cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, .9); cr.set_line_width(2.5); cr.stroke()
    cr.set_source_rgb(1, 1, 1); cr.set_line_width(7); cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for a0, flip in ((.35, 1), (math.pi + .35, 1)):
        cr.arc(cx, cy, 24, a0, a0 + math.pi * .72); cr.stroke()
        ex, ey = cx + 24 * math.cos(a0 + math.pi * .72), cy + 24 * math.sin(a0 + math.pi * .72)
        cr.save(); cr.translate(ex, ey); cr.rotate(a0 + math.pi * .72 + math.pi / 2)
        cr.move_to(-9, 2); cr.line_to(9, 2); cr.line_to(0, -12); cr.close_path(); cr.fill(); cr.restore()
    text(cr, 'MWX 7 is up to date', 215, 100, 12, '#12304f', True)
    text(cr, 'Security fixes install by themselves', 215, 122, 8, '#35506f')
    rr(cr, 215, 140, 170, 9, 4.5); cr.set_source_rgba(.6, .7, .85, .5); cr.fill()
    rr(cr, 215, 140, 170, 9, 4.5); cr.set_source(vgrad(0, 140, 149, [(0, '#8be37a', 1), (1, '#2fa84a', 1)])); cr.fill()
    rr(cr, 215, 164, 110, 24, 12); cr.set_source(vgrad(0, 164, 188, [(0, '#6fb4ff', 1), (1, '#2a72d6', 1)])); cr.fill()
    text(cr, 'Check for updates', 270, 176, 8, '#ffffff', True, 'c')
    num(cr, 70, 40, 1)
    for i, (title, sub, col, kind) in enumerate((('Repair MWX 7', 'Fixes the system, keeps your files', '#3bb26a', 'wrench'),
                                                 ('Reset to factory', 'Starts fresh, deletes everything', '#e0653b', 'reset'))):
        x = 34 + i * 218
        shadow(cr, x, 240, 210, 130, 12, 5)
        glass(cr, x, 240, 210, 130, 12, .5)
        cx, cy = x + 105, 288
        cr.arc(cx, cy, 28, 0, 2 * math.pi)
        rgba(cr, col); cr.fill_preserve(); cr.set_source_rgba(1, 1, 1, .9); cr.set_line_width(2); cr.stroke()
        cr.set_source_rgb(1, 1, 1); cr.set_line_width(6); cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if kind == 'wrench':
            cr.save(); cr.translate(cx, cy); cr.rotate(math.pi / 4)
            cr.move_to(0, 18); cr.line_to(0, -6); cr.stroke()
            cr.arc(0, -12, 9, 0, 2 * math.pi); cr.set_line_width(5); cr.stroke()
            cr.restore()
        else:
            cr.arc(cx, cy, 14, -math.pi * .15, math.pi * 1.5); cr.set_line_width(5); cr.stroke()
            cr.move_to(cx, cy - 22); cr.line_to(cx + 8, cy - 14); cr.line_to(cx, cy - 6); cr.close_path(); cr.fill()
        text(cr, title, x + 105, 334, 10, '#12304f', True, 'c')
        text(cr, sub, x + 105, 352, 8, '#35506f', False, 'c')
        num(cr, x + 4, 244, i + 2)
    tag(cr, 240, 400, 'Also in the boot menu: hold Esc at start', 9, 'c')


def art_keys(cr):
    rows = ((('Super', 70), ('V', 46)), (('Alt', 56), ('Tab', 64)), (('Super', 70), ('←', 46), ('→', 46)), (('Ctrl', 56), ('Alt', 56), ('T', 46)))
    labels = ('Clipboard history', 'Switch windows', 'Snap left or right', 'Open a terminal')
    for r_, (row, lab) in enumerate(zip(rows, labels)):
        y = 40 + r_ * 92
        total = sum(w for _, w in row) + 12 * (len(row) - 1)
        x = 240 - total / 2
        for i, (k, w) in enumerate(row):
            key(cr, x, y, w, k, 13)
            x += w + 12
            if i < len(row) - 1:
                text(cr, '+', x - 6, y + 18, 12, '#ffffff', True, 'c', shadow=True)
        text(cr, lab, 240, y + 58, 10, '#ffffff', True, 'c', shadow=True)


# ---------------------------------------------------------------- pages
SET = lambda page: ('Open Settings', [SETTINGS, '--page', page])  # noqa: E731
PAGES = [
    dict(id='welcome', title='Welcome to MWX 7', art=art_welcome, theme='day',
         lead='A dream desktop that blends the best of Windows XP, Windows 7 and macOS, on your own PC. Take a two-minute tour.',
         points=[('Familiar', 'A Start menu, a dock and glass windows: you already know your way around.'),
                 ('Yours', 'Wallpapers, window colours and animations all change in Settings.'),
                 ('Safe', 'Updates, Backup and Repair are built in.')], actions=[]),
    dict(id='desktop', title='Your desktop and dock', art=art_desktop, theme='day',
         lead='Everything is a click away, and every window is easy to find.',
         points=[('1  Dock', 'Your apps along the bottom; icons grow as you point at them. Right-click one for its recent files.'),
                 ('2  Aero Peek', 'Point at a running app to preview its windows.'),
                 ('3  Widgets', 'Clock, calendar and meters, right on the desktop.'),
                 ('4  Start', 'The orb opens every program and instant search.')],
         actions=[('Customize the dock', [SETTINGS, '--page', 'dock']), ('Desktop settings', [SETTINGS, '--page', 'desktop'])]),
    dict(id='bar', title='The status bar', art=art_bar, theme='dusk',
         lead='One bar holds what you reach for most.',
         points=[('1  Start', 'All programs, and shut down or lock.'), ('2  Search', 'Apps, files and settings. Press Super + S.'),
                 ('3  Clipboard', 'Everything you copied lately. Press Super + V.'),
                 ('4  Notifications', 'The bell collects them, with Do Not Disturb.'),
                 ('5  Calendar', 'Click the clock for the month; it opens Date & time.')],
         actions=[('Date & time settings', [SETTINGS, '--page', 'datetime'])]),
    dict(id='windows', title='Windows and the menu bar', art=art_windows, theme='mint',
         lead='Three lights on every window, and one menu bar for the app in front.',
         points=[('1  Green: minimize', 'Tucks the window into the dock.'),
                 ('2  Yellow: full screen', 'Fills the screen; click again to restore. Drag a window to an edge to snap it.'),
                 ('3  Red: close', 'Closes the window.'),
                 ('4  Menu bar', 'The focused app\'s menus (File, Edit, View...) live in the top bar, as on a Mac.')],
         actions=[('Window colour', [SETTINGS, '--page', 'wincolor'])]),
    dict(id='apps', title='Get Apps', art=art_apps, theme='day',
         lead='Browse and install free apps from Flathub: browsers, editors, games, media and more.',
         points=[('Install', 'One click; your administrator password is asked only when needed.'),
                 ('Update', 'The Updates tab keeps every app current.'),
                 ('Remove', 'Uninstall any app you no longer use.')],
         actions=[('Open Get Apps', [APP, 'store'])]),
    dict(id='settings', title='Make it yours', art=art_settings, theme='dusk',
         lead='Settings is where MWX 7 becomes your own.',
         points=[('1  Wallpapers', 'Meadows, mountains and your own pictures.'),
                 ('2  Animations', 'Full, Reduced or Off: choose Reduced or Off on a slower PC or a virtual machine.'),
                 ('3  Backup', 'Copy your files to a drive and bring them back.')],
         actions=[('Wallpapers', [SETTINGS, '--page', 'wallpapers']), ('Animations', [SETTINGS, '--page', 'display']),
                  ('Backup', [SETTINGS, '--page', 'backup'])]),
    dict(id='updates', title='Updates and Repair', art=art_updates, theme='mint',
         lead='New versions arrive through Settings; if something ever goes wrong, you can fix it without losing a file.',
         points=[('1  Updates', 'Security fixes install by themselves; bigger versions wait for your go-ahead.'),
                 ('2  Repair', 'Rebuilds MWX 7 and keeps your accounts, files and apps.'),
                 ('3  Reset to factory', 'Deletes everything and starts again. Think twice.')],
         actions=[('Open Updates', [SETTINGS, '--updates'])]),
    dict(id='keys', title='Keyboard shortcuts', art=art_keys, theme='day',
         lead='These are the real shortcuts of this session.', points=[], shortcuts=True,
         actions=[('Keyboard settings', [SETTINGS, '--page', 'keyboard'])]),
]

CSS = """
window.mwx7-welcome > box { background: #ffffff; }
.wl-text { background: #ffffff; }
.wl-title { font-size: 26px; font-weight: 300; color: #1c3150; }
.wl-lead { color: #3c5272; font-size: 13px; }
.wl-pt-h { font-weight: 700; color: #1c3150; }
.wl-pt { color: #4a5f7d; }
.wl-key { background: linear-gradient(to bottom, #ffffff, #dde6f3); border: 1px solid #a9bbd4; border-radius: 5px;
  padding: 1px 7px; font-weight: 700; color: #1c3150; font-size: 12px; }
.wl-row { padding: 5px 0; border-bottom: 1px solid #e3ebf5; }
.wl-foot { padding: 10px 16px; border-top: 1px solid #d5dfec; background: #f6f8fb; }
button.wl-dot { min-width: 10px; min-height: 10px; padding: 0; border-radius: 999px; background: #c6d4e6; border: none;
  box-shadow: none; }
button.wl-dot.on { background: #2a72d6; }
"""


def launch(cmd):
    try:
        subprocess.Popen(cmd, start_new_session=True)
    except OSError:
        pass


def build(app, win):
    win.add_css_class('mwx7-welcome')
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=260, vexpand=True)
    for pg in PAGES:
        page = Gtk.Box()
        area = Gtk.DrawingArea(hexpand=False, vexpand=True)
        area.set_size_request(490, -1)

        def draw(_a, cr, w, h, pg=pg):
            wallpaper(cr, w, h, pg['theme'])
            s = min(w / AW, h / AH)
            cr.translate((w - AW * s) / 2, (h - AH * s) / 2)
            cr.scale(s, s)
            pg['art'](cr)
        area.set_draw_func(draw)
        page.append(area)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=26, margin_bottom=16, margin_start=26,
                           margin_end=26, hexpand=True)
        text_box.add_css_class('wl-text')
        t = Gtk.Label(label=pg['title'], xalign=0, wrap=True)
        t.add_css_class('wl-title')
        text_box.append(t)
        ld = Gtk.Label(label=pg['lead'], xalign=0, wrap=True, max_width_chars=40)
        ld.add_css_class('wl-lead')
        text_box.append(ld)
        for h, d in pg['points']:
            hl = Gtk.Label(label=h, xalign=0, margin_top=6)
            hl.add_css_class('wl-pt-h')
            dl = Gtk.Label(label=d, xalign=0, wrap=True, max_width_chars=44)
            dl.add_css_class('wl-pt')
            text_box.append(hl)
            text_box.append(dl)
        if pg.get('shortcuts'):
            lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=4)
            for keys, what in real_shortcuts():
                row = Gtk.Box(spacing=8)
                row.add_css_class('wl-row')
                kb = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
                for k in keys.split(' + '):
                    kl = Gtk.Label(label=k)
                    kl.add_css_class('wl-key')
                    kb.append(kl)
                kb.set_size_request(168, -1)
                row.append(kb)
                row.append(Gtk.Label(label=what, xalign=0, hexpand=True, css_classes=['wl-pt']))
                lst.append(row)
            sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
            sc.set_child(lst)
            text_box.append(sc)
        else:
            text_box.append(Gtk.Box(vexpand=True))
        if pg['actions']:
            ab = Gtk.Box(spacing=8, margin_top=8, halign=Gtk.Align.START)
            for label, cmd in pg['actions']:
                b = Gtk.Button(label=label)
                b.connect('clicked', lambda _b, c=cmd: launch(c))
                ab.append(b)
            text_box.append(ab)
        page.append(text_box)
        stack.add_named(page, pg['id'])
    root.append(stack)

    foot = Gtk.CenterBox()
    foot.add_css_class('wl-foot')
    back = Gtk.Button(label='Back')
    nxt = Gtk.Button(label='Next')
    nxt.add_css_class('suggested-action')
    check = Gtk.CheckButton(label='Show at startup', active=bool(load_conf().get('show_at_startup', False)),
                            tooltip_text='Show this Welcome Center at every sign-in, not only the first')
    check.connect('toggled', lambda c: save_conf(show_at_startup=c.get_active()))
    dots_box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
    dots = []
    state = {'i': 0}

    def go(i):
        i = max(0, min(len(PAGES) - 1, i))
        state['i'] = i
        stack.set_visible_child_name(PAGES[i]['id'])
        back.set_sensitive(i > 0)
        nxt.set_label('Get started' if i == len(PAGES) - 1 else 'Next')
        for j, d in enumerate(dots):
            (d.add_css_class if j == i else d.remove_css_class)('on')

    for i, pg in enumerate(PAGES):
        d = Gtk.Button(tooltip_text=pg['title'], focusable=False)
        d.add_css_class('wl-dot')
        d.connect('clicked', lambda _b, i=i: go(i))
        dots.append(d)
        dots_box.append(d)
    back.connect('clicked', lambda *_: go(state['i'] - 1))

    def forward(*_):
        if state['i'] == len(PAGES) - 1:
            win.close()
        else:
            go(state['i'] + 1)
    nxt.connect('clicked', forward)
    right = Gtk.Box(spacing=8)
    right.append(back)
    right.append(nxt)
    foot.set_start_widget(check)
    foot.set_center_widget(dots_box)
    foot.set_end_widget(right)
    root.append(foot)

    # Arrows move between pages, Enter goes on (a focused button keeps its own Enter), Esc closes.
    keys = Gtk.EventControllerKey()

    def pressed(_c, keyval, _code, _mods):
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            go(state['i'] + 1)
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            go(state['i'] - 1)
        elif keyval == Gdk.KEY_Home:
            go(0)
        elif keyval == Gdk.KEY_End:
            go(len(PAGES) - 1)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            forward()
        elif keyval == Gdk.KEY_Escape:
            win.close()
        else:
            return False
        return True
    keys.connect('key-pressed', pressed)
    win.add_controller(keys)
    go(0)
    first = int(os.environ.get('WELCOME_PAGE', '0') or 0)  # for checking the pages headlessly
    if first:
        go(first)
    GLib.idle_add(lambda: win.set_focus(None) or False)
    return root


if __name__ == '__main__':
    mwx7ui.App('org.mwx7.welcome', 'Welcome Center', 'about', (940, 600), CSS, build, resizable=False).run_main()
