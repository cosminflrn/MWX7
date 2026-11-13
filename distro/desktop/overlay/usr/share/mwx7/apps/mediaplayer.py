"""Media Player (native), after Windows Media Player 12: a Library (Music and Videos, grouped by album with cover art from the
files' tags or a folder.jpg), a Now Playing view (spectrum from the real audio, cover or the video itself, the queue),
transport, seek, volume, shuffle, repeat, drag and drop, and MPRIS so media keys and `playerctl` can drive it.
GStreamer plays and reads the tags; nothing else is needed."""
import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk  # noqa: E402
import gi  # noqa: E402

gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf, Gst, GstPbutils  # noqa: E402

AUDIO = ('.ogg', '.oga', '.mp3', '.flac', '.wav', '.m4a', '.aac', '.opus', '.wma')
VIDEO = ('.mp4', '.m4v', '.mkv', '.webm', '.avi', '.mov', '.ogv')
SAMPLES = '/usr/share/mwx7/web/media/music'
COVERS = ('folder', 'cover', 'front', 'albumart', 'album')
BANDS = 36  # bars drawn
SPEC = 256  # linear bands GStreamer measures; bars group them logarithmically, as hearing does
EDGES = [0]
for _i in range(1, BANDS + 1):  # at least one measured band per bar, log-spaced above that
    EDGES.append(min(SPEC, max(EDGES[-1] + 1, int(SPEC ** (_i / BANDS)))))
CONFIG = os.path.join(GLib.get_user_config_dir(), 'mwx7', 'mediaplayer.json')
CACHE = os.path.join(GLib.get_user_cache_dir(), 'mwx7', 'mediaplayer')
LIBRARY_TAB = 'library'
NOW_TAB = 'now'

CSS = """
window.mwx7-mp > box { background: #080d15; }
.mp-nav { padding: 6px 10px; border-bottom: 1px solid #1d2b42;
  background: linear-gradient(180deg, #1a2a45, #0f192b); }
.mp-nav button { color: #c9d6ea; background: none; border: 1px solid transparent; box-shadow: none; padding: 3px 14px;
  border-radius: 4px; min-height: 0; }
.mp-nav button:hover { background: rgba(140, 180, 240, .14); border-color: rgba(140, 180, 240, .25); }
.mp-nav button.tab-on { color: #fff; border-color: #3b6aa8; background: linear-gradient(180deg, #2f5f9e, #1d4378); }
.mp-nav entry { min-height: 0; padding: 2px 8px; background: #0a111c; color: #c9d6ea; border: 1px solid #263a58;
  border-radius: 4px; box-shadow: none; }
.mp-nav entry image { color: #6f86a6; }
.mp-nav-side { background: linear-gradient(180deg, #0e1623, #080d15); border-right: 1px solid #1d2b42; }
.mp-nav-side list { background: transparent; }
.mp-nav-side row { padding: 7px 14px; color: #c9d6ea; border-radius: 4px; margin: 1px 6px; }
.mp-nav-side row:selected { background: linear-gradient(180deg, #2c5c9c, #1d4378); color: #fff; }
.mp-nav-side row:hover:not(:selected) { background: rgba(120, 160, 220, .12); }
.mp-nav-side .mp-cap { padding: 10px 14px 4px; color: #6f86a6; font-size: 11px; font-weight: 600; }
.mp-count { color: #7f95b4; font-size: 11px; }
.mp-lib, .mp-lib row { background: transparent; color: #c9d6ea; }
.mp-lib row.mp-track { padding: 4px 14px; border-radius: 0; }
.mp-lib row.mp-track:hover { background: rgba(120, 160, 220, .10); }
.mp-lib row.mp-track:selected { background: linear-gradient(180deg, #2c5c9c, #1d4378); color: #fff; }
.mp-lib row.mp-track.mp-playing label.mp-t { color: #6fc0ff; font-weight: 600; }
.mp-lib row.mp-head { padding: 14px 14px 6px; }
.mp-album { font-size: 16px; font-weight: 300; color: #fff; }
.mp-album-sub { color: #8ea6c6; }
.mp-lib row.mp-head button { color: #c9d6ea; background: rgba(140, 180, 240, .12); border: 1px solid #2a4468;
  box-shadow: none; border-radius: 4px; padding: 2px 12px; min-height: 0; }
.mp-lib row.mp-head button:hover { background: rgba(140, 180, 240, .24); }
.mp-empty { color: #8ea6c6; padding: 40px; }
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
.mp-bar scale trough { border: none; outline: none; background: #23324a; min-height: 4px; border-radius: 3px; }
.mp-bar scale highlight { background: linear-gradient(90deg, #3f8fe8, #7cc4ff); border-radius: 3px; }
.mp-bar scale slider { min-width: 12px; min-height: 12px; background: radial-gradient(circle at 50% 30%, #fff, #b9d4f0);
  border: 1px solid #2a5a92; border-radius: 999px; margin: 0; }
window.mwx7-mp.mp-drop > box { box-shadow: inset 0 0 0 3px #3f8fe8; }
"""

