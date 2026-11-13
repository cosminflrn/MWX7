"""Space Pinball (native): the web table ported to GTK 4 + cairo. Physics at a fixed 240 Hz, drawn at the frame clock's rate."""
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import time
import wave

import cairo

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, GLib, Gtk  # noqa: E402

CSS = """
window.mwx7-pinball > box { background: #070a1c; }
"""
SAVE = os.path.join(GLib.get_user_config_dir(), 'mwx7', 'pinball.json')

# Table units: a 580 x 740 playfield, y grows downwards (same numbers as the web table).
W, H = 580, 740
WALL_L, LANE_DIV, WALL_R = 10, 538, 570
CX = (WALL_L + LANE_DIV) / 2
MIRROR = WALL_L + LANE_DIV
ARCH = (290, 210, 280, 200)
BALL_R = 7.5
FLIP_LEN, FLIP_PX, FLIP_REST, FLIP_UP = 82, 187, 0.5236, -0.46
BUMPERS = [(CX - 80, 246), (CX, 186), (CX + 80, 246), (CX, 304)]
BUMPER_R = 21
SAUCER = (462, 402, 12)
PLUNGER_X = (LANE_DIV + WALL_R) / 2
PLUNGER_REST_Y, PLUNGER_TRAVEL = 668, 34
TARGET_Y = [330, 362, 394, 426]
LANE_X = [CX - 66, CX, CX + 66]
G, MAX_V, FLIP_UP_W, FLIP_DOWN_W = 980, 1700, 26, 12
STEP = 1 / 240
PANEL = 168
SCALE = 0.78

CYAN, MAGENTA, AMBER, LIME, VIOLET, ICE = ((0.25, 0.95, 1), (1, 0.24, 0.94), (1, 0.69, 0.23), (0.54, 1, 0.42),
                                           (0.6, 0.42, 1), (0.75, 0.89, 1))
