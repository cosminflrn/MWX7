"""Calendar (native): a month grid with today highlighted (week numbers optional), week and day lists, events with title,
all-day or a time range, repeat (daily / weekly / monthly / yearly), a reminder, and .ics import / export. Events live in
~/.local/share/mwx7/calendar.ics (read by the bar's calendar flyout and by mwx7-reminders, which sends the notifications).
The menus are the top bar's (see mwx7ui.App.menubar), as in the other native apps."""
import os
import sys

# Named calendarapp.py so it never shadows the standard calendar module for the apps beside it; and its own folder is
# dropped from sys.path all the same, as a belt and braces.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != _HERE]

import datetime as dt  # noqa: E402
import json  # noqa: E402

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ics as ics  # noqa: E402
import mwx7ui  # noqa: E402
from mwx7ui import Gio, GLib, Gtk, Pango  # noqa: E402

D, DT = dt.date, dt.datetime
CONFIG = os.path.join(GLib.get_user_config_dir(), 'mwx7', 'calendar.json')
MONDAY = D(2024, 1, 1)  # a Monday: the weekday names come from it, in the person's language
CHIPS = 3  # events shown in a month cell before "+N more"
REMINDERS = [(None, 'None'), (0, 'At time of event'), (5, '5 minutes before'), (10, '10 minutes before'),
             (15, '15 minutes before'), (30, '30 minutes before'), (60, '1 hour before'), (120, '2 hours before'),
             (1440, '1 day before'), (2880, '2 days before'), (10080, '1 week before')]
