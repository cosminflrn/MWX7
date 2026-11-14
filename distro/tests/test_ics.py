#!/usr/bin/python3
"""Self-check of MWX 7's iCalendar reader/writer (distro/desktop/overlay/usr/share/mwx7/lib/mwx7ics.py): folded lines, escapes,
VALUE=DATE, TZID taken as local, UTC converted to local, RRULE (FREQ / INTERVAL / COUNT / UNTIL / BYDAY), EXDATE, VALARM, the
write -> read round trip, and which reminders are due. No display needed. Run: python3 distro/tests/test_ics.py"""
import datetime as dt
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'desktop', 'overlay', 'usr', 'share', 'mwx7', 'lib', 'mwx7ics.py')
spec = importlib.util.spec_from_file_location('mwx7ics_under_test', SRC)
ics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ics)
D, DT = dt.date, dt.datetime
NOREPEAT = {'interval': 1, 'count': None, 'until': None, 'byday': []}


def cal(*body):
    return 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\n' + ''.join(l + '\r\n' for l in body) + 'END:VCALENDAR\r\n'


def one(*lines):
    evs = ics.parse(cal('BEGIN:VEVENT', *lines, 'END:VEVENT'))
    assert len(evs) == 1, evs
    return evs[0]


class Parse(unittest.TestCase):
    def test_folded_and_escaped(self):
        e = one('UID:a', 'DTSTART:20260310T090000', 'SUMMARY:Lunch\\, with a long title that goes on and on and',
                ' on and on', 'DESCRIPTION:line1\\nline2\\; end')
        self.assertEqual(e.summary, 'Lunch, with a long title that goes on and on andon and on')
        self.assertEqual(e.description, 'line1\nline2; end')

    def test_fold_roundtrip_long_utf8(self):
        title = 'Ünïcödé ' * 30
        out = ics.serialize([ics.Event(title, DT(2026, 1, 1, 9), DT(2026, 1, 1, 10))])
        for line in out.split('\r\n'):
            self.assertLessEqual(len(line.encode()), 75)
        self.assertEqual(ics.parse(out)[0].summary, title)

    def test_date_value_is_allday(self):
        e = one('DTSTART;VALUE=DATE:20260704', 'DTEND;VALUE=DATE:20260706', 'SUMMARY:Trip')
        self.assertTrue(e.allday)
        self.assertEqual((e.start, e.end), (D(2026, 7, 4), D(2026, 7, 6)))

    def test_allday_without_dtend_is_one_day(self):
        self.assertEqual(one('DTSTART;VALUE=DATE:20260704', 'SUMMARY:x').end, D(2026, 7, 5))

    def test_tzid_is_local_and_duration(self):
        e = one('DTSTART;TZID=Europe/Paris:20260310T093000', 'DURATION:PT1H30M', 'SUMMARY:x')
        self.assertEqual((e.start, e.end), (DT(2026, 3, 10, 9, 30), DT(2026, 3, 10, 11, 0)))

    def test_utc_becomes_local(self):
        e = one('DTSTART:20260310T090000Z', 'DTEND:20260310T100000Z', 'SUMMARY:x')
        want = DT.fromtimestamp(DT(2026, 3, 10, 9).replace(tzinfo=dt.timezone.utc).timestamp())
        self.assertEqual(e.start, want)
        self.assertEqual(e.end - e.start, dt.timedelta(hours=1))

    def test_bad_event_skipped_not_fatal(self):
        evs = ics.parse(cal('BEGIN:VEVENT', 'DTSTART:garbage', 'END:VEVENT', 'BEGIN:VEVENT', 'DTSTART:20260101T010000',
                            'SUMMARY:ok', 'END:VEVENT'))
        self.assertEqual([e.summary for e in evs], ['ok'])

    def test_lf_only_and_lowercase_names(self):
        evs = ics.parse('begin:vcalendar\nbegin:vevent\ndtstart:20260101T010000\nsummary:Hi\nend:vevent\nend:vcalendar\n')
        self.assertEqual(evs[0].summary, 'Hi')

    def test_alarm(self):
        e = one('DTSTART:20260101T100000', 'SUMMARY:x', 'BEGIN:VALARM', 'ACTION:DISPLAY', 'TRIGGER:-PT15M', 'END:VALARM')
        self.assertEqual(e.reminder, 15)
        e = one('DTSTART:20260101T100000', 'SUMMARY:x', 'BEGIN:VALARM', 'TRIGGER:-P1D', 'END:VALARM')
        self.assertEqual(e.reminder, 1440)

    def test_alarm_props_do_not_leak(self):
        e = one('DTSTART:20260101T100000', 'SUMMARY:real', 'BEGIN:VALARM', 'DESCRIPTION:alarm text', 'END:VALARM')
        self.assertEqual((e.summary, e.description), ('real', ''))


