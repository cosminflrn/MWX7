#!/usr/bin/env python3
"""Drives a running QEMU VM (installed MWX 7, see smoke-test.sh "session") through QMP: signs in as test/test, waits for the
shell, and takes screenshots of the real Wayfire desktop (the only place bar, dock and Start can be seen: they are
layer-shell surfaces). Fails when the shell or Wayfire logged a Python traceback.

usage: session-test.py QMP_SOCKET SERIAL_LOG OUT_DIR [SCALE]   (SCALE multiplies every wait: 1 with KVM, ~6 with TCG)
"""
import json
import os
import socket
import sys
import time

QMP, SERIAL, OUT = sys.argv[1:4]
SCALE = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
os.makedirs(OUT, exist_ok=True)
problems = []


def log(msg):
    print(f'[session {time.strftime("%H:%M:%S")}] {msg}', flush=True)


class Qmp:
    def __init__(self, path):
        self.s = socket.socket(socket.AF_UNIX)
        for _ in range(60):
            try:
                self.s.connect(path)
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('QMP socket never appeared')
        self.f = self.s.makefile('rw')
        self.f.readline()  # greeting
        self.cmd('qmp_capabilities')

    def cmd(self, name, **args):
        self.f.write(json.dumps({'execute': name, 'arguments': args}) + '\n')
        self.f.flush()
        while True:
            r = json.loads(self.f.readline())
            if 'return' in r:
                return r['return']
            if 'error' in r:
                raise RuntimeError(f'{name}: {r["error"]["desc"]}')

    def key(self, *names, hold=120):
        self.cmd('send-key', keys=[{'type': 'qcode', 'data': n} for n in names], **{'hold-time': hold})

    def type(self, text):
        for ch in text:
            self.key('spc' if ch == ' ' else ch)
            time.sleep(0.15)

    def move(self, x, y, size, steps=6):
        """Pointer to pixel (x, y) with the usb-tablet (absolute 0..32767), in small steps so hover events happen."""
        w, h = size
        cx, cy = getattr(self, 'pos', (x, y))
        for i in range(1, steps + 1):
            px = int((cx + (x - cx) * i / steps) * 32767 / (w - 1))
            py = int((cy + (y - cy) * i / steps) * 32767 / (h - 1))
            self.cmd('input-send-event', events=[{'type': 'abs', 'data': {'axis': 'x', 'value': px}},
                                                  {'type': 'abs', 'data': {'axis': 'y', 'value': py}}])
            time.sleep(0.05)
        self.pos = (x, y)


def read_ppm(path):
    with open(path, 'rb') as f:
        data = f.read()
    parts = data.split(b'\n', 3)
    w, h = map(int, parts[1].split())
    return w, h, parts[3]


def shot(q, name):
    """Writes OUT/name.png (for people) and a PPM (for locating things); returns (w, h, rgb bytes) or None."""
    png = os.path.join(OUT, name + '.png')
    ppm = os.path.join(OUT, '.' + name + '.ppm')
    try:
        q.cmd('screendump', filename=png, format='png')
        q.cmd('screendump', filename=ppm, format='ppm')
        r = read_ppm(ppm)
        os.remove(ppm)
        log(f'screenshot {name}.png ({r[0]}x{r[1]})')
        return r
    except Exception as e:  # noqa: BLE001
        log(f'screenshot {name} failed: {e}')
        problems.append(f'screenshot {name} failed: {e}')
        return None


def serial_text():
    try:
        with open(SERIAL, 'rb') as f:
            return f.read().decode(errors='replace').replace('\r', '')
    except OSError:
        return ''


def wait_marker(marker, limit):
    end = time.time() + limit * SCALE
    while time.time() < end:
        if marker in serial_text():
            return True
        time.sleep(2)
    return False


def pixels(img, step=2):
    w, h, d = img
    for y in range(0, h, step):
        row = y * w * 3
        for x in range(0, w, step):
            i = row + x * 3
            yield x, y, d[i], d[i + 1], d[i + 2]


