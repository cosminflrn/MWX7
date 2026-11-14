"""MWX 7 screen recorder (the Snipping Tool's Record mode, after Windows 11's): wf-recorder does the capture and the
H.264 encoding, this script chooses what to record, shows the small floating pill (red dot, elapsed time, Stop) and
announces the finished file.

  record.py start [--region|--full] [--audio none|mic|system]   records (a region is dragged with slurp first)
  record.py toggle                                              stops the running recording, or starts one with the
                                                                saved choices (Shift+Super+R)
  record.py stop                                                stops the running recording
  record.py --notify FILE [TEXT]                                the "Open / Show in folder" notification (internal)

Files go to ~/Videos/Screen Recordings/Recording YYYY-MM-DD HHMMSS.mp4. Stop sends wf-recorder SIGINT, which makes it
write the MP4 trailer; killing it any harder leaves a file that does not play."""
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

PREFS = os.path.expanduser('~/.config/mwx7/recorder.json')
PIDFILE = os.path.join(os.environ.get('XDG_RUNTIME_DIR') or '/tmp', f'mwx7-record-{os.getuid()}.pid')
RENDER_NODE = '/dev/dri/renderD128'
PILL_HEIGHT = 64  # pill plus its margin; a region this close to the screen edge leaves no room outside it
CSS = """
window.mwx7-rec-pill { background: transparent; }
window.mwx7-rec-pill .pill { background: rgba(24, 28, 38, .92); border: 1px solid rgba(255, 255, 255, .22);
  border-radius: 22px; padding: 6px 8px 6px 16px; box-shadow: 0 4px 16px rgba(0, 0, 0, .45); }
window.mwx7-rec-pill .dot { background: #e5322d; border-radius: 6px; min-width: 12px; min-height: 12px; }
window.mwx7-rec-pill .dot.off { opacity: .25; }
window.mwx7-rec-pill .time { color: #fff; font-weight: 600; font-size: 14px; min-width: 52px; }
window.mwx7-rec-pill .what { color: rgba(255, 255, 255, .6); font-size: 12px; }
window.mwx7-rec-pill button.stop { background: linear-gradient(to bottom, #f0605a, #c9211c); color: #fff; border: 1px solid #8f1410;
  border-radius: 14px; padding: 3px 14px; min-height: 0; font-weight: 600; box-shadow: none; }
window.mwx7-rec-pill button.stop:hover { background: linear-gradient(to bottom, #ff7c76, #d83630); }
"""


def load_prefs():
    try:
        with open(PREFS) as f:
            p = json.load(f)
    except (OSError, ValueError):
        p = {}
    return {'mode': p.get('mode') if p.get('mode') in ('region', 'full') else 'region',
            'audio': p.get('audio') if p.get('audio') in ('none', 'mic', 'system') else 'none'}


def save_prefs(mode, audio):
    try:
        os.makedirs(os.path.dirname(PREFS), exist_ok=True)
        with open(PREFS, 'w') as f:
            json.dump({'mode': mode, 'audio': audio}, f)
    except OSError:
        pass


def running_pid():
    """The pid of the recorder that is running now, or None (a stale pid file is ignored)."""
    try:
        pid = int(open(PIDFILE).read().strip())
        with open(f'/proc/{pid}/cmdline', 'rb') as f:
            return pid if b'record.py' in f.read() else None
    except (OSError, ValueError):
        return None


def out_dir():
    d = os.path.join(os.path.expanduser('~/Videos'), 'Screen Recordings')
    try:
        from gi.repository import GLib
        vids = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
        if vids:
            d = os.path.join(vids, 'Screen Recordings')
    except (ImportError, ValueError):
        pass
    return d


def notify(title, body, icon='media-record'):
    subprocess.Popen(['notify-send', '-a', 'Snipping Tool', '-i', icon, title, body], stderr=subprocess.DEVNULL)


def system_sink_monitor():
    """The monitor source of the default output ('what you hear'), from WirePlumber; None when it cannot be found."""
    try:
        out = subprocess.run(['wpctl', 'inspect', '@DEFAULT_AUDIO_SINK@'], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r'node\.name = "([^"]+)"', out)
    return m.group(1) + '.monitor' if m else None