REPEATS = [None, 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY']
REPEAT_NAMES = ['Never', 'Daily', 'Weekly', 'Monthly', 'Yearly']
UNITS = {'DAILY': 'day(s)', 'WEEKLY': 'week(s)', 'MONTHLY': 'month(s)', 'YEARLY': 'year(s)'}

CSS = """
window.mwx7-calendar > box { background: #f4f7fb; }
.ca-bar { padding: 6px 8px; background: linear-gradient(180deg, #f6faff, #dce8f6); border-bottom: 1px solid #a9c1de; }
.ca-bar button { min-height: 24px; min-width: 24px; padding: 2px 8px; border-radius: 3px; background: none;
  border: 1px solid transparent; box-shadow: none; color: #1c3150; }
.ca-bar button:hover { background: linear-gradient(180deg, #f4f9ff, #d6e7fa); border-color: #9bbbe3; }
.ca-bar button:checked { background: linear-gradient(180deg, #cfe3fa, #aecdf2); border-color: #6d9ad0; }
.ca-bar .ca-new { background: linear-gradient(180deg, #5da2ec, #2a6fc1); color: #fff; border-color: #1f5aa3; font-weight: 600; }
.ca-bar .ca-new:hover { background: linear-gradient(180deg, #74b2f4, #3a80d2); border-color: #1f5aa3; }
.ca-title { font-size: 17px; font-weight: 300; color: #1e3f66; margin: 0 10px; }
.ca-views button:checked { color: #0f3a73; }
.ca-dow { font-size: 11px; font-weight: 600; color: #5b7396; padding: 5px 0; background: #eaf0f8; border-bottom: 1px solid #c9d6e6; }
.ca-wk { font-size: 10px; color: #8a9bb3; padding: 2px 4px; }
.ca-cell { background: #ffffff; border-right: 1px solid #dbe4ef; border-bottom: 1px solid #dbe4ef; padding: 2px 3px; }
.ca-cell.other { background: #f6f8fb; }
.ca-cell.other .ca-num { color: #a3afc0; }
.ca-cell.weekend { background: #fbfcfe; }
.ca-cell.sel { background: #eef6ff; box-shadow: inset 0 0 0 1px #9cc8ef; }
.ca-cell.today { background: #e3f0fd; box-shadow: inset 0 0 0 2px #3b8be0; }
.ca-num { font-size: 12px; color: #243a57; padding: 1px 4px; }
.ca-cell.today .ca-num { background: #2a6fc1; color: #fff; border-radius: 9px; font-weight: 600; }
.ca-chip { min-height: 0; padding: 0 5px; margin: 1px 0; border-radius: 3px; font-size: 11px; box-shadow: none; border: 1px solid; }
.ca-more { font-size: 11px; color: #2a6fc1; padding: 0 5px; }
.ca-chip.c0, .ca-bar0 { background: #d9ebfc; border-color: #9cc8ef; color: #12427a; }
.ca-chip.c1, .ca-bar1 { background: #dcf3dc; border-color: #9fd49f; color: #1d5a1d; }
.ca-chip.c2, .ca-bar2 { background: #fdebd0; border-color: #e8bf80; color: #6a4210; }
.ca-chip.c3, .ca-bar3 { background: #f6dbe8; border-color: #dc9bbd; color: #6a1f45; }
.ca-chip.c4, .ca-bar4 { background: #e6dcf6; border-color: #b9a2e0; color: #3d2468; }
.ca-sw.ca-bar0 { background: #4b94e0; } .ca-sw.ca-bar1 { background: #55b055; } .ca-sw.ca-bar2 { background: #e3993a; }
.ca-sw.ca-bar3 { background: #d0629a; } .ca-sw.ca-bar4 { background: #8c6bd0; }
.ca-chip:hover { filter: brightness(0.96); }
.ca-list { padding: 10px 16px 16px; }
.ca-dayhead { font-size: 13px; font-weight: 600; color: #1e3f66; padding: 10px 4px 4px; border-bottom: 1px solid #c9d6e6; }
.ca-dayhead.today { color: #2a6fc1; }
.ca-none { color: #8a9bb3; padding: 6px 8px; font-size: 12px; }
button.ca-row { background: none; border: 1px solid transparent; box-shadow: none; padding: 4px 8px; border-radius: 3px; min-height: 0; }
button.ca-row:hover { background: #eaf4ff; border-color: #b7d5f2; }
.ca-time { font-size: 12px; color: #4a6384; min-width: 110px; }
.ca-sw { min-width: 5px; border-radius: 2px; margin: 1px 8px 1px 0; border-width: 0; }
.ca-name { font-size: 13px; color: #1a2b44; }
.ca-sub { font-size: 11px; color: #6b7f9b; }
.ca-status { font-size: 11px; color: #4a6384; padding: 3px 10px; background: #eaf0f8; border-top: 1px solid #c9d6e6; }
window.ca-editor { background: #f4f7fb; }
window.ca-editor .ca-form { padding: 14px 16px 6px; }
window.ca-editor .ca-lab { color: #4a6384; font-size: 12px; }
window.ca-editor .ca-err { color: #b3261e; font-size: 12px; }
window.ca-editor .ca-buttons { padding: 10px 16px 14px; }
window.ca-editor textview { min-height: 56px; padding: 4px; border: 1px solid #a9c1de; border-radius: 3px; }
"""


def day_span(s, e):
    """The dates an occurrence covers (an all-day end is exclusive; a timed one ending exactly at midnight stops before it)."""
    d = s if type(s) is D else s.date()
    last = (e - dt.timedelta(days=1)) if type(s) is D else ((e - dt.timedelta(seconds=1)).date() if e > s else d)
    out = []
    while d <= max(last, s if type(s) is D else s.date()) and len(out) < 60:
        out.append(d)
        d += dt.timedelta(days=1)
    return out


def span_text(s, e, day=None):
    """'All day' / '09:00 - 10:30' for the list views (a multi-day one says so from its second day on)."""
    if type(s) is D:
        return 'All day'
    first, last = s.date(), (e - dt.timedelta(seconds=1)).date() if e > s else s.date()
    if day and day != first and day != last:
        return 'All day'
    if day and day == last and first != last:
        return 'until ' + e.strftime('%H:%M')
    return s.strftime('%H:%M') + (' - ' + e.strftime('%H:%M') if e > s and first == last else '')


def chip_text(s, title, day):
    return (s.strftime('%H:%M ') if type(s) is DT and s.date() == day else '') + (title or '(no title)')


def color_of(ev):
    return sum(ev.uid.encode()) % 5


def month_label(d):
    return d.strftime('%B %Y')


def long_day(d):
    return d.strftime('%A, ') + str(d.day) + d.strftime(' %B %Y')


class DateButton(Gtk.MenuButton):
    """A date shown as text; clicking it opens a month to pick from."""

    def __init__(self, date, changed=None):
        super().__init__(hexpand=False)
        self.date, self.changed = date, changed
        self.cal = Gtk.Calendar()
        pop = Gtk.Popover()
        pop.set_child(self.cal)
        self.set_popover(pop)
        self.pop = pop
        self.last_month = None
        self.set_date(date)
        self.cal.connect('day-selected', self.picked)

    def set_date(self, date):
        self.date = date
        self.last_month = (date.year, date.month)
        self.cal.select_day(GLib.DateTime.new_local(date.year, date.month, date.day, 0, 0, 0))
        self.set_label(date.strftime('%a ') + str(date.day) + date.strftime(' %b %Y'))

    def picked(self, cal):
        g = cal.get_date()
        d = D(g.get_year(), g.get_month(), g.get_day_of_month())
        # Month arrows move the selection too: only a click on a day of the same month closes the picker.
        same_month = (d.year, d.month) == self.last_month
        self.last_month = (d.year, d.month)
        if d == self.date:
            return
        self.date = d
        self.set_label(d.strftime('%a ') + str(d.day) + d.strftime(' %b %Y'))
        if same_month:
            self.pop.popdown()
        if self.changed:
            self.changed(d)


def spin(lo, hi, value, step=1):
    s = Gtk.SpinButton.new_with_range(lo, hi, step)
    s.set_value(value)
    s.set_wrap(True)
    s.set_width_chars(2)
    s.set_numeric(True)
    s.connect('output', lambda w: w.set_text('%02d' % w.get_value_as_int()) or True)
    return s


class Editor:
    """The New / Edit event window."""

    def __init__(self, app, ev, day):
        self.app, self.new = app, ev is None
        if ev is None:
            now = DT.now()
            start = DT.combine(day, dt.time(now.hour + 1 if now.hour < 23 else 23) if day == D.today() else dt.time(9))
            ev = ics.Event('', start, start + dt.timedelta(hours=1))
            ev.reminder = 15
        self.ev = ev
        w = self.win = mwx7ui.dialog(app.win, 'New Event' if self.new else 'Edit Event', 'calendar')
        w.add_css_class('ca-editor')
        w.set_resizable(False)
        w.set_default_size(460, -1)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        form = Gtk.Grid(column_spacing=10, row_spacing=8, css_classes=['ca-form'])
        row = [0]

        def add(label, *widgets):
            lab = Gtk.Label(label=label, xalign=1, valign=Gtk.Align.CENTER, css_classes=['ca-lab'])
            form.attach(lab, 0, row[0], 1, 1)
            box = Gtk.Box(spacing=6)
            box.lab = lab
            for x in widgets:
                box.append(x)
            form.attach(box, 1, row[0], 1, 1)
            row[0] += 1
            return box

        self.title = Gtk.Entry(hexpand=True, placeholder_text='Event title', text=ev.summary)
        self.title.connect('activate', lambda *_a: self.save())
        add('Title', self.title)
        self.where = Gtk.Entry(hexpand=True, placeholder_text='Location (optional)', text=ev.location)
        add('Where', self.where)
        self.allday = Gtk.CheckButton(label='All day', active=ev.allday)
        add('', self.allday)

        sdate = ev.start if ev.allday else ev.start.date()
        edate = (ev.end - dt.timedelta(days=1)) if ev.allday else ev.end.date()
        if edate < sdate:
            edate = sdate
        stime = dt.time(9) if ev.allday else ev.start.time()
        etime = dt.time(10) if ev.allday else ev.end.time()
        self.sdate, self.edate = DateButton(sdate, self.start_moved), DateButton(edate)
        self.sh, self.sm = spin(0, 23, stime.hour), spin(0, 59, stime.minute)
        self.eh, self.em = spin(0, 23, etime.hour), spin(0, 59, etime.minute)
        self.stimes = [self.sh, Gtk.Label(label=':'), self.sm]
        self.etimes = [self.eh, Gtk.Label(label=':'), self.em]
        add('Starts', self.sdate, *self.stimes)
        add('Ends', self.edate, *self.etimes)
        self.allday.connect('toggled', self.sync)

        self.repeat = Gtk.DropDown.new_from_strings(REPEAT_NAMES)
        rule = ev.rule
        self.repeat.set_selected(REPEATS.index(rule['freq']) if rule else 0)
        self.every = Gtk.SpinButton.new_with_range(1, 99, 1)
        self.every.set_value(rule['interval'] if rule else 1)
        self.unit = Gtk.Label(label='')
        self.rbox = add('Repeat', self.repeat)
        self.ebox = Gtk.Box(spacing=6)
        for x in (Gtk.Label(label='every'), self.every, self.unit):
            self.ebox.append(x)
        self.rbox.append(self.ebox)
        self.until_kind = Gtk.DropDown.new_from_strings(['Forever', 'For', 'Until'])
        self.count = Gtk.SpinButton.new_with_range(1, 999, 1)
        u = rule['until'] if rule and rule['until'] else sdate + dt.timedelta(days=30)
        self.until = DateButton(u if type(u) is D else u.date())
        self.times_lab = Gtk.Label(label='times')
        if rule and rule['count']:
            self.until_kind.set_selected(1)
            self.count.set_value(rule['count'])
        elif rule and rule['until']:
            self.until_kind.set_selected(2)
        else:
            self.count.set_value(10)
        self.ubox = add('Repeat ends', self.until_kind, self.count, self.times_lab, self.until)
        self.repeat.connect('notify::selected', self.sync)
        self.until_kind.connect('notify::selected', self.sync)

        self.remind = Gtk.DropDown()
        opts = list(REMINDERS)
        if ev.reminder is not None and ev.reminder not in [m for m, _l in opts]:
            opts.append((ev.reminder, '%d minutes before' % ev.reminder))
        self.opts = opts
        self.remind.set_model(Gtk.StringList.new([l for _m, l in opts]))
        self.remind.set_selected(next(i for i, (m, _l) in enumerate(opts) if m == ev.reminder))
        add('Reminder', self.remind)

        self.notes = Gtk.TextView(hexpand=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.notes.get_buffer().set_text(ev.description)
        scroll = Gtk.ScrolledWindow(hexpand=True, min_content_height=64, child=self.notes)
        add('Notes', scroll)
        self.err = Gtk.Label(xalign=0, css_classes=['ca-err'], wrap=True)
        form.attach(self.err, 1, row[0], 1, 1)
        col.append(form)

        bar = Gtk.Box(spacing=8, css_classes=['ca-buttons'])
        if not self.new:
            d = Gtk.Button(label='Delete series' if ev.rule else 'Delete')
            d.connect('clicked', lambda *_a: self.delete())
            bar.append(d)
        bar.append(Gtk.Box(hexpand=True))
        cancel = Gtk.Button(label='Cancel')
        cancel.connect('clicked', lambda *_a: w.destroy())
        ok = Gtk.Button(label='Save', css_classes=['suggested-action'])
        ok.connect('clicked', lambda *_a: self.save())
        bar.append(cancel)
        bar.append(ok)
        col.append(bar)
        w.set_child(col)
        self.sync()
        w.present()
        self.title.grab_focus()

    def start_moved(self, d):
        # The end follows the start, keeping the length: the usual calendar behaviour.
        if self.edate.date < d:
            self.edate.set_date(d)

    def sync(self, *_a):
        timed = not self.allday.get_active()
        for x in self.stimes + self.etimes:
            x.set_visible(timed)
        freq = REPEATS[self.repeat.get_selected()]
        self.ebox.set_visible(bool(freq))
        kind = self.until_kind.get_selected()
        self.until_kind.set_visible(bool(freq))
        self.ubox.lab.set_visible(bool(freq))
        self.count.set_visible(bool(freq) and kind == 1)
        self.times_lab.set_visible(bool(freq) and kind == 1)
        self.until.set_visible(bool(freq) and kind == 2)
        self.unit.set_label(UNITS.get(freq, ''))

    def collect(self):
        sd, ed = self.sdate.date, self.edate.date
        if self.allday.get_active():
            start, end = sd, ed + dt.timedelta(days=1)
        else:
            start = DT.combine(sd, dt.time(self.sh.get_value_as_int(), self.sm.get_value_as_int()))
            end = DT.combine(ed, dt.time(self.eh.get_value_as_int(), self.em.get_value_as_int()))
        if end < start or (self.allday.get_active() and ed < sd):
            return None
        ev = self.ev.clone()
        ev.summary = self.title.get_text().strip()
        ev.location = self.where.get_text().strip()
        b = self.notes.get_buffer()
        ev.description = b.get_text(b.get_start_iter(), b.get_end_iter(), False).strip()
        if (type(start) is D) != (type(self.ev.start) is D) or start != self.ev.start:
            if (start if type(start) is D else start.date()) != (self.ev.start if type(self.ev.start) is D else self.ev.start.date()):
                ev.exdates = set()
        ev.start, ev.end = start, end
        freq = REPEATS[self.repeat.get_selected()]
        if freq:
            kind = self.until_kind.get_selected()
            old = self.ev.rule or {}
            same_day = (start if type(start) is D else start.date()) == (
                self.ev.start if type(self.ev.start) is D else self.ev.start.date())
            ev.rule = {'freq': freq, 'interval': self.every.get_value_as_int(),
                       'count': self.count.get_value_as_int() if kind == 1 else None,
                       'until': self.until.date if kind == 2 else None,
                       'byday': old.get('byday', []) if freq == 'WEEKLY' and old.get('freq') == 'WEEKLY' and same_day else []}
        else:
            ev.rule = None
        ev.reminder = self.opts[self.remind.get_selected()][0]
        return ev

    def save(self):
        ev = self.collect()
        if ev is None:
            self.err.set_label('The event ends before it starts.')
            return
        self.win.destroy()
        self.app.put(ev)

    def delete(self):
        self.win.destroy()
        self.app.remove(self.ev)


class Calendar:
    def __init__(self):
        self.events = ics.load()
        try:
            self.cfg = json.load(open(CONFIG))
        except (OSError, ValueError):
            self.cfg = {}
        if self.cfg.get('view') not in ('month', 'week', 'day'):
            self.cfg['view'] = 'month'
        self.view = self.cfg['view']
        self.weeks = bool(self.cfg.get('weeks', False))
        self.cursor = D.today()

    # ---- window ------------------------------------------------------------------------------------------------------
    def build(self, app, win):
        self.app, self.win = app, win
        win.add_css_class('mwx7-calendar')
        app.on_open = lambda files: self.import_path(files[0].get_path())
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('File', [('New Event', 'new', lambda: self.edit(None)), None,
                      ('Import .ics…', 'import', self.import_dialog), ('Export .ics…', 'export', self.export_dialog)]),
            ('View', [('Month', 'vmonth', lambda: self.set_view('month')), ('Week', 'vweek', lambda: self.set_view('week')),
                      ('Day', 'vday', lambda: self.set_view('day')), None,
                      ('Show / Hide Week Numbers', 'weeks', self.toggle_weeks)]),
            ('Go', [('Today', 'today', lambda: self.go_today()), ('Previous', 'prev', lambda: self.step(-1)),
                    ('Next', 'next', lambda: self.step(1))]),
        ]))
        for action, accels in (('new', ['<Ctrl>n']), ('import', ['<Ctrl>o']), ('export', ['<Ctrl>s']), ('today', ['<Ctrl>t']),
                               ('prev', ['<Alt>Left']), ('next', ['<Alt>Right'])):
            app.set_accels_for_action('app.' + action, accels)
        root.append(self.build_bar())
        self.body = Gtk.ScrolledWindow(vexpand=True, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        root.append(self.body)
        self.status = Gtk.Label(xalign=0, css_classes=['ca-status'])
        root.append(self.status)
        self.render()
        # Another program (Import elsewhere, a sync tool) may change the file: follow it.
        try:
            self.mon = Gio.File.new_for_path(ics.STORE).monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.mon.connect('changed', self.file_changed)
        except GLib.Error:
            self.mon = None
        win.connect('close-request', lambda *_a: self.save_config() or False)
        return root

    def build_bar(self):
        bar = Gtk.Box(spacing=4, css_classes=['ca-bar'])
        new = Gtk.Button(label='New Event', css_classes=['ca-new'])
        new.connect('clicked', lambda *_a: self.edit(None))
        today = Gtk.Button(label='Today')
        today.connect('clicked', lambda *_a: self.go_today())
        prev = Gtk.Button(icon_name='go-previous-symbolic', tooltip_text='Previous')
        nxt = Gtk.Button(icon_name='go-next-symbolic', tooltip_text='Next')
        prev.connect('clicked', lambda *_a: self.step(-1))
        nxt.connect('clicked', lambda *_a: self.step(1))
        self.title = Gtk.Label(xalign=0, hexpand=True, css_classes=['ca-title'])
        views = Gtk.Box(css_classes=['linked', 'ca-views'])
        self.vbtns = {}
        first = None
        for key, label in (('month', 'Month'), ('week', 'Week'), ('day', 'Day')):
            b = Gtk.ToggleButton(label=label, group=first)
            first = first or b
            b.connect('toggled', lambda b_, k=key: b_.get_active() and self.set_view(k))
            self.vbtns[key] = b
            views.append(b)
        for w in (new, Gtk.Separator(margin_start=4, margin_end=4), today, prev, nxt, self.title, views):
            bar.append(w)
        return bar

    # ---- state -------------------------------------------------------------------------------------------------------
    def save_config(self):
        self.cfg.update(view=self.view, weeks=self.weeks)
        try:
            os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
            json.dump(self.cfg, open(CONFIG, 'w'))
        except OSError:
            pass

    def say(self, text):
        self.status.set_label(text)

    def set_view(self, view):
        self.view = view
        self.vbtns[view].set_active(True)
        self.render()

    def toggle_weeks(self):
        self.weeks = not self.weeks
        self.render()

    def go_today(self):
        self.cursor = D.today()
        self.render()

    def step(self, n):
        c = self.cursor
        if self.view == 'month':
            y, m = ics.add_months(c.replace(day=1), n)
            c = D(y, m, min(c.day, 28))
        else:
            c += dt.timedelta(days=n * (7 if self.view == 'week' else 1))
        self.cursor = c
        self.render()

    def file_changed(self, _m, _f, _o, event):
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.DELETED):
            if self.writing:
                return
            self.events = ics.load()
            self.render()

    writing = False

    def persist(self):
        self.writing = True
        try:
            ics.save(self.events)
        except OSError as e:
            self.say('Couldn’t save the calendar: ' + (e.strerror or str(e)))
        finally:
            GLib.timeout_add(400, lambda: setattr(self, 'writing', False))
        self.render()

    def put(self, ev):
        self.events = [e for e in self.events if e.uid != ev.uid] + [ev]
        self.persist()
        self.say('Saved “%s”.' % (ev.summary or '(no title)'))

    def remove(self, ev):
        self.events = [e for e in self.events if e.uid != ev.uid]
        self.persist()
        self.say('Deleted “%s”.' % (ev.summary or '(no title)'))

    def edit(self, ev, day=None):
        Editor(self, ev, day or self.cursor)

    # ---- import / export -----------------------------------------------------------------------------------------------
    def ics_filter(self):
        flt = Gtk.FileFilter(name='iCalendar (.ics)')
        flt.add_mime_type('text/calendar')
        flt.add_suffix('ics')
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        return store

    def import_dialog(self):
        dlg = mwx7ui.FileDialog(title='Import', filters=self.ics_filter())

        def done(d, res):
            try:
                self.import_path(d.open_finish(res).get_path())
            except GLib.Error:
                pass
        dlg.open(self.win, None, done)

    def import_path(self, path):
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                new = ics.parse(f.read())
        except OSError as e:
            self.say('Couldn’t read %s: %s' % (os.path.basename(path), e.strerror))
            return
        if not new:
            self.say('No events found in %s.' % os.path.basename(path))
            return
        ids = {e.uid for e in new}
        updated = sum(1 for e in self.events if e.uid in ids)
        self.events = [e for e in self.events if e.uid not in ids] + new
        self.persist()
        self.say('Imported %d event%s from %s%s.' % (len(new), '' if len(new) == 1 else 's', os.path.basename(path),
                                                   ' (%d updated)' % updated if updated else ''))
        first = min((e.start if type(e.start) is D else e.start.date() for e in new), default=None)
        if first and self.view == 'month' and not any(
                True for _ in ics.occurrences(new, DT.combine(self.cursor.replace(day=1), dt.time()),
                                              DT.combine(self.cursor.replace(day=1) + dt.timedelta(days=32), dt.time()))):
            self.cursor = first
            self.render()

    def export_dialog(self):
        dlg = mwx7ui.FileDialog(title='Export', initial_name='calendar.ics', filters=self.ics_filter())

        def done(d, res):
            try:
                path = d.save_finish(res).get_path()
            except GLib.Error:
                return
            if not path.lower().endswith('.ics'):
                path += '.ics'
            try:
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(ics.serialize(self.events))
                self.say('Exported %d events to %s.' % (len(self.events), path))
            except OSError as e:
                self.say('Couldn’t write %s: %s' % (path, e.strerror))
        dlg.save(self.win, None, done)

    # ---- drawing -----------------------------------------------------------------------------------------------------
    def range(self):
        c = self.cursor
        if self.view == 'month':
            first = c.replace(day=1)
            lo = first - dt.timedelta(days=first.weekday())
            return lo, lo + dt.timedelta(days=42)
        if self.view == 'week':
            lo = c - dt.timedelta(days=c.weekday())
            return lo, lo + dt.timedelta(days=7)
        return c, c + dt.timedelta(days=1)

    def by_day(self, lo, hi):
        days = {}
        for s, e, ev in ics.occurrences(self.events, DT.combine(lo, dt.time()), DT.combine(hi, dt.time())):
            for d in day_span(s, e):
                if lo <= d < hi:
                    days.setdefault(d, []).append((s, e, ev))
        return days

    def render(self):
        lo, hi = self.range()
        c = self.cursor
        if self.view == 'month':
            self.title.set_label(month_label(c))
        elif self.view == 'week':
            end = hi - dt.timedelta(days=1)
            self.title.set_label('%d %s – %d %s' % (lo.day, lo.strftime('%b' if lo.year == end.year else '%b %Y'), end.day,
                                                  end.strftime('%b %Y')))
        else:
            self.title.set_label(long_day(c))
        for k, b in self.vbtns.items():
            if b.get_active() != (k == self.view):
                b.set_active(k == self.view)
        days = self.by_day(lo, hi)
        self.body.set_child(self.month(lo, days) if self.view == 'month' else self.listing(lo, hi, days))

    def month(self, lo, days):
        # Equal columns (homogeneous), so the week number sits inside each Monday cell rather than in a column of its own.
        grid = Gtk.Grid(column_homogeneous=True, hexpand=True, vexpand=True)
        for i in range(7):
            grid.attach(Gtk.Label(label=(MONDAY + dt.timedelta(days=i)).strftime('%a'), css_classes=['ca-dow']), i, 0, 1, 1)
        for i in range(42):
            d = lo + dt.timedelta(days=i)
            grid.attach(self.cell(d, days.get(d, [])), i % 7, i // 7 + 1, 1, 1)
        return grid

    def cell(self, d, items):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True, css_classes=['ca-cell'])
        box.set_size_request(100, 86)
        if d.month != self.cursor.month:
            box.add_css_class('other')
        if d.weekday() >= 5:
            box.add_css_class('weekend')
        if d == D.today():
            box.add_css_class('today')
        elif d == self.cursor:
            box.add_css_class('sel')
        top = Gtk.Box()
        top.append(Gtk.Label(label=str(d.day) if d.day != 1 else d.strftime('%-d %b'), xalign=0, css_classes=['ca-num']))
        if self.weeks and d.weekday() == 0:
            top.append(Gtk.Label(label='Wk %d' % d.isocalendar()[1], hexpand=True, xalign=1, css_classes=['ca-wk']))
        box.append(top)
        for s, e, ev in items[:CHIPS]:
            b = Gtk.Button(css_classes=['ca-chip', 'c%d' % color_of(ev)], tooltip_text=ev.summary)
            lab = Gtk.Label(label=chip_text(s, ev.summary, d), xalign=0, ellipsize=Pango.EllipsizeMode.END)
            b.set_child(lab)
            b.connect('clicked', lambda _b, ev=ev: self.edit(ev))
            box.append(b)
        if len(items) > CHIPS:
            more = Gtk.Label(label='+%d more' % (len(items) - CHIPS), xalign=0, css_classes=['ca-more'])
            box.append(more)
        click = Gtk.GestureClick()

        def pressed(_g, n, _x, _y):
            if n >= 2:
                self.cursor = d
                self.edit(None, d)
            elif len(items) > CHIPS:
                self.cursor = d
                self.set_view('day')
            else:
                self.cursor = d
                self.render()
        click.connect('pressed', pressed)
        box.add_controller(click)
        return box

    def listing(self, lo, hi, days):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['ca-list'])
        d = lo
        while d < hi:
            head = Gtk.Label(label=long_day(d) + ('  ·  Today' if d == D.today() else ''), xalign=0, css_classes=['ca-dayhead'])
            if d == D.today():
                head.add_css_class('today')
            col.append(head)
            items = days.get(d, [])
            if not items:
                col.append(Gtk.Label(label='No events', xalign=0, css_classes=['ca-none']))
            for s, e, ev in items:
                col.append(self.row(d, s, e, ev))
            d += dt.timedelta(days=1)
        return col

    def row(self, d, s, e, ev):
        b = Gtk.Button(css_classes=['ca-row'])
        line = Gtk.Box()
        line.append(Gtk.Label(label=span_text(s, e, d), xalign=0, valign=Gtk.Align.START, css_classes=['ca-time']))
        line.append(Gtk.Box(css_classes=['ca-sw', 'ca-bar%d' % color_of(ev)]))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        text.append(Gtk.Label(label=ev.summary or '(no title)', xalign=0, css_classes=['ca-name'], wrap=True))
        sub = [x for x in (ev.location, 'Repeats ' + ev.rule['freq'].lower() if ev.rule else '',
                           'Reminder' if ev.reminder is not None else '') if x]
        if sub:
            text.append(Gtk.Label(label='  ·  '.join(sub), xalign=0, css_classes=['ca-sub']))
        line.append(text)
        b.set_child(line)
        b.connect('clicked', lambda *_a: self.edit(ev))
        return b


if __name__ == '__main__':
    cal = Calendar()
    mwx7ui.App('org.mwx7.calendar', 'Calendar', 'calendar', (940, 660), CSS, cal.build).run_main()
