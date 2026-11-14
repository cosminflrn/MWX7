#!/usr/bin/env python3
"""Drives a running QEMU VM (installed MWX 7, see smoke-test.sh "session") through QMP: signs in as test/test, waits for the
shell, and takes screenshots of the real Wayfire desktop (the only place bar, dock and Start can be seen: they are
layer-shell surfaces). Fails when the shell or Wayfire logged a Python traceback.

usage: session-test.py QMP_SOCKET SERIAL_LOG OUT_DIR [SCALE]   (SCALE multiplies every wait: 1 with KVM, ~6 with TCG)
"""
import json
import os
import re
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


def click(q, x, y, size):
    q.move(x, y, size, steps=4)
    time.sleep(0.3)
    for down in (True, False):
        q.cmd('input-send-event', events=[{'type': 'btn', 'data': {'button': 'left', 'down': down}}])
        time.sleep(0.1)


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
    """The window's traffic lights. Red is the topmost new red blob (nothing else red appears with a window). Yellow and green
    are then searched only in the title bar row to the right of red: the busy widget background of the desktop (yellow and green
    pixels all over it) confused a whole-screen search."""
    w, h, b = before
    red_p = lambda r, g, bl: r > 190 and g < 100 and bl < 100  # noqa: E731
    xs, ys = [], []
    for x, y, r, g, bl in pixels(after):
        i = (y * w + x) * 3
        if red_p(r, g, bl) and not red_p(b[i], b[i + 1], b[i + 2]) and y < h * 0.7:
            xs.append(x)
            ys.append(y)
    found = {}
    log(f'traffic light red: {len(xs)} candidate pixels')
    if len(xs) < 12:
        return found
    top = min(ys)
    sel = [(x, y) for x, y in zip(xs, ys) if y < top + 30]
    rx, ry = sum(x for x, _ in sel) // len(sel), sum(y for _, y in sel) // len(sel)
    found['red'] = (rx, ry)
    d = after[2]
    preds = {'yellow': lambda r, g, bl: r > 200 and g > 160 and bl < 90,
             'green': lambda r, g, bl: g > 150 and r < 110 and bl < 110}
    for name, p in preds.items():
        px, py = [], []
        for y in range(max(0, ry - 8), ry + 9):
            for x in range(rx + 6, min(w, rx + 90)):
                i = (y * w + x) * 3
                if p(d[i], d[i + 1], d[i + 2]):
                    px.append(x)
                    py.append(y)
        if len(px) >= 12:
            found[name] = (sum(px) // len(px), sum(py) // len(py))
        log(f'traffic light {name}: {len(px)} candidate pixels in the title bar row -> {found.get(name)}')
    return found


def states():
    return [l for l in serial_text().split('\n') if l.startswith('MWX7-SESSION-STATE')]


tb_seen = 0
crashed = {}   # app -> first traceback lines
shots = []     # (file, what)


def traceback_excerpt():
    lines = serial_text().split('\n')
    idx = [i for i, l in enumerate(lines) if 'Traceback' in l]
    if not idx:
        return ''
    return '\n'.join(lines[idx[-1]: idx[-1] + 14])


def check_app(label, mark):
    """After an app was open for a while: wait for the next session-marker report (every 10 s) and see whether the
    traceback count in the shell/Wayfire logs grew; if so the app (or the shell reacting to it) crashed."""
    global tb_seen
    end = time.time() + 16 * SCALE
    while time.time() < end and len(states()) <= mark:
        time.sleep(1)
    st = states()
    if len(st) <= mark:
        log(f'{label}: no marker report to check')
        return
    m = re.search(r'tracebacks=(\d+)', st[-1])
    n = int(m.group(1)) if m else 0
    if n > tb_seen:
        crashed[label] = traceback_excerpt()
        problems.append(f'{label}: a Python traceback appeared while it was open ({n - tb_seen} new)')
        log(f'{label}: CRASH\n{crashed[label]}')
    else:
        log(f'{label}: no new traceback')
    tb_seen = max(tb_seen, n)


def open_app(q, label, query, name, wait=8):
    """Start menu -> type the query -> Enter, one screenshot, check the logs, Alt+F4."""
    q.key('meta_l')
    time.sleep(2.5 * SCALE)
    q.type(query)
    time.sleep(1.5 * SCALE)
    q.key('ret')
    time.sleep(wait * SCALE)
    shot(q, name)
    shots.append((name + '.png', label))
    check_app(label, len(states()))
    q.key('alt', 'f4')
    time.sleep(2 * SCALE)


def flyout(q, label, x, y, name, size):
    click(q, x, y, size)
    time.sleep(2.5 * SCALE)
    shot(q, name)
    shots.append((name + '.png', label))
    check_app(label, len(states()))
    click(q, x, y, size)  # a second click on the same button closes the flyout
    time.sleep(1.5 * SCALE)


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
    global tb_seen
    st = states()
    m = re.search(r'tracebacks=(\d+)', st[-1]) if st else None
    tb_seen = int(m.group(1)) if m else 0  # what the shell logged before the tour is not an app's fault
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
    app = shot(q, '03-notepad-opened')
    # The desktop widgets sit exactly where Wayfire places a new window's title bar, which hid the yellow/green lights from a
    # colour search: tile the window to the left half first (Super+Left, the [grid] binding), where nothing else is coloured.
    q.key('meta_l', 'left')
    time.sleep(3 * SCALE)
    app = shot(q, '03-notepad') or app
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
    # Move away, close Notepad, then the tour of the main apps.
    q.move(app[0] // 2, app[1] // 2, size=(app[0], app[1]), steps=3)
    for f, what in (('03-notepad-opened.png', 'Notepad as opened'), ('03-notepad.png', 'Notepad tiled left'), ('04-hover-close.png', 'Notepad close light'),
                    ('04-hover-minimize.png', 'Notepad minimize light'), ('04-hover-maximize.png', 'Notepad maximize light')):
        if os.path.exists(os.path.join(OUT, f)):
            shots.append((f, what))
    check_app('Notepad', len(states()))
    q.key('alt', 'f4')
    time.sleep(3 * SCALE)
    size = (app[0], app[1])
    # Apps by Start search; "display" and "updates" are Settings pages (search lists them under Settings).
    for i, (label, query) in enumerate((
            ('Settings', 'settings'), ('Settings: Display', 'display'), ('Settings: Updates', 'updates'),
            ('My Computer', 'my computer'), ('Reader', 'reader'), ('Calendar', 'calendar'), ('Task Manager', 'task manager'),
            ('Get Apps', 'get apps'), ('Paint', 'paint'), ('Snipping Tool', 'snipping tool'), ('Terminal', 'terminal')), 5):
        open_app(q, label, query, f'{i:02d}-{re.sub("[^a-z]+", "-", label.lower()).strip("-")}')
    # Snipping Tool may leave its capture overlay up (Escape ends it); make sure the bar is reachable.
    q.key('esc')
    time.sleep(1 * SCALE)
    # The bar's clock flyout and the notification centre have no keyboard shortcut: click them (bar on top, right-aligned:
    # ... clock, bell).
    w = size[0]
    flyout(q, 'Clock flyout', w - 95, 14, '16-clock-flyout', size)
    flyout(q, 'Notification center', w - 18, 14, '17-notification-center', size)
    q.move(w // 2, size[1] // 2, size=size, steps=3)
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
    with open(os.path.join(OUT, 'summary.md'), 'w') as f:
        f.write('## MWX 7 desktop tour\n\n')
        f.write('**Result: FAILED**\n\n' if problems else '**Result: passed**\n\n')
        if crashed:
            f.write('### Apps that produced a Python traceback\n\n')
            for k, v in crashed.items():
                f.write(f'- **{k}**\n\n```\n{v}\n```\n\n')
        if problems:
            f.write('### Problems\n\n' + ''.join(f'- {p}\n' for p in problems) + '\n')
        f.write('### Screenshots (artifact `smoke-serial-logs`, folder `distro/out/session/`)\n\n')
        f.write('- 00-logon.png: logon screen\n- 01-desktop.png: desktop\n- 02-start-menu.png, 02b-start-search.png: Start menu, search\n')
        for fn, what in shots:
            f.write(f'- {fn}: {what}\n')
    if problems:
        for p in problems:
            print(f'SESSION PROBLEM: {p}', file=sys.stderr)
        sys.exit(1)
    log('ok')
