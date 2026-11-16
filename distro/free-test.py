#!/usr/bin/env python3
"""Helpers of the smoke test "free" (distro/smoke-test.sh): the real, interactive setup installing MWX 7 into the free
space of a disk that holds Windows, driven with keyboard input only, and the proof that nothing else was touched.

  free-test.py build DIR                     DIR/win.img (GPT: 200 MB EFI with a fake Windows boot manager, NTFS "Windows" with
                                             Windows/System32/ntoskrnl.exe and data, ~24 GiB unallocated, 900 MB recovery) and
                                             DIR/hdd.img (one NTFS data partition); DIR/before.json = what they looked like
  free-test.py drive QMP SERIAL SHOTS SCALE  keyboard-only run of the setup (language page -> disk page -> free space -> Last
                                             check -> Install -> account test/test) until the VM powers off; screenshots in SHOTS
  free-test.py verify DIR                    after the install: every old partition byte for byte the same (the EFI partition:
                                             every old file), the HDD untouched, new partitions only in the former free space,
                                             MWX 7's boot files on the EFI partition, Windows in the installed boot menu

Needs root (loop devices, mounts), sfdisk, mkfs.ntfs + ntfs-3g, mtools, dosfstools, btrfs in the kernel; tesseract-ocr is optional
(it lets the driver check what is on screen and try another key sequence; without it the first sequence is used blindly).
"""
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

MIB = 1 << 20
SECTOR = 512
ESP_TYPE = 'C12A7328-F81F-11D2-BA4B-00A0C93EC93B'
MS_DATA = 'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7'
RECOVERY = 'DE94BBA4-06D1-4D40-A16A-BFD50179D6AC'
ESP_MIB, WIN_MIB, FREE_MIB, REC_MIB = 200, 4096, 24986, 900  # his PC: 200 MB EFI, C:, 24.4 GiB unallocated, 921 MB recovery
HDD_MIB = 4096


def run(*cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f'{" ".join(cmd)} failed: {(r.stderr or r.stdout).strip()[-400:]}')
    return r.stdout


def log(msg):
    print(f'[free {time.strftime("%H:%M:%S")}] {msg}', flush=True)


