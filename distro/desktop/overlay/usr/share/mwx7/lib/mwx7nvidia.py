"""The NVIDIA proprietary driver, installed the same way everywhere: Settings -> Display (through mwx7-admin), the first-start
setup (install.py, into the freshly copied system) and the first-boot retry (mwx7-nvidia-firstboot). One place, so the three
can never drift apart. `root` is '/' for the running system, or the mount point of the target (commands then run in a chroot)."""
import glob
import os
import re
import shutil
import subprocess
import urllib.request

CONF = 'etc/modprobe.d/mwx7-nvidia.conf'
FLAG = 'var/lib/mwx7/nvidia-pending'      # written by the installer when the driver could not be installed there
MOK_FLAG = 'var/lib/mwx7/mok-queued'      # a Secure Boot key was queued for enrolment at the next start
MOK_PASSWORD = 'mwx7mwx7'
MOK_STEPS = 'When the blue screen appears after restart: Enroll MOK → Continue → Yes → type mwx7mwx7 → Reboot.'
PACKAGES = ['linux-headers-amd64', 'dkms', 'nvidia-driver', 'firmware-misc-nonfree']


def gpu_present(lspci=None):
    """True when `lspci -nn` lists an NVIDIA (vendor 10de) VGA/3D/display device. MWX7_FAKE_LSPCI (a file) is a test hook."""
    if lspci is None:
        fake = os.environ.get('MWX7_FAKE_LSPCI')
        try:
            lspci = open(fake).read() if fake else subprocess.run(['lspci', '-nn'], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            return False
    return any(re.search(r'\b(VGA|3D|Display)\b', l) and '[10de:' in l.lower() for l in lspci.splitlines())


def online(timeout=6):
    try:
        urllib.request.urlopen('http://deb.debian.org/debian/dists/stable/InRelease', timeout=timeout).close()
        return True
    except (OSError, ValueError):
        return False


def secure_boot_on():
    # Always asked of the running firmware (also while installing into a target: same PC).
    r = subprocess.run(['mokutil', '--sb-state'], capture_output=True, text=True)
    return 'enabled' in r.stdout.lower()


def mok_pending():
    """True while a key waits for the blue screen; None when that cannot be told (no EFI, or not allowed to read it)."""
    r = subprocess.run(['mokutil', '--list-new'], capture_output=True, text=True)
    out = r.stdout + r.stderr
    if re.search(r'\[key \d+\]', out):
        return True
    return False if 'empty' in out.lower() or r.returncode == 0 else None


def enable_non_free(root='/'):
    """Debian's own sources only: add contrib and non-free to the one-line and the deb822 forms."""
    for path in [os.path.join(root, 'etc/apt/sources.list')] + glob.glob(os.path.join(root, 'etc/apt/sources.list.d/*.sources')):
        try:
            old = open(path).read()
        except OSError:
            continue
        lines = old.split('\n')
        deb822 = path.endswith('.sources')
        debian = deb822 and any(l.startswith('URIs:') and 'debian.org' in l for l in lines)
        for i, l in enumerate(lines):
            if (deb822 and debian and l.startswith('Components:')) or (
                    not deb822 and re.match(r'deb\s', l) and 'debian.org' in l):
                lines[i] = l + ''.join(f' {c}' for c in ('contrib', 'non-free') if c not in l.split())
        if '\n'.join(lines) != old:
            with open(path + '.tmp', 'w') as f:
                f.write('\n'.join(lines))
            os.replace(path + '.tmp', path)


def _run(root, *cmd, check=True, **kw):
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', LANG='C.UTF-8')
    argv = list(cmd) if root == '/' else ['chroot', root, *cmd]
    kw.setdefault('stdin', subprocess.DEVNULL)
    r = subprocess.run(argv, capture_output=True, text=True, env=env, **kw)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()[-300:]}")
    return r


def supported(root='/'):
    """False only when nvidia-detect says this card needs a legacy driver (then nouveau stays). Unknown: install anyway."""
    try:
        _run(root, 'apt-get', 'install', '-y', '-qq', 'nvidia-detect')
        out = _run(root, 'nvidia-detect', check=False).stdout
    except (RuntimeError, OSError):
        return True
    pkgs = {l.strip() for l in out.splitlines() if re.fullmatch(r'\s*nvidia-[a-z0-9-]*driver\s*', l)}
    return not pkgs or 'nvidia-driver' in pkgs


def install(root='/', step=lambda text: None):
    """Installs the driver; True when installed, False when this GPU is too old for it (nouveau stays). Raises RuntimeError
    on failure. Wayfire needs the driver's kernel modesetting (and its framebuffer) to get a screen at all, hence CONF."""
    resolv = os.path.join(root, 'etc/resolv.conf')
    had = False
    if root != '/':
        # The target's resolv.conf points at a resolver that is not running in a chroot: use this PC's for the time being.
        had = os.path.lexists(resolv)
        if had:
            os.rename(resolv, resolv + '.mwx7-bak')
        shutil.copyfile('/etc/resolv.conf', resolv)
    try:
        step('Preparing the NVIDIA graphics driver')
        enable_non_free(root)
        _run(root, 'apt-get', 'update', '-q')
        step('Checking the graphics card')
        if not supported(root):
            return False
        # The kernel module is built on this PC (DKMS), which needs the headers of the installed kernel; the headers
        # metapackage follows linux-image-amd64, so they always match it.
        step('Installing the NVIDIA graphics driver (a few minutes)')
        _run(root, 'apt-get', 'install', '-y', '-q', *PACKAGES)
        with open(os.path.join(root, CONF), 'w') as f:
            f.write('# MWX 7: Wayland needs kernel modesetting with the NVIDIA driver.\noptions nvidia-drm modeset=1 fbdev=1\n')
        step('Building the start-up files')
        _run(root, 'update-initramfs', '-u')
        key = os.path.join(root, 'var/lib/dkms/mok.pub')
        if secure_boot_on() and os.path.exists(key):
            # Unsigned kernel modules are refused with Secure Boot on, so the driver would never load. Queue DKMS's signing
            # key for enrollment: at the next start a blue screen (MOK manager) asks for this one-time password. The firmware
            # insists on a person at the screen, so this step cannot be skipped. Failure is not fatal: Settings explains.
            r = subprocess.run(['mokutil', '--import', key], input=f'{MOK_PASSWORD}\n{MOK_PASSWORD}\n', text=True,
                               capture_output=True)
            if r.returncode == 0:
                os.makedirs(os.path.join(root, 'var/lib/mwx7'), exist_ok=True)
                open(os.path.join(root, MOK_FLAG), 'w').close()
        return True
    finally:
        if root != '/':
            if os.path.lexists(resolv):
                os.unlink(resolv)
            if had:
                os.rename(resolv + '.mwx7-bak', resolv)


def remove(root='/'):
    # Only the driver goes: the firmware package is harmless and other hardware may use it.
    _run(root, 'apt-get', 'remove', '--purge', '-y', 'nvidia-driver')
    conf = os.path.join(root, CONF)
    if os.path.exists(conf):
        os.unlink(conf)
        _run(root, 'update-initramfs', '-u', check=False)
