#!/usr/bin/python3
"""Puts MWX 7 on a disk for the first-start setup (runs as root, through sudo, on the ISO only).

  install.py survey                 the disks, as JSON: what is on them and how MWX 7 could use each one
  install.py copy erase|free DISK   partitions, copies the system and installs the boot loader, printing
                                    "STEP <text>" and "PROGRESS <0-100>" lines for the setup's progress bar
  install.py finish ANSWERS.json    the person's choices: account, language, keyboard, time zone; then unmounts
  install.py finish ANSWERS --here  the same on the running system (first start after Settings -> Reset MWX 7)
  install.py update                 installs the newest updates (that first start, before the setup's pages)
  install.py ready                  tells the serial console the setup is on screen (for the automated boot tests)

Reset: right after copying, the fresh system is kept as the read-only btrfs snapshot @factory, set to start into the
first-start setup. Settings -> Reset MWX 7 (mwx7-admin reset) swaps it in for @ and gives @home a fresh start.

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
    say('STEP', 'Keeping a factory copy')
    make_factory(root)
    with open(STATE + '/state.json', 'w') as f:
        json.dump({'disk': disk, 'root': root, 'esp': esp}, f)
    say('PROGRESS', 100)
    say('STEP', 'Done')


FIRSTBOOT_SUDOERS = ('# MWX 7 first start after a reset: the setup runs as this user and needs root for its own steps only.\n'
                     'mwx ALL=(root) NOPASSWD: /usr/bin/python3 /usr/share/mwx7/oobe/install.py *\n')


def make_factory(root):
    """The fresh system as a read-only snapshot, so Settings -> Reset can bring it back in seconds, no ISO needed.
    It shares all its data with the running system, so it only takes space for what updates replace later."""
    write('etc/mwx7/factory', 'This system has a factory copy (Settings -> Updates -> Reset MWX 7).\n')
    top = STATE + '/top'
    os.makedirs(top, exist_ok=True)
    sh('mount', '-o', 'subvolid=5', root, top)
    try:
        sh('btrfs', '-q', 'subvolume', 'snapshot', f'{top}/@', f'{top}/@factory')
        f = top + '/@factory'
        # Started from the factory copy, MWX 7 goes straight into the first-start setup (without the disk page).
        for rel, text, mode in (('etc/mwx7/firstboot', 'Start into the first-start setup.\n', 0o644),
                                ('etc/sudoers.d/mwx7-firstboot', FIRSTBOOT_SUDOERS, 0o440),
                                ('etc/greetd/config.toml', greetd_config(None, firstboot=True), 0o644)):
            with open(f'{f}/{rel}', 'w') as out:
                out.write(text)
            os.chmod(f'{f}/{rel}', mode)
        sh('btrfs', 'property', 'set', '-ts', f, 'ro', 'true')
    finally:
        sh('umount', top)


def update():
    """Newest MWX 7 and Debian updates, before the first start's setup pages (after a reset)."""
    say('STEP', 'Looking for updates')
    r = subprocess.run(['/usr/share/mwx7/bin/mwx7-update', 'check'], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('No internet connection: updates can be installed later in Settings.')
    if not r.stdout.strip():
        say('STEP', 'MWX 7 is up to date')
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
GRUB_TIMEOUT=5
GRUB_DISTRIBUTOR="MWX 7"
# loglevel=3 after "quiet" (which sets 4): only critical kernel messages may cover the splash.
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=3 vt.global_cursor_default=0"
GRUB_CMDLINE_LINUX=""
GRUB_DISABLE_OS_PROBER=false
GRUB_DISABLE_RECOVERY=true
# The menu in MWX 7's look; it only shows when Esc is held or another system (Windows) is there to choose.
GRUB_THEME=/usr/share/grub/themes/mwx7/theme.txt
GRUB_GFXMODE=1920x1080,1280x800,auto
GRUB_GFXPAYLOAD_LINUX=keep
GRUB_TIMEOUT_STYLE=menu
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
        for old in ('@old', '@home-old'):
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
        elif cmd == 'update' and os.path.exists('/etc/mwx7/firstboot'):
            update()
        elif cmd == 'ready':
            ready()
        else:
            raise SystemExit(__doc__)
    except (RuntimeError, StopIteration, OSError) as e:
        say('ERROR', str(e) or type(e).__name__)
        sys.exit(1)
