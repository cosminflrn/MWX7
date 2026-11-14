#!/usr/bin/env python3
"""Draws the 256px Terminal icon with cairo (original artwork) -> public/media/icons/terminal.png.
Usage: python3 scripts/gen-terminal-icon.py"""
import math
import os

import cairo

S = 256
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public', 'media', 'icons', 'terminal.png')


def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    for cx, cy, a in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        cr.arc(cx, cy, r, math.radians(a), math.radians(a + 90))
    cr.close_path()


s = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
cr = cairo.Context(s)
# Soft shadow
for i in range(8):
    rrect(cr, 12 - i * .5, 18 - i * .5 + 4, S - 24 + i, S - 36 + i, 40)
    cr.set_source_rgba(0, 0, 0, .035)
    cr.fill()
# Glossy navy tile, like the other app icons
rrect(cr, 8, 8, S - 16, S - 16, 44)
g = cairo.LinearGradient(0, 8, 0, S - 8)
g.add_color_stop_rgb(0, .16, .27, .45)
g.add_color_stop_rgb(1, .04, .09, .17)
cr.set_source(g)
cr.fill_preserve()
cr.set_source_rgba(1, 1, 1, .55)
cr.set_line_width(3)
cr.stroke()
cr.save()
rrect(cr, 8, 8, S - 16, S - 16, 44)
cr.clip()
hl = cairo.LinearGradient(0, 8, 0, 130)
hl.add_color_stop_rgba(0, 1, 1, 1, .38)
hl.add_color_stop_rgba(1, 1, 1, 1, .02)
cr.set_source(hl)
cr.rectangle(0, 0, S, 130)
cr.fill()
cr.restore()
# Title bar strip with three dots
cr.set_source_rgba(1, 1, 1, .12)
rrect(cr, 30, 34, S - 60, 26, 8)
cr.fill()
for i, c in enumerate(((.93, .38, .41), (.9, .75, .4), (.37, .79, .54))):
    cr.set_source_rgb(*c)
    cr.arc(46 + i * 20, 47, 6, 0, math.tau)
    cr.fill()
# Prompt chevron ">" and underscore cursor in the accent blue
cr.set_line_cap(cairo.LINE_CAP_ROUND)
cr.set_line_join(cairo.LINE_JOIN_ROUND)
cr.set_line_width(20)
cr.set_source_rgb(.43, .69, 1)
cr.move_to(66, 100)
cr.line_to(110, 138)
cr.line_to(66, 176)
cr.stroke()
cr.set_source_rgb(.86, .91, .96)
cr.move_to(128, 182)
cr.line_to(190, 182)
cr.stroke()
s.write_to_png(OUT)
print(os.path.normpath(OUT))
