#!/usr/bin/python3
"""Self-check of Explorer's compressed folders (apps/explorer.py): Send to > zip, Extract All for zip/tar/tgz/txz/tbz2, name
collisions, and that archives cannot write outside the destination (zip-slip, absolute names, symlinks, hard links, setuid).
Needs GTK's Python bindings (run inside the distro): python3 distro/tests/test_explorer_archives.py"""
import io
import os
import sys
import tarfile
import tempfile
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'desktop', 'overlay', 'usr', 'share', 'mwx7')
sys.path.insert(0, os.path.join(ROOT, 'lib'))
sys.path.insert(0, os.path.join(ROOT, 'apps'))
import explorer as e  # noqa: E402

t = tempfile.mkdtemp()
os.chdir(t)
# safe_path
r = os.path.join(t, 'r'); os.makedirs(r)
assert e.safe_path(r, 'a/b.txt') == os.path.join(r, 'a/b.txt')
assert e.safe_path(r, './a') == os.path.join(r, 'a')
for bad in ('../x', 'a/../../x', '/etc/passwd', 'C:\\x', '..\\x', 'a/..\\..\\x'):
    assert e.safe_path(r, bad) is None, bad

# compress
src = os.path.join(t, 'proj'); os.makedirs(src + '/sub'); open(src + '/a.txt', 'w').write('hello' * 100000)
open(src + '/sub/b.sh', 'w').write('#!/bin/sh'); os.chmod(src + '/sub/b.sh', 0o755)
os.symlink('a.txt', src + '/ln'); os.makedirs(src + '/empty')
os.utime(src + '/a.txt', (1, 1))  # 1970: must not blow up
dest = e.unique_in(t, 'proj.zip'); open(dest, 'w').close()
dest2 = e.unique_in(t, 'proj.zip'); assert dest2.endswith('proj (2).zip'), dest2
j = e.Job('compress', [src], dest2); j.run()
assert not os.path.exists(os.path.join(t, '.proj (2).zip.part'))
z = zipfile.ZipFile(dest2); assert z.testzip() is None; print(sorted(z.namelist()))
assert 'proj/empty/' in z.namelist() and 'proj/ln' in z.namelist()

# extract zip
out = os.path.join(t, 'out')
j = e.Job('extract', [dest2], out); j.run()
assert open(out + '/proj/a.txt').read() == 'hello' * 100000
assert os.access(out + '/proj/sub/b.sh', os.X_OK) and os.path.islink(out + '/proj/ln') and os.path.isdir(out + '/proj/empty')
assert j.skipped == 0 and j.done == j.total, (j.done, j.total)

# malicious zip
evil = os.path.join(t, 'evil.zip')
with zipfile.ZipFile(evil, 'w') as zf:
    zf.writestr('../escape.txt', 'x'); zf.writestr('/abs.txt', 'x'); zf.writestr('a/../../esc2.txt', 'x')
    zf.writestr('ok.txt', 'fine')
    zi = zipfile.ZipInfo('evil_link'); zi.external_attr = (0o120777) << 16; zf.writestr(zi, '/etc')
    zi = zipfile.ZipInfo('up_link'); zi.external_attr = (0o120777) << 16; zf.writestr(zi, '../..')
    zi = zipfile.ZipInfo('good_link'); zi.external_attr = (0o120777) << 16; zf.writestr(zi, 'ok.txt')
    zf.writestr('evil_link/pwn.txt', 'x'); zf.writestr('suid', 'x')
    zi = zipfile.ZipInfo('suidf'); zi.external_attr = 0o104755 << 16; zf.writestr(zi, 'x')
eo = os.path.join(t, 'evilout')
j = e.Job('extract', [evil], eo); j.run()
assert not os.path.exists(os.path.join(t, 'escape.txt')) and not os.path.exists('/abs.txt') and not os.path.exists(os.path.join(t, 'esc2.txt'))
assert sorted(os.listdir(eo)) == ['evil_link', 'good_link', 'ok.txt', 'suid', 'suidf'] and not os.path.islink(eo + '/evil_link'), sorted(os.listdir(eo))
assert os.stat(eo + '/suidf').st_mode & 0o7000 == 0
print('skipped', j.skipped)

# malicious tar: symlink then file through it, hardlink out, absolute
tp = os.path.join(t, 'evil.tar.gz')
with tarfile.open(tp, 'w:gz') as tf:
    def add(name, data=b'x', type=tarfile.REGTYPE, link=''):
        ti = tarfile.TarInfo(name); ti.type = type; ti.linkname = link; ti.size = len(data) if type == tarfile.REGTYPE else 0
        tf.addfile(ti, io.BytesIO(data) if type == tarfile.REGTYPE else None)
    add('./'); add('d/', type=tarfile.DIRTYPE); add('d/f.txt', b'data')
    add('lnk', type=tarfile.SYMTYPE, link=os.path.join(t, 'outside'))
    add('lnk/pwn.txt'); add('../tarup.txt'); add('hard', type=tarfile.LNKTYPE, link='d/f.txt')
    add('hard2', type=tarfile.LNKTYPE, link='/etc/passwd'); add('fifo', type=tarfile.FIFOTYPE)
os.makedirs(os.path.join(t, 'outside'))
to = os.path.join(t, 'tout')
j = e.Job('extract', [tp], to); j.run()
assert not os.path.exists(os.path.join(t, 'outside', 'pwn.txt')) and not os.path.exists(os.path.join(t, 'tarup.txt'))
assert open(to + '/hard').read() == 'data' and not os.path.exists(to + '/hard2')
print(sorted(os.listdir(to)), 'skipped', j.skipped)
for ext, mode in (('tar', 'w'), ('tar.xz', 'w:xz'), ('tar.bz2', 'w:bz2'), ('tgz', 'w:gz')):
    p = os.path.join(t, 'p.' + ext)
    with tarfile.open(p, mode) as tf: tf.add(src, 'proj')
    o = os.path.join(t, 'o_' + ext); j = e.Job('extract', [p], o); j.run()
    assert open(o + '/proj/a.txt').read() == 'hello' * 100000, ext
    assert e.archive_kind(p) == 'tar'
# collisions: replace/skip/keep
c = os.path.join(t, 'coll'); os.makedirs(c); open(c + '/ok.txt', 'w').write('old')
for choice, want in (('skip', 'old'), ('replace', 'fine')):
    open(c + '/ok.txt', 'w').write('old')
    j = e.Job('extract', [evil], c); j.conflict = lambda s, d, ch=choice: ch; j.run()
    assert open(c + '/ok.txt').read() == want, choice
j = e.Job('extract', [evil], c); j.conflict = lambda s, d: 'keep'; j.run()
assert os.path.exists(c + '/ok (2).txt')
# cancel removes the folder we made
j = e.Job('extract', [dest2], os.path.join(t, 'cx')); j.cancel.set()
try: j.run()
except e.Cancelled: pass
assert not os.path.exists(os.path.join(t, 'cx'))
# cancel compress leaves no part
j = e.Job('compress', [src], os.path.join(t, 'cc.zip')); j.cancel.set()
try: j.run()
except e.Cancelled: pass
assert not [n for n in os.listdir(t) if n.startswith('.cc') or n == 'cc.zip']
# bad zip
open(os.path.join(t, 'bad.zip'), 'w').write('nope')
assert e.zsplit(os.path.join(t, 'bad.zip') + '!/') is not None and e.archive_stem('x.tar.gz') == 'x' and e.archive_stem('a.b.zip') == 'a.b'
print('ALL OK')