MPRIS_XML = """<node>
<interface name='org.mpris.MediaPlayer2'>
  <method name='Raise'/><method name='Quit'/>
  <property name='CanQuit' type='b' access='read'/><property name='CanRaise' type='b' access='read'/>
  <property name='HasTrackList' type='b' access='read'/><property name='Identity' type='s' access='read'/>
  <property name='DesktopEntry' type='s' access='read'/>
  <property name='SupportedUriSchemes' type='as' access='read'/><property name='SupportedMimeTypes' type='as' access='read'/>
</interface>
<interface name='org.mpris.MediaPlayer2.Player'>
  <method name='Next'/><method name='Previous'/><method name='Pause'/><method name='PlayPause'/><method name='Stop'/>
  <method name='Play'/><method name='Seek'><arg direction='in' name='Offset' type='x'/></method>
  <method name='SetPosition'><arg direction='in' name='TrackId' type='o'/><arg direction='in' name='Position' type='x'/></method>
  <method name='OpenUri'><arg direction='in' name='Uri' type='s'/></method>
  <signal name='Seeked'><arg name='Position' type='x'/></signal>
  <property name='PlaybackStatus' type='s' access='read'/><property name='LoopStatus' type='s' access='readwrite'/>
  <property name='Rate' type='d' access='readwrite'/><property name='Shuffle' type='b' access='readwrite'/>
  <property name='Metadata' type='a{sv}' access='read'/><property name='Volume' type='d' access='readwrite'/>
  <property name='Position' type='x' access='read'/><property name='MinimumRate' type='d' access='read'/>
  <property name='MaximumRate' type='d' access='read'/><property name='CanGoNext' type='b' access='read'/>
  <property name='CanGoPrevious' type='b' access='read'/><property name='CanPlay' type='b' access='read'/>
  <property name='CanPause' type='b' access='read'/><property name='CanSeek' type='b' access='read'/>
  <property name='CanControl' type='b' access='read'/>
</interface></node>"""
MPRIS_PATH = '/org/mpris/MediaPlayer2'
MPRIS_ROOT, MPRIS_PLAYER = 'org.mpris.MediaPlayer2', 'org.mpris.MediaPlayer2.Player'


# ---- library data -------------------------------------------------------------------------------------------------------
def natural(path):
    """Variatio 2 before Variatio 10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', os.path.basename(path))]


def fallback_names(path):
    """Title, artist, album for a file whose tags say nothing."""
    base = os.path.splitext(os.path.basename(path))[0]
    if 'goldberg-' in base:
        part = base.split('goldberg-', 1)[1].replace('-', ' ').title().replace('Da Capo', 'da capo')
        return part, 'Kimiko Ishizaka', 'Goldberg Variations'
    folder = os.path.basename(os.path.dirname(path))
    music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC) or ''
    album = '' if os.path.dirname(path) in (music, os.path.expanduser('~')) else folder
    return base.replace('_', ' '), 'Unknown artist', album or 'Unknown album'


def fmt(ns):
    s = max(0, int(ns / Gst.SECOND)) if ns and ns > 0 else 0
    return f'{s // 60}:{s % 60:02d}'


def folder_cover(folder, memo):
    if folder not in memo:
        memo[folder] = None
        try:
            names = {n.lower(): n for n in os.listdir(folder)}
        except OSError:
            names = {}
        for stem in COVERS:
            for ext in ('.jpg', '.jpeg', '.png'):
                if stem + ext in names:
                    memo[folder] = os.path.join(folder, names[stem + ext])
                    break
            if memo[folder]:
                break
    return memo[folder]


def probe(disc, path, memo):
    """One file's tags and length, as a dict. Runs in the scanner thread."""
    title, artist, album = fallback_names(path)
    t = {'path': path, 'kind': 'video' if path.lower().endswith(VIDEO) else 'audio', 'title': title, 'artist': artist,
         'album': album, 'track': 0, 'dur': 0, 'art': None, 'year': ''}
    try:
        info = disc.discover_uri(Gst.filename_to_uri(path))
    except GLib.Error:
        return t
    t['dur'] = info.get_duration() or 0
    tags = info.get_tags()
    if tags:
        for key, tag in (('title', 'title'), ('artist', 'artist'), ('album', 'album')):
            ok, val = tags.get_string(tag)
            if ok and val.strip():
                t[key] = val.strip()
        ok, n = tags.get_uint('track-number')
        t['track'] = n if ok else 0
        ok, dt = tags.get_date_time('datetime')
        if ok and dt and dt.has_year():
            t['year'] = str(dt.get_year())
        for tag in ('image', 'preview-image'):
            ok, sample = tags.get_sample(tag)
            if ok and sample and sample.get_buffer():
                buf = sample.get_buffer()
                data = buf.extract_dup(0, buf.get_size())
                dest = os.path.join(CACHE, hashlib.sha1(data).hexdigest() + '.img')
                if not os.path.exists(dest):
                    with open(dest, 'wb') as f:
                        f.write(data)
                t['art'] = dest
                break
    if not t['art'] and t['kind'] == 'audio':
        t['art'] = folder_cover(os.path.dirname(path), memo)
    return t


def walk(folders, exts):
    out = []
    for folder in folders:
        for root, _dirs, files in os.walk(folder):
            out += [os.path.join(root, f) for f in files if f.lower().endswith(exts)]
    return list(dict.fromkeys(out))


_pix = {}


def pixbuf(path, size):
    key = (path, size)
    if key not in _pix:
        try:
            _pix[key] = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size * 2, size * 2, True)
        except GLib.Error:
            _pix[key] = None
    return _pix[key]