def find_lights(before, after):
    """The window's traffic lights: saturated red/yellow/green blobs that were not in the frame before the app opened."""
    w, h, b = before
    preds = {
        'red': lambda r, g, bl: r > 190 and g < 100 and bl < 100,
        'yellow': lambda r, g, bl: r > 200 and g > 160 and bl < 90,
        'green': lambda r, g, bl: g > 150 and r < 110 and bl < 110,
    }
    found = {}
    for name, p in preds.items():
        xs, ys = [], []
        for x, y, r, g, bl in pixels(after):
            i = (y * w + x) * 3
            if p(r, g, bl) and not p(b[i], b[i + 1], b[i + 2]) and y < h * 0.7:
                xs.append(x)
                ys.append(y)
        if len(xs) >= 12:
            # The topmost blob: a window's title bar is above anything else coloured that appeared with it.
            top = min(ys)
            sel = [(x, y) for x, y in zip(xs, ys) if y < top + 30]
            found[name] = (sum(x for x, _ in sel) // len(sel), sum(y for _, y in sel) // len(sel))
        log(f'traffic light {name}: {len(xs)} candidate pixels -> {found.get(name)}')
    return found


def main():
    if not wait_marker('MWX7-LOGON-READY', 600):
        problems.append('no MWX7-LOGON-READY (logon screen)')
        return
    q = Qmp(QMP)
    time.sleep(3 * SCALE)
    shot(q, '00-logon')
    # The greeter focuses the password field of the only account (test), see greeter.py choose(): type it, Enter.
    q.type('test')
    q.key('ret')
    if not wait_marker('MWX7-SESSION-READY', 300):
        problems.append('no MWX7-SESSION-READY (the shell did not start after sign-in)')
        shot(q, '01-no-session')
        return
    # First sign-in: the Welcome Center opens after ~4 s; close it (Alt+F4 closes the top window) so the desktop is clear.
    time.sleep(15 * SCALE)
    q.key('alt', 'f4')
    time.sleep(3 * SCALE)
    desktop = shot(q, '01-desktop')
    if desktop:
        q.move(desktop[0] // 2, desktop[1] // 2, size=(desktop[0], desktop[1]), steps=1)  # the pointer must exist for hovering
    q.key('meta_l')
    time.sleep(3 * SCALE)
    shot(q, '02-start-menu')
    q.type('notepad')
    time.sleep(2 * SCALE)
    shot(q, '02b-start-search')
    q.key('ret')
    time.sleep(25 * SCALE)  # Notepad is a Chrome app window: the first start is slow
    app = shot(q, '03-notepad')
    if not (desktop and app):
        return
    # Hover the traffic lights, found by colour (the window is placed by Wayfire, nobody knows where).
    # Compare against a desktop frame without the Start menu: the menu closed itself when Notepad opened.
    lights = find_lights(desktop, app)
    if not lights:
        problems.append('no traffic lights found in the Notepad window (is it drawn with our decorations?)')
    for name in ('close', 'minimize', 'maximize'):
        colour = {'close': 'red', 'minimize': 'yellow', 'maximize': 'green'}[name]
        if colour in lights:
            q.move(*lights[colour], size=(app[0], app[1]))
            time.sleep(1.5 * SCALE)
            shot(q, f'04-hover-{name}')
    # Move away so the final state is quiet.
    q.move(app[0] // 2, app[1] // 2, size=(app[0], app[1]), steps=3)
    time.sleep(10 * SCALE)  # the marker service reports the shell state every 10 s


try:
    main()
except Exception as e:  # noqa: BLE001
    problems.append(f'driver error: {e!r}')
finally:
    text = serial_text()
    with open(os.path.join(OUT, 'guest-session-markers.txt'), 'w') as f:
        f.write('\n'.join(l for l in text.split('\n') if 'MWX7-SESSION' in l or 'Traceback' in l or l.startswith(('  File', 'MWX7-'))))
    states = [l for l in text.split('\n') if l.startswith('MWX7-SESSION-STATE')]
    if 'MWX7-SESSION-READY' in text:
        if not states:
            log('no MWX7-SESSION-STATE report yet (too early?)')
        else:
            last = states[-1]
            log(last)
            if 'shell=0' in last or 'wayfire=0' in last:
                problems.append(f'the shell or Wayfire is not running at the end: {last}')
            if not last.endswith('tracebacks=0'):
                problems.append(f'Python traceback in the session logs: {last}')
    if 'MWX7-SESSION-LOG' in text:
        problems.append('MWX7-SESSION-LOG: a log with a traceback was dumped to the serial console (see the serial log)')
    if problems:
        for p in problems:
            print(f'SESSION PROBLEM: {p}', file=sys.stderr)
        sys.exit(1)
    log('ok')