class Rules(unittest.TestCase):
    def occ(self, e, lo, hi):
        return [s for s, _e, _x in ics.occurrences([e], lo, hi)]

    def test_daily_count_interval(self):
        e = one('DTSTART:20260101T090000', 'RRULE:FREQ=DAILY;INTERVAL=2;COUNT=3', 'SUMMARY:x')
        self.assertEqual(self.occ(e, DT(2026, 1, 1), DT(2026, 2, 1)), [DT(2026, 1, 1, 9), DT(2026, 1, 3, 9), DT(2026, 1, 5, 9)])

    def test_weekly_byday_until(self):
        e = one('DTSTART:20260105T090000', 'RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20260114T000000', 'SUMMARY:x')  # a Monday
        self.assertEqual([s.day for s in self.occ(e, DT(2026, 1, 1), DT(2026, 3, 1))], [5, 7, 12])

    def test_until_date_includes_that_day(self):
        e = one('DTSTART:20260105T090000', 'RRULE:FREQ=DAILY;UNTIL=20260107', 'SUMMARY:x')
        self.assertEqual([s.day for s in self.occ(e, DT(2026, 1, 1), DT(2026, 2, 1))], [5, 6, 7])

    def test_monthly_skips_missing_day(self):
        e = one('DTSTART;VALUE=DATE:20260131', 'RRULE:FREQ=MONTHLY;COUNT=3', 'SUMMARY:x')
        self.assertEqual(self.occ(e, DT(2026, 1, 1), DT(2027, 1, 1)), [D(2026, 1, 31), D(2026, 3, 31), D(2026, 5, 31)])

    def test_yearly_leap_day(self):
        e = one('DTSTART;VALUE=DATE:20240229', 'RRULE:FREQ=YEARLY;COUNT=2', 'SUMMARY:x')
        self.assertEqual(self.occ(e, DT(2024, 1, 1), DT(2040, 1, 1)), [D(2024, 2, 29), D(2028, 2, 29)])

    def test_exdate(self):
        e = one('DTSTART:20260101T090000', 'RRULE:FREQ=DAILY;COUNT=3', 'EXDATE:20260102T090000', 'SUMMARY:x')
        self.assertEqual([s.day for s in self.occ(e, DT(2026, 1, 1), DT(2026, 2, 1))], [1, 3])

    def test_overlap_from_before_range(self):
        e = ics.Event('x', DT(2026, 1, 1, 22), DT(2026, 1, 2, 2))
        self.assertEqual(len(ics.occurrences([e], DT(2026, 1, 2), DT(2026, 1, 3))), 1)
        self.assertEqual(len(ics.occurrences([e], DT(2026, 1, 2, 2), DT(2026, 1, 3))), 0)

    def test_unsupported_freq_is_single(self):
        self.assertIsNone(one('DTSTART:20260101T090000', 'RRULE:FREQ=HOURLY;COUNT=5', 'SUMMARY:x').rule)

    def test_days_with_events_multiday_allday(self):
        e = ics.Event('x', D(2026, 7, 4), D(2026, 7, 6))
        self.assertEqual(sorted(ics.days_with_events([e], D(2026, 7, 1), D(2026, 8, 1))), [D(2026, 7, 4), D(2026, 7, 5)])

    def test_days_with_events_timed(self):
        e = ics.Event('x', DT(2026, 7, 4, 22), DT(2026, 7, 5, 1))
        self.assertEqual(sorted(ics.days_with_events([e], D(2026, 7, 1), D(2026, 8, 1))), [D(2026, 7, 4), D(2026, 7, 5)])

    def test_allday_sorts_before_timed(self):
        a = ics.Event('timed', DT(2026, 7, 4, 8), DT(2026, 7, 4, 9))
        b = ics.Event('all', D(2026, 7, 4), D(2026, 7, 5))
        got = [x[2].summary for x in ics.occurrences([a, b], DT(2026, 7, 4), DT(2026, 7, 5))]
        self.assertEqual(got, ['all', 'timed'])


class RoundTrip(unittest.TestCase):
    def test_roundtrip(self):
        a = ics.Event('Standup, daily; "quoted"', DT(2026, 3, 2, 9, 30), DT(2026, 3, 2, 10), reminder=10,
                      rule=dict(NOREPEAT, freq='WEEKLY', interval=2, until=D(2026, 12, 31), byday=['MO', 'TH']),
                      description='a\nb', location='Room 4')
        b = ics.Event('Holiday', D(2026, 8, 1), D(2026, 8, 15), rule=dict(NOREPEAT, freq='YEARLY', count=3), reminder=0)
        a.exdates.add(DT(2026, 3, 16, 9, 30))
        back = ics.parse(ics.serialize([a, b]))
        self.assertEqual(len(back), 2)
        for x, y in zip((a, b), back):
            self.assertEqual((x.uid, x.summary, x.start, x.end, x.rule, x.reminder, x.description, x.location, x.exdates),
                             (y.uid, y.summary, y.start, y.end, y.rule, y.reminder, y.description, y.location, y.exdates))

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'sub', 'c.ics')
            ics.save([ics.Event('x', DT(2026, 1, 1, 1), DT(2026, 1, 1, 2))], p)
            self.assertEqual(ics.load(p)[0].summary, 'x')
            self.assertEqual(ics.load(os.path.join(d, 'none.ics')), [])


class Reminders(unittest.TestCase):
    def test_due_window(self):
        e = ics.Event('x', DT(2026, 5, 1, 10), DT(2026, 5, 1, 11), reminder=15)
        self.assertEqual(len(ics.due_reminders([e], DT(2026, 5, 1, 9, 44), DT(2026, 5, 1, 9, 45))), 1)
        self.assertEqual(len(ics.due_reminders([e], DT(2026, 5, 1, 9, 45), DT(2026, 5, 1, 9, 46))), 0)  # already fired
        self.assertEqual(len(ics.due_reminders([e], DT(2026, 5, 1, 9, 0), DT(2026, 5, 1, 9, 44))), 0)

    def test_recurring_and_allday(self):
        e = ics.Event('x', D(2026, 5, 1), D(2026, 5, 2), rule=dict(NOREPEAT, freq='DAILY'), reminder=60)
        got = ics.due_reminders([e], DT(2026, 5, 9, 22), DT(2026, 5, 9, 23, 30))
        self.assertEqual([t for t, _o, _e in got], [DT(2026, 5, 9, 23)])

    def test_no_reminder(self):
        self.assertEqual(ics.due_reminders([ics.Event('x', DT(2026, 5, 1, 10))], DT(2026, 1, 1), DT(2027, 1, 1)), [])


if __name__ == '__main__':
    unittest.main()