RANKS = [('Cadet', 0), ('Pilot', 1), ('Navigator', 3), ('Commander', 5), ('Admiral', 8)]
MISSIONS = [('lanes', 'Light all three nav lanes', lambda d: 1), ('targets', 'Break the shield bank', lambda d: 1),
            ('bumpers', 'Overload the reactors', lambda d: 15 + 5 * (d // 5)),
            ('orbit', 'Fly the orbit loop', lambda d: 2 + d // 5), ('worm', 'Enter the wormhole', lambda d: 1)]


class Seg:
    def __init__(self, ax, ay, bx, by, kind, r=2.5, e=0.45, idx=0, one_way=False):
        self.ax, self.ay, self.bx, self.by, self.kind, self.r, self.e, self.idx = ax, ay, bx, by, kind, r, e, idx
        self.one_way, self.on = one_way, True


class Flipper:
    def __init__(self, side, px):
        self.side, self.px, self.py, self.theta, self.pressed = side, px, 640, FLIP_REST, False
        self.tx = self.ty = self.ptx = self.pty = 0.0
        self.tip()
        self.ptx, self.pty = self.tx, self.ty

    def tip(self):
        d = 1 if self.side == 'L' else -1
        self.tx = self.px + d * FLIP_LEN * math.cos(self.theta)
        self.ty = self.py + FLIP_LEN * math.sin(self.theta)


def closest_t(px, py, ax, ay, bx, by):
    abx, aby = bx - ax, by - ay
    l2 = abx * abx + aby * aby
    if l2 == 0:
        return 0
    return max(0, min(1, ((px - ax) * abx + (py - ay) * aby) / l2))


def build_world():
    segs = []
    n = 44
    for i in range(n):
        a0, a1 = math.pi + math.pi * i / n, math.pi + math.pi * (i + 1) / n
        segs.append(Seg(ARCH[0] + ARCH[2] * math.cos(a0), ARCH[1] + ARCH[3] * math.sin(a0),
                        ARCH[0] + ARCH[2] * math.cos(a1), ARCH[1] + ARCH[3] * math.sin(a1), 'arch', 3, 0.12))
    segs += [Seg(WALL_L, 210, WALL_L, 728, 'wall', 3), Seg(WALL_R, 210, WALL_R, 728, 'wall', 3),
             Seg(LANE_DIV, 200, LANE_DIV, 706, 'wall', 3),
             Seg(LANE_DIV, 110, LANE_DIV, 200, 'gate', 1.5, 0.3, 0, True)]
    for x in (CX - 99, CX - 33, CX + 33, CX + 99):
        segs.append(Seg(x, 70, x, 114, 'divider', 2.5, 0.4))
    for m in (0, 1):
        def X(x, m=m):
            return MIRROR - x if m else x
        segs += [Seg(X(44), 520, X(44), 728, 'guide', 3), Seg(X(44), 566, X(FLIP_PX), 640, 'guide', 3, 0.3),
                 Seg(X(88), 490, X(142), 578, 'sling', 3, 0.5, m),
                 Seg(X(88), 490, X(88), 562, 'body', 2.5, 0.3), Seg(X(88), 562, X(142), 578, 'body', 2.5, 0.3)]
    targets = [Seg(19, y - 12, 19, y + 12, 'target', 3.5, 0.3, i) for i, y in enumerate(TARGET_Y)]
    segs += targets
    plunger = Seg(LANE_DIV + 2, PLUNGER_REST_Y, WALL_R - 2, PLUNGER_REST_Y, 'plunger', 2, 0.1)
    segs.append(plunger)
    sensors = [[f'lane{i}', x, 98, 12, False] for i, x in enumerate(LANE_X)] + [
        ['inL', 66, 550, 11, False], ['inR', MIRROR - 66, 550, 11, False], ['outL', 27, 562, 9, False],
        ['outR', MIRROR - 27, 562, 9, False], ['orbA', MIRROR - 84, 96, 12, False], ['orbB', 84, 96, 12, False],
        ['saucer', SAUCER[0], SAUCER[1], 9, False]]
    return segs, targets, plunger, sensors, [Flipper('L', FLIP_PX), Flipper('R', MIRROR - FLIP_PX)]


SFX_DIR = os.path.join(GLib.get_user_cache_dir(), 'mwx7', 'pinball')
SFX_RATE = 22050


def _render(parts, total):
    """Mixes the web version's building blocks (thump / noise burst / metal ring) into a list of floats."""
    n = int(SFX_RATE * total)
    out = [0.0] * n
    rnd = random.Random(7)
    for kind, a in parts:
        t0 = int(a.get('delay', 0) * SFX_RATE)
        dur, vol = a['dur'], a['vol']
        m = min(n - t0, int((dur + 0.02) * SFX_RATE))
        if m <= 0:
            continue
        tau = dur / 6.9  # exponential decay to -60 dB over `dur`, like exponentialRampToValueAtTime(0.0001)
        if kind == 'thump':
            ph = 0.0
            for i in range(m):
                t = i / SFX_RATE
                f = a['f0'] * (max(20, a['f1']) / a['f0']) ** min(1.0, t / (dur * 0.8))
                ph += 2 * math.pi * f / SFX_RATE
                out[t0 + i] += vol * math.exp(-t / tau) * math.sin(ph)
        elif kind == 'ring':
            for mul, v in ((1, 1), (2.76, 0.5), (5.4, 0.25)):
                tt = dur / mul ** 0.5 / 6.9
                w = 2 * math.pi * a['f'] * mul / SFX_RATE
                for i in range(m):
                    out[t0 + i] += vol * v * math.exp(-i / SFX_RATE / tt) * math.sin(w * i)
        else:  # burst: white noise through an RBJ biquad whose cutoff may sweep
            typ, q, f0, f1 = a['type'], a['q'], a['f0'], a['f1']
            x1 = x2 = y1 = y2 = 0.0
            for i in range(m):
                if i % 32 == 0:
                    f = min(SFX_RATE * 0.45, f0 * (max(30, f1) / f0) ** (i / SFX_RATE / dur) if f1 != f0 else f0)
                    w0 = 2 * math.pi * f / SFX_RATE
                    al, cw = math.sin(w0) / (2 * q), math.cos(w0)
                    if typ == 'highpass':
                        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
                    elif typ == 'lowpass':
                        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
                    else:
                        b0, b1, b2 = al, 0.0, -al
                    a0, a1, a2 = 1 + al, -2 * cw, 1 - al
                x0 = rnd.random() * 2 - 1
                y0 = (b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0
                x2, x1, y2, y1 = x1, x0, y1, y0
                out[t0 + i] += vol * math.exp(-i / SFX_RATE / tau) * y0
    return out


def _thump(f0, f1, dur, vol, delay=0):
    return ('thump', dict(f0=f0, f1=f1, dur=dur, vol=vol, delay=delay))


def _burst(f, q, dur, vol, typ='bandpass', delay=0, f_end=None):
    return ('burst', dict(f0=f, f1=f_end or f, q=q, dur=dur, vol=vol, type=typ, delay=delay))


def _ring(f, dur, vol, delay=0):
    return ('ring', dict(f=f, dur=dur, vol=vol, delay=delay))


# name -> (minimum gap in ms, length in s, parts); the same recipes as src/apps/pinball/audio.ts.
SFX = {
    'bumper': (40, 0.2, [_thump(146, 48, 0.11, 0.7), _burst(2200, 0.9, 0.035, 0.5), _burst(900, 1.4, 0.06, 0.3),
                         _ring(1540, 0.09, 0.05)]),
    'sling': (50, 0.15, [_thump(110, 55, 0.08, 0.55), _burst(3200, 0.8, 0.022, 0.6, 'highpass'), _burst(1400, 1.2, 0.05, 0.25)]),
    'flipper': (35, 0.12, [_burst(4200, 0.7, 0.012, 0.6, 'highpass'), _thump(130, 52, 0.06, 0.6),
                           _burst(700, 1.1, 0.03, 0.22, 'bandpass', 0.014)]),
    'wall': (70, 0.1, [_burst(1600, 1.0, 0.03, 0.2), _thump(200, 100, 0.04, 0.12)]),
    'target': (40, 0.2, [_burst(3800, 1.0, 0.014, 0.5, 'highpass'), _thump(220, 100, 0.05, 0.3), _ring(1850, 0.12, 0.05)]),
    'rollover': (40, 0.08, [_burst(2400, 2, 0.018, 0.22), _thump(420, 260, 0.025, 0.1)]),
    'launch': (100, 0.7, [_thump(95, 32, 0.2, 0.65), _burst(2500, 0.8, 0.015, 0.5, 'highpass'),
                          _burst(1200, 0.7, 0.5, 0.14, 'lowpass', 0.03, 200)]),
    'charge': (90, 0.06, [_burst(1700, 2.2, 0.012, 0.16), _thump(110, 70, 0.025, 0.08)]),
    'drain': (300, 0.8, [_burst(1400, 0.6, 0.6, 0.25, 'lowpass', 0, 120), _thump(80, 30, 0.35, 0.55, 0.08)]),
    'save': (300, 0.6, [_ring(660, 0.35, 0.05), _ring(990, 0.4, 0.045, 0.1)]),
    'mission': (300, 0.7, [_ring(523, 0.45, 0.05), _ring(659, 0.45, 0.05, 0.09), _ring(784, 0.45, 0.05, 0.18),
                           _thump(100, 45, 0.18, 0.3)]),
    'wormhole': (200, 0.6, [_burst(300, 2.5, 0.55, 0.28, 'bandpass', 0, 2600), _thump(50, 110, 0.5, 0.3)]),
    'over': (500, 1.4, [_thump(90, 34, 0.5, 0.6), _thump(70, 28, 0.7, 0.5, 0.35), _burst(900, 0.7, 0.9, 0.12, 'lowpass', 0.35, 100)]),
}


class Sfx:
    """Pinball sounds: short WAVs rendered once into ~/.cache/mwx7/pinball, played by pw-play / paplay without blocking."""

    def __init__(self):
        self.player = shutil.which('pw-play') or shutil.which('paplay')
        self.last = {}
        self.ready = False

    def prepare(self):
        # Rendering takes a moment in pure Python, so it runs lazily on an idle callback instead of delaying the window.
        try:
            os.makedirs(SFX_DIR, exist_ok=True)
            for name, (_gap, total, parts) in SFX.items():
                path = os.path.join(SFX_DIR, name + '.wav')
                if os.path.exists(path):
                    continue
                pcm = _render(parts, total)
                with wave.open(path + '.tmp', 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(SFX_RATE)
                    w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, v)) * 32767 * 0.8)) for v in pcm))
                os.replace(path + '.tmp', path)
            self.ready = True
        except OSError:
            pass
        return False

    def play(self, name):
        if not self.ready or not self.player:
            return
        if os.path.exists(os.path.join(GLib.get_user_config_dir(), 'mwx7', 'sounds-off')):  # Settings -> Sound
            return
        gap = SFX[name][0]
        now = time.monotonic() * 1000
        if now - self.last.get(name, -1e9) < gap:
            return
        self.last[name] = now
        try:
            subprocess.Popen([self.player, os.path.join(SFX_DIR, name + '.wav')], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass


class Pinball:
    def build(self, app, win):
        win.add_css_class('mwx7-pinball')
        self.app, self.win = app, win
        self.segs, self.targets, self.plunger, self.sensors, self.flippers = build_world()
        self.high, self.paused, self.tick_id, self.last_t, self.acc = 0, False, None, None, 0.0
        try:
            with open(SAVE) as f:
                self.high = int(json.load(f).get('high', 0))
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        self.clock = self.last_kick = 0.0
        self.sfx = Sfx()
        GLib.idle_add(self.sfx.prepare)
        self.chain = 0
        self.new_game(first=True)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([('Game', [('New Game', 'new', self.new_game), ('Pause', 'pause', self.toggle_pause)])]))
        self.area = Gtk.DrawingArea(content_width=int(W * SCALE) + PANEL, content_height=int(H * SCALE))
        self.area.set_draw_func(self.draw)
        root.append(self.area)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', lambda _c, k, *_a: self.key(k, True))
        keys.connect('key-released', lambda _c, k, *_a: self.key(k, False))
        win.add_controller(keys)
        win.connect('close-request', lambda *_a: self.persist() or False)
        self.area.connect('map', lambda *_a: self.start())
        self.area.connect('unmap', lambda *_a: self.stop())
        return root

    # ---- state ----
    def new_game(self, first=False):
        self.score, self.ball_no, self.bonus, self.mult = 0, 1, 0, 1
        self.lanes, self.in_lit = [False] * 3, [False] * 2
        self.missions_done = self.mission_prog = self.bumper_hits = 0
        self.save_t, self.grant_save, self.sparks, self.banner = 0, True, [], None
        self.flash, self.trail, self.time = {}, [], 0.0
        self.serve_delay = self.saucer_t = self.target_reset = self.still_t = 0.0
        self.last_orb = None
        for t in self.targets:
            t.on = True
        self.phase = 'ready'
        self.serve()
        if not first:
            self.say('NEW GAME', 'Rank: Cadet', CYAN)
            self.paused = False
            self.start()

    def serve(self):
        self.bx, self.by = PLUNGER_X, PLUNGER_REST_Y - 2 - BALL_R
        self.vx = self.vy = 0.0
        self.active, self.held, self.in_play = True, False, False
        self.pull, self.charging = 0.0, False
        self.phase = 'over' if self.phase == 'over' else 'ready'
        self.trail = []
        self.plunger.ay = self.plunger.by = PLUNGER_REST_Y

    def say(self, text, sub='', color=CYAN, dur=1.8):
        self.banner = [text, sub, color, 0.0, dur]

    def add(self, n):
        if self.phase == 'over':
            return
        self.score += n
        self.high = max(self.high, self.score)

    def persist(self):
        try:
            os.makedirs(os.path.dirname(SAVE), exist_ok=True)
            with open(SAVE, 'w') as f:
                json.dump({'high': self.high, 'score': self.score, 'ball': self.ball_no}, f)
        except OSError:
            pass

    def rank(self):
        return max(i for i, (_n, at) in enumerate(RANKS) if self.missions_done >= at)

    def burst(self, x, y, color, n=10, speed=160):
        for _ in range(n):
            a, v = random.random() * math.tau, speed * (0.35 + random.random() * 0.8)
            self.sparks.append([x, y, math.cos(a) * v, math.sin(a) * v, 0.45 + random.random() * 0.3, color])
        del self.sparks[:-160]

    # ---- input ----
    def key(self, k, down):
        name = Gdk.keyval_name(k) or ''
        if name in ('z', 'Z', 'Left', 'Shift_L'):
            self.set_flipper(0, down)
        elif name in ('slash', 'question', 'Right', 'Shift_R'):
            self.set_flipper(1, down)
        elif name == 'space':
            if down and self.phase == 'over':
                self.new_game()
            elif not self.paused:
                self.set_plunger(down)
        else:
            return False
        return True

    def set_flipper(self, i, down):
        f = self.flippers[i]
        if down and not f.pressed:
            self.sfx.play('flipper')
            l = self.lanes  # flipper buttons rotate the rollover lights, like a real table
            self.lanes = [l[1], l[2], l[0]] if i == 0 else [l[2], l[0], l[1]]
        f.pressed = down and not self.paused

    def at_plunger(self):
        return self.active and not self.held and self.bx > LANE_DIV + 2 and self.by > 600 and abs(self.vy) < 120

    def set_plunger(self, down):
        if self.phase == 'over':
            return
        at = self.at_plunger()
        if down:
            self.charging = self.charging or at
        elif self.charging:
            self.charging = False
            if at:
                self.sfx.play('launch')
                self.vy, self.vx = -(430 + 1170 * self.pull), 0.0
                if self.phase == 'ready':
                    self.phase = 'play'
                    self.save_t = 8 if self.grant_save else 0
                    self.grant_save = False
            self.pull = 0.0

    def toggle_pause(self):
        if self.phase == 'over':
            return
        self.paused = not self.paused
        if self.paused:
            for f in self.flippers:
                f.pressed = False
            self.charging = False
            self.stop()
            self.area.queue_draw()
        else:
            self.start()

    # ---- loop ----
    def start(self):
        if self.tick_id is None and not self.paused:
            self.last_t = None
            self.tick_id = self.area.add_tick_callback(self.tick)

    def stop(self):
        if self.tick_id is not None:
            self.area.remove_tick_callback(self.tick_id)
            self.tick_id = None

    def tick(self, _w, clock):
        t = clock.get_frame_time() / 1e6
        dt = 0 if self.last_t is None else min(0.05, t - self.last_t)  # clamp: a stall must not teleport the ball
        self.last_t = t
        self.acc += dt
        while self.acc >= STEP:
            self.acc -= STEP
            self.step(STEP)
        self.area.queue_draw()
        return GLib.SOURCE_CONTINUE

    # ---- physics ----
    def resolve(self, cx, cy, rad, e, svx=0.0, svy=0.0):
        dx, dy = self.bx - cx, self.by - cy
        mn = BALL_R + rad
        d2 = dx * dx + dy * dy
        if d2 >= mn * mn:
            return -1
        d = math.sqrt(d2)
        if d < 1e-6:
            dx, dy = 0.0, -1.0
        else:
            dx, dy = dx / d, dy / d
        self.nx, self.ny = dx, dy
        self.bx, self.by = cx + dx * mn, cy + dy * mn
        vn = (self.vx - svx) * dx + (self.vy - svy) * dy
        if vn >= 0:
            return 0
        j = -(1 + (0 if -vn < 45 else e)) * vn
        self.vx += j * dx
        self.vy += j * dy
        return -vn

    def collide(self):
        for _ in range(2):
            for s in self.segs:
                if not s.on:
                    continue
                if s.one_way:
                    dx, dy = s.bx - s.ax, s.by - s.ay
                    if ((self.bx - s.ax) * -dy + (self.by - s.ay) * dx) / math.hypot(dx, dy) < 0:
                        continue
                t = closest_t(self.bx, self.by, s.ax, s.ay, s.bx, s.by)
                hit = self.resolve(s.ax + (s.bx - s.ax) * t, s.ay + (s.by - s.ay) * t, s.r, s.e)
                if hit < 0:
                    continue
                if s.kind == 'sling':
                    if hit > 90:
                        # After 3 kicks within 1.2 s the next only reflects, so the ball can't ping-pong forever.
                        self.chain = self.chain + 1 if self.clock - self.last_kick < 1.2 else 0
                        self.last_kick = self.clock
                        if self.chain < 3:
                            out = self.vx * self.nx + self.vy * self.ny
                            if out < 560:
                                self.vx += (560 - out) * self.nx
                                self.vy += (560 - out) * self.ny
                        self.sfx.play('sling')
                        self.add(10)
                        self.flash[f's{s.idx}'] = 1
                        self.burst((s.ax + s.bx) / 2, (s.ay + s.by) / 2, CYAN, 7, 200)
                elif s.kind == 'target':
                    if hit > 20:
                        self.hit_target(s)
                elif hit > 140:
                    self.sfx.play('wall')
            for i, (cx, cy) in enumerate(BUMPERS):
                hit = self.resolve(cx, cy, BUMPER_R, 0.9)
                if hit > 60:
                    out = self.vx * self.nx + self.vy * self.ny
                    if out < 470:
                        self.vx += (470 - out) * self.nx
                        self.vy += (470 - out) * self.ny
                    self.sfx.play('bumper')
                    self.add(100)
                    self.bonus += 100
                    self.flash[f'b{i}'] = 1
                    self.burst(cx, cy, AMBER, 12, 220)
                    self.mission('bumpers')
            for f in self.flippers:
                t = closest_t(self.bx, self.by, f.px, f.py, f.tx, f.ty)
                self.resolve(f.px + (f.tx - f.px) * t, f.py + (f.ty - f.py) * t, 6.5 + (3.8 - 6.5) * t, 0.32,
                             (f.tx - f.ptx) * t * 240, (f.ty - f.pty) * t * 240)

    def hit_target(self, t):
        if not t.on:
            return
        t.on = False
        self.sfx.play('target')
        self.add(500)
        self.bonus += 500
        self.flash[f't{t.idx}'] = 1
        self.burst(19, (t.ay + t.by) / 2, MAGENTA, 10, 180)
        if not any(q.on for q in self.targets):
            self.add(5000)
            self.bonus += 2000
            self.say('SHIELDS DOWN', '+5,000', MAGENTA)
            self.target_reset = 1.1
            self.mission('targets')

    def mission(self, mid):
        cur = MISSIONS[self.missions_done % len(MISSIONS)]
        if cur[0] != mid:
            return
        self.mission_prog += 1
        self.flash['mission'] = 1
        if self.mission_prog < cur[2](self.missions_done):
            return
        before = self.rank()
        self.missions_done += 1
        self.sfx.play('mission')
        self.mission_prog = 0
        self.add(5000 * self.missions_done)
        self.bonus += 2500
        after = self.rank()
        if after > before:
            self.say('PROMOTED: ' + RANKS[after][0].upper(), f'Missions flown: {self.missions_done}', AMBER, 2.6)
        else:
            self.say('MISSION COMPLETE', f'+{5000 * self.missions_done:,}', AMBER, 2.2)

    def on_sensor(self, sid):
        if sid.startswith('lane'):
            self.sfx.play('rollover')
            i = int(sid[4:])
            self.flash[sid] = 1
            if self.lanes[i]:
                return self.add(50)
            self.lanes[i] = True
            self.add(250)
            self.bonus += 250
            if all(self.lanes):
                self.lanes = [False] * 3
                self.mult = min(5, self.mult + 1)
                self.add(3000)
                self.say('NAV LANES LIT', f'Bonus x{self.mult}', CYAN)
                self.mission('lanes')
        elif sid in ('inL', 'inR'):
            i = 0 if sid == 'inL' else 1
            self.flash[sid] = 1
            self.add(500)
            self.in_lit[i] = True
            if all(self.in_lit):
                self.in_lit = [False, False]
                self.bonus += 3000
                self.say('DOCKING BONUS', '+3,000 end-of-ball', LIME)
        elif sid in ('outL', 'outR'):
            self.flash[sid] = 1
            self.add(1000)
        elif sid in ('orbA', 'orbB'):
            self.flash[sid] = 1
            if not self.in_play:
                return
            prev = self.last_orb
            if prev and prev[0] != sid and self.time - prev[1] < 2.6:
                self.last_orb = None
                self.add(2500)
                self.bonus += 1500
                self.say('ORBIT COMPLETE', '+2,500', MAGENTA)
                self.mission('orbit')
            else:
                self.last_orb = (sid, self.time)
        elif sid == 'saucer':
            if self.held or math.hypot(self.vx, self.vy) > 950:
                return
            self.sfx.play('wormhole')
            self.held, self.bx, self.by, self.vx, self.vy, self.saucer_t = True, SAUCER[0], SAUCER[1], 0.0, 0.0, 0.9
            self.add(1500)
            self.bonus += 1000
            self.flash['saucer'] = 1
            self.say('WORMHOLE', '+1,500', VIOLET)
            self.mission('worm')

    def step(self, dt):
        self.time += dt
        self.clock += dt
        if self.charging and self.at_plunger():
            self.pull = min(1.0, self.pull + dt / 1.1)
            self.sfx.play('charge')
            self.plunger.ay = self.plunger.by = PLUNGER_REST_Y + PLUNGER_TRAVEL * self.pull
        elif not self.charging and self.plunger.ay > PLUNGER_REST_Y:
            self.plunger.ay = self.plunger.by = max(PLUNGER_REST_Y, self.plunger.ay - 2600 * dt)
        for f in self.flippers:
            f.ptx, f.pty = f.tx, f.ty
            target, w = (FLIP_UP, FLIP_UP_W) if f.pressed else (FLIP_REST, FLIP_DOWN_W)
            d, st = target - f.theta, w * dt
            f.theta = target if abs(d) <= st else f.theta + math.copysign(st, d)
            f.tip()
        if self.active and not self.held:
            n = min(8, max(1, math.ceil(math.hypot(self.vx, self.vy) * dt / 2.5)))
            h = dt / n
            for _ in range(n):
                self.vy += G * h
                drag = 1 - 0.05 * h
                self.vx *= drag
                self.vy *= drag
                v = math.hypot(self.vx, self.vy)
                if v > MAX_V:
                    self.vx *= MAX_V / v
                    self.vy *= MAX_V / v
                self.bx += self.vx * h
                self.by += self.vy * h
                self.collide()
            for s in self.sensors:
                inside = math.hypot(self.bx - s[1], self.by - s[2]) < s[3] + 2
                if inside and not s[4]:
                    self.on_sensor(s[0])
                s[4] = inside
        if self.phase == 'play' and self.save_t > 0:
            self.save_t = max(0, self.save_t - dt)
        if self.active and not self.in_play and self.by > 300 and self.bx < LANE_DIV - 8:
            self.in_play = True
        if self.held:
            self.saucer_t -= dt
            if self.saucer_t <= 0:
                self.held = False
                self.vx, self.vy = -300 - random.random() * 120, -520 - random.random() * 120
                self.burst(SAUCER[0], SAUCER[1], VIOLET, 14, 240)
        if self.target_reset > 0:
            self.target_reset -= dt
            if self.target_reset <= 0:
                for t in self.targets:
                    t.on = True
        if self.active and not self.held and self.in_play:  # stuck on a flipper tip: nudge
            self.still_t = self.still_t + dt if math.hypot(self.vx, self.vy) < 8 else 0
            if self.still_t > 2.5:
                self.still_t = 0
                self.vx += (random.random() - 0.5) * 240
                self.vy -= 160
        if self.active and self.by > H + 16:
            self.drain()
        if not self.active and self.phase != 'over':
            self.serve_delay -= dt
            if self.serve_delay <= 0:
                self.serve()
        self.fx(dt)

    def drain(self):
        self.active = False
        if self.save_t > 0 or self.phase == 'ready':
            self.save_t = 0
            self.sfx.play('save')
            self.say('BALL SAVED', 'Shoot again', ICE)
            self.serve_delay = 0.8
            return
        self.sfx.play('over' if self.ball_no >= 3 else 'drain')
        self.add(self.bonus * self.mult)
        self.say('END OF BALL', f'Bonus {self.bonus:,} x{self.mult}', AMBER, 2.4)
        self.bonus, self.mult, self.in_lit, self.last_orb = 0, 1, [False, False], None
        if self.ball_no >= 3:
            self.phase = 'over'
            self.persist()
        else:
            self.ball_no += 1
            self.grant_save = True
            self.phase = 'ready'
            self.serve_delay = 2.2

    def fx(self, dt):
        for k in list(self.flash):
            self.flash[k] = max(0, self.flash[k] - dt * 2.6)
        if self.banner:
            self.banner[3] += dt
            if self.banner[3] > self.banner[4]:
                self.banner = None
        for s in self.sparks:
            s[4] -= dt
            s[3] += 380 * dt
            s[0] += s[2] * dt
            s[1] += s[3] * dt
        self.sparks = [s for s in self.sparks if s[4] > 0]
        if self.active:
            if not self.trail or math.hypot(self.trail[-1][0] - self.bx, self.trail[-1][1] - self.by) > 3:
                self.trail.append((self.bx, self.by))
                del self.trail[:-10]
        else:
            self.trail = []

    # ---- drawing ----
    def text(self, cr, s, x, y, size, color=(1, 1, 1), bold=True, align=0.0, alpha=1.0):
        cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(size)
        e = cr.text_extents(s)
        cr.set_source_rgba(*color, alpha)
        cr.move_to(x - e.width * align - e.x_bearing, y)
        cr.show_text(s)

    def line(self, cr, s, color, width=None):
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(*color)
        cr.set_line_width(width or s.r * 2)
        cr.move_to(s.ax, s.ay)
        cr.line_to(s.bx, s.by)
        cr.stroke()

    def glow_dot(self, cr, x, y, r, color, a):
        g = cairo.RadialGradient(x, y, 0, x, y, r * 2.6)
        g.add_color_stop_rgba(0, *color, a)
        g.add_color_stop_rgba(0.4, *color, a * 0.5)
        g.add_color_stop_rgba(1, *color, 0)
        cr.set_source(g)
        cr.arc(x, y, r * 2.6, 0, math.tau)
        cr.fill()

    def draw(self, _a, cr, w, h):
        cr.set_source_rgb(0.03, 0.04, 0.11)
        cr.paint()
        cr.save()
        cr.scale(SCALE, SCALE)
        cr.rectangle(0, 0, W, H)
        cr.clip()
        bg = cairo.RadialGradient(CX, 330, 20, CX, 330, 420)
        bg.add_color_stop_rgb(0, 0.12, 0.1, 0.3)
        bg.add_color_stop_rgb(1, 0.03, 0.03, 0.09)
        cr.set_source(bg)
        cr.paint()
        rnd = random.Random(7)
        for _ in range(70):  # stars
            cr.set_source_rgba(1, 1, 1, rnd.random() * 0.5 + 0.1)
            cr.arc(rnd.random() * W, rnd.random() * H, rnd.random() * 1.1 + 0.3, 0, math.tau)
            cr.fill()
        for s in self.segs:  # walls and rails
            if s.kind == 'plunger':
                continue
            col = {'sling': CYAN, 'target': MAGENTA, 'arch': VIOLET, 'gate': (0.5, 0.5, 0.6)}.get(s.kind, (0.35, 0.45, 0.85))
            if s.kind == 'target':
                if not s.on:
                    col = (0.25, 0.1, 0.25)
                elif self.flash.get(f't{s.idx}', 0):
                    col = (1, 1, 1)
            elif s.kind == 'sling' and self.flash.get(f's{s.idx}', 0):
                col = (1, 1, 1)
            self.line(cr, s, (*col, 0.25), s.r * 2 + 4)
            self.line(cr, s, (*col, 0.95), s.r * 2 - 1)
        lit = {f'lane{i}': self.lanes[i] for i in range(3)}
        lit.update({'inL': self.in_lit[0], 'inR': self.in_lit[1], 'save': self.save_t > 0})
        inserts = ([(f'lane{i}', LANE_X[i], 90, 7, CYAN) for i in range(3)] + [
            ('inL', 66, 540, 8, LIME), ('inR', MIRROR - 66, 540, 8, LIME), ('outL', 27, 552, 6, AMBER),
            ('outR', MIRROR - 27, 552, 6, AMBER), ('orbA', MIRROR - 84, 92, 8, MAGENTA), ('orbB', 84, 92, 8, MAGENTA),
            ('save', CX, 604, 8, ICE), ('mission', CX, 392, 15, AMBER)] + [
            (f'rank{i}', CX - 72 + i * 36, 476 + abs(i - 2) * 9, 6, VIOLET) for i in range(5)])
        for key, x, y, r, col in inserts:
            a = 1.0 if lit.get(key) else 0.18
            if key.startswith('rank'):
                a = 1.0 if int(key[4:]) <= self.rank() else 0.18
            a = max(a, self.flash.get(key, 0))
            if a > 0.5:
                self.glow_dot(cr, x, y, r, col, a)
            cr.set_source_rgba(*col, a)
            cr.arc(x, y, r * 0.7, 0, math.tau)
            cr.fill()
        sx, sy, sr = SAUCER  # wormhole
        g = cairo.RadialGradient(sx, sy, 1, sx, sy, sr + 6)
        g.add_color_stop_rgba(0, 0, 0, 0, 1)
        g.add_color_stop_rgba(0.6, *VIOLET, 0.9)
        g.add_color_stop_rgba(1, *VIOLET, 0)
        cr.set_source(g)
        cr.arc(sx, sy, sr + 6, 0, math.tau)
        cr.fill()
        for i, (bx, by) in enumerate(BUMPERS):
            f = self.flash.get(f'b{i}', 0)
            self.glow_dot(cr, bx, by, BUMPER_R * 0.8, AMBER, 0.2 + f * 0.6)
            g = cairo.RadialGradient(bx - 6, by - 6, 2, bx, by, BUMPER_R)
            g.add_color_stop_rgb(0, 1, 0.9 if f else 0.7, 0.5 if f else 0.3)
            g.add_color_stop_rgb(1, 0.55, 0.2, 0.05)
            cr.set_source(g)
            cr.arc(bx, by, BUMPER_R, 0, math.tau)
            cr.fill()
            cr.set_source_rgb(1, 0.85, 0.5)
            cr.set_line_width(2)
            cr.arc(bx, by, BUMPER_R - 4, 0, math.tau)
            cr.stroke()
        cr.set_source_rgb(0.7, 0.72, 0.8)  # plunger
        cr.rectangle(LANE_DIV + 6, self.plunger.ay, WALL_R - LANE_DIV - 12, 14)
        cr.fill()
        for f in self.flippers:
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            for width, col in ((13, (0.2, 0.7, 0.95)), (9, (0.8, 0.95, 1))):
                cr.set_source_rgb(*col)
                cr.set_line_width(width)
                cr.move_to(f.px, f.py)
                cr.line_to(f.tx, f.ty)
                cr.stroke()
        for i, (tx, ty) in enumerate(self.trail[:-1]):
            cr.set_source_rgba(0.8, 0.9, 1, 0.04 * i)
            cr.arc(tx, ty, BALL_R * (0.4 + i * 0.05), 0, math.tau)
            cr.fill()
        if self.active:
            g = cairo.RadialGradient(self.bx - 2.5, self.by - 2.5, 1, self.bx, self.by, BALL_R)
            g.add_color_stop_rgb(0, 1, 1, 1)
            g.add_color_stop_rgb(1, 0.55, 0.62, 0.75)
            cr.set_source(g)
            cr.arc(self.bx, self.by, BALL_R, 0, math.tau)
            cr.fill()
        for x, y, _vx, _vy, life, col in self.sparks:
            cr.set_source_rgba(*col, min(1, life * 2))
            cr.arc(x, y, 2, 0, math.tau)
            cr.fill()
        if self.pull > 0:  # plunger power
            cr.set_source_rgba(1, 1, 1, 0.15)
            cr.rectangle(LANE_DIV + 4, 560, 28, 6)
            cr.fill()
            cr.set_source_rgb(*AMBER)
            cr.rectangle(LANE_DIV + 4, 560, 28 * self.pull, 6)
            cr.fill()
        if self.banner:
            t, sub, col, age, dur = self.banner
            a = max(0, min(1, age * 6, (dur - age) * 4))
            self.text(cr, t, CX, 520, 26, col, align=0.5, alpha=a)
            self.text(cr, sub, CX, 546, 14, (1, 1, 1), align=0.5, alpha=a)
        if self.phase == 'over':
            cr.set_source_rgba(0, 0, 0, 0.6)
            cr.rectangle(0, 300, W, 130)
            cr.fill()
            self.text(cr, 'GAME OVER', CX, 355, 36, AMBER, align=0.5)
            self.text(cr, 'Space or Game > New Game', CX, 390, 16, (1, 1, 1), bold=False, align=0.5)
        cr.restore()
        self.panel(cr, int(W * SCALE), h)

    def panel(self, cr, x0, h):
        cr.set_source_rgb(0.05, 0.06, 0.15)
        cr.rectangle(x0, 0, PANEL, h)
        cr.fill()
        x = x0 + 14
        self.text(cr, 'SPACE PINBALL', x, 28, 15, CYAN)
        rows = [('SCORE', f'{self.score:,}'), ('HIGH', f'{self.high:,}'), ('BALL', f'{min(self.ball_no, 3)} / 3'),
                ('BONUS', f'{self.bonus:,} x{self.mult}'), ('RANK', RANKS[self.rank()][0])]
        y = 62
        for k, v in rows:
            self.text(cr, k, x, y, 10, (0.55, 0.62, 0.85), bold=False)
            self.text(cr, v, x, y + 22, 19, (1, 1, 1))
            y += 56
        m = MISSIONS[self.missions_done % len(MISSIONS)]
        self.text(cr, 'MISSION', x, y, 10, (0.55, 0.62, 0.85), bold=False)
        self.text(cr, m[1], x, y + 18, 11, AMBER)
        self.text(cr, f'{self.mission_prog} / {m[2](self.missions_done)}', x, y + 36, 13)
        for i, line in enumerate(('Z / Left  left flipper', '/ / Right  right flipper', 'Space  hold: plunger')):
            self.text(cr, line, x, h - 52 + i * 15, 10, (0.55, 0.62, 0.85), bold=False)
        if self.paused:
            self.text(cr, 'PAUSED', x, h - 70, 14, AMBER)


if __name__ == '__main__':
    game = Pinball()
    mwx7ui.App('org.mwx7.pinball', 'Space Pinball', 'pinball', (int(W * SCALE) + PANEL, int(H * SCALE)), CSS, game.build,
               resizable=False).run_main()
