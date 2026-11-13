#!/usr/bin/env python3
"""Draws the boot splash's extra art (original, PIL only): the orb's halo and the password box.
Run from the repo root: python3 scripts/gen-boot-art.py. The PNGs are committed; this only documents how they were made."""
from PIL import Image, ImageDraw, ImageFilter
import math, os

OUT = 'distro/desktop/overlay/usr/share/plymouth/themes/mwx7'

# Halo: a soft light-blue radial glow, 480 px, brightest just outside the orb's rim (the orb itself is 200 px).
n = 480
glow = Image.new('RGBA', (n, n))
px = glow.load()
for y in range(n):
    for x in range(n):
        r = math.hypot(x - n / 2, y - n / 2) / (n / 2)
        a = max(0.0, 1 - r) ** 2.2 * 0.85
        px[x, y] = (110, 190, 255, int(a * 255))
glow.save(f'{OUT}/glow.png')

# Password box: frosted glass, 2x supersampled for smooth corners.
w, h, s = 340, 40, 2
box = Image.new('RGBA', (w * s, h * s), (0, 0, 0, 0))
d = ImageDraw.Draw(box)
d.rounded_rectangle((0, 0, w * s - 1, h * s - 1), radius=8 * s, fill=(255, 255, 255, 46), outline=(190, 225, 255, 150), width=s)
d.rounded_rectangle((2 * s, 2 * s, w * s - 3 * s, h * s // 2), radius=6 * s, fill=(255, 255, 255, 30))
box.resize((w, h), Image.LANCZOS).save(f'{OUT}/entry.png')

# Bullet for each typed character.
b = Image.new('RGBA', (28, 28), (0, 0, 0, 0))
ImageDraw.Draw(b).ellipse((8, 8, 19, 19), fill=(235, 246, 255, 255))
b.filter(ImageFilter.GaussianBlur(0.6)).resize((14, 14), Image.LANCZOS).save(f'{OUT}/bullet.png')