def sha(path, offset=0, length=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        f.seek(offset)
        left = length if length is not None else os.path.getsize(path) - offset
        while left > 0:
            b = f.read(min(4 * MIB, left))
            if not b:
                break
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def table(img):
    t = json.loads(run('sfdisk', '-J', img))['partitiontable']
    return t, [{'n': int(re.search(r'(\d+)$', p['node']).group(1)), 'start': p['start'], 'size': p['size'], 'type': p['type'].upper(), 'uuid': p.get('uuid', '').upper()}
               for i, p in enumerate(t['partitions'])]


def esp_files(img, off):
    """{path: sha256} of every file on the FAT32 EFI partition at byte offset off, read with mtools (nothing is mounted)."""
    spec = f'{img}@@{off}'
    env = dict(os.environ, MTOOLS_SKIP_CHECK='1')
    out = subprocess.run(['mdir', '-i', spec, '-/', '-b', '::'], capture_output=True, text=True, env=env).stdout
    files = {}
    for line in out.splitlines():
        path = line.strip().lstrip(':').lstrip('/')
        if not path or path.endswith('/'):
            continue
        d = subprocess.run(['mcopy', '-i', spec, f'::{path}', '-'], capture_output=True, env=env)
        if d.returncode == 0:  # directories fail here and are skipped
            files[path] = hashlib.sha256(d.stdout).hexdigest()
    return files


class Loop:
    """One partition of an image as a loop device (offset + size, so it works without partition nodes or udev)."""
    def __init__(self, img, part, ro=False):
        self.dev = run('losetup', '-f', '--show', *(['-r'] if ro else []), '-o', str(part['start'] * SECTOR),
                       '--sizelimit', str(part['size'] * SECTOR), img).strip()

    def __enter__(self):
        return self.dev

    def __exit__(self, *_):
        subprocess.run(['sync'])
        subprocess.run(['losetup', '-d', self.dev], capture_output=True)


def mount_write(dev, fn):
    mnt = tempfile.mkdtemp(prefix='mwx7-free-')
    try:
        for fs in ('ntfs-3g', 'ntfs3'):
            if subprocess.run(['mount', '-t', fs, dev, mnt], capture_output=True).returncode == 0:
                break
        else:
            raise RuntimeError(f'cannot mount {dev} as NTFS')
        try:
            fn(mnt)
        finally:
            subprocess.run(['sync'])
            subprocess.run(['umount', mnt], check=True)
    finally:
        os.rmdir(mnt)


def build(d):
    os.makedirs(d, exist_ok=True)
    win, hdd = f'{d}/win.img', f'{d}/hdd.img'
    sec = lambda mib: mib * MIB // SECTOR  # noqa: E731
    p1 = 2048
    p2 = p1 + sec(ESP_MIB)
    p3 = p2 + sec(WIN_MIB) + sec(FREE_MIB)
    total = p3 + sec(REC_MIB) + 2048
    for f in (win, hdd):
        if os.path.exists(f):
            os.unlink(f)
    with open(win, 'wb') as f:
        f.truncate(total * SECTOR)
    run('sfdisk', '-q', win, input=(
        f'label: gpt\nfirst-lba: 2048\nstart={p1}, size={sec(ESP_MIB)}, type={ESP_TYPE}, name="EFI system partition"\n'
        f'start={p2}, size={sec(WIN_MIB)}, type={MS_DATA}, name="Basic data partition"\n'
        f'start={p3}, size={sec(REC_MIB)}, type={RECOVERY}, name="Windows RE"\n'))
    rnd = os.urandom(1 * MIB)
    wp = {p['n']: p for p in table(win)[1]}
    with Loop(win, wp[1]) as esp:
        run('mkfs.vfat', '-F', '32', '-n', 'SYSTEM', esp)
        env = dict(os.environ, MTOOLS_SKIP_CHECK='1')
        for dd in ('EFI', 'EFI/Microsoft', 'EFI/Microsoft/Boot', 'EFI/Boot'):
            subprocess.run(['mmd', '-i', esp, f'::{dd}'], check=True, env=env)
        for name, dest in (('bootmgfw.efi', 'EFI/Microsoft/Boot/bootmgfw.efi'), ('BCD', 'EFI/Microsoft/Boot/BCD'),
                           ('bootmgr.efi', 'EFI/Microsoft/Boot/bootmgr.efi')):
            with tempfile.NamedTemporaryFile() as t:
                t.write(b'MZ' + name.encode() + rnd[:300 * 1024])
                t.flush()
                subprocess.run(['mcopy', '-i', esp, t.name, f'::{dest}'], check=True, env=env)
    with Loop(win, wp[3]) as dev:
        run('mkfs.ntfs', '-f', '-L', 'Recovery', dev)
    with Loop(win, wp[2]) as dev:
        run('mkfs.ntfs', '-f', '-L', 'Windows', dev)

        def fill(m):
            os.makedirs(f'{m}/Windows/System32', exist_ok=True)
            os.makedirs(f'{m}/Users/Cosmin/Documents', exist_ok=True)
            for rel, size in (('Windows/System32/ntoskrnl.exe', 1), ('Windows/System32/config.dat', 1),
                              ('Users/Cosmin/Documents/important.xlsx', 3), ('pagefile.sys', 5)):
                with open(f'{m}/{rel}', 'wb') as f:
                    f.write(os.urandom(size * MIB))
        mount_write(dev, fill)
    with open(hdd, 'wb') as f:
        f.truncate(HDD_MIB * MIB)
    run('sfdisk', '-q', hdd, input=f'label: gpt\nstart=2048, type={MS_DATA}, name="Data"\n')
    with Loop(hdd, table(hdd)[1][0]) as dev:
        run('mkfs.ntfs', '-f', '-L', 'Data', dev)

        def fill_hdd(m):
            os.makedirs(f'{m}/Photos', exist_ok=True)
            for i in range(4):
                with open(f'{m}/Photos/img{i}.jpg', 'wb') as f:
                    f.write(os.urandom(2 * MIB))
        mount_write(dev, fill_hdd)
    t, parts = table(win)
    before = {'win': {'table': t, 'parts': parts,
                      'sha': {p['n']: sha(win, p['start'] * SECTOR, p['size'] * SECTOR) for p in parts},
                      'esp_files': esp_files(win, parts[0]['start'] * SECTOR),
                      'gap': [p2 + sec(WIN_MIB), p3]},
              'hdd': {'parts': table(hdd)[1], 'sha': sha(hdd)}}
    with open(f'{d}/before.json', 'w') as f:
        json.dump(before, f, indent=1)
    log(f'built {win} ({os.path.getsize(win) // MIB} MiB, free gap sectors {before["win"]["gap"]}) and {hdd}')
    log('ESP files before: ' + ', '.join(sorted(before['win']['esp_files'])))


def verify(d):
    b = json.load(open(f'{d}/before.json'))
    win, hdd = f'{d}/win.img', f'{d}/hdd.img'
    t, parts = table(win)
    results = []

    def check(name, ok, detail=''):
        results.append(ok)
        print(('PASS ' if ok else 'FAIL ') + name + (f': {detail}' if detail else ''), flush=True)

    old = {p['n']: p for p in b['win']['parts']}
    now = {(p['start'], p['size']): p for p in parts}
    # 1. every old partition is still there at the same place with the same type and id
    missing = [n for n, p in old.items() if (p['start'], p['size']) not in now or now[(p['start'], p['size'])]['type'] != p['type']
               or now[(p['start'], p['size'])]['uuid'] != p['uuid']]
    check('old partitions keep start, size, type and id', not missing, f'changed: {missing}' if missing else '')
    check('disk id unchanged', t.get('id') == b['win']['table'].get('id'), f"{b['win']['table'].get('id')} -> {t.get('id')}")
    # 2. byte for byte: Windows C: and the recovery partition (the EFI partition gets MWX 7's files, so it is compared file by file)
    for n, p in old.items():
        if n == 1:
            continue
        h = sha(win, p['start'] * SECTOR, p['size'] * SECTOR)
        check(f'partition {n} byte-identical (sha256)', h == b['win']['sha'][str(n)], h[:16])
    check('HDD byte-identical (whole disk sha256)', sha(hdd) == b['hdd']['sha'])
    check('HDD partition table unchanged', table(hdd)[1] == b['hdd']['parts'])
    # 3. new partitions only inside the former free space
    new = [p for p in parts if (p['start'], p['size']) not in {(o['start'], o['size']) for o in old.values()}]
    lo_s, hi_s = b['win']['gap']
    inside = all(lo_s <= p['start'] and p['start'] + p['size'] <= hi_s for p in new)
    check('MWX 7 partition(s) only inside the former free space', bool(new) and inside,
          ', '.join(f"#{p['n']} {p['start']}+{p['size']} type {p['type']}" for p in new) + f' (gap {lo_s}..{hi_s})')
    # 4. EFI partition: every old file identical, MWX 7's boot files added
    off = old[1]['start'] * SECTOR
    files = esp_files(win, off)
    changed = [f for f, h in b['win']['esp_files'].items() if files.get(f) != h]
    check('EFI/Microsoft files intact (sha256 of every old file)', not changed, f'changed or missing: {changed}' if changed else
          f'{len(b["win"]["esp_files"])} files')
    ours = sorted(f for f in files if f.lower().startswith(('efi/mwx7/', 'efi/debian/')))
    check('EFI partition holds MWX 7 boot files', any(f.lower().endswith(('grubx64.efi', 'shimx64.efi')) for f in ours), ', '.join(ours))
    # 5. the installed boot menu lists Windows (read from the installed system's grub.cfg)
    cfg = ''
    mnt = tempfile.mkdtemp(prefix='mwx7-free-')
    try:
        for p in new:
            with Loop(win, p, ro=True) as dev:
                # nologreplay: the VM of the second boot is killed, its btrfs log must not be replayed (or refused) on a read-only mount
                if any(subprocess.run(['mount', '-t', 'btrfs', '-o', o, dev, mnt], capture_output=True).returncode == 0
                       for o in ('ro,subvol=@,rescue=nologreplay', 'ro,subvol=@,norecovery', 'ro,subvol=@')):
                    try:
                        cfg = open(f'{mnt}/boot/grub/grub.cfg', errors='replace').read()
                        shutil.copy(f'{mnt}/boot/grub/grub.cfg', f'{d}/installed-grub.cfg')
                    except OSError as e:
                        cfg = ''
                        log(f'grub.cfg unreadable: {e}')
                    finally:
                        subprocess.run(['umount', mnt])
                    break
    finally:
        os.rmdir(mnt)
    entries = re.findall(r'^\s*menuentry\s+[\'"]([^\'"]+)', cfg, re.M)
    check('boot menu (grub.cfg of the installed system) lists Windows', any('windows' in e.lower() for e in entries),
          '; '.join(entries[:8]))
    return 0 if all(results) else 1


# ---- keyboard-only driver ---------------------------------------------------------------------------------------------
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
        self.f.readline()
        self.cmd('qmp_capabilities')

    def cmd(self, name, **args):
        self.f.write(json.dumps({'execute': name, 'arguments': args}) + '\n')
        self.f.flush()
        while True:
            line = self.f.readline()
            if not line:
                raise EOFError('the VM is gone')
            r = json.loads(line)
            if 'return' in r:
                return r['return']
            if 'error' in r:
                raise RuntimeError(f'{name}: {r["error"]["desc"]}')

    def key(self, *names, hold=120):
        self.cmd('send-key', keys=[{'type': 'qcode', 'data': n} for n in names], **{'hold-time': hold})

    def type(self, text):
        for ch in text:
            self.key('spc' if ch == ' ' else ch)
            time.sleep(0.2)


def drive(qmp, serial, shots, scale):
    os.makedirs(shots, exist_ok=True)
    q = Qmp(qmp)
    problems = []
    have_ocr = bool(shutil.which('tesseract') and shutil.which('convert'))
    log(f'OCR {"on" if have_ocr else "OFF (first key sequence is used blindly)"}')

    def serial_text():
        try:
            return open(serial, 'rb').read().decode(errors='replace').replace('\r', '')
        except OSError:
            return ''

    def shot(name):
        path = os.path.join(shots, name + '.png')
        try:
            q.cmd('screendump', filename=path, format='png')
        except EOFError:
            raise
        except Exception as e:  # noqa: BLE001
            log(f'screenshot {name} failed: {e}')
            return ''
        log(f'screenshot {name}.png')
        if not have_ocr:
            return ''
        # The card is a light, translucent panel over a photo: crop to it, grey, enlarge and stretch the contrast, or the text is garbled.
        small = path[:-4] + '.ocr.png'
        c = subprocess.run(['convert', path, '-crop', '760x560+260+110', '+repage', '-colorspace', 'Gray', '-resize', '200%', '-normalize', small],
                           capture_output=True)
        r = subprocess.run(['tesseract', small if c.returncode == 0 else path, 'stdout', '--psm', '6'], capture_output=True, text=True)
        if c.returncode == 0:
            os.unlink(small)
        text = ' '.join(r.stdout.lower().split())
        with open(path[:-4] + '.txt', 'w') as f:
            f.write(text)
        return text

    def seq(keys):
        for k in keys:
            q.key(*k.split('+'))
            time.sleep(0.5)

    def wait_text(words, limit, name):
        end = time.time() + limit * scale
        text = ''
        while time.time() < end:
            time.sleep(2)
            text = shot(name)
            if not have_ocr or any(w in text for w in words):
                return True, text
        return False, text

    def navigate(label, words, sequences, shot_name, limit=8):
        """Tries each key sequence until one of words is on screen (when OCR is there; else the first one only)."""
        for i, keys in enumerate(sequences):
            log(f'{label}: keys {keys}')
            seq(keys)
            ok, text = wait_text(words, limit, shot_name)
            if ok:
                return text
            if not have_ocr:
                break
            log(f'{label}: not there, screen says: {text[:200]}')
        problems.append(f'{label}: never reached {words}')
        return ''

    end = time.time() + 900 * scale
    while 'MWX7-SETUP-READY' not in serial_text():
        if time.time() > end:
            raise RuntimeError('the setup never reported MWX7-SETUP-READY')
        time.sleep(3)
    log('setup is on screen')
    time.sleep(4)
    shot('01-language')
    # language page -> Next. Focus is unknown: Enter presses the default button (Next); else Shift+Tab goes from the first field to Next.
    navigate('Next on the language page', ['where should', 'free space'], [['ret'], ['esc', 'shift+tab', 'ret'], ['esc', 'tab', 'tab', 'tab', 'ret']],
             '02-disk-page', limit=10)
    time.sleep(12 * scale)  # the survey of the disks (it reads the Windows volumes) runs before the list is filled in
    shot('03-disk-page-listed')
    # Tab goes to the first disk (the Windows SSD is vda), Space chooses it; "use the free space" is then preselected.
    navigate('choose the first disk', ['keep everything'], [['tab', 'spc'], ['tab', 'spc'], ['shift+tab', 'spc']], '04-disk-chosen', limit=6)
    # Shift+Tab from the first disk wraps round to the last control, Next.
    text = navigate('Next on the disk page', ['last check'], [['shift+tab', 'ret']], '05-last-check', limit=40)
    if have_ocr and 'nothing that is on the disk now is changed' not in text:
        problems.append('Last check panel does not say that nothing on the disk is changed: ' + text[:300])
    if have_ocr and 'vda' not in text:
        problems.append('Last check does not name the first disk (vda)')
    shot('05-last-check-final')
    # The panel's focus is on "Go back"; Tab moves to "Install MWX 7".
    seq(['tab', 'ret'])
    time.sleep(3)
    text = shot('06-after-install-click')
    # Wi-Fi page (only without a network) -> Next; then the account page.
    for _ in range(4):
        if not have_ocr or 'internet' in text and 'who' not in text:
            seq(['ret'])
        if not have_ocr:
            break
        ok, text = wait_text(['use this pc', 'sign in as'], 5, '07-account-page')
        if ok:
            break
    if have_ocr and 'sign in as' not in text and 'use this pc' not in text:
        problems.append('account page never appeared: ' + text[:200])
    q.type('test')
    seq(['ret'])
    q.type('test')
    seq(['ret'])
    q.type('test')
    shot('08-account-filled')
    seq(['ret'])
    log('account done; waiting for the copy and the restart')
    last_shot, n = 0, 0
    try:
        while True:
            time.sleep(10)
            text = shot('last') if time.time() - last_shot > 20 else ''
            last_shot = time.time()
            if have_ocr and ('could not be put' in text or 'went wrong' in text or 'could not be saved' in text):
                shot('99-failure')
                problems.append('the setup reported a failure: ' + text[:300])
                break
            if have_ocr and 'is ready' in text:
                n += 1
                if n == 1:
                    shot('09-finished')
    except EOFError:
        log('the VM powered off')
    for p in problems:
        log('PROBLEM: ' + p)
    return 1 if problems else 0


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'build':
        build(sys.argv[2])
    elif cmd == 'verify':
        sys.exit(verify(sys.argv[2]))
    elif cmd == 'shot':  # a screenshot of a running VM, for the failure case
        try:
            Qmp(sys.argv[2]).cmd('screendump', filename=sys.argv[3], format='png')
        except Exception as e:  # noqa: BLE001
            log(f'no screenshot: {e}')
    elif cmd == 'drive':
        sys.exit(drive(sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5]) if len(sys.argv) > 5 else 1.0))
    else:
        sys.exit(__doc__)
