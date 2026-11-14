"""A small iCalendar (RFC 5545) reader and writer for MWX 7's Calendar, the reminders helper and the bar's calendar flyout.

Only what a desktop calendar needs: VEVENT with SUMMARY / DESCRIPTION / LOCATION / DTSTART / DTEND / DURATION, RRULE
(FREQ DAILY|WEEKLY|MONTHLY|YEARLY, INTERVAL, COUNT, UNTIL, and BYDAY for weekly), EXDATE and one display VALARM. Everything is
kept as *local* time: TZID is ignored (treated as local) and a UTC time ("...Z") is converted to local on reading, so there is
no timezone database to ship. Anything else in a file (other components, unknown properties) is not kept.
Pure Python, no GTK: distro/tests/test_ics.py runs it without a display."""
import datetime as dt
import os
import re
import time
import uuid

D = dt.date
DT = dt.datetime
STORE = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'), 'mwx7', 'calendar.ics')
DAYS = ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')
FREQS = ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')
LIMIT = 5000  # occurrences looked at for one event in one query: a runaway rule cannot hang the app


# ---- text ------------------------------------------------------------------------------------------------------------
def unfold(text):
    """RFC 5545 3.1: a line starting with a space or tab continues the one before it."""
    out = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if line[:1] in (' ', '\t') and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def fold(line):
    """Lines go out at most 75 octets long, split between characters, continuation lines starting with a space."""
    parts, cur, n = [], '', 0
    limit = 75
    for ch in line:
        w = len(ch.encode())
        if n + w > limit:
            parts.append(cur)
            cur, n, limit = '', 0, 74  # the leading space counts
        cur += ch
        n += w
    parts.append(cur)
    return '\r\n '.join(parts)


def esc(s):
    return s.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\r\n', '\\n').replace('\n', '\\n')


def unesc(s):
    return re.sub(r'\\([nN\\;,])', lambda m: '\n' if m.group(1) in 'nN' else m.group(1), s)


def split_prop(line):
    """'DTSTART;TZID=Europe/Paris:20260101T090000' -> ('DTSTART', {'TZID': 'Europe/Paris'}, '20260101T090000')."""
    quoted = False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ':' and not quoted:
            head, value = line[:i], line[i + 1:]
            break
    else:
        return None
    bits = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', head)
    params = {}
    for b in bits[1:]:
        k, _, v = b.partition('=')
        params[k.upper()] = v.strip('"')
    return bits[0].upper(), params, value


# ---- dates -----------------------------------------------------------------------------------------------------------
def parse_when(value, params):
    """A date (VALUE=DATE or 8 digits) or a local datetime. 'Z' times are UTC and become local; TZID is taken as local."""
    v = value.strip()
    if params.get('VALUE') == 'DATE' or re.fullmatch(r'\d{8}', v):
        return D(int(v[0:4]), int(v[4:6]), int(v[6:8]))
    m = re.fullmatch(r'(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)(\d\d)?(Z?)', v)
    if not m:
        raise ValueError('bad date-time: ' + value)
    y, mo, d, h, mi, s = (int(m.group(i) or 0) for i in range(1, 7))
    t = DT(y, mo, d, h, mi, s)
    if m.group(7):
        t = DT.fromtimestamp(calendar_timegm(t))
    return t


def calendar_timegm(t):
    import calendar  # imported here: the Calendar app's own file is named calendar.py
    return calendar.timegm(t.timetuple())


def fmt_when(t):
    return t.strftime('%Y%m%d') if type(t) is D else t.strftime('%Y%m%dT%H%M%S')


def parse_duration(v):
    m = re.fullmatch(r'([+-]?)P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?', v.strip())
    if not m:
        raise ValueError('bad duration: ' + v)
    sign = -1 if m.group(1) == '-' else 1
    w, d, h, mi, s = (int(g or 0) for g in m.groups()[1:])
    return sign * dt.timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


