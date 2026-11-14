#!/usr/bin/env python3
"""Draws the 256px icon of Reader with cairo (original artwork, no external images).
Usage: python3 scripts/gen-reader-icon.py   -> distro/desktop/overlay/usr/share/mwx7/icons/reader.png"""
import os

import cairo

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'distro', 'desktop', 'overlay', 'usr', 'share', 'mwx7',
                   'icons', 'reader.png')
S = 256


def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -1.5708, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
    cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
    cr.arc(x + r, y + r, r, 3.1416, 4.7124)
    cr.close_path()


def main():
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
    cr = cairo.Context(surf)
    # Glossy rounded tile in a deep red (PDF's colour without borrowing anyone's mark).
    rrect(cr, 8, 8, S - 16, S - 16, 44)
    g = cairo.LinearGradient(0, 8, 0, S - 8)
    g.add_color_stop_rgb(0, 0.93, 0.36, 0.30)
    g.add_color_stop_rgb(1, 0.60, 0.09, 0.12)
    cr.set_source(g)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 0.55)
    cr.set_line_width(3)
    cr.stroke()
    # The sheet, with a folded corner and lines of text.
    x, y, w, h, fold = 62, 38, 132, 180, 36
    cr.save()
    cr.translate(3, 5)
    cr.move_to(x, y)
    cr.line_to(x + w - fold, y)
    cr.line_to(x + w, y + fold)
    cr.line_to(x + w, y + h)
    cr.line_to(x, y + h)
    cr.close_path()
    cr.set_source_rgba(0, 0, 0, 0.30)
    cr.fill()
    cr.restore()
    cr.move_to(x, y)
    cr.line_to(x + w - fold, y)
    cr.line_to(x + w, y + fold)
    cr.line_to(x + w, y + h)
    cr.line_to(x, y + h)
    cr.close_path()
    pg = cairo.LinearGradient(x, y, x, y + h)
    pg.add_color_stop_rgb(0, 1, 1, 1)
    pg.add_color_stop_rgb(1, 0.90, 0.92, 0.95)
    cr.set_source(pg)
    cr.fill()
    cr.move_to(x + w - fold, y)
    cr.line_to(x + w - fold, y + fold)
    cr.line_to(x + w, y + fold)
    cr.close_path()
    cr.set_source_rgb(0.78, 0.82, 0.88)
    cr.fill()
    cr.set_source_rgb(0.55, 0.62, 0.72)
    cr.set_line_width(2)
    for i, ln in enumerate((88, 70, 88, 52, 88, 76)):
        cr.move_to(x + 16, y + 74 + i * 18)
        cr.line_to(x + 16 + ln, y + 74 + i * 18)
        cr.stroke()
    # A bookmark ribbon hanging from the top edge.
    cr.move_to(x + 20, y)
    cr.line_to(x + 20, y + 62)
    cr.line_to(x + 33, y + 50)
    cr.line_to(x + 46, y + 62)
    cr.line_to(x + 46, y)
    cr.close_path()
    rg = cairo.LinearGradient(0, y, 0, y + 62)
    rg.add_color_stop_rgb(0, 0.95, 0.40, 0.33)
    rg.add_color_stop_rgb(1, 0.70, 0.12, 0.14)
    cr.set_source(rg)
    cr.fill()
    # Gloss on the upper half of the tile.
    cr.save()
    rrect(cr, 8, 8, S - 16, S - 16, 44)
    cr.clip()
    hl = cairo.LinearGradient(0, 8, 0, 130)
    hl.add_color_stop_rgba(0, 1, 1, 1, 0.38)
    hl.add_color_stop_rgba(1, 1, 1, 1, 0.02)
    cr.set_source(hl)
    cr.rectangle(0, 0, S, 130)
    cr.fill()
    cr.restore()
    surf.write_to_png(OUT)


if __name__ == '__main__':
    main()
