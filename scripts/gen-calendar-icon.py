#!/usr/bin/env python3
"""Draws the 256px icon of Calendar with cairo (original artwork, no external images, no fonts).
Usage: python3 scripts/gen-calendar-icon.py   -> distro/desktop/overlay/usr/share/mwx7/icons/calendar.png"""
import math
import os

import cairo

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'distro', 'desktop', 'overlay', 'usr', 'share', 'mwx7',
                   'icons', 'calendar.png')
S = 256


def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


def main():
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
    cr = cairo.Context(surf)
    # Glossy rounded tile in blue, like the other app icons.
    rrect(cr, 8, 8, S - 16, S - 16, 44)
    g = cairo.LinearGradient(0, 8, 0, S - 8)
    g.add_color_stop_rgb(0, 0.36, 0.63, 0.93)
    g.add_color_stop_rgb(1, 0.10, 0.30, 0.62)
    cr.set_source(g)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 0.55)
    cr.set_line_width(3)
    cr.stroke()
    # The page: a soft shadow, white sheet, red header band.
    x, y, w, h = 40, 46, 176, 166
    rrect(cr, x + 2, y + 6, w, h, 16)
    cr.set_source_rgba(0, 0, 0, 0.30)
    cr.fill()
    rrect(cr, x, y, w, h, 16)
    pg = cairo.LinearGradient(0, y, 0, y + h)
    pg.add_color_stop_rgb(0, 1, 1, 1)
    pg.add_color_stop_rgb(1, 0.91, 0.94, 0.98)
    cr.set_source(pg)
    cr.fill()
    cr.save()
    rrect(cr, x, y, w, h, 16)
    cr.clip()
    hg = cairo.LinearGradient(0, y, 0, y + 44)
    hg.add_color_stop_rgb(0, 0.93, 0.34, 0.30)
    hg.add_color_stop_rgb(1, 0.74, 0.14, 0.15)
    cr.set_source(hg)
    cr.rectangle(x, y, w, 44)
    cr.fill()
    cr.set_source_rgba(1, 1, 1, 0.28)
    cr.rectangle(x, y, w, 20)
    cr.fill()
    cr.restore()
    # Binder rings.
    for rx in (x + 44, x + w - 44):
        rrect(cr, rx - 6, y - 14, 12, 34, 6)
        rg = cairo.LinearGradient(rx - 6, 0, rx + 6, 0)
        rg.add_color_stop_rgb(0, 0.82, 0.85, 0.9)
        rg.add_color_stop_rgb(0.5, 1, 1, 1)
        rg.add_color_stop_rgb(1, 0.7, 0.75, 0.82)
        cr.set_source(rg)
        cr.fill_preserve()
        cr.set_source_rgba(0.2, 0.25, 0.35, 0.55)
        cr.set_line_width(1.5)
        cr.stroke()
    # The month: 5 rows of 7 day cells (drawn as small rounded squares), today in blue.
    gx, gy, cw, ch = x + 11, y + 58, 20, 18
    for r in range(5):
        for c in range(7):
            cx, cy = gx + c * (cw + 2.5), gy + r * (ch + 3)
            today = (r, c) == (2, 3)
            rrect(cr, cx, cy, cw, ch, 4)
            if today:
                tg = cairo.LinearGradient(0, cy, 0, cy + ch)
                tg.add_color_stop_rgb(0, 0.36, 0.63, 0.93)
                tg.add_color_stop_rgb(1, 0.13, 0.40, 0.75)
                cr.set_source(tg)
            else:
                cr.set_source_rgb(0.78, 0.83, 0.90) if c < 5 else cr.set_source_rgb(0.9, 0.72, 0.72)
            cr.fill()
    surf.write_to_png(OUT)


if __name__ == '__main__':
    main()
