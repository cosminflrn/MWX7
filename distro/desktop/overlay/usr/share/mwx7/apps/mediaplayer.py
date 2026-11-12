"""Media Player (native): the concept's player: your Music folder (and MWX 7's sample music) as a playlist, a spectrum
visualisation from the real audio, shuffle, repeat, seek and volume. GStreamer plays; its spectrum element feeds the
bars."""
import math
import os
import random
import re
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import GLib, Gtk  # noqa: E402
import gi  # noqa: E402

gi.require_version('Gst', '1.0')
from gi.repository import Gst  # noqa: E402

AUDIO = ('.ogg', '.oga', '.mp3', '.flac', '.wav', '.m4a', '.aac', '.opus')
SAMPLES = '/usr/share/mwx7/web/media/music'
BANDS = 48
CSS = """
window.mwx7-mp > box { background: #080d15; }
.mp-stage { background: radial-gradient(circle at 50% 120%, #17345e, #0b1424 55%, #060a12); }
.mp-title { font-size: 20px; font-weight: 300; color: #ffffff; }
.mp-artist { color: #8ea6c6; }
.mp-side { background: linear-gradient(180deg, #0e1623, #080d15); border-left: 1px solid #1d2b42; }
.mp-side-h { padding: 8px 12px; font-weight: 600; color: #9fb7d8; border-bottom: 1px solid #1d2b42;
  background: linear-gradient(180deg, #16233a, #0e1727); }
.mp-side list, .mp-side row { background: transparent; color: #c9d6ea; }
.mp-side row { padding: 5px 10px; border-radius: 4px; }
.mp-side row:selected { background: linear-gradient(180deg, #2c5c9c, #1d4378); color: #ffffff; }
.mp-side row:hover:not(:selected) { background: rgba(120, 160, 220, .12); }
.mp-n { color: #6f86a6; } .mp-it-a { font-size: 11px; color: #7f95b4; }
.mp-bar { padding: 8px 14px 10px; border-top: 1px solid #22344f;
  background: linear-gradient(180deg, rgba(40, 62, 96, .95), rgba(14, 22, 36, .98) 45%, #0a111c); }
.mp-time { color: #9fb7d8; font-feature-settings: "tnum"; }
.mp-bar button { color: #c9d6ea; background: none; border: none; box-shadow: none; border-radius: 999px; padding: 5px; }
.mp-bar button:hover { background: rgba(140, 180, 240, .16); }
.mp-bar button.on { color: #6fc0ff; }
.mp-bar button.mp-play { min-width: 46px; min-height: 46px; padding: 0; border: 1px solid #0b2a52;
  background: radial-gradient(circle at 50% 30%, #9ad3ff, #2f86e0 55%, #0d4f9c); color: #ffffff;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.6), 0 0 12px rgba(60, 150, 255, .45); }
.mp-bar button.mp-play:hover { background: radial-gradient(circle at 50% 30%, #b8e1ff, #47a0f5 55%, #1663b8); }
.mp-bar scale trough { background: #23324a; min-height: 4px; border-radius: 3px; }
.mp-bar scale highlight { background: linear-gradient(90deg, #3f8fe8, #7cc4ff); border-radius: 3px; }
.mp-bar scale slider { min-width: 12px; min-height: 12px; background: radial-gradient(circle at 50% 30%, #fff, #b9d4f0);
  border: 1px solid #2a5a92; border-radius: 999px; margin: 0; }
"""


def nice(path):
    base = os.path.splitext(os.path.basename(path))[0]
    if base.startswith('goldberg-'):
        part = base.removeprefix('goldberg-').replace('-', ' ').title().replace('Da Capo', 'da capo')
        return part, 'Goldberg Variations · Kimiko Ishizaka'
    return base.replace('_', ' '), 'Unknown artist'