def fmt_minutes(minutes):
    """-PT15M style trigger for 'minutes before'."""
    if minutes == 0:
        return 'PT0S'
    return '-PT%dM' % minutes if minutes % 60 else '-PT%dH' % (minutes // 60)


# ---- events ----------------------------------------------------------------------------------------------------------
class Event:
    """start / end: dates for an all-day event (end is the day after the last one, as in iCalendar), otherwise local
    datetimes. rule: None or {'freq', 'interval', 'count', 'until', 'byday'}. reminder: minutes before, or None."""

    def __init__(self, summary='', start=None, end=None, rule=None, reminder=None, description='', location='', uid=None):
        self.uid = uid or uuid.uuid4().hex + '@mwx7'
        self.summary, self.description, self.location = summary, description, location
        self.start = start or DT.now().replace(minute=0, second=0, microsecond=0)
        self.end = end or (self.start + (dt.timedelta(days=1) if type(self.start) is D else dt.timedelta(hours=1)))
        self.rule, self.reminder, self.exdates = rule, reminder, set()

    @property
    def allday(self):
        return type(self.start) is D

    @property
    def length(self):
        return self.end - self.start

    def clone(self):
        e = Event(self.summary, self.start, self.end, dict(self.rule) if self.rule else None, self.reminder,
                  self.description, self.location, self.uid)
        e.exdates = set(self.exdates)
        return e


def parse_rrule(value):
    parts = dict(p.split('=', 1) for p in value.split(';') if '=' in p)
    freq = parts.get('FREQ', '').upper()
    if freq not in FREQS:
        return None  # HOURLY, MINUTELY...: shown once rather than wrongly
    rule = {'freq': freq, 'interval': max(1, int(parts.get('INTERVAL', 1) or 1)), 'count': None, 'until': None, 'byday': []}
    if parts.get('COUNT', '').isdigit():
        rule['count'] = int(parts['COUNT'])
    if parts.get('UNTIL'):
        rule['until'] = parse_when(parts['UNTIL'], {})
    # "1MO" or "-1FR" (nth weekday) is beyond what the editor offers: only plain weekday names are kept.
    rule['byday'] = [d for d in (x.strip().upper() for x in parts.get('BYDAY', '').split(',')) if d in DAYS]
    return rule


def format_rrule(rule):
    s = 'FREQ=' + rule['freq']
    if rule.get('interval', 1) > 1:
        s += ';INTERVAL=%d' % rule['interval']
    if rule.get('byday') and rule['freq'] == 'WEEKLY':
        s += ';BYDAY=' + ','.join(rule['byday'])
    if rule.get('count'):
        s += ';COUNT=%d' % rule['count']
    elif rule.get('until'):
        u = rule['until']
        s += ';UNTIL=' + fmt_when(u)
    return s


def parse(text):
    """The events of an .ics text. A broken event is skipped, not fatal: one bad line must not lose the whole file."""
    events, cur, alarm = [], None, None
    for line in unfold(text):
        up = line.upper()
        if up == 'BEGIN:VEVENT':
            cur, alarm = {'props': []}, None
        elif up == 'END:VEVENT' and cur is not None:
            try:
                e = build(cur)
                if e:
                    events.append(e)
            except (ValueError, KeyError, OverflowError):
                pass
            cur = None
        elif cur is None:
            continue
        elif up == 'BEGIN:VALARM':
            alarm = True
        elif up == 'END:VALARM':
            alarm = None
        else:
            p = split_prop(line)
            if p:
                cur['props'].append((p[0], p[1], p[2], bool(alarm)))
    return events


def build(c):
    props = c['props']

    def first(name, alarm=False):
        return next(((p, v) for n, p, v, a in props if n == name and a == alarm), None)
    s = first('DTSTART')
    if not s:
        return None
    start = parse_when(s[1], s[0])
    e = first('DTEND')
    dur = first('DURATION')
    if e:
        end = parse_when(e[1], e[0])
    elif dur:
        end = start + parse_duration(dur[1])
    else:
        end = start + (dt.timedelta(days=1) if type(start) is D else dt.timedelta())
    if type(end) is not type(start):  # a mixed pair: trust the start
        end = start + (dt.timedelta(days=1) if type(start) is D else dt.timedelta())
    if end < start:
        end = start
    ev = Event(unesc((first('SUMMARY') or ({}, ''))[1]), start, end, uid=(first('UID') or ({}, ''))[1] or None,
               description=unesc((first('DESCRIPTION') or ({}, ''))[1]), location=unesc((first('LOCATION') or ({}, ''))[1]))
    r = first('RRULE')
    if r:
        ev.rule = parse_rrule(r[1])
    for n, p, v, a in props:
        if n == 'EXDATE' and not a:
            for piece in v.split(','):
                try:
                    ev.exdates.add(parse_when(piece, p))
                except ValueError:
                    pass
    t = first('TRIGGER', True)
    if t and t[0].get('RELATED', 'START').upper() == 'START' and t[0].get('VALUE', 'DURATION').upper() == 'DURATION':
        try:
            d = parse_duration(t[1])
            ev.reminder = max(0, int(-d.total_seconds() // 60))
        except ValueError:
            pass
    return ev


def serialize(events, prodid='-//MWX 7//Calendar//EN'):
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:' + prodid, 'CALSCALE:GREGORIAN']
    stamp = time.strftime('%Y%m%dT%H%M%S', time.gmtime()) + 'Z'
    for e in events:
        lines += ['BEGIN:VEVENT', 'UID:' + e.uid, 'DTSTAMP:' + stamp]
        if e.allday:
            lines += ['DTSTART;VALUE=DATE:' + fmt_when(e.start), 'DTEND;VALUE=DATE:' + fmt_when(e.end)]
        else:
            lines += ['DTSTART:' + fmt_when(e.start), 'DTEND:' + fmt_when(e.end)]
        lines.append('SUMMARY:' + esc(e.summary))
        if e.description:
            lines.append('DESCRIPTION:' + esc(e.description))
        if e.location:
            lines.append('LOCATION:' + esc(e.location))
        if e.rule:
            lines.append('RRULE:' + format_rrule(e.rule))
        for x in sorted(e.exdates, key=fmt_when):
            lines.append(('EXDATE;VALUE=DATE:' if type(x) is D else 'EXDATE:') + fmt_when(x))
        if e.reminder is not None:
            lines += ['BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:' + esc(e.summary or 'Reminder'),
                      'TRIGGER:' + fmt_minutes(e.reminder), 'END:VALARM']
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return ''.join(fold(l) + '\r\n' for l in lines)


# ---- recurrence ------------------------------------------------------------------------------------------------------
def add_months(d, n):
    m = d.month - 1 + n
    return d.year + m // 12, m % 12 + 1


def starts(e, hi):
    """The start of each occurrence in order, up to (not past) `hi`, honouring COUNT, UNTIL and EXDATE."""
    r = e.rule
    s = e.start
    day = s if type(s) is D else s.date()
    tod = None if type(s) is D else s.time()
    count, n = (r or {}).get('count'), 0
    until = (r or {}).get('until')
    if until is not None and type(until) is D and tod is not None:
        until = DT.combine(until, dt.time(23, 59, 59))  # a date UNTIL covers its whole day
    elif until is not None and type(until) is not type(s):
        until = until.date() if type(s) is D else until
    gen = _days(day, r) if r else iter([day])
    for i, d in enumerate(gen):
        if i > LIMIT:
            return
        o = d if tod is None else DT.combine(d, tod)
        if (DT.combine(o, dt.time()) if tod is None else o) > hi or (until is not None and o > until):
            return
        n += 1
        if count and n > count:
            return
        if o in e.exdates or (tod is not None and o.date() in e.exdates):
            continue
        yield o


def _days(day, r):
    step = r['interval']
    f = r['freq']
    if f == 'DAILY':
        k = 0
        while True:
            yield day + dt.timedelta(days=k * step)
            k += 1
    elif f == 'WEEKLY':
        wds = sorted(DAYS.index(x) for x in r['byday']) or [day.weekday()]
        monday = day - dt.timedelta(days=day.weekday())
        k = 0
        while True:
            for w in wds:
                d = monday + dt.timedelta(weeks=k * step, days=w)
                if d >= day:
                    yield d
            k += 1
    elif f == 'MONTHLY':
        k = 0
        while True:
            y, m = add_months(day, k * step)
            try:
                yield D(y, m, day.day)
            except ValueError:
                pass  # no 31st in this month: RFC 5545 skips it
            k += 1
            if y > 9999 - 1:
                return
    else:
        k = 0
        while day.year + k * step < 9999:
            try:
                yield D(day.year + k * step, day.month, day.day)
            except ValueError:
                pass  # 29 February in a common year
            k += 1


def occurrences(events, lo, hi):
    """[(start, end, event)] of every occurrence overlapping [lo, hi) (datetimes), sorted by start; all-day ones first
    within their day."""
    out = []
    for e in events:
        ln = e.length
        for o in starts(e, hi):
            end = o + ln
            so, eo = (DT.combine(o, dt.time()), DT.combine(end, dt.time())) if type(o) is D else (o, end)
            if so >= hi or (eo <= lo and not (eo == so and so >= lo)):
                continue
            out.append((o, end, e))
    def key(x):
        s = x[0]
        return (DT.combine(s, dt.time()) if type(s) is D else s, 0 if type(s) is D else 1, x[2].summary.lower())
    out.sort(key=key)
    return out


def days_with_events(events, lo, hi):
    """The set of dates in [lo, hi) (dates) that have something on them (a multi-day event marks each of its days)."""
    seen = set()
    for s, en, _e in occurrences(events, DT.combine(lo, dt.time()), DT.combine(hi, dt.time())):
        d = s if type(s) is D else s.date()
        if type(s) is D:
            last = en - dt.timedelta(days=1)
        else:
            last = (en - dt.timedelta(seconds=1)).date() if en > s else d
        while True:
            if lo <= d < hi:
                seen.add(d)
            d += dt.timedelta(days=1)
            if d > last:
                break
    return seen


def due_reminders(events, after, upto):
    """[(trigger time, occurrence start, event)] whose reminder time falls in (after, upto]. An all-day event counts from
    midnight of its day."""
    out = []
    for e in events:
        if e.reminder is None:
            continue
        off = dt.timedelta(minutes=e.reminder)
        for o in starts(e, upto + off + dt.timedelta(days=1)):
            t = (DT.combine(o, dt.time()) if type(o) is D else o) - off
            if after < t <= upto:
                out.append((t, o, e))
    out.sort(key=lambda x: x[0])
    return out


# ---- the file --------------------------------------------------------------------------------------------------------
def load(path=STORE):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return parse(f.read())
    except OSError:
        return []


def save(events, path=STORE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(serialize(events))
    os.replace(tmp, path)
