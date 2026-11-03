import type { VFS } from '../../core/types';

/**
 * MWX 7 is session-only, so a fresh boot would show an empty-looking Documents folder.
 * The first Explorer of a session fills in some tasteful content — but only when the user
 * hasn't touched anything yet (Welcome.txt is the sole document).
 */
let seeding: Promise<void> | null = null;

export function seedSamples(fs: VFS): Promise<void> {
  return (seeding ??= run(fs));
}

const NOTES: Record<string, string> = {
  '/Documents/Projects/MWX 7 Roadmap.txt': [
    'MWX 7 — Roadmap',
    '',
    'Now',
    '  - My Computer with a proper navigation pane and details view',
    '  - Window snapping polish',
    '  - Search: find apps and words inside documents',
    '',
    'Next',
    '  - Media viewer with a filmstrip',
    '  - Wallpaper slideshow',
    '  - Jump lists on the dock',
    '',
    'Later',
    '  - Installable build for Linux',
  ].join('\n'),
  '/Documents/Projects/Meeting notes.md': [
    '# Design review',
    '',
    '**Attendees:** Design, Shell, Apps',
    '',
    '## Decisions',
    '- Glass is used for chrome only; content panes stay opaque.',
    '- Icons are rendered at 64 px and scaled down, never the other way round.',
    '- Keyboard shortcuts follow the desktop conventions people already know.',
    '',
    '## Follow-ups',
    '- [ ] Review the sheet animations',
    '- [ ] Audit contrast of selected rows',
  ].join('\n'),
  '/Documents/Recipes.txt': [
    'Lemon & ricotta pasta (serves 2)',
    '',
    '  200 g spaghetti',
    '  150 g fresh ricotta',
    '  1 lemon, zest and juice',
    '  40 g grated parmesan',
    '  olive oil, black pepper, salt',
    '',
    '1. Boil the pasta in well-salted water until just shy of al dente.',
    '2. Whisk the ricotta with the zest, a splash of juice and a ladle of pasta water.',
    '3. Toss everything off the heat. Finish with parmesan, pepper and a thread of olive oil.',
    '',
    'Weekend bread',
    '',
    '  500 g strong flour, 360 g water, 10 g salt, 2 g yeast',
    '  Mix, rest overnight, fold twice, bake at 240 C in a covered pot for 40 minutes.',
  ].join('\n'),
  '/Documents/Ideas for MWX 7.txt': [
    'Ideas for MWX 7',
    '',
    '  * Peek: hover a dock thumbnail to preview the window',
    '  * Preview: double-click a picture in My Computer',
    '  * Stacks: group a folder into a fan above the dock',
    '  * A slow, calm screensaver drawn from the wallpaper palette',
    '  * Sound themes: a quiet one for libraries',
  ].join('\n'),
  '/Music/Playlist.txt': [
    'Evening focus',
    '',
    '  01  Glass Hours',
    '  02  Slow Tide',
    '  03  Lanterns on the Bay',
    '  04  Soft Static',
    '  05  Night Train to Nowhere',
    '  06  Morning Light, Reprise',
  ].join('\n'),
};

// Pointer files for the bundled media (same format Photo Viewer / Media Player seed themselves; apps can't import each other).
const PICS = ['Cliffs and Bay:cliffs-and-bay', 'Alpine Lake:alpine-lake', 'Snowy Peaks and Moon:snowy-peaks-moon', 'Aurora over Snow:aurora-over-snow', 'Coastal Ridge:coastal-ridge', 'White Sand Beach:white-sand-beach'];
const TRACKS = ['Variatio 1:1', 'Variatio 4:4', 'Variatio 5:5'];

async function seedMedia(fs: VFS): Promise<void> {
  const has = async (dir: string, re: RegExp) => (await fs.list(dir)).some((f) => f.type !== 'dir' && re.test(f.name));
  if (!(await has('/Pictures', /\.(jpe?g|png|webp)$/i))) {
    for (const p of PICS) {
      const [name, file] = p.split(':');
      await fs.write(`/Pictures/${name}.jpg`, `mwx-media:media/pictures/${file}.jpg`);
    }
  }
  if (!(await has('/Music', /\.(mp3|ogg|oga|wav|m4a|flac)$/i))) {
    for (const t of TRACKS) {
      const [name, n] = t.split(':');
      await fs.write(`/Music/Goldberg Variations - ${name}.ogg`, `mwx-media:media/music/goldberg-variatio-${n}.ogg`);
    }
  }
}

async function run(fs: VFS): Promise<void> {
  await seedMedia(fs);
  const docs = await fs.list('/Documents');
  if (docs.length !== 1 || docs[0].name !== 'Welcome.txt') return;
  await fs.mkdir('/Documents/Projects');
  for (const [path, text] of Object.entries(NOTES)) await fs.write(path, text);
}
