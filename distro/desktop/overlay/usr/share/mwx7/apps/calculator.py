"""Calculator (native): the concept's Windows 7 Standard calculator: memory, √, %, 1/x, repeat with =."""
import math
import re
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gtk  # noqa: E402

MAX = 16
LAYOUT = [  # (id, label, kind, col, row, width, height)
    ('MC', 'MC', 'mem', 0, 0, 1, 1), ('MR', 'MR', 'mem', 1, 0, 1, 1), ('MS', 'MS', 'mem', 2, 0, 1, 1),
    ('M+', 'M+', 'mem', 3, 0, 1, 1), ('M-', 'M-', 'mem', 4, 0, 1, 1),
    ('⌫', '←', 'fn', 0, 1, 1, 1), ('CE', 'CE', 'fn', 1, 1, 1, 1), ('C', 'C', 'fn', 2, 1, 1, 1),
    ('±', '±', 'fn', 3, 1, 1, 1), ('√', '√', 'fn', 4, 1, 1, 1),
    ('7', '7', 'num', 0, 2, 1, 1), ('8', '8', 'num', 1, 2, 1, 1), ('9', '9', 'num', 2, 2, 1, 1),
    ('÷', '÷', 'op', 3, 2, 1, 1), ('%', '%', 'fn', 4, 2, 1, 1),
    ('4', '4', 'num', 0, 3, 1, 1), ('5', '5', 'num', 1, 3, 1, 1), ('6', '6', 'num', 2, 3, 1, 1),
    ('×', '×', 'op', 3, 3, 1, 1), ('1/x', '1/x', 'fn', 4, 3, 1, 1),
    ('1', '1', 'num', 0, 4, 1, 1), ('2', '2', 'num', 1, 4, 1, 1), ('3', '3', 'num', 2, 4, 1, 1),
    ('−', '−', 'op', 3, 4, 1, 1), ('=', '=', 'eq', 4, 4, 1, 2),
    ('0', '0', 'num', 0, 5, 2, 1), ('.', '.', 'num', 2, 5, 1, 1), ('+', '+', 'op', 3, 5, 1, 1),
]
CSS = """
window.mwx7-calc > box { background: linear-gradient(180deg, #dbe6f3 0%, #cddcee 55%, #c3d3e8 100%); }
.calc-screen { padding: 3px 7px 4px; background: linear-gradient(180deg, #ffffff, #f4f8fd); border: 1px solid #7f93ab;
  border-radius: 2px; box-shadow: inset 0 1px 2px rgba(40, 70, 110, .22); }
.calc-expr { font-size: 11px; color: #7a8696; min-height: 15px; }
.calc-mem { font-size: 10px; font-weight: 700; color: #5b6b80; }
.calc-value { font-size: 28px; color: #1c2530; }
.calc-value.s24 { font-size: 24px; } .calc-value.s21 { font-size: 21px; } .calc-value.s17 { font-size: 17px; }
button.calc-key { min-height: 27px; min-width: 34px; padding: 0; border-radius: 3px; font-size: 13px; color: #1c2530;
  border: 1px solid #8b9db5; box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
  background: linear-gradient(180deg, #f6f9fd 0%, #e6edf6 49%, #d6e1ee 50%, #e3ebf5 100%); }
button.calc-key:hover { border-color: #3c7fb1;
  background: linear-gradient(180deg, #eaf6fd 0%, #d9f0fc 49%, #bee6fd 50%, #a7d9f5 100%); }
button.calc-key:active { background: linear-gradient(180deg, #c2e4f6 0%, #a9d9f2 49%, #90cbeb 50%, #a4d5ef 100%); }
button.calc-key.num { font-weight: 600; }
button.calc-key:disabled { color: #9aa5b3; }
"""