def vaapi_h264():
    """True when the GPU can encode H.264 (vainfo lists an encode entry point). Without vainfo, x264 is used."""
    if not os.path.exists(RENDER_NODE):
        return False
    try:
        out = subprocess.run(['vainfo', '--display', 'drm', '--device', RENDER_NODE], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(re.search(r'H264\w*\s*:\s*VAEntrypointEncSlice', out))


def even_geometry(geo):
    """slurp's 'x,y WxH' with an even width and height, which yuv420p (needed to play everywhere) requires."""
    m = re.match(r'(-?\d+),(-?\d+) (\d+)x(\d+)', geo.strip())
    if not m:
        return None
    x, y, w, h = (int(v) for v in m.groups())
    w, h = w - w % 2, h - h % 2
    return f'{x},{y} {w}x{h}' if w >= 16 and h >= 16 else None


def recorder_cmd(path, geometry, output, audio, hw):
    cmd = ['wf-recorder', '-y', '-f', path]
    if geometry:
        cmd += ['-g', geometry]
    elif output:
        cmd += ['-o', output]
    if hw:
        cmd += ['-c', 'h264_vaapi', '-d', RENDER_NODE]
    else:
        # veryfast keeps the CPU load low enough to record while working; crf 23 is x264's visually-fine default.
        cmd += ['-c', 'libx264', '-p', 'preset=veryfast', '-p', 'crf=23', '-x', 'yuv420p']
    if audio == 'mic':
        cmd += ['--audio']
    elif audio == 'system':
        mon = system_sink_monitor()
        cmd += [f'--audio={mon}'] if mon else ['--audio']
    if audio != 'none':
        cmd += ['-C', 'aac']
    return cmd


def screen_locked():
    uid = str(os.getuid())
    for pat in (['pgrep', '-u', uid, '-x', 'swaylock'], ['pgrep', '-u', uid, '-f', '[m]wx7-lockscreen']):
        if subprocess.run(pat, capture_output=True).returncode == 0:
            return True
    return False


def pick_region():
    try:
        r = subprocess.run(['slurp', '-d', '-b', '#1e64dc22', '-c', '#1e64dcff', '-w', '2'], capture_output=True, text=True,
                           timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def fmt(secs):
    return f'{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}' if secs >= 3600 else f'{secs // 60:02d}:{secs % 60:02d}'


class Recording:
    def __init__(self, mode, audio, geometry):
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        gi.require_version('Gtk4LayerShell', '1.0')
        from gi.repository import Gdk, GLib, Gtk
        from gi.repository import Gtk4LayerShell as Layer
        self.Gtk, self.GLib, self.Gdk, self.Layer = Gtk, GLib, Gdk, Layer
        self.mode, self.audio, self.geometry = mode, audio, geometry
        self.proc, self.stopping, self.reason, self.started = None, False, None, 0
        self.path = os.path.join(out_dir(), time.strftime('Recording %Y-%m-%d %H%M%S.mp4'))
        self.hw = vaapi_h264()
        self.err = ''
        Gtk.init()
        self.loop = GLib.MainLoop()
        self.build()

    # ---- the pill ----------------------------------------------------------------------------------------------------
    def build(self):
        Gtk, Gdk, Layer = self.Gtk, self.Gdk, self.Layer
        css = Gtk.CssProvider()
        css.load_from_data(CSS.encode())
        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.win = w = Gtk.Window(title='Screen recording', resizable=False, decorated=False)
        w.add_css_class('mwx7-rec-pill')
        box = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        box.add_css_class('pill')
        self.dot = Gtk.Box(valign=Gtk.Align.CENTER)
        self.dot.add_css_class('dot')
        self.time = Gtk.Label(label='00:00', xalign=0)
        self.time.add_css_class('time')
        what = Gtk.Label(label={'none': '', 'mic': 'Microphone', 'system': 'System audio'}[self.audio])
        what.add_css_class('what')
        stop = Gtk.Button(label='Stop', tooltip_text='Stop recording (Shift+Super+R)')
        stop.add_css_class('stop')
        stop.connect('clicked', lambda *_: self.stop())
        for c in (self.dot, self.time) + ((what,) if self.audio != 'none' else ()) + (stop,):
            box.append(c)
        w.set_child(box)
        Layer.init_for_window(w)
        Layer.set_layer(w, Layer.Layer.OVERLAY)
        Layer.set_namespace(w, 'mwx7-recording')
        Layer.set_keyboard_mode(w, Layer.KeyboardMode.NONE)
        Layer.set_exclusive_zone(w, 0)
        # The pill is part of the screen, so wf-recorder would film it. A region recording puts it on the side of the region
        # with room; only a full-screen recording (or a region that leaves no room) shows it in the video.
        edge = Layer.Edge.TOP
        mons = display.get_monitors()
        mon = mons.get_item(0) if mons.get_n_items() else None
        if self.geometry and mon:
            x, y, _w, gh = (int(v) for v in re.match(r'(-?\d+),(-?\d+) (\d+)x(\d+)', self.geometry).groups())
            for i in range(mons.get_n_items()):
                g = mons.get_item(i).get_geometry()
                if g.x <= x < g.x + g.width and g.y <= y < g.y + g.height:
                    mon = mons.get_item(i)
                    break
            g = mon.get_geometry()
            if y - g.y < PILL_HEIGHT + 30 and (g.y + g.height) - (y + gh) >= PILL_HEIGHT:
                edge = Layer.Edge.BOTTOM
        if mon:
            Layer.set_monitor(w, mon)
        self.output = mon.get_connector() if mon else None
        Layer.set_anchor(w, edge, True)
        Layer.set_margin(w, edge, 12)
        w.present()

    # ---- recording ---------------------------------------------------------------------------------------------------
    def begin(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            self.spawn()
        except OSError:
            notify('Recording did not start', 'wf-recorder is not installed.')
            self.loop.quit()
            return False
        self.started = time.monotonic()
        self.GLib.timeout_add(500, self.tick)
        return False

    def spawn(self):
        self.proc = subprocess.Popen(recorder_cmd(self.path, self.geometry, self.output, self.audio, self.hw),
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        # Drained on a thread so a chatty recorder never fills the pipe, and kept for the failure message.
        threading.Thread(target=self.drain, args=(self.proc,), daemon=True).start()

    def drain(self, proc):
        for line in proc.stderr:
            self.err = (self.err + line)[-600:]

    def tick(self):
        if self.proc is None:
            return False
        code = self.proc.poll()
        if code is not None:
            if self.hw and not self.stopping and time.monotonic() - self.started < 4:
                # The GPU encoder refused (VMs, old drivers): the software encoder always works.
                self.hw, self.err = False, ''
                self.spawn()
                self.started = time.monotonic()
                return True
            self.finished(code)
            return False
        secs = int(time.monotonic() - self.started)
        self.time.set_label('Saving...' if self.stopping else fmt(secs))
        self.dot.set_css_classes(['dot'] + (['off'] if secs % 2 and not self.stopping else []))
        if not self.stopping and secs % 2 == 0 and screen_locked():
            self.stop('The screen was locked, so the recording was stopped and saved.')
        return True

    def stop(self, reason=None):
        if self.stopping or self.proc is None:
            return
        self.stopping, self.reason = True, reason
        self.time.set_label('Saving...')
        # SIGINT: wf-recorder flushes the encoder and writes the MP4 trailer. tick() sees it exit; a recorder that has not
        # finished in 20 s is hung, and only then is it killed.
        self.proc.send_signal(signal.SIGINT)
        self.GLib.timeout_add_seconds(20, self.force)

    def force(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        return False

    def finished(self, code):
        self.win.close()
        ok = os.path.exists(self.path) and os.path.getsize(self.path) > 0 and (self.stopping or code == 0)
        if ok:
            args = [sys.executable, os.path.abspath(__file__), '--notify', self.path] + ([self.reason] if self.reason else [])
            subprocess.Popen(args, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            last = self.err.strip().splitlines()[-1] if self.err.strip() else 'The recorder stopped unexpectedly.'
            notify('Recording failed', last[:160])
        self.loop.quit()

    def run(self):
        with open(PIDFILE, 'w') as f:
            f.write(str(os.getpid()))
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            self.GLib.unix_signal_add(self.GLib.PRIORITY_HIGH, sig, lambda: (self.stop(), True)[1])
        # After slurp's overlay has gone from the screen, so it is not the first frame.
        self.GLib.timeout_add(400, self.begin)
        self.loop.run()
        try:
            os.unlink(PIDFILE)
        except OSError:
            pass


def announce(path, reason=None):
    """Waits on the notification (a process of its own, since notify-send -w blocks) and acts on the button pressed."""
    name = os.path.basename(path)
    answer = subprocess.run(['notify-send', '-a', 'Snipping Tool', '-i', 'media-record', '-A', 'open=Open', '-A',
                             'folder=Show in folder', '-w', 'Recording saved', (reason + '\n' if reason else '') + name],
                            capture_output=True, text=True).stdout.strip()
    if answer == 'open':
        subprocess.Popen(['xdg-open', path], start_new_session=True, stderr=subprocess.DEVNULL)
    elif answer == 'folder':
        subprocess.Popen(['/usr/share/mwx7/bin/mwx7-app', 'explorer', os.path.dirname(path)], start_new_session=True,
                         stderr=subprocess.DEVNULL)


def main(argv):
    if argv and argv[0] == '--notify':
        announce(argv[1], argv[2] if len(argv) > 2 else None)
        return 0
    cmd = argv[0] if argv else 'toggle'
    pid = running_pid()
    if cmd in ('stop', 'toggle') and pid:
        os.kill(pid, signal.SIGTERM)
        return 0
    if cmd == 'stop' or cmd not in ('start', 'toggle'):
        return 0 if cmd == 'stop' else 2
    if pid:
        return 0
    prefs = load_prefs()
    mode, audio, i = prefs['mode'], prefs['audio'], 1
    while i < len(argv):
        if argv[i] == '--region':
            mode = 'region'
        elif argv[i] == '--full':
            mode = 'full'
        elif argv[i] == '--audio' and i + 1 < len(argv) and argv[i + 1] in ('none', 'mic', 'system'):
            audio, i = argv[i + 1], i + 1
        i += 1
    save_prefs(mode, audio)
    geometry = None
    if mode == 'region':
        geometry = even_geometry(pick_region() or '')
        if not geometry:
            return 0  # Esc in slurp: nothing to record
    Recording(mode, audio, geometry).run()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
