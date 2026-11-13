#!/usr/bin/python3
"""Puts MWX 7 on a disk for the first-start setup (runs as root, through sudo, on the ISO only).

  install.py survey                 the disks, as JSON: what is on them and how MWX 7 could use each one
  install.py copy erase|free DISK   partitions, copies the system and installs the boot loader, printing
                                    "STEP <text>" and "PROGRESS <0-100>" lines for the setup's progress bar
  install.py finish ANSWERS.json    the person's choices: account, language, keyboard, time zone; then unmounts
  install.py finish ANSWERS --here  the same on the running system (first start after Settings -> Reset MWX 7)
  install.py recovery sync|prepare  the recovery copy: keep its packages at the installed versions (apt hook) /
                                    make it complete (downloads the ISO once on PCs set up before it existed)
  install.py reinstall keep|clean   Settings -> Reset MWX 7 (through mwx7-admin): MWX 7 again from the newest ISO on
                                    GitHub at the version this PC has; keep: accounts, files, apps and settings come
                                    along; clean: nothing does, the first-start setup runs. Then a restart.
  install.py update check|install   after a reset, before the setup's pages: what is new, then (if wanted) install
  install.py ready                  tells the serial console the setup is on screen (for the automated boot tests)

Reset: the system is unpacked again from the newest MWX 7 ISO published on GitHub into a new subvolume, brought to the
version this PC runs, and swapped in for @ on the next start. No snapshots are kept.

Nothing is ever erased unless the setup passes "erase", which it only does after the person confirmed it. "free" only
adds partitions in space no partition uses. Layout: GPT, a 512 MB EFI partition (UEFI) or a 1 MB BIOS boot partition
(legacy BIOS), and one btrfs partition with zstd compression (less to write, more room) and the usual @ subvolumes.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

MEDIUM = '/run/live/medium'
SQUASHFS = MEDIUM + '/live/filesystem.squashfs'
STATE = '/run/mwx7-install'
TARGET = STATE + '/target'
MIN_SIZE = 20 * 2 ** 30  # the system needs ~6 GB; 20 GB leaves room for updates and some files
ESP_TYPE = 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
BIOS_BOOT_TYPE = '21686148-6449-6e6f-744e-656564454649'
MOUNT_OPTS = 'compress=zstd:1,noatime'
SUBVOLS = (('@', ''), ('@home', 'home'), ('@log', 'var/log'), ('@cache', 'var/cache'))
GROUPS = ('cdrom', 'sudo', 'audio', 'dip', 'video', 'render', 'input', 'plugdev', 'netdev', 'users', 'lpadmin')


def sh(*cmd, quiet=True, **kw):
    if 'input' not in kw:
        kw['stdin'] = subprocess.DEVNULL  # nothing here may ever wait for the keyboard (apt, dpkg)
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()[-400:]}")
    return r.stdout


def chroot(*cmd, **kw):
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', LANG='C.UTF-8')
    return sh('chroot', TARGET, *cmd, env=env, **kw)


def say(kind, value):
    print(kind, value, flush=True)


def uefi():
    return os.path.isdir('/sys/firmware/efi')


# ---- survey -----------------------------------------------------------------------------------------------------
def live_disk():
    """The disk the ISO itself runs from (a USB stick, or none in a VM's CD drive): never offered."""
    try:
        src = sh('findmnt', '-no', 'SOURCE', MEDIUM).strip()
        return sh('lsblk', '-no', 'PKNAME', src).strip().splitlines()[0] or None
    except (RuntimeError, IndexError):
        return None


def kind_of(part):
    fs, ptype = part.get('fstype') or '', (part.get('parttype') or '').lower()
    label = (part.get('label') or part.get('partlabel') or '')
    if ptype == ESP_TYPE or ptype == '0xef':
        return 'efi'
    if ptype == 'de94bba4-06d1-4d40-a16a-bfd50179d6ac' or ptype == '0x27':
        return 'recovery'
    if ptype == BIOS_BOOT_TYPE:
        return 'bios'
    if fs == 'ntfs':
        return 'windows' if label.lower() not in ('data', 'recovery') else 'data'
    if fs in ('ext4', 'btrfs', 'xfs', 'f2fs'):
        return 'linux'
    if fs in ('vfat', 'exfat'):
        return 'data'
    if fs == 'swap':
        return 'swap'
    if fs in ('crypto_LUKS', 'BitLocker'):
        return 'encrypted'
    return 'other' if fs else 'empty'


def free_space(dev):
    """Largest stretch of the disk no partition uses (start sector, sectors), aligned to 1 MiB."""
    if os.geteuid() != 0:
        return None, 0, 512
    try:
        t = json.loads(sh('sfdisk', '-J', dev))['partitiontable']
    except (RuntimeError, ValueError, KeyError):
        return None, 0, 512  # no partition table at all: the whole disk is free, handled as "empty"
    ss = t.get('sectorsize', 512)
    total = int(sh('blockdev', '--getsz', dev)) * 512 // ss
    first, last = t.get('firstlba', 2048), t.get('lastlba', total - 1)
    used = sorted((p['start'], p['start'] + p['size']) for p in t.get('partitions', []))
    best, pos = (0, 0), max(first, 2048)
    for s, e in used + [(last + 1, last + 1)]:
        start = -(-pos // 2048) * 2048
        if s - start > best[1]:
            best = (start, s - start)
        pos = max(pos, e)
    return best[0], best[1], ss


def survey():
    tree = json.loads(sh('lsblk', '-J', '-b', '-o', 'NAME,PATH,SIZE,TYPE,TRAN,RM,RO,MODEL,PTTYPE,FSTYPE,LABEL,'
                         'PARTTYPE,PARTLABEL,MOUNTPOINTS'))
    skip = live_disk()
    disks = []
    for d in tree.get('blockdevices', []):
        if d.get('type') != 'disk' or d['name'].startswith(('zram', 'loop', 'sr', 'fd')) or d.get('ro'):
            continue
        parts = [{'path': p['path'], 'size': int(p['size']), 'fstype': p.get('fstype'), 'label': p.get('label'),
                  'partlabel': p.get('partlabel'), 'kind': kind_of(p)} for p in d.get('children') or []]
        start, sectors, ss = free_space(d['path']) if parts or d.get('pttype') else (None, 0, 512)
        empty = all(p['kind'] == 'empty' for p in parts) and not d.get('fstype')
        has_mwx7 = any(p['label'] == 'MWX7' and p['fstype'] == 'btrfs' for p in parts)
        disk = {'path': d['path'], 'name': d['name'], 'model': (d.get('model') or '').strip(), 'size': int(d['size']),
                'tran': d.get('tran'), 'removable': bool(d.get('rm')), 'pttype': d.get('pttype'), 'parts': parts,
                'empty': empty, 'free': sectors * ss if not empty else int(d['size']),
                'live': d['name'] == skip, 'big_enough': int(d['size']) >= MIN_SIZE, 'has_mwx7': has_mwx7}
        disk['can_free'] = (not empty and not disk['live'] and disk['free'] >= MIN_SIZE and free_mode_ok(disk))
        disks.append(disk)
    print(json.dumps({'firmware': 'uefi' if uefi() else 'bios', 'min_size': MIN_SIZE, 'disks': disks}))


def free_mode_ok(disk):
    """Free space is usable when the partition table can take what MWX 7 adds there."""
    if disk['pttype'] == 'gpt':
        return True
    if disk['pttype'] == 'dos':
        needed = 1 + (1 if uefi() and not any(p['kind'] == 'efi' for p in disk['parts']) else 0)
        return len(disk['parts']) + needed <= 4
    return False


# ---- copy -------------------------------------------------------------------------------------------------------
def partitions_of(disk):
    tree = json.loads(sh('lsblk', '-J', '-o', 'NAME,PATH,TYPE,PARTTYPE', disk))
    return {p['path']: (p.get('parttype') or '').lower() for p in tree['blockdevices'][0].get('children') or []}


def settle():
    subprocess.run(['udevadm', 'settle', '--timeout=15'])


def partition(mode, disk):
    """Returns (root partition, EFI partition or None, whether the EFI partition is MWX 7's own)."""
    efi = uefi()
    before = partitions_of(disk)
    if mode == 'erase':
        for p in before:
            subprocess.run(['wipefs', '-a', '-q', p])
        sh('wipefs', '-a', '-q', disk)
        boot = 'size=512MiB, type=U, name="EFI"' if efi else f'size=1MiB, type={BIOS_BOOT_TYPE}, name="BIOS boot"'
        sh('sfdisk', '-q', '--wipe', 'always', '--wipe-partitions', 'always', disk,
           input=f'label: gpt\n{boot}\ntype=L, name="MWX 7"\n')
        expected = 2
    else:
        start, sectors, ss = free_space(disk)
        if sectors * ss < MIN_SIZE:
            raise RuntimeError('There is not enough free space on this disk any more.')
        gpt = json.loads(sh('sfdisk', '-J', disk))['partitiontable']['label'] == 'gpt'
        lines, pos = [], start
        has_esp = any(t in (ESP_TYPE, '0xef') for t in before.values())
        has_bios = any(t == BIOS_BOOT_TYPE for t in before.values())
        if efi and not has_esp:
            n = 512 * 1024 * 1024 // ss
            lines.append(f'start={pos}, size={n}, type=U'); pos += n
        if not efi and gpt and not has_bios:
            n = 1024 * 1024 // ss
            lines.append(f'start={pos}, size={n}, type={BIOS_BOOT_TYPE}'); pos += n
        lines.append(f'start={pos}, size={start + sectors - pos}, type=L')
        sh('sfdisk', '-q', '--append', disk, input='\n'.join(lines) + '\n')
        expected = len(before) + len(lines)
    # The kernel and udev announce new partitions a moment after sfdisk returns.
    for _ in range(40):
        settle()
        after = partitions_of(disk)
        if len(after) >= expected and all(after.values()) and all(os.path.exists(p) for p in after):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError('The new partitions did not appear.')
    new = [p for p in after if p not in before] if mode == 'free' else list(after)
    root = next(p for p in reversed(new) if after[p] not in (ESP_TYPE, '0xef', BIOS_BOOT_TYPE))
    esp = next((p for p in new if after[p] in (ESP_TYPE, '0xef')), None)
    own_esp = esp is not None
    if efi and esp is None:
        esp = next(p for p, t in after.items() if t in (ESP_TYPE, '0xef'))
    return root, esp, own_esp


def mount_target(root, esp):
    os.makedirs(TARGET, exist_ok=True)
    sh('mount', root, TARGET)
    for sub, _ in SUBVOLS:
        sh('btrfs', '-q', 'subvolume', 'create', f'{TARGET}/{sub}')
    sh('umount', TARGET)
    for sub, where in SUBVOLS:
        path = os.path.join(TARGET, where)
        os.makedirs(path, exist_ok=True)
        sh('mount', '-o', f'subvol=/{sub},{MOUNT_OPTS}', root, path)
    if esp:
        os.makedirs(TARGET + '/boot/efi', exist_ok=True)
        sh('mount', '-o', 'umask=0077', esp, TARGET + '/boot/efi')


def bind_system():
    for d in ('dev', 'proc', 'sys'):
        sh('mount', '--rbind', '/' + d, f'{TARGET}/{d}')
        sh('mount', '--make-rslave', f'{TARGET}/{d}')
    sh('mount', '-t', 'tmpfs', 'tmpfs', TARGET + '/run')
    os.makedirs(TARGET + '/run/udev', exist_ok=True)
    sh('mount', '--bind', '/run/udev', TARGET + '/run/udev')


def unmount_all():
    subprocess.run(['sync'])
    if os.path.ismount(TARGET):
        subprocess.run(['umount', '-R', TARGET])
    if os.path.ismount(TARGET):  # something still busy: detach it so the restart can't hang on it
        subprocess.run(['umount', '-R', '-l', TARGET])


def uuid(dev):
    return sh('blkid', '-s', 'UUID', '-o', 'value', dev).strip()


def copy(mode, disk):
    if mode not in ('erase', 'free'):
        raise SystemExit('mode must be erase or free')
    info = next(d for d in json.loads(subprocess.run([sys.executable, __file__, 'survey'], capture_output=True,
                                                      text=True, check=True).stdout)['disks'] if d['path'] == disk)
    if info['live'] or not info['big_enough'] or (mode == 'free' and not info['can_free']):
        raise SystemExit('That disk cannot be used.')
    unmount_all()
    say('STEP', 'Preparing the disk')
    say('PROGRESS', 1)
    root, esp, own_esp = partition(mode, disk)
    sh('mkfs.btrfs', '-q', '-f', '-L', 'MWX7', root)
    if esp and own_esp:
        sh('mkfs.vfat', '-F', '32', '-n', 'EFI', esp)
    mount_target(root, esp)
    say('PROGRESS', 3)

    # The system itself: unpacked straight from the ISO on every processor core, the slow part (~1-3 minutes).
    say('STEP', 'Copying MWX 7')
    p = subprocess.Popen(['unsquashfs', '-f', '-d', TARGET, '-p', str(os.cpu_count() or 2), '-percentage', SQUASHFS],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        if line.strip().isdigit():
            say('PROGRESS', 3 + int(line) * 72 // 100)
    if p.wait() != 0:
        raise RuntimeError('Copying the system failed (the ISO file may be damaged; downloading it again helps).')
    kver = os.listdir(TARGET + '/lib/modules')[0]
    shutil.copyfile(MEDIUM + '/live/vmlinuz', f'{TARGET}/boot/vmlinuz-{kver}')
    shutil.copyfile(MEDIUM + '/live/initrd.img', f'{TARGET}/boot/initrd.img-{kver}')

    say('STEP', 'Setting up MWX 7')
    r = uuid(root)
    fstab = ['# <file system> <mount point> <type> <options> <dump> <pass>']
    for sub, where in SUBVOLS:
        fstab.append(f'UUID={r} /{where} btrfs subvol=/{sub},{MOUNT_OPTS} 0 0')
    if esp:
        fstab.append(f'UUID={uuid(esp)} /boot/efi vfat umask=0077 0 1')
    write('etc/fstab', '\n'.join(fstab) + '\n')
    write('etc/machine-id', '')  # a new one on the first start
    for f in ('var/lib/dbus/machine-id',):
        if os.path.lexists(os.path.join(TARGET, f)):
            os.unlink(os.path.join(TARGET, f))
    # ISO-only pieces: the setup's passwordless sudo, its session and the advanced installer.
    for f in ('etc/sudoers.d/mwx7-live', 'usr/local/bin/mwx7-install', 'usr/local/bin/mwx7-oobe-session'):
        if os.path.lexists(os.path.join(TARGET, f)):
            os.unlink(os.path.join(TARGET, f))
    for d in ('etc/calamares', 'usr/lib/calamares'):
        shutil.rmtree(os.path.join(TARGET, d), ignore_errors=True)
    write('etc/mwx7/installed', 'Installed by the MWX 7 first-start setup.\n')
    write('etc/default/grub', GRUB_DEFAULTS)
    write('etc/greetd/config.toml', greetd_config(None))
    bind_system()
    say('PROGRESS', 77)
    # live-boot and the advanced installer only make sense on the ISO. Removing live-boot also rebuilds the start-up
    # files (initramfs) for this PC.
    chroot('apt-get', 'purge', '-y', '-qq', '--autoremove', '-o', 'Dpkg::Use-Pty=0', 'live-boot',
           'live-boot-initramfs-tools', 'calamares', 'qt6-wayland', 'qml6-module-qtquick', 'qml6-module-qtquick-window')
    say('PROGRESS', 90)

    say('STEP', 'Installing the boot menu')
    if uefi():
        extra = ['--force-extra-removable'] if own_esp else []  # never replace another system's fallback loader
        chroot('grub-install', '--target=x86_64-efi', '--efi-directory=/boot/efi', '--bootloader-id=MWX7',
               '--uefi-secure-boot', *extra)
        # Debian's signed GRUB (the one Secure Boot accepts) reads its first config from /EFI/debian, whatever folder it
        # was installed to.
        stub = f'{TARGET}/boot/efi/EFI/MWX7/grub.cfg'
        for folder in ('debian',) + (('BOOT',) if own_esp else ()):
            os.makedirs(f'{TARGET}/boot/efi/EFI/{folder}', exist_ok=True)
            shutil.copyfile(stub, f'{TARGET}/boot/efi/EFI/{folder}/grub.cfg')
    else:
        chroot('grub-install', '--target=i386-pc', disk)
    chroot('update-grub')
    say('STEP', 'Keeping a recovery copy')
    store_install_medium(root)
    with open(STATE + '/state.json', 'w') as f:
        json.dump({'disk': disk, 'root': root, 'esp': esp}, f)
    say('PROGRESS', 100)
    say('STEP', 'Done')


FIRSTBOOT_SUDOERS = ('# MWX 7 first start after a reset: the setup runs as this user and needs root for its own steps only.\n'
                     'mwx ALL=(root) NOPASSWD: /usr/bin/python3 /usr/share/mwx7/oobe/install.py *\n')


# ---- The recovery copy (Settings -> Repair MWX 7 / Reset to factory, and "Repair MWX 7" in the boot menu) ---------
# The btrfs subvolume @recovery (never mounted while MWX 7 runs, never touched by Repair or Reset) holds the ISO this PC
# was set up from, plus the exact package files of everything that has changed since (updates, apps added). Together
# they rebuild this PC's current version without downloading anything. An apt hook keeps the packages in step.
GITHUB = 'https://github.com/cosminflrn/MWX7/releases'
RELEASES = 'https://api.github.com/repos/cosminflrn/MWX7/releases'
KEYRING = '/usr/share/keyrings/mwx7-updates.gpg'
REC = STATE + '/recovery'  # where @recovery is mounted while it is used
# Repair (keep everything): this PC's accounts, logon, network, language, keyboard and time zone come along whole...
KEEP = ('etc/passwd', 'etc/shadow', 'etc/group', 'etc/gshadow', 'etc/subuid', 'etc/subgid', 'etc/greetd/config.toml',
        'etc/hostname', 'etc/hosts', 'etc/default/locale', 'etc/default/keyboard', 'etc/timezone', 'etc/localtime',
        'etc/machine-id', 'etc/NetworkManager/system-connections', 'etc/sudoers.d', 'var/lib/AccountsService',
        'var/lib/flatpak', 'var/lib/bluetooth')
# ...and from these, whatever the new system doesn't have (apps put in /opt or /usr/local, extra app sources).
ADD = ('opt', 'usr/local', 'etc/apt/sources.list.d', 'etc/apt/keyrings', 'etc/apt/trusted.gpg.d', 'usr/share/keyrings')


def root_device():
    source = sh('findmnt', '-no', 'SOURCE', '/').strip()  # /dev/sda2[/@]
    if sh('findmnt', '-no', 'FSTYPE', '/').strip() != 'btrfs' or not source.endswith('[/@]'):
        raise RuntimeError('This needs the disk layout MWX 7 sets up.')
    return source.split('[')[0]


class Recovery:
    """@recovery mounted for the duration of a with-block (created on first use)."""
    def __init__(self, root):
        self.root = root

    def __enter__(self):
        top = STATE + '/rtop'
        os.makedirs(top, exist_ok=True)
        sh('mount', '-o', 'subvolid=5', self.root, top)
        try:
            if not os.path.isdir(top + '/@recovery'):
                sh('btrfs', '-q', 'subvolume', 'create', top + '/@recovery')
        finally:
            sh('umount', top)
        os.makedirs(REC, exist_ok=True)
        if not os.path.ismount(REC):
            sh('mount', '-o', f'subvol=@recovery,{MOUNT_OPTS}', self.root, REC)
        os.makedirs(REC + '/debs', exist_ok=True)
        return REC

    def __exit__(self, *_exc):
        subprocess.run(['umount', REC], capture_output=True)


def iso_manifest(iso_path):
    """{package: version} of the system inside an ISO, read from its dpkg database without unpacking it."""
    mnt = STATE + '/iso-m'
    os.makedirs(mnt, exist_ok=True)
    sh('mount', '-o', 'loop,ro', iso_path, mnt)
    try:
        status = sh('unsquashfs', '-cat', mnt + '/live/filesystem.squashfs', 'var/lib/dpkg/status')
    finally:
        subprocess.run(['umount', mnt])
    out, pkg = {}, None
    for line in status.splitlines():
        if line.startswith('Package: '):
            pkg = line[9:].strip()
        elif line.startswith('Status: ') and not line.endswith(' installed'):
            pkg = None
        elif line.startswith('Version: ') and pkg:
            out[pkg] = line[9:].strip()
    return out


def deb_name(pkg, version, arch):
    return f"{pkg}_{version.replace(':', '%3a')}_{arch}.deb"


def recovery_sync(fetch):
    """The packages that differ from the ISO, at the versions installed now. Run after every package change (apt
    hook); fetch: also download what apt's cache no longer has (needs internet; never during a dpkg run)."""
    with Recovery(root_device()) as rec:
        if not os.path.exists(rec + '/manifest.json'):
            return
        base = json.load(open(rec + '/manifest.json'))
        want = {}
        for line in sh('dpkg-query', '-W', '-f', '${db:Status-Abbrev} ${Package} ${Version} ${Architecture}\n').splitlines():
            st, pkg, ver, arch = line.split()
            if st.startswith('ii') and base.get(pkg) != ver:
                want[deb_name(pkg, ver, arch)] = (pkg, ver)
        have = set(os.listdir(rec + '/debs'))
        for name in have - set(want) - {'Packages'}:
            os.unlink(f'{rec}/debs/{name}')
        missing = []
        for name, (pkg, ver) in want.items():
            if name in have:
                continue
            cached = f'/var/cache/apt/archives/{name}'
            if os.path.exists(cached):
                sh('cp', '--reflink=auto', cached, f'{rec}/debs/{name}')
            else:
                missing.append((name, pkg, ver))
        if fetch:
            for name, pkg, ver in missing:
                subprocess.run(['apt-get', 'download', '-q', f'{pkg}={ver}'], cwd=rec + '/debs', capture_output=True)
        with open(rec + '/debs/Packages', 'w') as f:
            subprocess.run(['apt-ftparchive', 'packages', '.'], cwd=rec + '/debs', stdout=f, check=True)
        n = len([d for d in os.listdir(rec + '/debs') if d.endswith('.deb')])
        state = {'version': open('/usr/share/mwx7/version').read().strip(), 'packages': n, 'missing': len(want) - n}
        # Settings reads this copy (it can't look inside @recovery) to say whether Repair and Reset are ready.
        os.makedirs('/var/lib/mwx7', exist_ok=True)
        for path in (rec + '/state.json', '/var/lib/mwx7/recovery.json'):
            with open(path, 'w') as f:
                json.dump(state, f)


def fetch_iso(dest):
    """The newest MWX 7 ISO from GitHub into dest, for PCs set up before the recovery copy existed. Resumes a broken
    download and checks the ISO's signature (the update channel's key) or, for ISOs published before signing, its
    checksum."""
    import hashlib
    import urllib.request
    try:
        latest = json.load(urllib.request.urlopen(GITHUB + '/latest/download/latest.json', timeout=30))
        name = latest['iso']
        url = f'{GITHUB}/latest/download/{name}'
    except (OSError, ValueError, KeyError):
        req = urllib.request.Request(RELEASES + '?per_page=20', headers={'Accept': 'application/vnd.github+json'})
        rels = json.load(urllib.request.urlopen(req, timeout=30))
        name, url = next((a['name'], a['browser_download_url']) for r in rels for a in r.get('assets', [])
                         if a['name'].endswith('.iso'))
    part = dest + '.part'
    while True:
        done = os.path.getsize(part) if os.path.exists(part) else 0
        req = urllib.request.Request(url, headers={'Range': f'bytes={done}-'} if done else {})
        with urllib.request.urlopen(req, timeout=60) as r:
            if done and r.status != 206:
                done = 0  # the server ignored the resume: start over
            total = done + int(r.headers.get('Content-Length') or 0)
            with open(part, 'ab' if done else 'wb') as out:
                while True:
                    block = r.read(1 << 20)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if total:
                        say('PROGRESS', done * 100 // total)
        if not total or done >= total:
            break
    sig = None
    try:
        sig = urllib.request.urlopen(url + '.sig', timeout=30).read()
    except OSError:
        pass
    if sig:
        with open(part + '.sig', 'wb') as f:
            f.write(sig)
        ok = subprocess.run(['gpgv', '--keyring', KEYRING, part + '.sig', part], capture_output=True).returncode == 0
        os.unlink(part + '.sig')
    else:
        want = urllib.request.urlopen(url + '.sha256', timeout=30).read().decode().split()[0].lower()
        h = hashlib.sha256()
        with open(part, 'rb') as f:
            for block in iter(lambda: f.read(1 << 20), b''):
                h.update(block)
        ok = h.hexdigest() == want
    if not ok:
        os.unlink(part)
        raise RuntimeError('The downloaded MWX 7 was damaged or not genuine. Try again.')
    os.replace(part, dest)


def recovery_prepare():
    """Makes sure the recovery copy is complete: the ISO (downloaded once if this PC never had it) and its packages."""
    with Recovery(root_device()) as rec:
        if not os.path.exists(rec + '/manifest.json'):
            say('STEP', 'Downloading MWX 7 for the recovery copy')
            if not os.path.exists(rec + '/mwx7.iso'):
                fetch_iso(rec + '/mwx7.iso')
            with open(rec + '/manifest.json', 'w') as f:
                json.dump(iso_manifest(rec + '/mwx7.iso'), f)
    say('STEP', 'Copying the packages of this version')
    recovery_sync(fetch=True)


def store_install_medium(root):
    """At setup: the ISO MWX 7 was installed from becomes the recovery copy (no download ever needed)."""
    dev = sh('findmnt', '-no', 'SOURCE', MEDIUM).strip()
    if not dev:
        return
    with Recovery(root) as rec:
        size = int(sh('blockdev', '--getsize64', dev)) if dev.startswith('/dev/') else os.path.getsize(dev)
        with open(dev, 'rb') as src, open(rec + '/mwx7.iso.part', 'wb') as out:
            left = size
            while left > 0:
                block = src.read(min(4 << 20, left))
                if not block:
                    break
                out.write(block)
                left -= len(block)
        os.replace(rec + '/mwx7.iso.part', rec + '/mwx7.iso')
        with open(rec + '/manifest.json', 'w') as f:
            json.dump(iso_manifest(rec + '/mwx7.iso'), f)
    write('var/lib/mwx7/recovery.json', json.dumps({'packages': 0, 'missing': 0}) + '\n')


def keep_everything(old, new):
    """Repair: the rebuilt system gets the old one's accounts and settings; the homes (with every app's settings)
    are untouched. Only MWX 7's and Debian's own files come back new: that is what repairs a broken system."""
    def cp(src, dst):
        sh('cp', '-a', '--reflink=auto', src, dst)
    for rel in KEEP:
        src, dst = f'{old}/{rel}', f'{new}/{rel}'
        if not os.path.lexists(src):
            continue
        if os.path.isdir(dst) and not os.path.islink(dst):
            shutil.rmtree(dst)
        elif os.path.lexists(dst):
            os.unlink(dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        cp(src, dst)
    for rel in ADD:
        if os.path.isdir(f'{old}/{rel}'):
            for name in os.listdir(f'{old}/{rel}'):
                if not os.path.lexists(f'{new}/{rel}/{name}'):
                    os.makedirs(f'{new}/{rel}', exist_ok=True)
                    cp(f'{old}/{rel}/{name}', f'{new}/{rel}/{name}')


def reinstall(keep):
    """Settings -> Repair MWX 7 (keep) / Reset to factory, or the boot menu's Repair: MWX 7 rebuilt from the recovery
    copy at the version this PC runs, no download. The new system is unpacked beside the old one; the swap happens
    only once it is complete, and anything failing before that leaves the PC as it was."""
    global TARGET
    root = root_device()
    top, iso = STATE + '/top', STATE + '/iso'
    for d in (top, iso):
        os.makedirs(d, exist_ok=True)
    # The person only asks for Repair or Reset: a recovery copy that is missing or incomplete is completed first.
    try:
        st = json.load(open('/var/lib/mwx7/recovery.json'))
    except (OSError, ValueError):
        st = None
    if not st or st.get('missing'):
        recovery_prepare()
    with Recovery(root) as rec:
        if not os.path.exists(rec + '/manifest.json'):
            raise RuntimeError('MWX 7 could not be downloaded for this. Connect to the internet and try again.')
        sh('mount', '-o', 'subvolid=5', root, top)
        new, swapped = top + '/@new', False
        try:
            for old in ('@new', '@old', '@home-old', '@log-old', '@cache-old', '@factory'):
                if os.path.isdir(f'{top}/{old}'):
                    subprocess.run(['btrfs', 'property', 'set', '-ts', f'{top}/{old}', 'ro', 'false'], capture_output=True)
                    sh('btrfs', '-q', 'subvolume', 'delete', f'{top}/{old}')
            free = shutil.disk_usage(top).free
            if free < 5 << 30:
                raise RuntimeError(f'This needs about 5 GB free on the disk; there are {free / (1 << 30):.1f} GB.')
            say('STEP', 'Unpacking MWX 7')
            sh('mount', '-o', 'loop,ro', rec + '/mwx7.iso', iso)
            try:
                sh('btrfs', '-q', 'subvolume', 'create', new)
                p = subprocess.Popen(['unsquashfs', '-f', '-d', new, '-p', str(os.cpu_count() or 2), '-percentage',
                                      iso + '/live/filesystem.squashfs'], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True)
                for line in p.stdout:
                    if line.strip().isdigit():
                        say('PROGRESS', int(line) * 50 // 100)
                if p.wait() != 0:
                    raise RuntimeError('Unpacking MWX 7 failed.')
                kver = os.listdir(new + '/lib/modules')[0]
                shutil.copyfile(iso + '/live/vmlinuz', f'{new}/boot/vmlinuz-{kver}')
                shutil.copyfile(iso + '/live/initrd.img', f'{new}/boot/initrd.img-{kver}')
            finally:
                subprocess.run(['umount', iso])
            # The swap comes first so everything below runs where the system will live (the boot menu records the
            # subvolume's name); a failure below swaps back.
            os.rename(f'{top}/@', f'{top}/@old')
            os.rename(new, f'{top}/@')
            swapped = True
            TARGET = STATE + '/target'
            os.makedirs(TARGET, exist_ok=True)
            sh('mount', '-o', f'subvol=@,{MOUNT_OPTS}', root, TARGET)
            old = top + '/@old'
            say('STEP', 'Setting up MWX 7')
            say('PROGRESS', 52)
            shutil.copyfile(old + '/etc/fstab', TARGET + '/etc/fstab')  # same disk, same subvolumes
            for f in ('etc/sudoers.d/mwx7-live', 'usr/local/bin/mwx7-install', 'usr/local/bin/mwx7-oobe-session',
                      'var/lib/dbus/machine-id'):
                if os.path.lexists(os.path.join(TARGET, f)):
                    os.unlink(os.path.join(TARGET, f))
            for d in ('etc/calamares', 'usr/lib/calamares'):
                shutil.rmtree(os.path.join(TARGET, d), ignore_errors=True)
            write('etc/machine-id', '')
            write('etc/mwx7/installed', 'Installed by MWX 7 (repair or reset).\n')
            write('etc/default/grub', GRUB_DEFAULTS)
            if keep:
                keep_everything(old, TARGET)
            else:
                # Absolutely clean: the first-start setup runs (it offers the newest version) as the ISO's setup user.
                write('etc/mwx7/firstboot', 'Start into the first-start setup.\n')
                write('etc/sudoers.d/mwx7-firstboot', FIRSTBOOT_SUDOERS, 0o440)
                write('etc/greetd/config.toml', greetd_config(None, firstboot=True))
            bind_system()
            os.makedirs(TARGET + '/recovery', exist_ok=True)
            sh('mount', '--bind', rec, TARGET + '/recovery')
            if os.path.ismount('/boot/efi'):
                os.makedirs(TARGET + '/boot/efi', exist_ok=True)
                sh('mount', '--bind', '/boot/efi', TARGET + '/boot/efi')
            env = dict(os.environ, DEBIAN_FRONTEND='noninteractive')
            chroot('apt-get', 'purge', '-y', '-qq', '-o', 'Dpkg::Use-Pty=0', 'live-boot', 'live-boot-initramfs-tools',
                   'calamares', 'qt6-wayland', 'qml6-module-qtquick', 'qml6-module-qtquick-window')
            say('PROGRESS', 60)
            # This PC's versions, from the recovery copy only (no internet): updated packages always; for Repair also
            # the apps added since setup.
            say('STEP', 'Bringing MWX 7 to this PC\'s version')
            base = json.load(open(rec + '/manifest.json'))
            wanted = []
            for line in open(rec + '/debs/Packages').read().split('\n\n'):
                m = dict(re.findall(r'^(Package|Version): (.*)$', line, re.M))
                if m.get('Package') and (keep or m['Package'] in base):
                    wanted.append(f"{m['Package']}={m['Version']}")
            if wanted:
                src = TARGET + '/tmp/mwx7-recovery.list'
                write('tmp/mwx7-recovery.list', 'deb [trusted=yes] file:/recovery/debs ./\n')
                opts = ['-o', 'Dir::Etc::SourceList=/tmp/mwx7-recovery.list', '-o', 'Dir::Etc::SourceParts=-',
                        '-o', 'APT::Get::List-Cleanup=0', '-o', 'Dpkg::Use-Pty=0']
                chroot('apt-get', *opts, 'update', '-q')
                r = subprocess.run(['chroot', TARGET, 'apt-get', *opts, 'install', '-y', '-q', '--allow-downgrades',
                                    '-o', 'Dpkg::Options::=--force-confold', *wanted], capture_output=True, text=True,
                                   env=env, stdin=subprocess.DEVNULL)
                if r.returncode != 0:
                    raise RuntimeError('Installing this PC\'s version failed: ' + (r.stdout + r.stderr).strip()[-300:])
                os.unlink(src)
            chroot('apt-get', 'autoremove', '--purge', '-y', '-qq', '-o', 'Dpkg::Use-Pty=0')
            say('PROGRESS', 88)
            say('STEP', 'Installing the boot menu')
            if uefi():
                chroot('grub-install', '--target=x86_64-efi', '--efi-directory=/boot/efi', '--bootloader-id=MWX7',
                       '--uefi-secure-boot')
                os.makedirs(f'{TARGET}/boot/efi/EFI/debian', exist_ok=True)
                shutil.copyfile(f'{TARGET}/boot/efi/EFI/MWX7/grub.cfg', f'{TARGET}/boot/efi/EFI/debian/grub.cfg')
            else:
                chroot('grub-install', '--target=i386-pc', '/dev/' + sh('lsblk', '-no', 'PKNAME', root).strip())
            chroot('update-grub')
            unmount_all()
            if not keep:
                for sub in ('@home', '@log', '@cache'):
                    if os.path.isdir(f'{top}/{sub}'):
                        os.rename(f'{top}/{sub}', f'{top}/{sub}-old')
                    sh('btrfs', '-q', 'subvolume', 'create', f'{top}/{sub}')
            else:
                # Repair has no setup to delete the replaced system: a one-time job on the next start does.
                write_cleanup(top + '/@')
        except BaseException:
            unmount_all()
            if swapped:
                os.rename(f'{top}/@', f'{top}/@new')
                os.rename(f'{top}/@old', f'{top}/@')
            if os.path.isdir(new):
                subprocess.run(['btrfs', '-q', 'subvolume', 'delete', new], capture_output=True)
            raise
        finally:
            subprocess.run(['umount', top], capture_output=True)
    say('PROGRESS', 100)
    say('STEP', 'Restarting')
    subprocess.Popen(['systemctl', 'reboot'])


CLEANUP_UNIT = '''[Unit]
Description=MWX 7: delete the system replaced by Repair MWX 7

[Service]
Type=exec
ExecStart=/bin/sh -c 'd=$$(findmnt -no SOURCE / | cut -d[ -f1); mkdir -p /run/mwx7-cleanup && \\
  mount -o subvolid=5 "$$d" /run/mwx7-cleanup && { btrfs -q subvolume delete /run/mwx7-cleanup/@old || true; \\
  umount /run/mwx7-cleanup; }; rm -f /etc/systemd/system/multi-user.target.wants/mwx7-repair-cleanup.service \\
  /etc/systemd/system/mwx7-repair-cleanup.service'

[Install]
WantedBy=multi-user.target
'''


def write_cleanup(new):
    with open(f'{new}/etc/systemd/system/mwx7-repair-cleanup.service', 'w') as f:
        f.write(CLEANUP_UNIT)
    os.makedirs(f'{new}/etc/systemd/system/multi-user.target.wants', exist_ok=True)
    link = f'{new}/etc/systemd/system/multi-user.target.wants/mwx7-repair-cleanup.service'
    if not os.path.lexists(link):
        os.symlink('/etc/systemd/system/mwx7-repair-cleanup.service', link)


def update(action):
    """After a reset, before the setup's pages: "check" says what is new (NEWEST <version>, COUNT <n>), "install"
    installs it. The setup asks in between, so the person decides."""
    if action == 'check':
        say('STEP', 'Looking for updates')
        r = subprocess.run(['/usr/share/mwx7/bin/mwx7-update', 'check'], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError('No internet connection: updates can be installed later in Settings.')
        pkgs = dict(l.split()[:2] for l in r.stdout.splitlines() if len(l.split()) >= 2)
        if pkgs.get('mwx7-desktop'):
            say('NEWEST', pkgs['mwx7-desktop'])
        say('COUNT', len(pkgs))
        return
    say('STEP', 'Installing updates')
    p = subprocess.Popen(['/usr/share/mwx7/bin/mwx7-update', 'install'], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        if line.startswith(('Unpacking', 'Setting up')):
            say('STEP', line.strip()[:90])
    if p.wait() != 0:
        raise RuntimeError('Installing updates did not finish: try again later in Settings.')
    say('STEP', 'Updates installed')


GRUB_DEFAULTS = '''# MWX 7 boot menu settings. Run "sudo update-grub" after changing this file.
# Always the first entry: remembering the last choice needs GRUB to write to the disk, which it can't on btrfs
# ("error: sparse file not allowed" on every start).
GRUB_DEFAULT=0
GRUB_TIMEOUT=1
GRUB_DISTRIBUTOR="MWX 7"
# loglevel=3 after "quiet" (which sets 4): only critical kernel messages may cover the splash.
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=3 vt.global_cursor_default=0"
GRUB_CMDLINE_LINUX=""
GRUB_DISABLE_OS_PROBER=false
GRUB_DISABLE_RECOVERY=true
# The menu in MWX 7's look. Hidden (straight into MWX 7; holding Esc during that one second shows it, with Repair MWX 7
# and the previous version) unless another system such as Windows is there to choose: then it shows for 5 seconds
# (mwx7-grub-names turns that on in GRUB's os-prober script).
GRUB_THEME=/usr/share/grub/themes/mwx7/theme.txt
GRUB_GFXMODE=1920x1080,1280x800,auto
GRUB_GFXPAYLOAD_LINUX=keep
GRUB_TIMEOUT_STYLE=hidden
'''


def greetd_config(autologin_user, firstboot=False):
    """The MWX 7 logon screen; with automatic logon the desktop starts right after boot (Settings -> Account)."""
    if firstboot:
        return ('# Written by MWX 7: the first start after a reset runs the first-start setup.\n[terminal]\nvt = 1\n\n'
                '[default_session]\ncommand = "/usr/share/mwx7/oobe/oobe-session --firstboot"\nuser = "mwx"\n')
    text = ('# Written by MWX 7 (first-start setup, Settings -> Account).\n[terminal]\nvt = 1\n\n'
            '[default_session]\ncommand = "/usr/local/bin/mwx7-greeter-session"\nuser = "_greetd"\n')
    if autologin_user:
        text += f'\n[initial_session]\ncommand = "/usr/local/bin/mwx7-session"\nuser = "{autologin_user}"\n'
    return text


def write(rel, text, mode=0o644):
    path = os.path.join(TARGET, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)
    os.chmod(path, mode)


# ---- finish -----------------------------------------------------------------------------------------------------
def finish(answers_path, here=False):
    global TARGET
    if here:
        TARGET = '/'
    with open(answers_path) as f:
        a = json.load(f)
    os.unlink(answers_path)  # it may hold the password
    login, full = a['login'], a['fullname']
    if not login.isascii() or not login.replace('-', '').replace('_', '').isalnum() or login in ('root', 'mwx'):
        raise SystemExit('invalid user name')
    say('STEP', 'Creating your account')
    # The ISO's setup user (its mail spool never existed, which userdel reports but is harmless).
    # -f: after a reset the setup itself runs as mwx.
    subprocess.run(['chroot', TARGET, 'userdel', '-f', '-r', 'mwx'], capture_output=True)
    shutil.rmtree(TARGET + '/home/mwx', ignore_errors=True)
    groups = [g for g in GROUPS if subprocess.run(['chroot', TARGET, 'getent', 'group', g],
                                                  capture_output=True).returncode == 0]
    chroot('useradd', '-m', '-s', '/bin/bash', '-c', full, '-G', ','.join(groups), login)
    if a.get('password'):
        chroot('chpasswd', input=f"{login}:{a['password']}\n")
    else:
        chroot('passwd', '-d', login)  # no password: the logon screen lets this account straight in
    chroot('passwd', '-l', 'root')  # nobody logs in as root; administration goes through the person's account
    pic = a.get('picture')
    if pic and os.path.isfile(pic):
        os.makedirs(TARGET + '/var/lib/AccountsService/icons', exist_ok=True)
        shutil.copyfile(pic, f'{TARGET}/var/lib/AccountsService/icons/{login}')

    say('STEP', 'Applying your settings')
    lang = a.get('language') or 'en_US.UTF-8'
    write('etc/default/locale', f'LANG={lang}\n')
    layout, variant = a.get('layout') or 'us', a.get('variant') or ''
    write('etc/default/keyboard', f'XKBMODEL="pc105"\nXKBLAYOUT="{layout}"\nXKBVARIANT="{variant}"\nXKBOPTIONS=""\n'
                                  'BACKSPACE="guess"\n')
    # The desktop's keyboard: the chosen layout first, US English as the second (Windows key + Space switches).
    ini = open(TARGET + '/etc/mwx7/wayfire.ini').read()
    lay, var = (layout, variant) if layout == 'us' else (f'{layout},us', f'{variant},')
    ini = re.sub(r'^xkb_layout = .*$', f'xkb_layout = {lay}', ini, flags=re.M)
    ini = re.sub(r'^xkb_variant = .*$', f'xkb_variant = {var}', ini, flags=re.M)
    home = f'{TARGET}/home/{login}'
    write(f'home/{login}/.config/mwx7/wayfire.ini', ini)
    tz = a.get('timezone') or 'Europe/Bucharest'
    if os.path.exists(f'{TARGET}/usr/share/zoneinfo/{tz}'):
        target_tz = f'{TARGET}/etc/localtime'
        if os.path.lexists(target_tz):
            os.unlink(target_tz)
        os.symlink(f'/usr/share/zoneinfo/{tz}', target_tz)
        write('etc/timezone', tz + '\n')
    host = a.get('hostname') or 'mwx7'
    write('etc/hostname', host + '\n')
    hosts = [l for l in open(TARGET + '/etc/hosts').read().splitlines() if not l.startswith('127.0.1.1')]
    write('etc/hosts', '\n'.join(hosts + [f'127.0.1.1\t{host}']) + '\n')
    # Wi-Fi networks joined during the setup (after a reset they are already in place).
    for f in [] if here else glob.glob('/etc/NetworkManager/system-connections/*'):
        dst = TARGET + '/etc/NetworkManager/system-connections/' + os.path.basename(f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(f, dst)
        os.chmod(dst, 0o600)
    write('etc/greetd/config.toml', greetd_config(login if a.get('autologin') else None))
    chroot('chown', '-R', f'{login}:{login}', f'/home/{login}')
    os.chmod(home, 0o700)
    if here:
        finish_reset()
    else:
        unmount_all()
    say('PROGRESS', 100)
    say('STEP', 'Done')


def finish_reset():
    """End of the first start after a reset: back to the normal logon, the old system's leftovers deleted, restart."""
    for f in ('/etc/mwx7/firstboot', '/etc/sudoers.d/mwx7-firstboot'):
        if os.path.exists(f):
            os.unlink(f)
    root = sh('findmnt', '-no', 'SOURCE', '/').strip().split('[')[0]
    top = STATE + '/top'
    os.makedirs(top, exist_ok=True)
    sh('mount', '-o', 'subvolid=5', root, top)
    try:
        for old in ('@old', '@home-old', '@log-old', '@cache-old'):
            if os.path.isdir(f'{top}/{old}'):
                subprocess.run(['btrfs', '-q', 'subvolume', 'delete', f'{top}/{old}'], capture_output=True)
    finally:
        sh('umount', top)
    # The setup's own user is gone now; the restart is scheduled here so the setup can still say it is done.
    subprocess.run(['systemd-run', '--on-active=7', '--', 'systemctl', 'reboot'], capture_output=True)


def ready():
    for tty in ('/dev/ttyS0', '/dev/console'):
        try:
            with open(tty, 'w') as f:
                f.write('\nMWX7-SETUP-READY\n')
            return
        except OSError:
            continue


if __name__ == '__main__':
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ''), sys.argv[2:]
    if os.geteuid() != 0 and cmd != 'survey':  # survey also works unprivileged (the setup's preview), minus free space
        raise SystemExit('run as root')
    try:
        if cmd == 'survey':
            survey()
        elif cmd == 'copy' and len(args) == 2 and not os.path.exists('/etc/mwx7/installed'):  # never on an installed PC
            copy(*args)
        elif cmd == 'finish' and len(args) == 1:
            finish(args[0])
        elif cmd == 'finish' and args[1:] == ['--here'] and os.path.exists('/etc/mwx7/firstboot'):
            finish(args[0], here=True)
        elif cmd == 'recovery' and args in (['sync'], ['prepare']) and os.path.exists('/etc/mwx7/installed'):
            recovery_sync(fetch=False) if args == ['sync'] else recovery_prepare()
        elif cmd == 'reinstall' and args in (['keep'], ['clean']) and os.path.exists('/etc/mwx7/installed'):
            reinstall(args[0] == 'keep')
        elif cmd == 'update' and args in (['check'], ['install']) and os.path.exists('/etc/mwx7/firstboot'):
            update(args[0])
        elif cmd == 'ready':
            ready()
        else:
            raise SystemExit(__doc__)
    except (RuntimeError, StopIteration, OSError) as e:
        say('ERROR', str(e) or type(e).__name__)
        sys.exit(1)