class Art(Gtk.DrawingArea):
    """Cover art, or a drawn note / film frame when there is none."""

    def __init__(self, size):
        super().__init__(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.size, self.path, self.kind = size, None, 'audio'
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_draw_func(self.draw)

    def set_art(self, path, kind='audio'):
        if (path, kind) != (self.path, self.kind):
            self.path, self.kind = path, kind
            self.queue_draw()

    def draw(self, _a, cr, w, h):
        r = max(3, w / 14)
        cr.new_sub_path()
        cr.arc(w - r, r, r, -math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0, math.pi / 2)
        cr.arc(r, h - r, r, math.pi / 2, math.pi)
        cr.arc(r, r, r, math.pi, 1.5 * math.pi)
        cr.close_path()
        cr.clip_preserve()
        pb = pixbuf(self.path, self.size) if self.path else None
        if pb:
            pw, ph = pb.get_width(), pb.get_height()
            s = max(w / pw, h / ph)
            cr.save()
            cr.translate((w - pw * s) / 2, (h - ph * s) / 2)
            cr.scale(s, s)
            Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
            cr.paint()
            cr.restore()
        else:
            import cairo
            g = cairo.LinearGradient(0, 0, w, h)
            g.add_color_stop_rgb(0, 0.20, 0.36, 0.60)
            g.add_color_stop_rgb(1, 0.07, 0.14, 0.27)
            cr.set_source(g)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.78)
            if self.kind == 'video':
                cr.move_to(w * .38, h * .30)
                cr.line_to(w * .72, h * .5)
                cr.line_to(w * .38, h * .70)
                cr.close_path()
                cr.fill()
            else:
                cr.set_line_width(max(2, w * .055))
                cr.arc(w * .36, h * .70, w * .11, 0, 2 * math.pi)
                cr.fill()
                cr.move_to(w * .46, h * .70)
                cr.line_to(w * .46, h * .26)
                cr.line_to(w * .70, h * .32)
                cr.line_to(w * .70, h * .40)
                cr.line_to(w * .46, h * .34)
                cr.stroke()
        cr.reset_clip()
        cr.new_path()
        cr.set_source_rgba(1, 1, 1, 0.12)
        cr.set_line_width(1)
        cr.rectangle(.5, .5, w - 1, h - 1)
        cr.stroke()


