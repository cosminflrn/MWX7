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

Oxygen icon theme, (c) 2007 Nuno Pinheiro, David Vignoni, David Miller, Johann Ollivier Lapeyre, Kenneth Wimer,
Riccardo Iaconelli and the Oxygen Team. Source: https://github.com/KDE/oxygen-icons (commit 48f4538).
License: LGPL-3.0-or-later (full text in `icons/LICENSE-LGPL-3.0.txt`; upstream `COPYING.txt` and `AUTHORS.txt`
are included alongside). The icons are unmodified apart from rasterisation to 256x256 PNG (SVG sources were rendered
with resvg) and 256-colour quantisation for the folder icons to keep them small.

| File | Oxygen icon |
|---|---|
| `notepad.png` | apps/accessories-text-editor |
| `calculator.png` | apps/accessories-calculator |
| `terminal.png` | apps/utilities-terminal |
| `settings.png` | categories/preferences-system |
| `about.png` | status/dialog-information |
| `folder.png` | mimetypes/inode-directory |
| `folder-documents.png` | places/folder-documents |
| `folder-pictures.png` | places/folder-pictures |
| `folder-music.png` | places/folder-music |
| `computer.png` | devices/computer |
| `trash-empty.png` | places/user-trash |
| `trash-full.png` | places/user-trash-full |
| `search.png` | apps/preferences-desktop-search (binoculars) |
| `user.png` | places/user-identity |
| `explorer.png` | apps/system-file-manager |
| `shutdown.png` | actions/system-shutdown |
| `logoff.png` | actions/system-log-out |

## Font (`../fonts/selawik/`)

Selawik, (c) 2015 Microsoft Corporation, Reserved Font Name "Selawik". Source: https://github.com/microsoft/Selawik
License: SIL Open Font License 1.1 (`fonts/selawik/OFL.txt`).
The repository ships only sources, so the four weights (Light 200, Regular 400, Semibold 600, Bold 700) were built
from `selawik.glyphs` with fontmake (TTF, no autohint) and converted to WOFF2 with fontTools. The sources were not modified; only the build format changed. OFL terms apply: the font may not be sold by itself.
