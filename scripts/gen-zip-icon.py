#!/usr/bin/env python3
"""Draws public/media/icons/zipfolder.png (Explorer's 'Compressed (zipped) folder'): the folder icon with a zipper down
its front. Original artwork drawn here with Pillow on top of our own folder.png.  Usage: python3 scripts/gen-zip-icon.py"""
import os

from PIL import Image, ImageDraw

ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public', 'media', 'icons')
K = 4  # supersampling, for smooth edges
S = 256 * K


def r(*v):
    return [int(x * K) for x in v]


base = Image.open(os.path.join(ICONS, 'folder.png')).convert('RGBA').resize((S, S), Image.LANCZOS)
ov = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(ov)
cx = 128
# zipper track: a dark seam, then interlocking teeth left/right
d.rounded_rectangle(r(cx - 3, 104, cx + 3, 214), radius=2 * K, fill=(120, 84, 24, 255))
y = 108
left = True
while y < 176:
    x0 = cx - 11 if left else cx + 1
    d.rounded_rectangle(r(x0, y, x0 + 10, y + 6), radius=2 * K, fill=(246, 248, 252, 255), outline=(126, 140, 164, 255), width=K)
    y += 8
    left = not left
# pull tab: a slider with a hanging ring, as in the archive icon
d.rounded_rectangle(r(cx - 15, 176, cx + 15, 200), radius=6 * K, fill=(232, 150, 30, 255), outline=(150, 92, 12, 255), width=2 * K)
d.rounded_rectangle(r(cx - 15, 176, cx + 15, 188), radius=6 * K, fill=(252, 196, 96, 255))
d.rounded_rectangle(r(cx - 6, 196, cx + 6, 218), radius=5 * K, outline=(150, 92, 12, 255), width=3 * K)
d.rounded_rectangle(r(cx - 3, 183, cx + 3, 191), radius=2 * K, fill=(120, 70, 8, 255))
out = Image.alpha_composite(base, ov).resize((256, 256), Image.LANCZOS)
out.save(os.path.join(ICONS, 'zipfolder.png'), optimize=True)