class Player:
    def __init__(self):
        Gst.init(None)
        self.cfg = {'volume': 50, 'shuffle': False, 'repeat': 'off', 'folder': None, 'view': 'Music', 'tab': LIBRARY_TAB}
        try:
            with open(CONFIG) as f:
                self.cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
        self.library, self.queue, self.cur, self.index = [], [], None, -1
        self.shuffle, self.repeat = bool(self.cfg['shuffle']), self.cfg['repeat'] if self.cfg['repeat'] in (
            'off', 'all', 'one') else 'off'
        self.levels, self.shown = [0.0] * BANDS, [0.0] * BANDS
        self.history, self.hold_until, self.playing, self.scanning = [], 0.0, False, False
        self.search, self.mute = '', False
        self.conn = None
        self.play = Gst.ElementFactory.make('playbin', 'play')
        spec = Gst.ElementFactory.make('spectrum', 'spec')
        if spec:
            spec.set_property('bands', SPEC)
            spec.set_property('threshold', -70)
            spec.set_property('interval', 50_000_000)
            spec.set_property('post-messages', True)
            self.play.set_property('audio-filter', spec)
        # The video lands in a Gtk.Paintable inside the window; without that plugin videos play as sound only.
        self.vsink = Gst.ElementFactory.make('gtk4paintablesink', None)
        self.play.set_property('video-sink', self.vsink or Gst.ElementFactory.make('fakesink', None))
        if os.environ.get('MWX7_MP_FAKE_AUDIO'):  # headless checks: there is no sound card in a container
            fake = Gst.ElementFactory.make('fakesink', None)
            fake.set_property('sync', True)
            self.play.set_property('audio-sink', fake)
        bus = self.play.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_message)

    def save(self):
        self.cfg.update(shuffle=self.shuffle, repeat=self.repeat, volume=round(self.vol.get_value()))
        try:
            os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
            with open(CONFIG, 'w') as f:
                json.dump(self.cfg, f)
        except OSError:
            pass

    # ---- window ---------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-mp')
        app.on_open = lambda files: self.open_paths([f.get_path() for f in files if f.get_path()])
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('File', [('Open...', 'open', self.open_dialog)]),
            ('Play', [('Play / Pause', 'toggle', self.toggle), ('Stop', 'stop', self.stop),
                      ('Previous', 'prev', lambda: self.step(-1)), ('Next', 'next', lambda: self.step(1)), None,
                      ('Shuffle', 'shuffle', self.toggle_shuffle), ('Repeat', 'repeat', self.cycle_repeat), None,
                      ('Mute', 'mute', self.toggle_mute)]),
            ('View', [('Library', 'view-library', lambda: self.show_tab(LIBRARY_TAB)),
                      ('Now Playing', 'view-now', lambda: self.show_tab(NOW_TAB))]),
            ('Library', [('Refresh', 'refresh', self.scan)]),
        ]))
        root.append(self.build_nav())
        self.stack = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=150)
        self.stack.add_named(self.build_library(), LIBRARY_TAB)
        self.stack.add_named(self.build_now(), NOW_TAB)
        root.append(self.stack)
        root.append(self.build_bar())

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect('enter', lambda *_a: win.add_css_class('mp-drop') or Gdk.DragAction.COPY)
        drop.connect('leave', lambda *_a: win.remove_css_class('mp-drop'))
        drop.connect('drop', self.on_drop)
        root.add_controller(drop)

        self.set_volume(self.cfg['volume'], save=False)
        self.shuffle_btn.add_css_class('on') if self.shuffle else None
        self.sync_repeat()
        self.show_tab(NOW_TAB if app.files else self.cfg['tab'] if self.cfg['tab'] in (LIBRARY_TAB, NOW_TAB) else LIBRARY_TAB)
        self.scan()
        if app.files:
            GLib.idle_add(lambda: self.open_paths([f.get_path() for f in app.files if f.get_path()]) and False)
        GLib.timeout_add(250, self.tick)
        GLib.timeout_add(33, self.animate)
        win.connect('close-request', self.on_close)
        self.start_mpris()
        return root

    def build_nav(self):
        nav = Gtk.Box(spacing=4)
        nav.add_css_class('mp-nav')
        self.tabs = {}
        for key, label in ((LIBRARY_TAB, 'Library'), (NOW_TAB, 'Now Playing')):
            b = Gtk.Button(label=label, focusable=False)
            b.connect('clicked', lambda _b, k=key: self.show_tab(k))
            self.tabs[key] = b
            nav.append(b)
        op = Gtk.Button(label='Open...', focusable=False, margin_start=10)
        op.connect('clicked', lambda *_: self.open_dialog())
        nav.append(op)
        nav.append(Gtk.Box(hexpand=True))
        self.search_entry = Gtk.SearchEntry(placeholder_text='Search library', width_chars=22)
        self.search_entry.connect('search-changed', self.on_search)
        nav.append(self.search_entry)
        return nav

    def build_library(self):
        box = Gtk.Box()
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.add_css_class('mp-nav-side')
        side.set_size_request(180, -1)
        cap = Gtk.Label(label='Library', xalign=0)
        cap.add_css_class('mp-cap')
        side.append(cap)
        self.cats = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.cat_counts = {}
        for name in ('Music', 'Videos'):
            row = Gtk.ListBoxRow()
            row.cat = name
            line = Gtk.Box(spacing=6)
            line.append(Gtk.Label(label=name, xalign=0, hexpand=True))
            n = Gtk.Label(label='')
            n.add_css_class('mp-count')
            self.cat_counts[name] = n
            line.append(n)
            row.set_child(line)
            self.cats.append(row)
            if name == self.cfg['view']:
                self.cats.select_row(row)
        if not self.cats.get_selected_row():
            self.cats.select_row(self.cats.get_row_at_index(0))
        self.cats.connect('row-selected', self.on_category)
        side.append(self.cats)
        self.scan_label = Gtk.Label(label='', xalign=0, margin_start=14, margin_top=10)
        self.scan_label.add_css_class('mp-count')
        side.append(self.scan_label)
        box.append(side)
        self.lib = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=False)
        self.lib.add_css_class('mp-lib')
        self.lib.connect('row-activated', self.on_lib_activate)
        sc = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        sc.set_child(self.lib)
        box.append(sc)
        return box

    def build_now(self):
        main = Gtk.Box()
        stage = Gtk.Overlay(hexpand=True)
        stage.add_css_class('mp-stage')
        self.viz = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.viz.set_draw_func(self.draw)
        stage.set_child(self.viz)
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True, visible=False)
        if self.vsink:
            self.picture.set_paintable(self.vsink.get_property('paintable'))
        stage.add_overlay(self.picture)
        self.art = Art(200)
        self.art.set_valign(Gtk.Align.START)
        self.art.set_margin_top(28)
        stage.add_overlay(self.art)
        np = self.caption = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.END, margin_bottom=16, can_target=False)
        self.title = Gtk.Label(label='Nothing playing', ellipsize=3, margin_start=12, margin_end=12)
        self.title.add_css_class('mp-title')
        self.artist = Gtk.Label(label='Pick a track from the Library', ellipsize=3)
        self.artist.add_css_class('mp-artist')
        np.append(self.title)
        np.append(self.artist)
        stage.add_overlay(np)
        main.append(stage)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.add_css_class('mp-side')
        side.set_size_request(250, -1)
        h = Gtk.Label(label='Playing queue', xalign=0)
        h.add_css_class('mp-side-h')
        side.append(h)
        self.qlist = Gtk.ListBox()
        self.qlist.connect('row-activated', lambda _l, r: self.play_index(r.get_index(), True))
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.qlist)
        side.append(sc)
        main.append(side)
        return main

    def build_bar(self):
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
        self.shuffle_btn = self.button('media-playlist-shuffle-symbolic', 'Shuffle', lambda *_: self.toggle_shuffle())
        self.repeat_btn = self.button('media-playlist-repeat-symbolic', 'Repeat: off', lambda *_: self.cycle_repeat())
        left.append(self.shuffle_btn)
        left.append(self.repeat_btn)
        mid = Gtk.Box(spacing=10)
        mid.append(self.button('media-playback-stop-symbolic', 'Stop', lambda *_: self.stop()))
        mid.append(self.button('media-skip-backward-symbolic', 'Previous', lambda *_: self.step(-1)))
        self.play_btn = self.button('media-playback-start-symbolic', 'Play', lambda *_: self.toggle())
        self.play_btn.add_css_class('mp-play')
        mid.append(self.play_btn)
        mid.append(self.button('media-skip-forward-symbolic', 'Next', lambda *_: self.step(1)))
        right = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        self.mute_btn = self.button('audio-volume-high-symbolic', 'Mute', lambda *_: self.toggle_mute())
        right.append(self.mute_btn)
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.vol.set_size_request(100, -1)
        self.vol.set_draw_value(False)
        self.vol.connect('value-changed', lambda s: self.set_volume(s.get_value()))
        right.append(self.vol)
        ctrls.set_start_widget(left)
        ctrls.set_center_widget(mid)
        ctrls.set_end_widget(right)
        bar.append(ctrls)
        return bar

    def button(self, icon, tip, fn):
        b = Gtk.Button(icon_name=icon, tooltip_text=tip, focusable=False, valign=Gtk.Align.CENTER)
        b.connect('clicked', fn)
        return b

    def show_tab(self, key):
        self.stack.set_visible_child_name(key)
        for k, b in self.tabs.items():
            (b.add_css_class if k == key else b.remove_css_class)('tab-on')
        self.cfg['tab'] = key
        self.search_entry.set_visible(key == LIBRARY_TAB)

    def on_close(self, *_a):
        self.play.set_state(Gst.State.NULL)
        self.save()
        return False

    # ---- library --------------------------------------------------------------------------------------------------
    def scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scan_label.set_label('Scanning...')
        threading.Thread(target=self.scan_thread, daemon=True).start()

    def scan_thread(self):
        """Tags are read off the main thread; results are cached by file time so the next start is instant."""
        os.makedirs(CACHE, exist_ok=True)
        cache_file = os.path.join(CACHE, 'library.json')
        try:
            with open(cache_file) as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}
        music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC) or os.path.expanduser('~/Music')
        videos = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS) or os.path.expanduser('~/Videos')
        files = walk([music, SAMPLES], AUDIO) + walk([videos], VIDEO)
        disc, memo, out, fresh = GstPbutils.Discoverer.new(4 * Gst.SECOND), {}, [], {}
        for p in files:
            try:
                stamp = os.stat(p).st_mtime
            except OSError:
                continue
            hit = cache.get(p)
            if hit and hit[0] == stamp and (not hit[1]['art'] or os.path.exists(hit[1]['art'])):
                t = hit[1]
            else:
                t = probe(disc, p, memo)
            fresh[p] = [stamp, t]
            out.append(t)
        try:
            with open(cache_file, 'w') as f:
                json.dump(fresh, f)
        except OSError:
            pass
        GLib.idle_add(self.scan_done, out)

    def scan_done(self, tracks):
        self.scanning = False
        self.scan_label.set_label('')
        self.library = tracks
        self.render_library()
        return False

    def category_tracks(self):
        kind = 'video' if self.cfg['view'] == 'Videos' else 'audio'
        q = self.search.lower()
        mine = [t for t in self.library if t['kind'] == kind and (
            not q or q in (t['title'] + ' ' + t['artist'] + ' ' + t['album']).lower())]
        mine.sort(key=lambda t: (t['album'].lower(), t['track'] or 999, natural(t['path'])))
        return mine

    def render_library(self):
        while (r := self.lib.get_row_at_index(0)) is not None:
            self.lib.remove(r)
        for name, lbl in self.cat_counts.items():
            kind = 'video' if name == 'Videos' else 'audio'
            lbl.set_label(str(sum(1 for t in self.library if t['kind'] == kind)))
        tracks = self.category_tracks()
        self.shown_tracks = tracks
        if not tracks:
            msg = 'No matches.' if self.search else (
                'No videos found. Put videos in your Videos folder.' if self.cfg['view'] == 'Videos' else
                'No music found. Put music in your Music folder, or choose File > Open.')
            row = Gtk.ListBoxRow(activatable=False, selectable=False)
            row.set_child(Gtk.Label(label=msg, css_classes=['mp-empty']))
            self.lib.append(row)
            return
        album = None
        for i, t in enumerate(tracks):
            if t['kind'] == 'audio' and t['album'] != album:
                album = t['album']
                group = [x for x in tracks if x['album'] == album]
                self.lib.append(self.head_row(album, group))
            self.lib.append(self.track_row(t, i))
        self.mark_playing()

    def head_row(self, album, group):
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        row.add_css_class('mp-head')
        box = Gtk.Box(spacing=14)
        art = Art(72)
        art.set_art(next((t['art'] for t in group if t['art']), None))
        box.append(art)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        a = Gtk.Label(label=album, xalign=0, ellipsize=3)
        a.add_css_class('mp-album')
        artists = sorted({t['artist'] for t in group})
        year = next((t['year'] for t in group if t['year']), '')
        total = sum(t['dur'] for t in group)
        sub = ' · '.join(x for x in (artists[0] if len(artists) == 1 else 'Various artists', year,
                                     f'{len(group)} tracks, {fmt(total)}') if x)
        s = Gtk.Label(label=sub, xalign=0, ellipsize=3)
        s.add_css_class('mp-album-sub')
        col.append(a)
        col.append(s)
        box.append(col)
        play = Gtk.Button(label='Play album', valign=Gtk.Align.CENTER, focusable=False)
        play.connect('clicked', lambda *_: self.play_list(group, 0))
        box.append(play)
        row.set_child(box)
        return row

    def track_row(self, t, i):
        row = Gtk.ListBoxRow()
        row.add_css_class('mp-track')
        row.path, row.pos = t['path'], i
        box = Gtk.Box(spacing=10)
        n = Gtk.Label(label=str(t['track'] or ''), width_chars=3, xalign=1)
        n.add_css_class('mp-n')
        box.append(n)
        title = Gtk.Label(label=t['title'], xalign=0, hexpand=True, ellipsize=3)
        title.add_css_class('mp-t')
        box.append(title)
        who = Gtk.Label(label=t['artist'], xalign=0, ellipsize=3, width_chars=18, max_width_chars=18)
        who.add_css_class('mp-it-a')
        box.append(who)
        box.append(Gtk.Label(label=fmt(t['dur']), width_chars=5, xalign=1, css_classes=['mp-n']))
        row.set_child(box)
        return row

    def mark_playing(self):
        path = self.cur['path'] if self.cur else None
        r, i = self.lib.get_row_at_index(0), 0
        while r is not None:
            (r.add_css_class if getattr(r, 'path', None) == path and path else r.remove_css_class)('mp-playing')
            i += 1
            r = self.lib.get_row_at_index(i)

    def on_category(self, _box, row):
        if row is not None and row.cat != self.cfg['view']:
            self.cfg["view"] = row.cat
            self.render_library()

    def on_search(self, entry):
        self.search = entry.get_text().strip()
        self.render_library()

    def on_lib_activate(self, _l, row):
        pos = getattr(row, 'pos', None)
        if pos is not None:
            self.play_list(self.shown_tracks, pos)

    # ---- queue ----------------------------------------------------------------------------------------------------
    def play_list(self, tracks, start):
        self.queue, self.history = list(tracks), []
        self.render_queue()
        self.play_index(start, True)
        if self.queue[start]['kind'] == 'video':
            self.show_tab(NOW_TAB)

    def render_queue(self):
        while (r := self.qlist.get_row_at_index(0)) is not None:
            self.qlist.remove(r)
        if not self.queue:
            self.qlist.append(Gtk.Label(label='Nothing queued.', wrap=True, margin_top=12))
        for i, t in enumerate(self.queue):
            box = Gtk.Box(spacing=8)
            n = Gtk.Label(label=str(i + 1), width_chars=2, xalign=1)
            n.add_css_class('mp-n')
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            col.append(Gtk.Label(label=t['title'], xalign=0, ellipsize=3))
            al = Gtk.Label(label=t['artist'] if t['kind'] == 'audio' else 'Video', xalign=0, ellipsize=3)
            al.add_css_class('mp-it-a')
            col.append(al)
            box.append(n)
            box.append(col)
            self.qlist.append(box)
        self.qlist.select_row(self.qlist.get_row_at_index(self.index) if self.index >= 0 else None)

    def play_index(self, i, start):
        if not (0 <= i < len(self.queue)):
            return False
        t = self.queue[i]
        self.index, self.cur = i, t
        self.title.set_label(t['title'])
        self.artist.set_label(t['artist'] if t['kind'] == 'audio' else 'Video')
        if t['album'] and t['kind'] == 'audio':
            self.artist.set_label(f"{t['artist']} · {t['album']}")
        self.art.set_art(t['art'], t['kind'])
        video = t['kind'] == 'video' and self.vsink is not None
        self.picture.set_visible(video)
        self.art.set_visible(not video)
        self.caption.set_visible(not video)
        self.app.set_title(f"{t['title']} - Media Player")
        self.qlist.select_row(self.qlist.get_row_at_index(i))
        self.mark_playing()
        self.play.set_state(Gst.State.NULL)
        self.play.set_property('uri', Gst.filename_to_uri(t['path']))
        self.play.set_state(Gst.State.PLAYING if start else Gst.State.PAUSED)
        self.seek.set_value(0)
        self.set_playing(start)
        self.mpris_changed(Metadata=self.mpris_metadata(), CanGoNext=len(self.queue) > 1, CanGoPrevious=len(self.queue) > 1)
        return False

    def step(self, d):
        if not self.queue:
            return
        if d < 0:
            ok, pos = self.play.query_position(Gst.Format.TIME)
            # Like every player: Previous restarts the track first, and only goes back when pressed near the start.
            if ok and pos > 3 * Gst.SECOND:
                self.seek_to(0)
                return
            if self.history:
                return self.play_index(self.history.pop(), True)
        if self.shuffle and len(self.queue) > 1:
            i = random.choice([j for j in range(len(self.queue)) if j != self.index])
        else:
            i = (self.index + d) % len(self.queue)
        if d > 0 and self.index >= 0:
            self.history.append(self.index)
            del self.history[:-200]
        self.play_index(i, True)

    def toggle(self):
        if self.index < 0:
            tracks = self.category_tracks() if hasattr(self, 'shown_tracks') else []
            return self.play_list(tracks, 0) if tracks else None
        if self.playing:
            self.play.set_state(Gst.State.PAUSED)
        else:
            self.play.set_state(Gst.State.PLAYING)
        self.set_playing(not self.playing)

    def pause(self):
        if self.playing:
            self.toggle()

    def stop(self):
        if self.index < 0:
            return
        self.play.set_state(Gst.State.READY)
        self.seek.set_value(0)
        self.set_playing(False)

    def set_playing(self, on):
        self.playing = on
        self.play_btn.set_icon_name('media-playback-pause-symbolic' if on else 'media-playback-start-symbolic')
        self.play_btn.set_tooltip_text('Pause' if on else 'Play')
        self.mpris_changed(PlaybackStatus=self.mpris_status())

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        (self.shuffle_btn.add_css_class if self.shuffle else self.shuffle_btn.remove_css_class)('on')
        self.mpris_changed(Shuffle=self.shuffle)
        self.save()

    def cycle_repeat(self):
        self.repeat = {'off': 'all', 'all': 'one', 'one': 'off'}[self.repeat]
        self.sync_repeat()
        self.mpris_changed(LoopStatus=self.mpris_loop())
        self.save()

    def sync_repeat(self):
        b = self.repeat_btn
        (b.remove_css_class if self.repeat == 'off' else b.add_css_class)('on')
        b.set_icon_name('media-playlist-repeat-song-symbolic' if self.repeat == 'one' else 'media-playlist-repeat-symbolic')
        b.set_tooltip_text(f'Repeat: {self.repeat}')

    def set_volume(self, v, save=True):
        v = max(0.0, min(100.0, float(v)))
        if abs(self.vol.get_value() - v) > 0.01:
            self.vol.set_value(v)  # re-enters once with the same value, which stops here
            return
        self.play.set_property('volume', (v / 100) ** 2)
        self.sync_mute_icon()
        self.mpris_changed(Volume=v / 100)
        if save:
            self.cfg['volume'] = round(v)

    def toggle_mute(self):
        self.mute = not self.mute
        self.play.set_property('mute', self.mute)
        self.sync_mute_icon()

    def sync_mute_icon(self):
        v = self.vol.get_value()
        name = 'audio-volume-muted-symbolic' if self.mute or v == 0 else \
            'audio-volume-low-symbolic' if v < 34 else 'audio-volume-medium-symbolic' if v < 67 else 'audio-volume-high-symbolic'
        self.mute_btn.set_icon_name(name)
        (self.mute_btn.add_css_class if self.mute else self.mute_btn.remove_css_class)('on')

    # ---- opening files --------------------------------------------------------------------------------------------
    def open_filters(self):
        media = Gtk.FileFilter(name='Music and Videos')
        for ext in AUDIO + VIDEO:
            media.add_suffix(ext[1:])
        every = Gtk.FileFilter(name='All Files')
        every.add_pattern('*')
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(media)
        store.append(every)
        return store

    def open_dialog(self):
        folder = self.cfg.get('folder')
        if not folder or not os.path.isdir(folder):
            folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC) or os.path.expanduser('~')
        dlg = mwx7ui.FileDialog(title='Open', initial_folder=Gio.File.new_for_path(folder), filters=self.open_filters())

        def done(d, res):
            try:
                path = d.open_finish(res).get_path()
            except GLib.Error:
                return
            self.open_paths([path])
        dlg.open(self.win, None, done)

    def open_paths(self, paths):
        """Plays the files (folders: everything playable inside), probing tags off the main thread."""
        exts = AUDIO + VIDEO
        files = []
        for p in paths:
            if os.path.isdir(p):
                files += sorted(walk([p], exts), key=natural)
            elif p.lower().endswith(exts) or os.path.isfile(p):
                files.append(p)
        if not files:
            return False
        self.cfg['folder'] = os.path.dirname(files[0])
        for p in files:
            mwx7ui.remember(p)

        def work():
            disc, memo = GstPbutils.Discoverer.new(4 * Gst.SECOND), {}
            os.makedirs(CACHE, exist_ok=True)
            tracks = [probe(disc, p, memo) for p in files]
            GLib.idle_add(lambda: self.play_list(tracks, 0) or self.show_tab(NOW_TAB) or False)
        threading.Thread(target=work, daemon=True).start()
        return False

    def on_drop(self, _t, value, _x, _y):
        self.win.remove_css_class('mp-drop')
        paths = [f.get_path() for f in value.get_files() if f.get_path()]
        self.open_paths(paths)
        return bool(paths)

    # ---- playback -------------------------------------------------------------------------------------------------
    def on_message(self, _bus, msg):
        if msg.type == Gst.MessageType.EOS:
            if self.repeat == 'one':
                self.play_index(self.index, True)
            elif self.repeat == 'all' or self.shuffle or self.index < len(self.queue) - 1:
                self.step(1)
            else:
                self.play.set_state(Gst.State.READY)
                self.set_playing(False)
        elif msg.type == Gst.MessageType.ERROR:
            err, _dbg = msg.parse_error()
            self.play.set_state(Gst.State.NULL)
            self.artist.set_label(f'This file cannot be played ({err.message}).')
            self.set_playing(False)
        elif msg.type == Gst.MessageType.ELEMENT and msg.get_structure() and msg.get_structure().get_name() == 'spectrum':
            # PyGObject cannot unbox a GstValueList, so the magnitudes are read from the structure's text form.
            m = re.search(r'magnitude=\(float\)\{([^}]*)\}', msg.get_structure().to_string())
            if m:
                mags = [float(x) for x in m.group(1).split(',')]
                self.levels = [max(0.0, min(1.0, (max(mags[lo:hi] or [-70]) + 70) / 70))
                               for lo, hi in zip(EDGES, EDGES[1:])]

    def tick(self):
        ok_d, dur = self.play.query_duration(Gst.Format.TIME)
        ok_p, pos = self.play.query_position(Gst.Format.TIME)
        if ok_d and dur > 0 and ok_p and time.monotonic() > self.hold_until:
            self.seek.set_value(min(1000, pos / dur * 1000))
        self.time.set_label(f'{fmt(pos if ok_p else 0)} / {fmt(dur if ok_d else (self.cur or {}).get("dur", 0))}')
        return True

    def on_seek(self, _s, _scroll, value):
        ok, dur = self.play.query_duration(Gst.Format.TIME)
        if ok and dur > 0:
            self.hold_until = time.monotonic() + 0.5  # the playhead must not jump back under the user's finger
            self.seek_to(int(max(0, min(1000, value)) / 1000 * dur))
        return False

    def seek_to(self, ns):
        kind = (self.cur or {}).get('kind')
        flags = Gst.SeekFlags.FLUSH | (Gst.SeekFlags.KEY_UNIT if kind == 'video' else Gst.SeekFlags.ACCURATE)
        self.play.seek_simple(Gst.Format.TIME, flags, max(0, ns))
        if self.conn:
            self.conn.emit_signal(None, MPRIS_PATH, MPRIS_PLAYER, 'Seeked', GLib.Variant('(x)', (ns // 1000,)))

    # ---- visualisation --------------------------------------------------------------------------------------------
    def animate(self):
        if not self.playing:
            self.levels = [v * 0.85 for v in self.levels]
        quiet = max(self.shown) < 0.002 and max(self.levels) < 0.002
        self.shown = [max(lv, s * 0.88) for lv, s in zip(self.levels, self.shown)]
        # Nothing moves while paused and settled, or while another tab is up: an idle player costs nothing.
        if not quiet and self.stack.get_visible_child_name() == NOW_TAB:
            self.viz.queue_draw()
        return True

    def draw(self, _area, cr, w, h):
        n = len(self.shown)
        gap = 3
        bw = max(2.0, (w - 40 - gap * (n - 1)) / n)
        base = h * 0.68
        for i, v in enumerate(self.shown):
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

    # ---- MPRIS ----------------------------------------------------------------------------------------------------
    def mpris_status(self):
        if self.index < 0:
            return 'Stopped'
        return 'Playing' if self.playing else 'Paused'

    def mpris_loop(self):
        return {'off': 'None', 'all': 'Playlist', 'one': 'Track'}[self.repeat]

    def mpris_metadata(self):
        t = self.cur
        if not t:
            return {}
        md = {'mpris:trackid': GLib.Variant('o', f'/org/mwx7/mediaplayer/track/{self.index}'),
              'mpris:length': GLib.Variant('x', int(t['dur'] // 1000)),
              'xesam:title': GLib.Variant('s', t['title']),
              'xesam:artist': GLib.Variant('as', [t['artist']]),
              'xesam:album': GLib.Variant('s', t['album']),
              'xesam:url': GLib.Variant('s', Gst.filename_to_uri(t['path']))}
        if t['art']:
            md['mpris:artUrl'] = GLib.Variant('s', Gst.filename_to_uri(t['art']))
        return md

    def mpris_get(self, _c, _sender, _path, iface, prop):
        if iface == MPRIS_ROOT:
            return {'CanQuit': GLib.Variant('b', True), 'CanRaise': GLib.Variant('b', True),
                    'HasTrackList': GLib.Variant('b', False), 'Identity': GLib.Variant('s', 'Media Player'),
                    'DesktopEntry': GLib.Variant('s', 'org.mwx7.mediaplayer'),
                    'SupportedUriSchemes': GLib.Variant('as', ['file']),
                    'SupportedMimeTypes': GLib.Variant('as', ['audio/mpeg', 'audio/ogg', 'audio/flac', 'video/mp4'])}.get(prop)
        ok, pos = self.play.query_position(Gst.Format.TIME)
        many = len(self.queue) > 1
        return {'PlaybackStatus': GLib.Variant('s', self.mpris_status()), 'LoopStatus': GLib.Variant('s', self.mpris_loop()),
                'Rate': GLib.Variant('d', 1.0), 'Shuffle': GLib.Variant('b', self.shuffle),
                'Metadata': GLib.Variant('a{sv}', self.mpris_metadata()),
                'Volume': GLib.Variant('d', self.vol.get_value() / 100),
                'Position': GLib.Variant('x', int(pos // 1000) if ok else 0), 'MinimumRate': GLib.Variant('d', 1.0),
                'MaximumRate': GLib.Variant('d', 1.0), 'CanGoNext': GLib.Variant('b', many),
                'CanGoPrevious': GLib.Variant('b', many), 'CanPlay': GLib.Variant('b', True),
                'CanPause': GLib.Variant('b', True), 'CanSeek': GLib.Variant('b', True),
                'CanControl': GLib.Variant('b', True)}.get(prop)

    def mpris_set(self, _c, _sender, _path, iface, prop, value):
        if iface != MPRIS_PLAYER:
            return False
        if prop == 'Volume':
            self.set_volume(value.get_double() * 100)
        elif prop == 'Shuffle':
            if value.get_boolean() != self.shuffle:
                self.toggle_shuffle()
        elif prop == 'LoopStatus':
            want = {'None': 'off', 'Playlist': 'all', 'Track': 'one'}.get(value.get_string())
            while want and self.repeat != want:
                self.cycle_repeat()
        else:
            return False
        return True

    def mpris_call(self, _c, _sender, _path, iface, method, params, inv):
        args = params.unpack()
        if iface == MPRIS_ROOT:
            if method == 'Raise':
                self.win.present()
            elif method == 'Quit':
                self.win.close()
        elif method == 'PlayPause':
            self.toggle()
        elif method == 'Play':
            if not self.playing:
                self.toggle()
        elif method == 'Pause':
            self.pause()
        elif method == 'Stop':
            self.stop()
        elif method == 'Next':
            self.step(1)
        elif method == 'Previous':
            self.step(-1)
        elif method == 'Seek':
            ok, pos = self.play.query_position(Gst.Format.TIME)
            if ok:
                self.seek_to(pos + args[0] * 1000)
        elif method == 'SetPosition':
            self.seek_to(args[1] * 1000)
        elif method == 'OpenUri':
            path = Gio.File.new_for_uri(args[0]).get_path()
            if path:
                self.open_paths([path])
        inv.return_value(None)

    def mpris_changed(self, **props):
        if not self.conn:
            return
        changed = {k: (v if isinstance(v, GLib.Variant) else GLib.Variant({
            'Metadata': 'a{sv}', 'Volume': 'd', 'PlaybackStatus': 's', 'LoopStatus': 's', 'Shuffle': 'b'}.get(k, 'b'), v))
            for k, v in props.items()}
        if 'Metadata' in props:
            changed['Metadata'] = GLib.Variant('a{sv}', props['Metadata'])
        try:
            self.conn.emit_signal(None, MPRIS_PATH, 'org.freedesktop.DBus.Properties', 'PropertiesChanged',
                                  GLib.Variant('(sa{sv}as)', (MPRIS_PLAYER, changed, [])))
        except GLib.Error:
            pass

    def start_mpris(self):
        """Media keys and the shell's controls talk to the player through the session bus; no bus, no problem."""
        try:
            conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            info = Gio.DBusNodeInfo.new_for_xml(MPRIS_XML)
            for i, name in enumerate((MPRIS_ROOT, MPRIS_PLAYER)):
                conn.register_object(MPRIS_PATH, info.interfaces[i], self.mpris_call, self.mpris_get, self.mpris_set)
            Gio.bus_own_name_on_connection(conn, 'org.mpris.MediaPlayer2.mwx7mediaplayer', Gio.BusNameOwnerFlags.NONE,
                                           None, None)
            self.conn = conn
        except (GLib.Error, TypeError):
            self.conn = None


if __name__ == '__main__':
    player = Player()
    mwx7ui.App('org.mwx7.mediaplayer', 'Media Player', 'mediaplayer', (980, 600), CSS, player.build).run_main()