def natural(path):
    """Variatio 2 before Variatio 10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', os.path.basename(path))]


def find_tracks(extra=()):
    music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC) or os.path.expanduser('~/Music')
    out = list(extra)
    for folder in (music, SAMPLES):
        for root, _dirs, files in os.walk(folder):
            out += sorted((os.path.join(root, f) for f in files if f.lower().endswith(AUDIO)), key=natural)
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def fmt(ns):
    s = max(0, int(ns / Gst.SECOND)) if ns and ns > 0 else 0
    return f'{s // 60}:{s % 60:02d}'


class Player:
    def __init__(self):
        Gst.init(None)
        self.tracks, self.index, self.shuffle, self.repeat = [], -1, False, 'off'
        self.levels = [0.0] * BANDS
        self.seeking = False
        self.play = Gst.ElementFactory.make('playbin', 'play')
        spec = Gst.ElementFactory.make('spectrum', 'spec')
        if spec:
            spec.set_property('bands', BANDS)
            spec.set_property('threshold', -70)
            spec.set_property('interval', 50_000_000)
            spec.set_property('post-messages', True)
            self.play.set_property('audio-filter', spec)
        self.play.set_property('video-sink', Gst.ElementFactory.make('fakesink', None))
        bus = self.play.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_message)

    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-mp')
        app.on_open = lambda files: self.open_paths([f.get_path() for f in files])
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('Play', [('Play / Pause', 'toggle', self.toggle), ('Previous', 'prev', lambda: self.step(-1)),
                      ('Next', 'next', lambda: self.step(1)), None,
                      ('Shuffle', 'shuffle', lambda: self.shuffle_btn.emit('clicked')),
                      ('Repeat', 'repeat', lambda: self.repeat_btn.emit('clicked'))]),
            ('Library', [('Refresh Music Folder', 'refresh', self.refresh)]),
        ]))
        main = Gtk.Box(vexpand=True)
        stage = Gtk.Overlay(hexpand=True)
        stage.add_css_class('mp-stage')
        self.viz = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.viz.set_draw_func(self.draw)
        stage.set_child(self.viz)
        np = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.END, margin_bottom=16)
        self.title = Gtk.Label(label='Nothing playing', ellipsize=3)
        self.title.add_css_class('mp-title')
        self.artist = Gtk.Label(label='Pick a track from the playlist')
        self.artist.add_css_class('mp-artist')
        np.append(self.title)
        np.append(self.artist)
        stage.add_overlay(np)
        main.append(stage)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.add_css_class('mp-side')
        side.set_size_request(240, -1)
        h = Gtk.Label(label='Playlist', xalign=0)
        h.add_css_class('mp-side-h')
        side.append(h)
        self.list = Gtk.ListBox()
        self.list.connect('row-activated', lambda _l, r: self.select(r.get_index(), True))
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.list)
        side.append(sc)
        main.append(side)
        root.append(main)

        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        bar.add_css_class('mp-bar')
        row = Gtk.Box(spacing=10)
        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1000, 1)
        self.seek.set_hexpand(True)
        self.seek.set_draw_value(False)
        self.seek.connect('change-value', self.on_seek)
        self.time = Gtk.Label(label='0:00 / 0:00')
        self.time.add_css_class('mp-time')
        row.append(self.seek)
        row.append(self.time)
        bar.append(row)
        ctrls = Gtk.CenterBox()
        left = Gtk.Box(spacing=6)
        self.shuffle_btn = self.button('media-playlist-shuffle-symbolic', 'Shuffle', self.on_shuffle)
        self.repeat_btn = self.button('media-playlist-repeat-symbolic', 'Repeat: off', self.on_repeat)
        left.append(self.shuffle_btn)
        left.append(self.repeat_btn)
        mid = Gtk.Box(spacing=10)
        mid.append(self.button('media-skip-backward-symbolic', 'Previous', lambda *_: self.step(-1)))
        self.play_btn = self.button('media-playback-start-symbolic', 'Play', lambda *_: self.toggle())
        self.play_btn.add_css_class('mp-play')
        mid.append(self.play_btn)
        mid.append(self.button('media-skip-forward-symbolic', 'Next', lambda *_: self.step(1)))
        right = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        right.append(Gtk.Image.new_from_icon_name('audio-volume-high-symbolic'))
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.vol.set_size_request(100, -1)
        self.vol.set_draw_value(False)
        self.vol.set_value(50)
        self.vol.connect('value-changed', lambda s: self.play.set_property('volume', (s.get_value() / 100) ** 2))
        self.play.set_property('volume', 0.25)
        right.append(self.vol)
        ctrls.set_start_widget(left)
        ctrls.set_center_widget(mid)
        ctrls.set_end_widget(right)
        bar.append(ctrls)
        root.append(bar)

        self.tracks = find_tracks([f.get_path() for f in app.files])
        self.render_list()
        if app.files:
            GLib.idle_add(lambda: self.select(0, True) and False)
        GLib.timeout_add(250, self.tick)
        GLib.timeout_add(33, self.animate)
        win.connect('close-request', lambda *_: self.play.set_state(Gst.State.NULL) and False)
        return root

    def button(self, icon, tip, fn):
        b = Gtk.Button(icon_name=icon, tooltip_text=tip, focusable=False, valign=Gtk.Align.CENTER)
        b.connect('clicked', fn)
        return b

    # ---- playlist -------------------------------------------------------------------------------------------------
    def render_list(self):
        while (r := self.list.get_row_at_index(0)) is not None:
            self.list.remove(r)
        if not self.tracks:
            self.list.append(Gtk.Label(label='No audio files in your Music folder.', wrap=True))
        for i, p in enumerate(self.tracks):
            t, a = nice(p)
            box = Gtk.Box(spacing=8)
            n = Gtk.Label(label=str(i + 1), width_chars=2, xalign=1)
            n.add_css_class('mp-n')
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            col.append(Gtk.Label(label=t, xalign=0, ellipsize=3))
            al = Gtk.Label(label=a, xalign=0, ellipsize=3)
            al.add_css_class('mp-it-a')
            col.append(al)
            box.append(n)
            box.append(col)
            self.list.append(box)

    def refresh(self):
        cur = self.tracks[self.index] if 0 <= self.index < len(self.tracks) else None
        self.tracks = find_tracks()
        self.render_list()
        self.index = self.tracks.index(cur) if cur in self.tracks else -1

    def open_paths(self, paths):
        for p in reversed(paths):
            if p in self.tracks:
                self.tracks.remove(p)
            self.tracks.insert(0, p)
        self.render_list()
        self.select(0, True)

    def select(self, i, start):
        if not (0 <= i < len(self.tracks)):
            return False
        self.index = i
        p = self.tracks[i]
        t, a = nice(p)
        self.title.set_label(t)
        self.artist.set_label(a)
        self.app.set_title(f'{t} - Media Player')
        self.list.select_row(self.list.get_row_at_index(i))
        self.play.set_state(Gst.State.NULL)
        self.play.set_property('uri', Gst.filename_to_uri(p))
        if start:
            self.play.set_state(Gst.State.PLAYING)
            self.set_playing(True)
        return False

    def step(self, d):
        if not self.tracks:
            return
        if self.shuffle and len(self.tracks) > 1:
            i = random.choice([j for j in range(len(self.tracks)) if j != self.index])
        else:
            i = (self.index + d) % len(self.tracks)
        self.select(i, True)

    def toggle(self):
        if self.index < 0:
            return self.select(0, True) if self.tracks else None
        _ok, state, _p = self.play.get_state(0)
        playing = state == Gst.State.PLAYING
        self.play.set_state(Gst.State.PAUSED if playing else Gst.State.PLAYING)
        self.set_playing(not playing)

    def set_playing(self, on):
        self.play_btn.set_icon_name('media-playback-pause-symbolic' if on else 'media-playback-start-symbolic')
        self.play_btn.set_tooltip_text('Pause' if on else 'Play')

    def on_shuffle(self, b):
        self.shuffle = not self.shuffle
        (b.add_css_class if self.shuffle else b.remove_css_class)('on')

    def on_repeat(self, b):
        self.repeat = {'off': 'all', 'all': 'one', 'one': 'off'}[self.repeat]
        (b.remove_css_class if self.repeat == 'off' else b.add_css_class)('on')
        b.set_icon_name('media-playlist-repeat-song-symbolic' if self.repeat == 'one' else 'media-playlist-repeat-symbolic')
        b.set_tooltip_text(f'Repeat: {self.repeat}')

    # ---- playback -------------------------------------------------------------------------------------------------
    def on_message(self, _bus, msg):
        if msg.type == Gst.MessageType.EOS:
            if self.repeat == 'one':
                self.select(self.index, True)
            elif self.repeat == 'all' or self.shuffle or self.index < len(self.tracks) - 1:
                self.step(1)
            else:
                self.play.set_state(Gst.State.READY)
                self.set_playing(False)
        elif msg.type == Gst.MessageType.ERROR:
            err, _dbg = msg.parse_error()
            self.artist.set_label(f'This file cannot be played ({err.message}).')
            self.set_playing(False)
        elif msg.type == Gst.MessageType.ELEMENT and msg.get_structure().get_name() == 'spectrum':
            st = msg.get_structure()
            mags = st.get_value('magnitude')
            if mags:
                self.levels = [max(0.0, (float(m) + 70) / 70) for m in mags][:BANDS]

    def tick(self):
        ok_d, dur = self.play.query_duration(Gst.Format.TIME)
        ok_p, pos = self.play.query_position(Gst.Format.TIME)
        if ok_d and dur > 0 and ok_p and not self.seeking:
            self.seek.set_value(pos / dur * 1000)
        self.time.set_label(f'{fmt(pos if ok_p else 0)} / {fmt(dur if ok_d else 0)}')
        return True

    def on_seek(self, _s, _scroll, value):
        ok, dur = self.play.query_duration(Gst.Format.TIME)
        if ok and dur > 0:
            self.play.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                                  int(max(0, min(1000, value)) / 1000 * dur))
        return False

    # ---- visualisation --------------------------------------------------------------------------------------------
    def animate(self):
        _ok, state, _p = self.play.get_state(0)
        if state != Gst.State.PLAYING:
            self.levels = [v * 0.85 for v in self.levels]
        if not hasattr(self, 'shown'):
            self.shown = [0.0] * BANDS
        self.shown = [max(lv, s * 0.88) for lv, s in zip(self.levels, self.shown)]
        self.viz.queue_draw()
        return True

    def draw(self, _area, cr, w, h):
        shown = getattr(self, 'shown', [0.0] * BANDS)
        n = len(shown)
        gap = 3
        bw = max(2.0, (w - 40 - gap * (n - 1)) / n)
        base = h * 0.68
        for i, v in enumerate(shown):
            x = 20 + i * (bw + gap)
            bh = v * base * 0.9
            if bh < 1:
                continue
            hue = i / n
            r, g, b = 0.25 + 0.3 * hue, 0.55 + 0.25 * math.sin(hue * math.pi), 1.0
            cr.set_source_rgba(r, g, b, 0.9)
            cr.rectangle(x, base - bh, bw, bh)
            cr.fill()
            # reflection, as on glass
            cr.set_source_rgba(r, g, b, 0.18)
            cr.rectangle(x, base + 2, bw, bh * 0.35)
            cr.fill()


if __name__ == '__main__':
    player = Player()
    mwx7ui.App('org.mwx7.mediaplayer', 'Media Player', 'mediaplayer', (860, 520), CSS, player.build).run_main()
