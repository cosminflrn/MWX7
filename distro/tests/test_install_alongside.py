#!/usr/bin/python3
"""Self-check of "install alongside Windows" (distro/desktop/overlay/usr/share/mwx7/oobe/install.py) with a fake disk: no root,
no real commands. Run: python3 distro/tests/test_install_alongside.py
It checks the detection, every refusal, the sizes, and that the dry run (MWX7_INSTALL_DRYRUN=1 behaviour) prints exactly the
command sequence: test run, ntfsresize, parted, sfdisk append, and never a mkfs/wipefs on the existing EFI partition."""
import contextlib
import importlib.util
import io
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'desktop', 'overlay', 'usr', 'share', 'mwx7', 'oobe', 'install.py')
GIB = 2 ** 30
SS = 512
D = '/dev/nvme0n1'


def load():
    spec = importlib.util.spec_from_file_location('install_under_test', SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Fake:
    """A 1 TB NVMe: EFI 100 MiB, MSR 16 MiB, Windows C: 470 GiB, Recovery 1 GiB (the usual Windows 11 layout)."""
    def __init__(self, bitlocker=False, hibernated=False, used=60 * GIB, win_gib=470, ntfs_error=None):
        self.bitlocker, self.hib, self.used, self.ntfs_error = bitlocker, hibernated, used, ntfs_error
        self.win_sectors = win_gib * GIB // SS
        self.ran = []
        self.win_start = 239616
        self.parts = [(1, 2048, 204800), (2, 206848, 32768), (3, self.win_start, self.win_sectors),
                      (4, self.win_start + self.win_sectors, 2 * 1024 * 1024)]

    def lsblk(self):
        kinds = {1: ('vfat', 'EFI', 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b'), 2: (None, None, 'e3c9e316-0b5c-4db8-817d-f92df00215ae'),
                 3: ('BitLocker' if self.bitlocker else 'ntfs', 'Windows' if not self.bitlocker else None,
                     'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7'),
                 4: ('ntfs', 'Recovery', 'de94bba4-06d1-4d40-a16a-bfd50179d6ac')}
        ch = [{'name': f'nvme0n1p{n}', 'path': f'{D}p{n}', 'size': sz * SS, 'type': 'part', 'fstype': kinds[n][0],
               'label': kinds[n][1], 'parttype': kinds[n][2], 'partlabel': None} for n, _s, sz in self.parts]
        return json.dumps({'blockdevices': [{'name': 'nvme0n1', 'path': D, 'size': 1000 * GIB, 'type': 'disk', 'tran': 'nvme',
                                              'rm': False, 'ro': False, 'model': 'Fake SSD', 'pttype': 'gpt', 'children': ch}]})

    def sfdisk_json(self):
        return json.dumps({'partitiontable': {'label': 'gpt', 'sectorsize': SS, 'firstlba': 2048, 'lastlba': 1000 * GIB // SS - 34,
                                              'partitions': [{'node': f'{D}p{n}', 'start': s, 'size': z} for n, s, z in self.parts]}})

    def sh(self, *cmd, **kw):
        self.ran.append(cmd)
        if cmd[0] == 'lsblk':
            return self.lsblk()
        if cmd[:2] == ('sfdisk', '-J'):
            return self.sfdisk_json()
        if cmd[0] == 'blockdev':
            return str(1000 * GIB // SS)
        if cmd[:2] == ('ntfsresize', '--info'):
            if self.ntfs_error:
                raise RuntimeError(self.ntfs_error)
            return (f'Cluster size                 : 4096 bytes\nCurrent volume size          : {self.win_sectors * SS - 4096} bytes\n'
                    f'Space in use                 : {self.used // 2 ** 20} MB\nYou might resize at {self.used} bytes\n')
        if cmd[:2] == ('ntfsresize', '--no-action'):
            return 'The read-only test run ended successfully.\n'
        raise AssertionError(f'unexpected command {cmd}')


def setup(m, fake):
    m.sh = fake.sh
    m.uefi = lambda: True
    m.live_disk = lambda: None
    m.release = lambda disk: None
    m.unmount_all = lambda: None
    m.free_space = lambda dev: (None, 0, 512)
    m.os.geteuid = lambda: 0
    m.is_bitlocker = lambda p: p.get('fstype') == 'BitLocker'
    esp_has_windows = True

    def probe(dev, fstype, fn):
        if fstype == 'vfat':
            return (esp_has_windows, 80 * 2 ** 20)
        if fn is m.windows_name:
            return None if fake.bitlocker else 'Windows 11'
        return fake.hib  # hibernated()'s look function
    m.probe_mount = probe
    m.DRYRUN = True


class Alongside(unittest.TestCase):
    def test_detection_and_range(self):
        m, f = load(), Fake()
        setup(m, f)
        d = m.disk_info(D)
        self.assertEqual([s['name'] for s in d['systems']], ['Windows 11'])
        self.assertTrue(d['has_windows'] and not d['bitlocker'])
        self.assertEqual(d['win_part'], f'{D}p3')
        self.assertEqual(d['esp'], f'{D}p1')
        r = m.alongside_check(d)
        self.assertEqual((r['min'], r['default']), (40, 60))
        self.assertEqual(r['max'], 470 - 90)  # Windows keeps used 60 GB + 30 GB free

    def test_bitlocker_refused(self):
        m, f = load(), Fake(bitlocker=True)
        setup(m, f)
        d = m.disk_info(D)
        self.assertTrue(d['bitlocker'] and d['has_windows'] and d['win_part'] is None)
        self.assertEqual([s['name'] for s in d['systems']], ['Windows'])
        with self.assertRaisesRegex(RuntimeError, 'Turn off BitLocker'):
            m.alongside_check(d)

    def test_fast_startup_refused(self):
        for kw in ({'hibernated': True}, {'ntfs_error': 'ntfsresize failed: The NTFS partition is in an unsafe state.'}):
            m, f = load(), Fake(**kw)
            setup(m, f)
            with self.assertRaisesRegex(RuntimeError, 'fast startup'):
                m.alongside_check(m.disk_info(D))

    def test_too_little_room(self):
        m, f = load(), Fake(used=420 * GIB)
        setup(m, f)
        with self.assertRaisesRegex(RuntimeError, 'not enough room'):
            m.alongside_check(m.disk_info(D))
        m, f = load(), Fake(win_gib=100, used=40 * GIB)  # 100 - 70 = 30 < 40
        setup(m, f)
        with self.assertRaisesRegex(RuntimeError, 'not enough room'):
            m.alongside_check(m.disk_info(D))

    def test_size_out_of_range_refused(self):
        m, f = load(), Fake()
        setup(m, f)
        for g in (39, 381, 5000):
            with self.assertRaises(RuntimeError):
                m.alongside_check(m.disk_info(D), g)

    def test_dry_run_sequence(self):
        m, f = load(), Fake()
        setup(m, f)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.copy('alongside', D, 80)
        out = buf.getvalue().splitlines()
        cmds = [l for l in out if l.startswith('DRYRUN')]
        self.assertEqual(len(cmds), 3, out)
        lay = m.alongside_check(m.disk_info(D), 80)
        nb = lay['win_sectors'] * SS
        self.assertEqual(cmds[0], f'DRYRUN ntfsresize --size {nb} {D}p3 <<< \'y\\n\'')
        self.assertEqual(cmds[1], f"DRYRUN parted -s {D} resizepart 3 {lay['m_start'] - 1}s")
        self.assertTrue(cmds[2].startswith(f"DRYRUN sfdisk -q --append {D} <<< 'start={lay['m_start']}, size={lay['m_sectors']}, type=L"))
        # the layout: Windows shrinks, MWX 7 gets >= 80 GB inside the freed gap, 1 MiB aligned, nothing overlaps the recovery partition
        self.assertGreaterEqual(lay['m_sectors'] * SS, 80 * GIB)
        self.assertLess(lay['m_sectors'] * SS, 81 * GIB)
        self.assertEqual(lay['m_start'] % 2048, 0)
        self.assertEqual(lay['m_start'], f.win_start + lay['win_sectors'])
        self.assertLessEqual(lay['m_start'] + lay['m_sectors'], f.win_start + f.win_sectors)
        self.assertGreaterEqual(lay['win_sectors'] * SS, f.used + 30 * GIB)
        # nothing in the sequence formats or wipes anything
        self.assertFalse([c for c in f.ran if c[0] in ('wipefs', 'mkfs.vfat', 'mkfs.btrfs')])
        self.assertEqual(out[-1], 'STEP Dry run: nothing was changed')

    def test_plan_text(self):
        m, f = load(), Fake()
        setup(m, f)
        lines = m.plan('alongside', D, 80)['lines']
        self.assertIn('SHRUNK', lines[0])
        self.assertTrue(any('NOT formatted' in l for l in lines))

    def test_bitlocker_copy_aborts_before_any_command(self):
        m, f = load(), Fake(bitlocker=True)
        setup(m, f)
        with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()) as buf:
            m.copy('alongside', D, 80)
        self.assertNotIn('DRYRUN', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
