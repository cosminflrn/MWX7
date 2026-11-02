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

Tango Icon Theme 0.8.90 (warm, glossy 2005-era style), by Ulisse Perusin, Steven Garrity, Lapo Calamandrei, Ryan Collier,
Rodney Dawes, Andreas Nilsson, Tuomas Kuosmanen, Garrett LeSage and Jakub Steiner (the Tango Desktop Project).
Source: https://tango.freedesktop.org/releases/tango-icon-theme-0.8.90.tar.gz
License: Public Domain (upstream `COPYING` and `AUTHORS` are included as `icons/TANGO-COPYING.txt` and
`icons/TANGO-AUTHORS.txt`).

Processing: SVGs rendered to 256x256 PNG with cairosvg; `folder-documents/pictures/music` are the Tango folder with a
small Tango document / film / music-note icon composited on the front. The 32x32 menu icons in `icons/16/` are Tango's
own hand-hinted 32x32 PNGs where they exist (otherwise the SVG rendered at 32 px).

| File | Tango icon |
|---|---|
| `notepad.png` | apps/accessories-text-editor |
| `calculator.png` | apps/accessories-calculator |
| `terminal.png` | apps/utilities-terminal |
| `settings.png` | categories/preferences-system |
| `about.png` | apps/help-browser |
| `folder.png` | places/folder |
| `folder-documents.png` / `folder-pictures.png` / `folder-music.png` | places/folder + mimetypes/text-x-generic / emblems/emblem-photos / mimetypes/audio-x-generic |
| `computer.png`, `explorer.png` | devices/computer |
| `trash-empty.png` / `trash-full.png` | places/user-trash / status/user-trash-full |
| `search.png` | actions/system-search |
| `user.png` | apps/system-users |
| `shutdown.png` / `logoff.png` | actions/system-shutdown / actions/system-log-out |
| `paint.png` | categories/applications-graphics |
| `pinball.png` | devices/input-gaming |
| `desktop.png` | places/user-desktop |
| `file.png` / `text.png` / `image.png` | mimetypes/text-x-generic-template / text-x-generic / image-x-generic |
| `drive.png` | devices/drive-harddisk |
| `16/*.png` | actions/* (document-open, edit-cut/copy/paste/delete, document-save-as, folder-new, document-new, document-properties, view-refresh, process-stop, go-bottom, view-fullscreen, go-up, system-*), apps/preferences-desktop-wallpaper, status/dialog-information, places/user-trash |

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
