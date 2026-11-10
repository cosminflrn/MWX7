"""Turns the copied live system into an installed MWX 7: logon instead of the live autologin, no live leftovers,
root locked, the chosen keyboard in the desktop, and GRUB named and set up for MWX 7."""
import os
import re

import libcalamares


def pretty_name():
    return "Finishing MWX 7"


def write(path, text, mode=0o644):
    with open(path, 'w') as f:
        f.write(text)
    os.chmod(path, mode)


def run():
    gs = libcalamares.globalstorage
    root = gs.value('rootMountPoint')
    user = gs.value('username')
    if not root or not user:
        return ('MWX 7 could not be finished', 'The installer did not say where the system is or who uses it.')

    def target(*parts):
        return os.path.join(root, *parts)

    # 1. Logon. The MWX 7 logon screen asks for the password; with "log in automatically" the desktop starts directly
    #    after boot and the logon screen only appears after logging out.
    greetd = ('[terminal]\nvt = 1\n\n'
              '[default_session]\ncommand = "/usr/local/bin/mwx7-greeter-session"\nuser = "_greetd"\n')
    if gs.value('autoLoginUser'):
        greetd += f'\n[initial_session]\ncommand = "/usr/local/bin/mwx7-session"\nuser = "{user}"\n'
    write(target('etc/greetd/config.toml'), greetd)

    # 2. Live leftovers: passwordless sudo and the installer's own entry.
    for leftover in ('etc/sudoers.d/mwx7-live', 'usr/share/applications/mwx7-install.desktop',
                     'usr/local/bin/mwx7-install', 'etc/calamares'):
        path = target(leftover)
        if os.path.isdir(path):
            libcalamares.utils.host_env_process_output(['rm', '-rf', '--one-file-system', path])
        elif os.path.exists(path):
            os.remove(path)

    # 3. Nobody logs in as root; administration goes through sudo with the user's password.
    libcalamares.utils.target_env_call(['passwd', '-l', 'root'])

    # 4. The keyboard picked in the installer is the desktop's first layout (US stays available as the second).
    layout, variant = gs.value('keyboardLayout') or 'us', gs.value('keyboardVariant') or ''
    if layout != 'us':
        ini = target('etc/mwx7/wayfire.ini')
        text = open(ini).read()
        text = re.sub(r'^xkb_layout = .*$', f'xkb_layout = {layout},us', text, flags=re.M)
        text = re.sub(r'^xkb_variant = .*$', f'xkb_variant = {variant},', text, flags=re.M)
        write(ini, text)

    # 5. GRUB: MWX 7's name, the quiet boot the splash needs, and other systems (Windows) listed in the menu.
    #    Calamares' grubcfg job runs next and adds what an encrypted disk needs.
    write(target('etc/default/grub'), '''# MWX 7 boot menu settings. Run "sudo update-grub" after changing this file.
GRUB_DEFAULT=saved
GRUB_SAVEDEFAULT=true
GRUB_TIMEOUT=5
GRUB_DISTRIBUTOR="MWX 7"
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
GRUB_CMDLINE_LINUX="loglevel=3 vt.global_cursor_default=0"
GRUB_DISABLE_OS_PROBER=false
GRUB_DISABLE_RECOVERY=true
# The menu in MWX 7's look; it only shows when Esc is held or another system (Windows) is there to choose.
GRUB_THEME=/usr/share/grub/themes/mwx7/theme.txt
GRUB_GFXMODE=1920x1080,1280x800,auto
GRUB_GFXPAYLOAD_LINUX=keep
GRUB_TIMEOUT_STYLE=menu
''')
    return None