def fmt(n):
    if not math.isfinite(n):
        return 'Error'
    if n == 0:
        return '0'
    if abs(n) >= 1e16 or abs(n) < 1e-9:
        return re.sub(r'\.?0+e', 'e', f'{n:.8e}').replace('e+', 'e+').replace('e+0', 'e+').replace('e-0', 'e-')
    # Up to 16 digits in all, as Windows shows them: fewer decimals the bigger the whole part.
    whole = len(str(int(abs(n))))
    s = f'{n:.{max(0, MAX - whole)}f}'
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def group(s):
    if not re.fullmatch(r'-?\d+(\.\d*)?', s):
        return s
    i, _, f = s.partition('.')
    neg = i.startswith('-')
    g = f'{int(i.lstrip("-")):,}'
    return ('-' if neg else '') + g + ('.' + f if '.' in s else '')


def apply(a, b, o):
    return a + b if o == '+' else a - b if o == '−' else a * b if o == '×' else a / b


class Calc:
    def __init__(self):
        self.display, self.acc, self.op, self.fresh, self.expr = '0', None, None, True, ''
        self.memory, self.has_mem, self.error, self.repeat = 0.0, False, False, None
        self.keys = {}

    def build(self, app, win):
        win.add_css_class('mwx7-calc')
        self.app = app
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('View', [('Standard', 'standard', lambda: None)]),
            ('Edit', [('Copy', 'copy', self.copy), ('Paste', 'paste', self.paste)]),
            ('Help', [('About Calculator', 'about', lambda: app.win and __import__('subprocess').Popen(
                ['/usr/share/mwx7/bin/mwx7-app', 'about']))]),
        ]))
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8, margin_bottom=9, margin_start=8,
                       margin_end=8)
        scr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scr.add_css_class('calc-screen')
        self.hist = Gtk.Label(xalign=1, ellipsize=3)
        self.hist.add_css_class('calc-expr')
        line = Gtk.Box(spacing=4)
        self.mem = Gtk.Label(label='M', valign=Gtk.Align.END)
        self.mem.add_css_class('calc-mem')
        self.value = Gtk.Label(xalign=1, hexpand=True, selectable=False)
        self.value.add_css_class('calc-value')
        line.append(self.mem)
        line.append(self.value)
        scr.append(self.hist)
        scr.append(line)
        body.append(scr)
        grid = Gtk.Grid(column_spacing=5, row_spacing=5, column_homogeneous=True, row_homogeneous=True, vexpand=True)
        for kid, label, kind, c, r, w, h in LAYOUT:
            b = Gtk.Button(label=label, focusable=False)
            b.add_css_class('calc-key')
            b.add_css_class(kind)
            b.connect('clicked', lambda _b, k=kid: self.press(k))
            self.keys[kid] = b
            grid.attach(b, c, r, w, h)
        body.append(grid)
        root.append(body)
        # Typing numbers and operators works too (typing is allowed input; there are no shortcuts).
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.on_key)
        win.add_controller(keys)
        self.render()
        return root

    def on_key(self, _c, keyval, _code, _state):
        ch = chr(Gdk.keyval_to_unicode(keyval) or 0)
        name = Gdk.keyval_name(keyval) or ''
        k = {'/': '÷', '*': '×', '-': '−', '+': '+', '=': '=', '%': '%', '.': '.', ',': '.'}.get(ch)
        if ch.isdigit():
            k = ch
        elif name in ('Return', 'KP_Enter'):
            k = '='
        elif name == 'BackSpace':
            k = '⌫'
        elif name == 'Escape':
            k = 'C'
        elif name == 'Delete':
            k = 'CE'
        if k:
            self.press(k)
            return True
        return False

    def render(self):
        text = group(self.display)
        self.value.set_label(text)
        for c in ('s24', 's21', 's17'):
            self.value.remove_css_class(c)
        n = len(text)
        if n > 10:
            self.value.add_css_class('s17' if n > 18 else 's21' if n > 13 else 's24')
        self.hist.set_label(self.expr)
        self.mem.set_opacity(1 if self.has_mem else 0)
        self.keys['MC'].set_sensitive(self.has_mem)
        self.keys['MR'].set_sensitive(self.has_mem)

    def fail(self, msg):
        self.display, self.error, self.acc, self.op, self.expr, self.repeat, self.fresh = msg, True, None, None, '', None, True

    def prefix(self):
        return f'{fmt(self.acc)} {self.op} ' if self.op and self.acc is not None else ''

    def unary(self, name, fn, bad=None):
        v = float(self.display)
        msg = bad(v) if bad else None
        if msg:
            return self.fail(msg)
        self.expr = f'{self.prefix()}{name}({fmt(v)})'
        self.display, self.fresh = fmt(fn(v)), True

    def press(self, k):
        if self.error and not re.fullmatch(r'C|CE|[0-9.]', k):
            return
        if k.isdigit():
            if self.error:
                self.error, self.display = False, '0'
            if self.fresh:
                if not self.op:
                    self.expr = ''
                self.display = k
            elif len(re.sub(r'[-.]', '', self.display)) < MAX:
                self.display = k if self.display == '0' else self.display + k
            self.fresh = False
        elif k == '.':
            if self.error:
                self.error, self.display = False, '0'
            if self.fresh:
                if not self.op:
                    self.expr = ''
                self.display = '0.'
            elif '.' not in self.display:
                self.display += '.'
            self.fresh = False
        elif k == 'C':
            self.display, self.acc, self.op, self.expr, self.repeat, self.error, self.fresh = '0', None, None, '', None, False, True
        elif k == 'CE':
            self.display, self.error, self.fresh = '0', False, True
            if not self.op:
                self.expr = ''
        elif k == '±':
            d = self.display
            self.display = d[1:] if d.startswith('-') else d if d == '0' else '-' + d
        elif k == '%':
            v = float(self.display)
            self.display = fmt(self.acc * v / 100 if self.op and self.acc is not None else 0)
            self.expr, self.fresh = f'{self.prefix()}{self.display}', True
        elif k == '√':
            self.unary('√', math.sqrt, lambda v: 'Invalid input' if v < 0 else None)
        elif k == '1/x':
            self.unary('1/', lambda v: 1 / v, lambda v: 'Cannot divide by zero' if v == 0 else None)
        elif k == '⌫':
            if not self.fresh:
                d = self.display
                self.display = '0' if len(d) <= 1 or (len(d) == 2 and d.startswith('-')) else d[:-1]
        elif k == 'MC':
            self.memory, self.has_mem = 0.0, False
        elif k == 'MR':
            self.display, self.fresh = fmt(self.memory), True
        elif k == 'MS':
            self.memory, self.has_mem, self.fresh = float(self.display), True, True
        elif k in ('M+', 'M-'):
            self.memory += float(self.display) * (1 if k == 'M+' else -1)
            self.has_mem, self.fresh = True, True
        elif k == '=':
            b = float(self.display)
            if self.op and self.acc is not None:
                if self.op == '÷' and b == 0:
                    self.fail('Cannot divide by zero')
                    return self.render()
                self.expr = f'{fmt(self.acc)} {self.op} {fmt(b)} ='
                self.repeat = (self.op, b)
                self.display, self.acc, self.op = fmt(apply(self.acc, b, self.op)), None, None
            elif self.repeat:
                o, operand = self.repeat
                if o == '÷' and operand == 0:
                    return
                self.expr = f'{fmt(b)} {o} {fmt(operand)} ='
                self.display = fmt(apply(b, operand, o))
            self.fresh = True
        else:
            if self.op and self.acc is not None and not self.fresh:
                if self.op == '÷' and float(self.display) == 0:
                    self.fail('Cannot divide by zero')
                    return self.render()
                self.display = fmt(apply(self.acc, float(self.display), self.op))
            self.acc, self.op, self.repeat = float(self.display), k, None
            self.expr, self.fresh = f'{fmt(self.acc)} {self.op}', True
        self.render()

    def copy(self):
        self.app.win.get_clipboard().set(self.display)

    def paste(self):
        def done(cb, res):
            try:
                t = (cb.read_text_finish(res) or '').strip().replace(',', '')
            except Exception:  # noqa: BLE001 (nothing usable on the clipboard)
                return
            if re.fullmatch(r'-?\d*\.?\d+', t):
                self.error, self.display, self.fresh = False, fmt(float(t)), False
                self.render()
        self.app.win.get_clipboard().read_text_async(None, done)


if __name__ == '__main__':
    calc = Calc()
    mwx7ui.App('org.mwx7.calculator', 'Calculator', 'calculator', (260, 330), CSS, calc.build, resizable=False).run_main()
