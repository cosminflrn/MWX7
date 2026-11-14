#!/usr/bin/python3
"""Self-check of "previous versions" (lib/mwx7versions.py; bin/mwx7-snapshots is exercised against a real loopback btrfs
image by hand, see the PR). No root, no btrfs: the retention choice and the version listing on a fake snapshot tree.
Run: python3 distro/tests/test_previous_versions.py"""
import datetime
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, '..', 'desktop', 'overlay', 'usr', 'share', 'mwx7', 'lib', 'mwx7versions.py')
spec = importlib.util.spec_from_file_location('mwx7versions_under_test', LIB)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def name(d):
    return d.strftime(v.STAMP)


class Retention(unittest.TestCase):
    def test_hourly_daily_weekly(self):
        now = datetime.datetime(2026, 11, 14, 12, 30)
        names = [name(now - datetime.timedelta(hours=h)) for h in range(0, 24 * 40)]  # an hourly snapshot for 40 days
        keep = v.keep_set(names)
        days = {parse.date() for parse in map(v.parse, keep)}
        hours = [n for n in keep if now - v.parse(n) < datetime.timedelta(hours=24)]
        self.assertEqual(len(hours), 24)
        self.assertLessEqual(len(keep), 24 + 7 + 4)
        self.assertGreater(len(keep), 24 + 3)
        self.assertIn(name(now), keep)                                   # the newest always stays
        self.assertTrue(all(n in names for n in keep))
        self.assertGreaterEqual(len(days), 7)

    def test_sparse_and_foreign_names(self):
        names = ['2026-11-01_100000', '2026-11-01_100500', 'not-ours', '2026-13-45_000000', '.hidden']
        # the same hour twice: only the newer one is picked by any bucket; names that are not ours are never kept (or deleted)
        self.assertEqual(v.keep_set(names), {'2026-11-01_100500'})

    def test_empty(self):
        self.assertEqual(v.keep_set([]), set())


class Versions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, 'home')
        self.snaps = os.path.join(self.home, '.mwx7-snapshots')
        os.makedirs(os.path.join(self.home, 'u', 'Documents'))

    def put(self, snap, rel, text, mtime):
        p = os.path.join(self.snaps, snap, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)
        os.utime(p, (mtime, mtime))

    def test_only_differing_versions(self):
        cur = os.path.join(self.home, 'u', 'Documents', 'a.txt')
        with open(cur, 'w') as f:
            f.write('now!')
        os.utime(cur, (3000, 3000))
        rel = 'u/Documents/a.txt'
        self.put('2026-11-01_100000', rel, 'one', 1000)
        self.put('2026-11-01_110000', rel, 'one', 1000)        # same as the one before: listed once
        self.put('2026-11-01_120000', rel, 'two2', 2000)
        self.put('2026-11-01_130000', rel, 'now!', 3000)       # same as the current file: not listed
        got = v.versions_of(cur, snapdir=self.snaps, home=self.home)
        self.assertEqual([g['snap'] for g in got], ['2026-11-01_120000', '2026-11-01_110000'])
        self.assertEqual(got[0]['size'], 4)

    def test_deleted_file_and_outside_home(self):
        self.put('2026-11-01_100000', 'u/Documents/gone.txt', 'x', 5)
        gone = os.path.join(self.home, 'u', 'Documents', 'gone.txt')
        self.assertEqual(len(v.versions_of(gone, snapdir=self.snaps, home=self.home)), 1)
        self.assertEqual(v.versions_of('/etc/passwd', snapdir=self.snaps, home=self.home), [])
        self.assertEqual(v.versions_of(os.path.join(self.snaps, '2026-11-01_100000', 'u'), snapdir=self.snaps, home=self.home), [])


if __name__ == '__main__':
    unittest.main()
