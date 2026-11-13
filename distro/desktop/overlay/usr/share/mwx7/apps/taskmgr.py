"""Task Manager (native): Windows 7's three tabs. Applications (the open windows; End Task closes one), Processes
(this account's programs with CPU and memory; End Process), Performance (CPU and memory graphs). Updates every second."""
import json
import os
import signal
import socket
import struct
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import GLib, Gtk  # noqa: E402

HISTORY = 60
CSS = """
window.mwx7-taskmgr > box { background: #f0f4fa; }
.tm-tabs { padding: 6px 8px 0; }
.tm-list { background: #ffffff; border: 1px solid #a9b9cf; }
.tm-list row { padding: 2px 8px; }
.tm-list row:selected { background: linear-gradient(180deg, #dcebfc, #c1dcfc); color: #0b2440; }
.tm-head { padding: 3px 8px; font-weight: 600; color: #1e3f66; background: linear-gradient(180deg, #ffffff, #e4ecf6);
  border: 1px solid #a9b9cf; border-bottom: none; }
.tm-empty { color: #6b7b92; }
.tm-num { font-feature-settings: "tnum"; color: #1c2530; }
.tm-graph { background: #000000; border: 1px solid #4d5c70; }
.tm-cap { font-weight: 600; color: #1e3f66; margin-top: 6px; }
.tm-status { padding: 3px 10px; font-size: 11px; color: #33475f; border-top: 1px solid #c3d0e0; background: #e8eef6; }
"""


def ipc(method, data=None):
    path = os.environ.get('WAYFIRE_SOCKET') or '/tmp/wayfire-wayland-1.socket'
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(2)
        s.connect(path)
        body = json.dumps({'method': method, 'data': data or {}}).encode()
        s.sendall(struct.pack('<I', len(body)) + body)
        n = struct.unpack('<I', s.recv(4))[0]
        buf = b''
        while len(buf) < n:
            buf += s.recv(n - len(buf))
        s.close()
        return json.loads(buf)
    except (OSError, ValueError, struct.error):
        return None


def cpu_times():
    with open('/proc/stat') as f:
        parts = [int(x) for x in f.readline().split()[1:]]
    idle = parts[3] + parts[4]
    return sum(parts), idle


def meminfo():
    m = {}
    with open('/proc/meminfo') as f:
        for line in f:
            k, v = line.split(':', 1)
            m[k] = int(v.split()[0])
    return m['MemTotal'], m['MemTotal'] - m.get('MemAvailable', m['MemFree'])


