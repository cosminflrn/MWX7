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

Processing: a 22 s window was cut from the 1080p source (meadow: from 8 s at 1.25x speed; sierra: from 14 s at real
speed), scaled/cropped to 1920x1080, 24 fps, H.264 High yuv420p, no audio, two-pass about 2.3 Mbit/s, `+faststart`.
The final 2 s are cross-faded into the first 2 s so the 20 s clip loops with no visible seam (the last frame is the
frame immediately before frame 0 in the source). The `.jpg` posters are frame 0 (quality 85); thumbnails are 320x180.

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

## Icons (`icons/`)

Crystal Clear icon set by Everaldo Coelho (http://www.everaldo.com/), glossy XP-era style. Source mirror:
https://github.com/niko-yanev/crystal-clear. License: GNU LGPL 2.1 or later (full text in `icons/CRYSTAL-CLEAR-LGPL.txt`,
upstream notice in `icons/CRYSTAL-CLEAR-README.txt`). The PNGs are unmodified 128x128 originals; `icons/16/*.png` are the
same artwork downscaled to 32x32 (shown at 16 px). Because the artwork is LGPL, it may be replaced by any user: keep the
file names and swap the PNGs.

Exception: `pinball.png` is from the Tango Icon Theme 0.8.90 (devices/input-gaming), Public Domain (`icons/TANGO-COPYING.txt`,
`icons/TANGO-AUTHORS.txt`).

| File | Crystal Clear icon |
|---|---|
| `notepad` / `text` / `file` | apps/kwrite / minetypes/txt / minetypes/document |
| `calculator`, `paint`, `terminal` | apps/calc, apps/kpaint, apps/terminal |
| `settings`, `about`, `search` | apps/kcontrol, actions/info, actions/filefind |
| `folder`, `folder-music`, `folder-pictures`, `folder-documents` | filesystems/folder, folder_music, folder_image; apps/my_documents |
| `computer`, `explorer`, `drive`, `desktop` | apps/mymac, apps/file-manager, devices/hdd_mount, filesystems/desktop |
| `trash-empty` / `trash-full` | filesystems/trashcan_empty / trashcan_full |
| `user`, `shutdown`, `logoff`, `image` | apps/personal, apps/shutdown, apps/logout, minetypes/image |
| `16/*` | actions/* (button_cancel, editcopy/cut/delete/paste, filenew, edit, reload, find, configure, exit, window_*), apps/(kcontrol, shutdown, logout, background), filesystems/(folder_green, folder_grey_open, trashcan_empty) |

## Font (`../fonts/selawik/`)

Selawik, (c) 2015 Microsoft Corporation, Reserved Font Name "Selawik". Source: https://github.com/microsoft/Selawik
License: SIL Open Font License 1.1 (`fonts/selawik/OFL.txt`).
The repository ships only sources, so the four weights (Light 200, Regular 400, Semibold 600, Bold 700) were built
from `selawik.glyphs` with fontmake (TTF, no autohint) and converted to WOFF2 with fontTools. The sources were not modified; only the build format changed. OFL terms apply: the font may not be sold by itself.

## Music (`music/`)

| File | Title | Performer | Source | License |
|---|---|---|---|---|
| `goldberg-variatio-1.ogg`, `goldberg-variatio-4.ogg`, `goldberg-variatio-5.ogg` | J.S. Bach, Goldberg Variations BWV 988: Variatio 1, 4 and 5 (from "The Open Goldberg Variations") | Kimiko Ishizaka | https://archive.org/details/OpenGoldbergVariations | CC0 1.0 (public domain dedication) |

Unmodified copies of the Ogg Vorbis files published by the project.

## VGA bitmap font (`../fonts/vga/`)

"Web437 IBM VGA 8x16" (`WebPlus_IBM_VGA_8x16.woff`, a.k.a. Px437 IBM VGA 8x16) from The Ultimate Oldschool PC Font Pack v2.2 by VileR, (c) 2016-2020. Source: https://int10h.org/oldschool-pc-fonts/ (WOFF taken from the npm package `@monowind/themes` 0.3.5, unmodified).
License: Creative Commons Attribution-ShareAlike 4.0 (`fonts/vga/LICENSE-CC-BY-SA-4.0.txt`). Used by MWX Commander and the BIOS screen.

## UI click (`sounds/click.ogg`, `sounds/click.mp3`)

`mouseclick1.wav` from "UI SFX Set" by Kenney Vleugels (Kenney.nl), https://kenney.nl (mirror: https://github.com/Calinou/kenney-ui-audio). License: CC0 1.0 (public domain). A real mouse button press/release recording; here converted to mono, high-passed at 80 Hz, loudness-normalised and trimmed to 77 ms, then encoded to Ogg Vorbis and MP3.
