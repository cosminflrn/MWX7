# Media credits and licenses

All media in `public/media/` and `public/fonts/` is third-party material under a license that permits free use and
redistribution (including in a future Linux distribution). No Microsoft or Apple artwork is used.

Pexels files: the Pexels License (https://www.pexels.com/license/) allows free use and modification without
attribution. Contributor names could not be retrieved automatically (pexels.com pages are closed to automated
fetching), so the author is listed as "Pexels contributor"; the page URL identifies the work.

## Wallpaper videos (`wallpapers/`)

| File | Title | Author | Source | License |
|---|---|---|---|---|
| `meadow.mp4`, `meadow.jpg`, `meadow-thumb.jpg` | "Scenery of Relaxing Farm Field During Daytime" (Pexels video 4471213) | Pexels contributor | https://www.pexels.com/video/scenery-of-relaxing-farm-field-during-daytime-4471213/ | Pexels License |
| `sierra.mp4`, `sierra.jpg`, `sierra-thumb.jpg` | "Clouds Moving over Mountains" (Pexels video 14372030) | Pexels contributor | https://www.pexels.com/video/clouds-moving-over-mountains-14372030/ | Pexels License |

Processing: a 22 s window was cut from the 1080p source (meadow: `meadow-hd.mp4` 2560x1440 (served on large screens) and `meadow.mp4` 1920x1080, from 8 s at 1.25x speed; sierra: from 14 s at real
speed), scaled/cropped to 1920x1080, 24 fps, H.264 High yuv420p, no audio, two-pass about 2.3 Mbit/s, `+faststart`.
The final 2 s are cross-faded into the first 2 s so the 20 s clip loops with no visible seam (the last frame is the
frame immediately before frame 0 in the source). The `.jpg` posters are frame 0 (quality 85); thumbnails are 320x180.

Sierra re-cut: the original window had a slow camera pan in its first ~10 s (about 55 px at 1920 wide, measured by phase correlation on the bottom half) and a pan back at its end. The shipped clip is the zero-camera-motion stretch (13-37 s of that window, re-encoded at CRF 18, 30 fps), 24 s, with a 2 s cross-fade at the seam; the poster/thumbnail are its frame 0 so poster and video match exactly.

Notes: `meadow` is a static-camera shot of a gently rolling green barley field under blue sky with white clouds and
wind-moved grass (real time, not a true time-lapse, so cloud drift is slow). `sierra` is an alpine peak (Machapuchare
massif, Nepal Himalaya) with fast-moving clouds, not the Sierra Nevada. Both file names are fixed by the OS spec.

## User avatars (`avatars/`)

256x256 JPEG, square-cropped on the subject, quality 88, mild unsharp mask. All Pexels License, Pexels contributor.

| File | Title (as on Pexels) | Source |
|---|---|---|
| `01-flower.jpg` | Close Up Shot of a Red Poppy Flower | https://www.pexels.com/photo/14918574/ |
| `02-goldfish.jpg` | Close-up Photo of a Goldfish Swimming Underwater | https://www.pexels.com/photo/13831047/ |
| `03-guitar.jpg` | Close-Up Shot of a Brown Acoustic Guitar | https://www.pexels.com/photo/9057760/ |
| `04-chess.jpg` | Chess Pieces in Close-up Shot | https://www.pexels.com/photo/12989478/ |
| `05-soccer.jpg` | A Soccer Ball on a Grass Field | https://www.pexels.com/photo/16493254/ |
| `06-dog.jpg` | Golden Retriever Portrait against Blue Background | https://www.pexels.com/photo/35439661/ |
| `07-cat.jpg` | Portrait of a Cat | https://www.pexels.com/photo/14355838/ |
| `08-butterfly.jpg` | Close Up Photo of Monarch Butterfly on Top of Flower | https://www.pexels.com/photo/1046287/ |
| `09-airplane.jpg` | Plane In The Sky | https://www.pexels.com/photo/967103/ |
| `10-snowboard.jpg` | Man in Snowboard Jumping on Ramp | https://www.pexels.com/photo/1635086/ |
| `11-beach.jpg` | Beautiful Tropical Beach with Palm Trees and Turquoise Water | https://www.pexels.com/photo/12858509/ |
| `12-horse.jpg` | Close-up Photo of Brown Horse | https://www.pexels.com/photo/1730760/ |

## Power-on photo (`boot/`)

| File | Title | Author | Source | License |
|---|---|---|---|---|
| `boot/pc-crt.jpg` | "Vintage Desktop Computer With Monitor and Keyboard" (Pexels photo 37148217) | Pexels contributor | https://www.pexels.com/photo/vintage-desktop-computer-with-monitor-and-keyboard-37148217/ | Pexels License |

Processing: 1920x1280 download, the small Apple logo, the model label and the "PowerPC" mark on the tower front were retouched out (filled with the surrounding beige), re-encoded as progressive JPEG quality 84. The CRT glass, power-switch hit area and LED are overlays in `src/shell/screens.ts`.

## Icons (`icons/`)

Original artwork by MWX 7 (including `snip.png`), drawn as SVG (glossy blue / silver / manila palette, top lighting) and exported to PNG:
256x256 for `icons/*.png` (shown at 128 px or less), 32x32 for `icons/16/*.png` (shown at 16 px). No third-party artwork except
`pinball.png` (below) and `explorer.png`, kept from the earlier set. Replace any PNG by keeping its file name.

`explorer.png`: Crystal Clear (apps/display) by Everaldo Coelho, http://www.everaldo.com/, GNU LGPL 2.1 or later
(`icons/CRYSTAL-CLEAR-LGPL.txt`, `icons/CRYSTAL-CLEAR-README.txt`), unmodified 128x128 original.

`pinball.png` is from the Tango Icon Theme 0.8.90 (devices/input-gaming), Public Domain (`icons/TANGO-COPYING.txt`,
`icons/TANGO-AUTHORS.txt`).

## Font (`../fonts/selawik/`)

Selawik, (c) 2015 Microsoft Corporation, Reserved Font Name "Selawik". Source: https://github.com/microsoft/Selawik
License: SIL Open Font License 1.1 (`fonts/selawik/OFL.txt`).
The repository ships only sources, so the four weights (Light 200, Regular 400, Semibold 600, Bold 700) were built
from `selawik.glyphs` with fontmake (TTF, no autohint) and converted to WOFF2 with fontTools. The sources were not modified; only the build format changed. OFL terms apply: the font may not be sold by itself.

## Music (`music/`)

| File | Title | Performer | Source | License |
|---|---|---|---|---|
| `goldberg-variatio-1.ogg`, `goldberg-variatio-4.ogg`, `goldberg-variatio-5.ogg` | J.S. Bach, Goldberg Variations BWV 988: Variatio 1, 4 and 5 (from "The Open Goldberg Variations") | Kimiko Ishizaka | https://archive.org/details/OpenGoldbergVariations | CC0 1.0 (public domain dedication) |
| `goldberg-variatio-2.ogg`, `goldberg-variatio-6.ogg`, `goldberg-variatio-8.ogg`, `goldberg-variatio-10.ogg`, `goldberg-variatio-18.ogg` | J.S. Bach, Goldberg Variations BWV 988: Variatio 2, 6 (Canone alla Seconda), 8, 10 (Fughetta) and 18 (Canone alla Sexta), from "The Open Goldberg Variations", unmodified Ogg Vorbis from the archive | Kimiko Ishizaka (piano) | https://archive.org/details/OpenGoldbergVariations | CC0 1.0 |
| `goldberg-aria-da-capo.ogg` | J.S. Bach, Goldberg Variations BWV 988: Aria da Capo e Fine (Open Goldberg Variations), background music of the Welcome tour | Kimiko Ishizaka (piano) | https://archive.org/details/OpenGoldbergVariations | CC0 1.0 |

Unmodified copies of the Ogg Vorbis files published by the project.

| File | Title | Performer | Source | License |
|---|---|---|---|---|
| `solitaire-goldberg-variatio-3.ogg` | J.S. Bach, Goldberg Variations BWV 988: Variatio 3 (Canone all'Unisuono) | Kimiko Ishizaka | https://archive.org/details/OpenGoldbergVariations | CC0 1.0 |
| `mines-goldberg-variatio-12.ogg` | J.S. Bach, Goldberg Variations BWV 988: Variatio 12 (Canone alla Quarta) | Kimiko Ishizaka | https://archive.org/details/OpenGoldbergVariations | CC0 1.0 |

Game-music loops (Solitaire, Mines): the last 4 s of the recording are cross-faded into the first 4 s and the piece is re-encoded (Ogg Vorbis, quality 2.5-3), so the file loops without a gap. Played with a looping `<audio>`.

## VGA bitmap font (`../fonts/vga/`)

"Web437 IBM VGA 8x16" (`WebPlus_IBM_VGA_8x16.woff`, a.k.a. Px437 IBM VGA 8x16) from The Ultimate Oldschool PC Font Pack v2.2 by VileR, (c) 2016-2020. Source: https://int10h.org/oldschool-pc-fonts/ (WOFF taken from the npm package `@monowind/themes` 0.3.5, unmodified).
License: Creative Commons Attribution-ShareAlike 4.0 (`fonts/vga/LICENSE-CC-BY-SA-4.0.txt`). Used by MWX Commander and the BIOS screen.

## UI sounds (`sounds/click.*`, `sounds/switch.*`)

Both from "UI Audio" by Kenney Vleugels (Kenney.nl), https://kenney.nl (mirror: https://github.com/Calinou/kenney-ui-audio). License: CC0 1.0 (public domain). Chosen by waveform analysis (duration, attack, spectral centroid, energy above 6 kHz), converted to mono, high-passed, trimmed, level-matched (RMS about -23 dBFS for the click) and encoded to Ogg Vorbis and MP3.

| File | Source sample | Use |
|---|---|---|
| `click.ogg`, `click.mp3` | `click4.wav` (22 ms press tick, 8 ms attack, spectral centroid 3.6 kHz, 40% of energy in 2-5 kHz) plus `click5.wav` (16 ms, quieter) as the release tick 70 ms later, mixed, high-passed at 500 Hz, mono | Mouse click / right click (microswitch tick) |
| `switch.ogg`, `switch.mp3` | `switch32.wav` (heavy mechanical switch, 64% energy below 1.5 kHz), 240 ms | Power-on screen switch "clunk" |

The start-up fan / hard-disk hum and the POST beep are synthesized in `src/core/sound.ts` (no third-party material).

## Sample pictures (`pictures/`)

Landscape photographs seeded into `/Pictures` for Photo Viewer. Pexels License (https://www.pexels.com/license/): free use and redistribution, no attribution required. Pexels contributor names could not be retrieved automatically; the photo id identifies the work. Processing: resized to 1600 px wide, metadata stripped, progressive JPEG quality 80 (all under 300 KB).

| File | Pexels photo id |
|---|---|
| `cliffs-and-bay.jpg` | 462162 |
| `alpine-lake.jpg` | 2662116 |
| `snowy-peaks-moon.jpg` | 1287145 |
| `aurora-over-snow.jpg` | 3408744 |
| `coastal-ridge.jpg` | 2559941 |
| `white-sand-beach.jpg` | 1450353 |

Source URL pattern: `https://www.pexels.com/photo/<id>/`.

Media Player album art is generated in code (original SVG, no third-party artwork).