class TaskManager:
    def __init__(self):
        self.prev_total, self.prev_idle = cpu_times()
        self.prev_proc = {}
        self.cpu_hist, self.mem_hist = [0.0] * HISTORY, [0.0] * HISTORY
        self.uid = os.getuid()
        self.ticks = os.sysconf('SC_CLK_TCK')
        self.page = os.sysconf('SC_PAGE_SIZE')

    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-taskmgr')
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stack = Gtk.Stack(vexpand=True, margin_start=8, margin_end=8, margin_bottom=8)
        sw = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.START)
        sw.add_css_class('tm-tabs')
        root.append(sw)
        root.append(self.stack)
        # Applications
        apps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8)
        head = Gtk.Box()
        head.add_css_class('tm-head')
        head.append(Gtk.Label(label='Task', xalign=0, hexpand=True))
        head.append(Gtk.Label(label='Status', width_chars=12, xalign=0))
        apps.append(head)
        self.app_list = Gtk.ListBox()
        self.app_list.add_css_class('tm-list')
        # Shown by GTK itself whenever the list has no rows, so it needs no bookkeeping in the refresh code.
        none = Gtk.Label(label='No applications are open.\nPrograms you start will show up here.',
                         justify=Gtk.Justification.CENTER, margin_top=60)
        none.add_css_class('tm-empty')
        self.app_list.set_placeholder(none)
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.app_list)
        apps.append(sc)
        row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        b = Gtk.Button(label='End Task')
        b.connect('clicked', lambda *_: self.end_task())
        sw2 = Gtk.Button(label='Switch To')
        sw2.connect('clicked', lambda *_: self.switch_to())
        row.append(b)
        row.append(sw2)
        apps.append(row)
        self.stack.add_titled(apps, 'apps', 'Applications')
        # Processes
        procs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8)
        head = Gtk.Box()
        head.add_css_class('tm-head')
        for text, w, x in (('Image Name', 0, 0), ('PID', 7, 1), ('CPU', 6, 1), ('Memory', 11, 1)):
            l = Gtk.Label(label=text, xalign=x, hexpand=not w)
            if w:
                l.set_width_chars(w)
            head.append(l)
        procs.append(head)
        self.proc_list = Gtk.ListBox()
        self.proc_list.add_css_class('tm-list')
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.proc_list)
        procs.append(sc)
        row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        b = Gtk.Button(label='End Process')
        b.connect('clicked', lambda *_: self.end_process())
        row.append(b)
        procs.append(row)
        self.stack.add_titled(procs, 'procs', 'Processes')
        # Performance
        perf = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=8)
        for cap, hist, color in (('CPU Usage History', 'cpu', (0.2, 1.0, 0.3)), ('Physical Memory Usage History', 'mem', (0.35, 0.8, 1.0))):
            perf.append(Gtk.Label(label=cap, xalign=0, css_classes=['tm-cap']))
            da = Gtk.DrawingArea(vexpand=True)
            da.add_css_class('tm-graph')
            da.set_draw_func(self.graph, (hist, color))
            setattr(self, hist + '_graph', da)
            perf.append(da)
        self.perf_text = Gtk.Label(xalign=0, css_classes=['tm-num'])
        perf.append(self.perf_text)
        self.stack.add_titled(perf, 'perf', 'Performance')
        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class('tm-status')
        root.append(self.status)
        self.tick()
        GLib.timeout_add_seconds(1, self.tick)
        return root

    # ---- data -----------------------------------------------------------------------------------------------------
    def tick(self):
        total, idle = cpu_times()
        dt = max(1, total - self.prev_total)
        cpu = 100 * (1 - (idle - self.prev_idle) / dt)
        self.prev_total, self.prev_idle = total, idle
        mt, mu = meminfo()
        self.cpu_hist = self.cpu_hist[1:] + [cpu]
        self.mem_hist = self.mem_hist[1:] + [100 * mu / mt]
        procs = self.processes(dt)
        self.status.set_label(f'Processes: {len(procs)}    CPU Usage: {cpu:.0f}%    '
                              f'Physical Memory: {100 * mu / mt:.0f}%')
        page = self.stack.get_visible_child_name()
        if page == 'apps':
            self.fill_apps()
        elif page == 'procs':
            self.fill_procs(procs)
        else:
            self.cpu_graph.queue_draw()
            self.mem_graph.queue_draw()
            self.perf_text.set_label(f'CPU {cpu:.0f}% · {os.cpu_count()} threads    Memory {mu / 1048576:.1f} GB of '
                                     f'{mt / 1048576:.1f} GB    Up {self.uptime()}')
        return True

    @staticmethod
    def uptime():
        s = int(float(open('/proc/uptime').read().split()[0]))
        return f'{s // 86400}d {s % 86400 // 3600:02d}:{s % 3600 // 60:02d}' if s >= 86400 else f'{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}'

    def processes(self, dt_total):
        out, now = [], {}
        ncpu = os.cpu_count() or 1
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                st = os.stat(f'/proc/{pid}')
                with open(f'/proc/{pid}/stat') as f:
                    raw = f.read()
                name = raw[raw.index('(') + 1:raw.rindex(')')]
                fields = raw[raw.rindex(')') + 2:].split()
                used = int(fields[11]) + int(fields[12])
                rss = int(fields[21]) * self.page
            except (OSError, ValueError, IndexError):
                continue
            now[pid] = used
            if st.st_uid != self.uid:
                continue
            cpu = 100 * ncpu * (used - self.prev_proc.get(pid, used)) / dt_total
            try:
                cmd = open(f'/proc/{pid}/cmdline', 'rb').read().split(b'\0')
                if name in ('python3', 'sh') and len(cmd) > 1 and cmd[1]:
                    name = os.path.basename(cmd[1].decode(errors='replace'))
            except OSError:
                pass
            out.append((int(pid), name, cpu, rss))
        self.prev_proc = now
        out.sort(key=lambda p: (-p[2], -p[3]))
        return out

    # ---- tabs -----------------------------------------------------------------------------------------------------
    def keep_selection(self, lst):
        r = lst.get_selected_row()
        return getattr(r, 'key', None) if r else None

    def fill_apps(self):
        views = ipc('window-rules/list-views') or []
        keep = self.keep_selection(self.app_list)
        while (r := self.app_list.get_row_at_index(0)) is not None:
            self.app_list.remove(r)
        for v in views:
            if v.get('role') != 'toplevel' or not v.get('mapped', True) or v.get('app-id') == 'org.mwx7.taskmgr':
                continue
            row = Gtk.ListBoxRow()
            row.key = v['id']
            box = Gtk.Box(spacing=8)
            box.append(Gtk.Label(label=v.get('title') or v.get('app-id') or '?', xalign=0, hexpand=True, ellipsize=3))
            box.append(Gtk.Label(label='Minimized' if v.get('minimized') else 'Running', width_chars=12, xalign=0))
            row.set_child(box)
            self.app_list.append(row)
            if row.key == keep:
                self.app_list.select_row(row)

    def fill_procs(self, procs):
        keep = self.keep_selection(self.proc_list)
        while (r := self.proc_list.get_row_at_index(0)) is not None:
            self.proc_list.remove(r)
        for pid, name, cpu, rss in procs:
            row = Gtk.ListBoxRow()
            row.key = pid
            box = Gtk.Box()
            box.append(Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3))
            for text, w in ((str(pid), 7), (f'{cpu:.0f}', 6), (f'{rss // 1024:,} K', 11)):
                l = Gtk.Label(label=text, xalign=1, width_chars=w)
                l.add_css_class('tm-num')
                box.append(l)
            row.set_child(box)
            self.proc_list.append(row)
            if pid == keep:
                self.proc_list.select_row(row)

    def graph(self, _a, cr, w, h, data):
        which, color = data
        hist = self.cpu_hist if which == 'cpu' else self.mem_hist
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        cr.set_source_rgb(0, 0.35, 0.12)
        cr.set_line_width(1)
        step = 12
        off = (len(hist) * 3) % step
        for x in range(-off, w, step):
            cr.move_to(x + 0.5, 0)
            cr.line_to(x + 0.5, h)
        for y in range(0, h, step):
            cr.move_to(0, y + 0.5)
            cr.line_to(w, y + 0.5)
        cr.stroke()
        cr.set_source_rgb(*color)
        cr.set_line_width(1.5)
        for i, v in enumerate(hist):
            x = w * i / (len(hist) - 1)
            y = h - 2 - (h - 4) * max(0, min(100, v)) / 100
            (cr.move_to if i == 0 else cr.line_to)(x, y)
        cr.stroke()

    # ---- actions --------------------------------------------------------------------------------------------------
    def end_task(self):
        r = self.app_list.get_selected_row()
        if r:
            ipc('window-rules/close-view', {'id': r.key})

    def switch_to(self):
        r = self.app_list.get_selected_row()
        if r:
            ipc('wm-actions/set-minimized', {'view_id': r.key, 'state': False})
            ipc('window-rules/focus-view', {'id': r.key})

    def end_process(self):
        r = self.proc_list.get_selected_row()
        if not r:
            return
        pid = r.key
        dlg = Gtk.AlertDialog(message='End this process?', detail='Unsaved work in it will be lost.',
                              buttons=['End Process', 'Cancel'], default_button=1, cancel_button=1)

        def done(d, res):
            try:
                if d.choose_finish(res) == 0:
                    os.kill(pid, signal.SIGTERM)
            except (GLib.Error, OSError):
                pass
        dlg.choose(self.win, None, done)


if __name__ == '__main__':
    tm = TaskManager()
    mwx7ui.App('org.mwx7.taskmgr', 'Task Manager', 'taskmgr', (520, 560), CSS, tm.build).run_main()
