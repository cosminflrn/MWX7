"""What the shell, the desktop layer and Settings share about screens: which one is the primary, and where each sits.

The primary screen (Settings -> Display -> "Make this my main display") carries the bar, the dock, the desktop icons and
the widgets; every other screen shows just the wallpaper. The choice lives in ~/.config/mwx7/displays.json as
{"primary": "<connector>"}; positions live in wayfire.ini ([output:NAME] position = x,y), which Wayfire itself reads.
Everything here is defensive: no monitors, no connector names or a damaged file all fall back to the first screen.
"""
import json
import os

CONF = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'mwx7', 'displays.json')


def read_conf():
    try:
        c = json.load(open(CONF))
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def primary_name():
    p = read_conf().get('primary')
    return p if isinstance(p, str) else ''


def set_primary(name):
    c = read_conf()
    c['primary'] = name
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    tmp = CONF + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(c, f)
    os.replace(tmp, CONF)  # a rename is what the shells' file monitors see (WATCH_MOVES)


def monitors(display):
    """The display's monitors as a plain list (GTK 4's Gdk.Display.get_monitors() is a Gio.ListModel)."""
    out = []
    try:
        model = display.get_monitors()
        for i in range(model.get_n_items()):
            m = model.get_item(i)
            if m is not None:
                out.append(m)
    except Exception:
        pass
    return out


def connector(mon):
    try:
        return mon.get_connector() or ''
    except Exception:
        return ''


def pick_primary(mons, wanted=None):
    """The chosen connector if it is connected, else the screen at the layout's origin (0,0), else the first one."""
    if not mons:
        return None
    wanted = primary_name() if wanted is None else wanted
    for m in mons:
        if wanted and connector(m) == wanted:
            return m
    for m in mons:
        g = m.get_geometry()
        if g.x == 0 and g.y == 0:
            return m
    return mons[0]


def monitor_at(mons, x, y):
    """The monitor whose rectangle (layout coordinates) holds the point, or None."""
    for m in mons:
        g = m.get_geometry()
        if g.x <= x < g.x + g.width and g.y <= y < g.y + g.height:
            return m
    return None
