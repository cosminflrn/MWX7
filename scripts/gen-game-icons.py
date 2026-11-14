#!/usr/bin/env python3
"""Draws the 256px icons of FreeCell, Spider and Hearts with cairo (original artwork, no external images).
Usage: python3 scripts/gen-game-icons.py   -> distro/desktop/overlay/usr/share/mwx7/icons/{freecell,spider,hearts}.png"""
import math
import os
import sys

import cairo

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'distro', 'desktop', 'overlay', 'usr', 'share', 'mwx7')
sys.path.insert(0, os.path.join(ROOT, 'lib'))
import mwx7cards as mc  # noqa: E402

S = 256


def tile(cr, top, bottom):
    """Glossy rounded square, the shape of MWX 7's other app icons."""
    mc.card_rrect(cr, 8, 8, S - 16, S - 16, 44)
    g = cairo.LinearGradient(0, 8, 0, S - 8)
    g.add_color_stop_rgb(0, *top)
    g.add_color_stop_rgb(1, *bottom)
    cr.set_source(g)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 0.55)
    cr.set_line_width(3)
    cr.stroke()
    cr.save()
    mc.card_rrect(cr, 8, 8, S - 16, S - 16, 44)
    cr.clip()
    hl = cairo.LinearGradient(0, 8, 0, 130)
    hl.add_color_stop_rgba(0, 1, 1, 1, 0.38)
    hl.add_color_stop_rgba(1, 1, 1, 1, 0.02)
    cr.set_source(hl)
    cr.rectangle(0, 0, S, 130)
    cr.fill()
    cr.restore()


def card(cr, c, x, y, angle=0, scale=1.6):
    cr.save()
    cr.translate(x, y)
    cr.rotate(math.radians(angle))
    cr.scale(scale, scale)
    mc.draw_card(cr, c, -mc.CW / 2, -mc.CH / 2)
    cr.restore()


def freecell(cr):
    tile(cr, (0.25, 0.72, 0.4), (0.04, 0.33, 0.16))
    for i in range(4):  # the four free cells
        mc.card_rrect(cr, 30 + i * 48, 34, 38, 54, 5)
        cr.set_source_rgba(0, 0, 0, 0.25)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.7)
        cr.set_line_width(2.5)
        cr.stroke()
    card(cr, (3, 12, True), 100, 175, -14, 1.35)
    card(cr, (1, 1, True), 152, 170, 8, 1.35)


def spider(cr):
    tile(cr, (0.22, 0.28, 0.42), (0.05, 0.08, 0.16))
    card(cr, (0, 1, True), 128, 130, -6, 1.9)
    cr.set_source_rgb(0.08, 0.09, 0.12)
    cx, cy = 128, 138
    cr.set_line_width(7)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for side in (-1, 1):  # eight jointed legs
        for k, (dy, reach) in enumerate(((-22, 62), (-8, 78), (8, 78), (24, 62))):
            kx, ky = cx + side * (reach * 0.55), cy + dy - 30 + k * 4
            cr.move_to(cx + side * 12, cy + dy * 0.5)
            cr.line_to(kx, ky)
            cr.line_to(cx + side * reach, cy + dy * 1.5 + 14)
            cr.stroke()
    cr.arc(cx, cy - 18, 14, 0, 2 * math.pi)
    cr.fill()
    cr.save()
    cr.translate(cx, cy + 14)
    cr.scale(1, 1.25)
    cr.arc(0, 0, 24, 0, 2 * math.pi)
    cr.restore()
    cr.fill()
    cr.set_source_rgba(0.9, 0.15, 0.15, 0.95)  # hourglass mark on the back
    cr.move_to(cx - 8, cy + 4)
    cr.line_to(cx + 8, cy + 4)
    cr.line_to(cx - 8, cy + 26)
    cr.line_to(cx + 8, cy + 26)
    cr.close_path()
    cr.fill()
    for side in (-1, 1):
        cr.set_source_rgb(1, 1, 1)
        cr.arc(cx + side * 6, cy - 21, 3, 0, 2 * math.pi)
        cr.fill()


def hearts(cr):
    tile(cr, (0.95, 0.38, 0.4), (0.55, 0.05, 0.12))
    card(cr, (0, 12, True), 90, 150, -18, 1.4)
    card(cr, (1, 1, True), 166, 140, 14, 1.4)
    g = cairo.RadialGradient(120, 90, 4, 128, 110, 60)  # a glossy heart on top
    g.add_color_stop_rgb(0, 1, 0.55, 0.55)
    g.add_color_stop_rgb(1, 0.75, 0.04, 0.12)
    cr.set_source(g)
    mc.suit_path(cr, 1, 128, 100, 44)


def main():
    out = os.path.join(ROOT, 'icons')
    for name, fn in (('freecell', freecell), ('spider', spider), ('hearts', hearts)):
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
        cr = cairo.Context(surf)
        fn(cr)
        surf.write_to_png(os.path.join(out, name + '.png'))
        print('wrote', name)


if __name__ == '__main__':
    main()
