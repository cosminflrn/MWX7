"""Calculator (native): the concept's Windows 7 calculator. View menu: Standard (memory, √, %, 1/x, repeat with =),
Scientific (trig + inverse, deg/rad/grad, powers, roots, logs, n!, parentheses, Exp, real operator precedence) and
Programmer (Hex/Dec/Oct/Bin, Qword/Dword/Word/Byte, And/Or/Xor/Not/Lsh/Rsh/Mod, clickable bit display); History panel
(Ctrl+H) and keyboard input everywhere. Expressions are parsed by a small precedence parser: nothing is ever eval()'d."""
import math
import random
import re
import sys

sys.path.insert(0, '/usr/share/mwx7/lib')
import mwx7ui  # noqa: E402
from mwx7ui import Gdk, Gio, GLib, Gtk  # noqa: E402

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

# Scientific: five scientific columns on the left, the Standard keypad (columns 5-9) on the right.
SCI_LEFT = [
    ('Deg', 'Deg', 'ang', 0, 0), ('Rad', 'Rad', 'ang', 1, 0), ('Grad', 'Grad', 'ang', 2, 0), ('Inv', 'Inv', 'tog', 3, 0),
    ('Mod', 'Mod', 'sci', 4, 0),
    ('sin', 'sin', 'sci', 0, 1), ('cos', 'cos', 'sci', 1, 1), ('tan', 'tan', 'sci', 2, 1), ('ln', 'ln', 'sci', 3, 1),
    ('log', 'log', 'sci', 4, 1),
    ('x²', 'x²', 'sci', 0, 2), ('x³', 'x³', 'sci', 1, 2), ('xʸ', 'xʸ', 'sci', 2, 2), ('³√', '³√', 'sci', 3, 2),
    ('ʸ√x', 'ʸ√x', 'sci', 4, 2),
    ('π', 'π', 'sci', 0, 3), ('e', 'e', 'sci', 1, 3), ('(', '(', 'sci', 2, 3), (')', ')', 'sci', 3, 3),
    ('n!', 'n!', 'sci', 4, 3),
    ('Exp', 'Exp', 'sci', 0, 4), ('|x|', '|x|', 'sci', 1, 4), ('Int', 'Int', 'sci', 2, 4), ('Frac', 'Frac', 'sci', 3, 4),
    ('Rand', 'Rand', 'sci', 4, 4),
    ('10ˣ', '10ˣ', 'sci', 0, 5), ('eˣ', 'eˣ', 'sci', 1, 5), ('2ˣ', '2ˣ', 'sci', 2, 5), ('⌊x⌋', '⌊x⌋', 'sci', 3, 5),
    ('⌈x⌉', '⌈x⌉', 'sci', 4, 5),
]
SCI_LAYOUT = [(k, t, kind, c, r, 1, 1) for k, t, kind, c, r in SCI_LEFT] + \
    [(k, t, kind, c + 5, r, w, h) for k, t, kind, c, r, w, h in LAYOUT]
INV_KEYS = {'sin': ('sin⁻¹', 'sin⁻¹'), 'cos': ('cos⁻¹', 'cos⁻¹'), 'tan': ('tan⁻¹', 'tan⁻¹'), 'ln': ('eˣ', 'eˣ'),
            'log': ('10ˣ', '10ˣ')}
# Programmer: letters and logic on the left, digits in the middle, operators on the right.
PROG_LAYOUT = [
    ('A', 'A', 'hex', 0, 0, 1, 1), ('B', 'B', 'hex', 1, 0, 1, 1), ('⌫', '←', 'fn', 2, 0, 1, 1), ('CE', 'CE', 'fn', 3, 0, 1, 1),
    ('C', 'C', 'fn', 4, 0, 1, 1), ('±', '±', 'fn', 5, 0, 1, 1), ('Mod', 'Mod', 'sci', 6, 0, 1, 1),
    ('C#', 'C', 'hex', 0, 1, 1, 1), ('D', 'D', 'hex', 1, 1, 1, 1), ('7', '7', 'num', 2, 1, 1, 1), ('8', '8', 'num', 3, 1, 1, 1),
    ('9', '9', 'num', 4, 1, 1, 1), ('÷', '÷', 'op', 5, 1, 1, 1), ('And', 'And', 'sci', 6, 1, 1, 1),
    ('E', 'E', 'hex', 0, 2, 1, 1), ('F', 'F', 'hex', 1, 2, 1, 1), ('4', '4', 'num', 2, 2, 1, 1), ('5', '5', 'num', 3, 2, 1, 1),
    ('6', '6', 'num', 4, 2, 1, 1), ('×', '×', 'op', 5, 2, 1, 1), ('Or', 'Or', 'sci', 6, 2, 1, 1),
    ('(', '(', 'sci', 0, 3, 1, 1), (')', ')', 'sci', 1, 3, 1, 1), ('1', '1', 'num', 2, 3, 1, 1), ('2', '2', 'num', 3, 3, 1, 1),
    ('3', '3', 'num', 4, 3, 1, 1), ('−', '−', 'op', 5, 3, 1, 1), ('Xor', 'Xor', 'sci', 6, 3, 1, 1),
    ('Lsh', 'Lsh', 'sci', 0, 4, 1, 1), ('Rsh', 'Rsh', 'sci', 1, 4, 1, 1), ('Not', 'Not', 'sci', 2, 4, 1, 1),
    ('0', '0', 'num', 3, 4, 2, 1), ('+', '+', 'op', 5, 4, 1, 1), ('=', '=', 'eq', 6, 4, 1, 1),
]
BASES = (('Hex', 16), ('Dec', 10), ('Oct', 8), ('Bin', 2))
WORDS = (('Qword', 64), ('Dword', 32), ('Word', 16), ('Byte', 8))
PREC_SCI = {'+': 1, '−': 1, '×': 2, '÷': 2, 'Mod': 2, 'xʸ': 3, 'ʸ√x': 3}
PREC_PROG = {'Or': 1, 'Xor': 2, 'And': 3, 'Lsh': 4, 'Rsh': 4, '+': 5, '−': 5, '×': 6, '÷': 6, 'Mod': 6}
RIGHT = ('xʸ', 'ʸ√x')
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
.calc-sci button.calc-key { min-width: 36px; font-size: 12px; }
.calc-prog button.calc-key { min-width: 34px; font-size: 12px; }
button.calc-key.ang { font-size: 11px; } button.calc-key.hex { font-weight: 600; }
button.calc-key.on { border-color: #2d6ea3; color: #0b2a4a; box-shadow: inset 0 1px 3px rgba(20,60,100,.45);
  background: linear-gradient(180deg, #a9d3ee 0%, #bfe1f6 100%); }
.calc-value.s12 { font-size: 12px; } .calc-value.s10 { font-size: 10px; }
.calc-par { font-size: 10px; font-weight: 700; color: #5b6b80; }
.calc-side { padding: 2px; }
button.calc-radio { min-height: 0; padding: 2px 6px; border: 1px solid transparent; border-radius: 3px; background: none;
  box-shadow: none; color: #1c2530; font-size: 12px; }
button.calc-radio:hover { background: rgba(255,255,255,.55); border-color: #9db3cd; }
button.calc-radio:checked { background: linear-gradient(180deg, #e9f4fc, #c9e3f5); border-color: #5d93c0; font-weight: 700; }
.calc-bitrow { margin: 0 0 1px 0; }
button.calc-bit { min-width: 9px; min-height: 14px; padding: 0; border: none; border-radius: 2px; background: none;
  box-shadow: none; font-size: 10px; font-family: monospace; color: #7a8696; }
button.calc-bit:hover { background: #cfe5f6; }
button.calc-bit.set { color: #0b3b6b; font-weight: 800; }
.calc-hist { border: 1px solid #7f93ab; border-radius: 2px; background: #fbfdff; }
.calc-hist list, .calc-hist row { background: none; }
.calc-hist row { padding: 3px 8px; border-bottom: 1px solid #e3ebf4; }
.calc-hist row:hover { background: #e4f1fb; }
.calc-hist-e { font-size: 11px; color: #7a8696; } .calc-hist-r { font-size: 16px; font-weight: 600; color: #1c2530; }
.calc-hist-none { color: #7a8696; font-size: 12px; padding: 14px; }
button.calc-hist-clear { min-height: 0; padding: 2px 10px; font-size: 11px; border-radius: 3px; }
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


def nibbles(s):
    """Hex and binary read in groups of four, from the right."""
    return ' '.join(reversed([s[max(0, i - 4):i] for i in range(len(s), 0, -4)]))


def apply(a, b, o):
    return a + b if o == '+' else a - b if o == '−' else a * b if o == '×' else a / b


class Err(Exception):
    """A calculation that has no answer: the message is what the display shows, as in Windows."""


def wrap(v, bits):
    """Two's complement: what a signed integer of `bits` bits holds."""
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def tidy(r):
    """Floating point dust (sin 180° = 1.2e-16, 64^(1/3) = 3.9999999999999996) is rounded away like a 15-digit calculator."""
    if not math.isfinite(r):
        raise Err('Overflow' if math.isinf(r) else 'Invalid input')
    return 0.0 if abs(r) < 1e-15 else float(f'{r:.15g}')


def cbrt(v):
    return math.cbrt(v) if hasattr(math, 'cbrt') else math.copysign(abs(v) ** (1 / 3), v)


class Engine:
    """Scientific and Programmer modes. The entry is kept as text in `display`; operators and parentheses collect in `tokens`
    ([kind, value, label]) and '=' evaluates them by precedence climbing, so 2 + 3 × 4 = 14 and 2 ^ 3 ^ 2 = 512."""

    def __init__(self, calc, prog):
        self.calc, self.prog = calc, prog
        self.base, self.bits, self.angle, self.inv = 10, 64, 'Deg', False
        self.reset()

    def reset(self):
        self.display, self.tokens, self.label, self.expr = '0', [], None, ''
        self.fresh, self.error = True, False

    # ---- values ------------------------------------------------------------------------------------------------------
    def depth(self, toks=None):
        return sum(1 if t[0] == '(' else -1 if t[0] == ')' else 0 for t in (self.tokens if toks is None else toks))

    def val(self):
        s = self.display
        if self.prog:
            return wrap(int(s or '0', self.base), self.bits)
        if s.endswith(('e+', 'e-')):
            s = s[:-2]
        return float(s)

    def tostr(self, v):
        if self.base == 10:
            return str(v)
        return format(v & ((1 << self.bits) - 1), {16: 'X', 8: 'o', 2: 'b'}[self.base])

    def show(self, v):
        self.display = self.tostr(v) if self.prog else fmt(v)
        self.fresh = True

    def numlabel(self, v):
        return self.tostr(v) if self.prog else fmt(v)

    def retext(self):
        self.expr = ' '.join([t[2] for t in self.tokens] + ([self.label] if self.label else []))

    def fail(self, msg):
        self.reset()
        self.display, self.error = msg, True

    # ---- evaluation --------------------------------------------------------------------------------------------------
    def binop(self, op, a, b):
        if self.prog:
            if op == '+':
                r = a + b
            elif op == '−':
                r = a - b
            elif op == '×':
                r = a * b
            elif op in ('÷', 'Mod'):
                if b == 0:
                    raise Err('Cannot divide by zero')
                q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)  # truncates toward zero, like the CPU
                r = q if op == '÷' else a - b * q
            elif op == 'And':
                r = a & b
            elif op == 'Or':
                r = a | b
            elif op == 'Xor':
                r = a ^ b
            elif op == 'Lsh':
                r = a << b if 0 <= b < self.bits else 0
            else:  # Rsh is arithmetic: the sign is kept
                r = a >> min(max(b, 0), self.bits)
            return wrap(r, self.bits)
        try:
            if op == '+':
                r = a + b
            elif op == '−':
                r = a - b
            elif op == '×':
                r = a * b
            elif op == '÷':
                if b == 0:
                    raise Err('Result is undefined' if a == 0 else 'Cannot divide by zero')
                r = a / b
            elif op == 'Mod':
                if b == 0:
                    raise Err('Cannot divide by zero')
                r = math.fmod(a, b)
            elif op == 'xʸ':
                r = math.pow(a, b)
            else:  # ʸ√x: the y-th root of x
                if b == 0:
                    raise Err('Invalid input')
                if a < 0 and float(b).is_integer() and int(b) % 2:
                    r = -math.pow(-a, 1 / b)
                else:
                    r = math.pow(a, 1 / b)
        except OverflowError:
            raise Err('Overflow')
        except ValueError:
            raise Err('Invalid input')
        return tidy(r)

    def evaluate(self, toks):
        prec, pos = (PREC_PROG if self.prog else PREC_SCI), [0]

        def atom():
            if pos[0] >= len(toks):
                raise Err('Invalid input')
            kind, v = toks[pos[0]][0], toks[pos[0]][1]
            pos[0] += 1
            if kind == 'n':
                return v
            if kind == '(':
                r = expr(1)
                if pos[0] >= len(toks) or toks[pos[0]][0] != ')':
                    raise Err('Invalid input')
                pos[0] += 1
                return r
            raise Err('Invalid input')

        def expr(minp):
            lhs = atom()
            while pos[0] < len(toks) and toks[pos[0]][0] == 'o' and prec[toks[pos[0]][1]] >= minp:
                op = toks[pos[0]][1]
                pos[0] += 1
                lhs = self.binop(op, lhs, expr(prec[op] if op in RIGHT else prec[op] + 1))
            return lhs
        r = expr(1)
        if pos[0] != len(toks):
            raise Err('Invalid input')
        return r

    def to_rad(self, v):
        return v if self.angle == 'Rad' else v * math.pi / (180 if self.angle == 'Deg' else 200)

    def from_rad(self, r):
        return r if self.angle == 'Rad' else r * (180 if self.angle == 'Deg' else 200) / math.pi

    def func(self, k, v):
        """One-operand functions apply to the entry at once, as on a Windows calculator."""
        if k in ('sin', 'cos', 'tan'):
            r = self.to_rad(v)
            if k == 'tan' and abs(math.cos(r)) < 1e-15:
                raise Err('Invalid input')
            return tidy(getattr(math, k)(r))
        if k in ('sin⁻¹', 'cos⁻¹', 'tan⁻¹'):
            fn = {'sin⁻¹': math.asin, 'cos⁻¹': math.acos, 'tan⁻¹': math.atan}[k]
            try:
                return tidy(self.from_rad(fn(v)))
            except ValueError:
                raise Err('Invalid input')
        try:
            if k == 'x²':
                return tidy(v * v)
            if k == 'x³':
                return tidy(v ** 3)
            if k == '√':
                if v < 0:
                    raise Err('Invalid input')
                return tidy(math.sqrt(v))
            if k == '³√':
                return tidy(cbrt(v))
            if k == '1/x':
                if v == 0:
                    raise Err('Cannot divide by zero')
                return tidy(1 / v)
            if k == 'n!':
                if v < 0 or v > 170:
                    raise Err('Invalid input' if v < 0 else 'Overflow')
                return tidy(float(math.factorial(int(v))) if float(v).is_integer() else math.gamma(v + 1))
            if k in ('log', 'ln'):
                if v <= 0:
                    raise Err('Invalid input')
                return tidy(math.log10(v) if k == 'log' else math.log(v))
            if k == '10ˣ':
                return tidy(10.0 ** v)
            if k == 'eˣ':
                return tidy(math.exp(v))
            if k == '2ˣ':
                return tidy(2.0 ** v)
            if k == '|x|':
                return abs(v)
            if k == 'Int':
                return float(math.trunc(v))
            if k == 'Frac':
                return tidy(v - math.trunc(v))
            if k == '⌊x⌋':
                return float(math.floor(v))
            if k == '⌈x⌉':
                return float(math.ceil(v))
        except OverflowError:
            raise Err('Overflow')
        raise Err('Invalid input')

    # ---- keys --------------------------------------------------------------------------------------------------------
    def push_value(self):
        if self.tokens and self.tokens[-1][0] == ')':
            return
        v = self.val()
        self.tokens.append(['n', v, self.label or self.numlabel(v)])
        self.label = None

    def digit(self, ch):
        if self.error:
            self.error, self.display, self.fresh = False, '0', True
        if self.fresh and self.tokens and self.tokens[-1][0] in ')n':
            self.tokens.append(['o', '×', '×'])
        if self.fresh:
            if not self.tokens:
                self.expr = ''
            self.display = '0.' if ch == '.' else ch
        elif self.prog:
            cand = (self.display + ch).lstrip('0') or '0'
            # Decimal holds a signed number; the other bases show (and so accept) the raw bit pattern.
            if int(cand, self.base) < (1 << (self.bits - (1 if self.base == 10 else 0))):
                self.display = cand
        elif ch == '.':
            if 'e' not in self.display and '.' not in self.display:
                self.display += '.'
        elif 'e' in self.display:
            if len(self.display.split('e')[1]) < 4:
                self.display += ch
        elif len(re.sub(r'[-.]', '', self.display)) < MAX:
            self.display = ch if self.display == '0' else self.display + ch
        self.fresh, self.label = False, None
        if self.tokens:
            self.retext()

    def press(self, k):
        if self.error and not re.fullmatch(r'C|CE|[0-9.A-F]|C#', k):
            return
        try:
            self.dispatch(k)
        except Err as e:
            self.fail(str(e))
        self.calc.render()

    def dispatch(self, k):
        c = self.calc
        digit = k == 'C#' or (len(k) == 1 and (k.isdigit() or (k == '.' and not self.prog) or
                                                (self.prog and k in 'ABDEF')))
        if digit:
            ch = 'C' if k == 'C#' else k
            if self.prog and int(ch, 16) >= self.base:
                return
            self.digit(ch)
        elif k == 'C':
            self.reset()
        elif k == 'CE':
            self.display, self.error, self.fresh, self.label = '0', False, True, None
            self.retext()
        elif k == '±':
            if self.prog:
                self.show(wrap(-self.val(), self.bits))
            elif 'e' in self.display:
                self.display = re.sub(r'e([+-])', lambda m: 'e' + ('-' if m.group(1) == '+' else '+'), self.display)
            elif self.display != '0':
                self.display = self.display[1:] if self.display.startswith('-') else '-' + self.display
        elif k == '⌫':
            if not self.fresh:
                d = self.display
                d = d[:-2] if d.endswith(('e+', 'e-')) else d[:-1]
                self.display = '0' if d in ('', '-') else d
        elif k in ('Deg', 'Rad', 'Grad'):
            self.angle = k
        elif k == 'Inv':
            self.inv = not self.inv
        elif k in ('π', 'e', 'Rand'):
            self.show(math.pi if k == 'π' else math.e if k == 'e' else random.random())
            self.label = None if k == 'Rand' else k
            self.retext()
        elif k == 'Exp':
            if 'e' not in self.display:
                self.display += 'e+'
                self.fresh = False
        elif k in ('MC', 'MR', 'MS', 'M+', 'M-'):
            self.memory_key(k)
        elif k == '%':
            v = self.val()
            prev = self.tokens[-2] if len(self.tokens) >= 2 and self.tokens[-1][0] == 'o' else None
            self.show(tidy(prev[1] * v / 100) if prev and prev[0] == 'n' else 0.0)
            self.label = self.display
            self.retext()
        elif k == '(':
            if self.tokens and self.tokens[-1][0] in ')n':
                self.tokens.append(['o', '×', '×'])
            self.tokens.append(['(', None, '('])
            self.display, self.fresh, self.label = '0', True, None
            self.retext()
        elif k == ')':
            if self.depth() <= 0:
                return
            self.push_value()
            self.tokens.append([')', None, ')'])
            level, i = 0, len(self.tokens) - 1
            while i >= 0:  # the '(' that this ')' closes
                level += 1 if self.tokens[i][0] == ')' else -1 if self.tokens[i][0] == '(' else 0
                if level == 0:
                    break
                i -= 1
            self.show(self.evaluate(self.tokens[i + 1:-1]))
            self.retext()
        elif k == '=':
            if not self.tokens:
                if not self.prog and 'e' in self.display:
                    self.show(self.val())
                self.fresh = True
                return
            self.push_value()
            self.tokens += [[')', None, ')']] * self.depth()
            text = ' '.join(t[2] for t in self.tokens) + ' ='
            r = self.evaluate(self.tokens)
            self.tokens = []
            self.show(r)
            self.expr = text
            c.hist_add(text, self.display)
        elif k in (PREC_PROG if self.prog else PREC_SCI):
            if self.fresh and self.tokens and self.tokens[-1][0] == 'o':
                self.tokens[-1] = ['o', k, k]
            else:
                self.push_value()
                prec = PREC_PROG if self.prog else PREC_SCI
                # Like Windows: when nothing is left waiting on a tighter operator, the display shows the running result.
                if self.depth() == 0 and len(self.tokens) >= 3 and prec[k] <= min(prec[t[1]] for t in self.tokens if t[0] == 'o'):
                    self.show(self.evaluate(self.tokens))
                self.tokens.append(['o', k, k])
            self.fresh = True
            self.retext()
        elif self.prog and k == 'Not':
            v = self.val()
            self.label = f'Not({self.tostr(v)})'
            self.show(wrap(~v, self.bits))
            self.retext()
        elif not self.prog:
            if self.inv and k in INV_KEYS:
                k = INV_KEYS[k][0]
            v = self.val()
            shown = self.label or self.numlabel(v)
            r = self.func(k, v)
            self.label = {'x²': f'({shown})²', 'x³': f'({shown})³', '|x|': f'abs({shown})', '1/x': f'1/({shown})'}.get(
                k, f'{k}({shown})')
            self.show(r)
            self.retext()
            if not self.tokens:
                c.hist_add(self.expr + ' =', self.display)

    def memory_key(self, k):
        c, v = self.calc, self.val()
        if k == 'MC':
            c.memory, c.has_mem = 0.0, False
        elif k == 'MR':
            self.show(c.memory)
            self.label = None
        elif k == 'MS':
            c.memory, c.has_mem, self.fresh = v, True, True
        else:
            c.memory += v * (1 if k == 'M+' else -1)
            c.has_mem, self.fresh = True, True

    # ---- Programmer-only settings ------------------------------------------------------------------------------------
    def set_base(self, base):
        v = self.val()
        self.base = base
        self.show(v)
        self.calc.render()

    def set_bits(self, bits):
        v = self.val()
        self.bits = bits
        self.tokens = [[t[0], wrap(t[1], bits) if t[0] == 'n' else t[1], t[2]] for t in self.tokens]
        self.show(wrap(v, bits))
        self.calc.render()

    def toggle_bit(self, i):
        self.show(wrap(self.val() ^ (1 << i), self.bits))
        self.calc.render()


class Calc:
    def __init__(self):
        self.display, self.acc, self.op, self.fresh, self.expr = '0', None, None, True, ''
        self.memory, self.has_mem, self.error, self.repeat = 0.0, False, False, None
        self.keys = {'standard': {}, 'sci': {}, 'prog': {}}
        self.mode, self.history, self.panel_wanted = 'standard', [], False
        self.sci, self.prog = Engine(self, False), Engine(self, True)

    @property
    def ex(self):
        """Whatever holds the entry on screen: this object in Standard, the engine in the other two modes."""
        return self if self.mode == 'standard' else self.sci if self.mode == 'sci' else self.prog

    def keypad(self, layout, page, css_class=None):
        grid = Gtk.Grid(column_spacing=5, row_spacing=5, column_homogeneous=True, row_homogeneous=True, vexpand=True)
        if css_class:
            grid.add_css_class(css_class)
        for kid, label, kind, c, r, w, h in layout:
            b = Gtk.Button(label=label, focusable=False)
            b.add_css_class('calc-key')
            b.add_css_class(kind)
            b.connect('clicked', lambda _b, k=kid: self.press(k))
            self.keys[page][kid] = b
            grid.attach(b, c, r, w, h)
        return grid

    def build(self, app, win):
        win.add_css_class('mwx7-calc')
        self.app, self.win = app, win
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(app.menubar([
            ('View', [('Standard', 'standard', lambda: self.set_mode('standard')),
                      ('Scientific', 'sci', lambda: self.set_mode('sci')),
                      ('Programmer', 'prog', lambda: self.set_mode('prog')), None,
                      ('History', 'history', self.toggle_history)]),
            ('Edit', [('Copy', 'copy', self.copy), ('Paste', 'paste', self.paste), None,
                      ('Clear History', 'clearhist', self.clear_history)]),
            ('Help', [('About Calculator', 'about', lambda: app.win and __import__('subprocess').Popen(
                ['/usr/share/mwx7/bin/mwx7-app', 'about']))]),
        ]))
        # The distro allows shortcuts (unlike the web version): the Windows 7 ones.
        for action, accels in (('standard', ['<Alt>1']), ('sci', ['<Alt>2']), ('prog', ['<Alt>3']),
                               ('history', ['<Ctrl>h']), ('copy', ['<Ctrl>c']), ('paste', ['<Ctrl>v'])):
            app.set_accels_for_action('app.' + action, accels)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8, margin_bottom=9, margin_start=8,
                       margin_end=8)
        scr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scr.add_css_class('calc-screen')
        self.hist = Gtk.Label(xalign=1, ellipsize=1)
        self.hist.add_css_class('calc-expr')
        line = Gtk.Box(spacing=4)
        self.mem = Gtk.Label(label='M', valign=Gtk.Align.END)
        self.mem.add_css_class('calc-mem')
        self.par = Gtk.Label(valign=Gtk.Align.END, xalign=0)
        self.par.add_css_class('calc-par')
        self.value = Gtk.Label(xalign=1, hexpand=True, selectable=False, ellipsize=1)
        self.value.add_css_class('calc-value')
        line.append(self.mem)
        line.append(self.par)
        line.append(self.value)
        scr.append(self.hist)
        scr.append(line)
        body.append(scr)

        self.stack = Gtk.Stack(hhomogeneous=False, vhomogeneous=False, vexpand=True)
        self.stack.add_named(self.keypad(LAYOUT, 'standard'), 'standard')
        sci = self.keypad(SCI_LAYOUT, 'sci', 'calc-sci')
        sci.set_size_request(430, 235)
        self.stack.add_named(sci, 'sci')
        self.stack.add_named(self.build_prog(), 'prog')
        body.append(self.stack)
        root.append(body)

        # History: a panel under the keys (as in Windows 7); a click puts a result back on the display.
        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_start=8, margin_end=8, margin_bottom=9,
                             visible=False)
        self.hlist = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, activate_on_single_click=True)
        self.hlist.connect('row-activated', self.recall)
        self.hnone = Gtk.Label(label='There’s no history yet.', xalign=0)
        self.hnone.add_css_class('calc-hist-none')
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inner.append(self.hnone)
        inner.append(self.hlist)
        self.hscroll = Gtk.ScrolledWindow(min_content_height=118, max_content_height=118, propagate_natural_height=False,
                                          hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.hscroll.set_child(inner)
        self.hscroll.add_css_class('calc-hist')
        clear = Gtk.Button(label='Clear history', halign=Gtk.Align.END, focusable=False)
        clear.add_css_class('calc-hist-clear')
        clear.connect('clicked', lambda *_: self.clear_history())
        self.panel.append(self.hscroll)
        self.panel.append(clear)
        root.append(self.panel)

        # Typing numbers and operators works too.
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.on_key)
        win.add_controller(keys)
        self.render()
        return root

    def build_prog(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        page.add_css_class('calc-prog')
        # The 64 bits: four rows of sixteen in groups of four; a click flips a bit.
        bits = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER)
        self.bitbtn, self.bitgroup, self.bitrow = {}, {}, []
        for r in range(4):
            row = Gtk.Box(spacing=7)
            row.add_css_class('calc-bitrow')
            for g in range(4):
                nib = Gtk.Box()
                for j in range(4):
                    i = 63 - 16 * r - 4 * g - j
                    b = Gtk.Button(label='0', focusable=False)
                    b.add_css_class('calc-bit')
                    b.connect('clicked', lambda _b, i=i: self.prog.toggle_bit(i))
                    self.bitbtn[i] = b
                    nib.append(b)
                self.bitgroup[63 - 16 * r - 4 * g] = nib
                row.append(nib)
            self.bitrow.append(row)
            bits.append(row)
        page.append(bits)
        mid = Gtk.Box(spacing=8)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        side.add_css_class('calc-side')
        self.basebtn, first = {}, None
        for name, base in BASES:
            b = Gtk.ToggleButton(focusable=False, active=base == 10)
            b.add_css_class('calc-radio')
            row = Gtk.Box(spacing=6)
            row.append(Gtk.Label(label=name, xalign=0, width_chars=4))
            val = Gtk.Label(label='0', xalign=1, hexpand=True, ellipsize=1, max_width_chars=16, width_chars=14)
            row.append(val)
            b.set_child(row)
            if first:
                b.set_group(first)
            first = first or b
            b.connect('toggled', lambda w, base=base: w.get_active() and self.prog.set_base(base))
            self.basebtn[base] = (b, val)
            side.append(b)
        side.append(Gtk.Separator(margin_top=4, margin_bottom=4))
        self.wordbtn, first = {}, None
        wordrow = Gtk.Box(spacing=0)
        for name, n in WORDS:
            b = Gtk.ToggleButton(label=name, focusable=False, active=n == 64)
            b.add_css_class('calc-radio')
            if first:
                b.set_group(first)
            first = first or b
            b.connect('toggled', lambda w, n=n: w.get_active() and self.prog.set_bits(n))
            self.wordbtn[n] = b
            wordrow.append(b)
        side.append(wordrow)
        mid.append(side)
        grid = self.keypad(PROG_LAYOUT, 'prog')
        mid.append(grid)
        grid.set_hexpand(True)
        page.append(mid)
        return page

    # ---- modes -------------------------------------------------------------------------------------------------------
    def set_mode(self, mode):
        self.mode = mode
        self.stack.set_visible_child_name(mode)
        # No history in Programmer, as in Windows 7. The window is not resizable: it takes the size of the mode's keys.
        self.panel.set_visible(self.panel_wanted and mode != 'prog')
        self.win.queue_resize()
        self.render()

    def toggle_history(self):
        self.panel_wanted = not self.panel_wanted
        self.panel.set_visible(self.panel_wanted and self.mode != 'prog')
        self.win.queue_resize()

    def hist_add(self, expr, result):
        self.history.append((expr, result))
        self.hnone.set_visible(False)
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        e, r = Gtk.Label(label=expr, xalign=1, ellipsize=1), Gtk.Label(label=group(result), xalign=1, ellipsize=1)
        e.add_css_class('calc-hist-e')
        r.add_css_class('calc-hist-r')
        box.append(e)
        box.append(r)
        row.set_child(box)
        row.result = result
        self.hlist.append(row)
        # Newest at the bottom, scrolled into view.
        GLib.idle_add(lambda: self.hscroll.get_vadjustment().set_value(self.hscroll.get_vadjustment().get_upper()) and False)

    def clear_history(self):
        self.history = []
        while (row := self.hlist.get_first_child()):
            self.hlist.remove(row)
        self.hnone.set_visible(True)

    def recall(self, _list, row):
        s = self.ex
        if s.error:
            s.error = False
        s.display, s.fresh = row.result, True
        if s is not self:
            s.label = None
        self.render()

    # ---- keyboard ----------------------------------------------------------------------------------------------------
    def on_key(self, _c, keyval, _code, state):
        if state & Gdk.ModifierType.ALT_MASK:
            return False
        ch = chr(Gdk.keyval_to_unicode(keyval) or 0)
        name = Gdk.keyval_name(keyval) or ''
        mode = self.mode
        if state & Gdk.ModifierType.CONTROL_MASK:  # Windows 7's memory keys; Ctrl+C/V/H are menu accelerators
            k = {'l': 'MC', 'r': 'MR', 'm': 'MS', 'p': 'M+', 'q': 'M-'}.get(ch.lower())
            if k and mode != 'prog':
                self.press(k)
                return True
            return False
        k = {'/': '÷', '*': '×', '-': '−', '+': '+', '=': '='}.get(ch)
        common = {'Return': '=', 'KP_Enter': '=', 'BackSpace': '⌫', 'Escape': 'C', 'Delete': 'CE', 'F9': '±'}
        if ch.isdigit():
            k = ch
        elif name in common:
            k = common[name]
        elif mode == 'standard':
            k = k or {'%': '%', '.': '.', ',': '.', 'r': '1/x', '@': '√'}.get(ch)
        elif mode == 'sci':
            k = k or {'%': '%', '.': '.', ',': '.', '^': 'xʸ', '(': '(', ')': ')', '!': 'n!', 's': 'sin', 'o': 'cos', 't': 'tan',
                      'l': 'log', 'n': 'ln', 'q': 'x²', 'r': '1/x', '@': '√', 'p': 'π', 'e': 'Exp', 'x': 'Exp', 'i': 'Inv',
                      'm': 'Mod', 'd': 'Deg', 'g': 'Grad'}.get(ch.lower() if ch.isalpha() else ch)
        else:
            k = k or {'(': '(', ')': ')', '&': 'And', '|': 'Or', '^': 'Xor', '~': 'Not', '<': 'Lsh', '>': 'Rsh',
                      '%': 'Mod'}.get(ch)
            if not k and ch.upper() in list('ABCDEF'):
                k = 'C#' if ch.upper() == 'C' else ch.upper()
        if k:
            self.press(k)
            return True
        return False

    # ---- display -----------------------------------------------------------------------------------------------------
    def render(self):
        s = self.ex
        prog = self.mode == 'prog'
        if prog:
            text = group(s.display) if s.base == 10 and not s.error else s.display if s.error else nibbles(s.display)
        else:
            text = group(s.display)
        self.value.set_label(text)
        for c in ('s24', 's21', 's17', 's12', 's10'):
            self.value.remove_css_class(c)
        n = len(text)
        if n > 10:
            self.value.add_css_class('s10' if n > 40 else 's12' if n > 26 else 's17' if n > 18 else 's21' if n > 13 else 's24')
        self.hist.set_label(s.expr)
        self.mem.set_opacity(1 if self.has_mem and not prog else 0)
        depth = s.depth() if s is not self else 0
        self.par.set_label(f'({depth}' if depth > 0 else '')
        for page in ('standard', 'sci'):
            self.keys[page]['MC'].set_sensitive(self.has_mem)
            self.keys[page]['MR'].set_sensitive(self.has_mem)
        if self.mode == 'sci':
            k = self.keys['sci']
            for a in ('Deg', 'Rad', 'Grad'):
                (k[a].add_css_class if s.angle == a else k[a].remove_css_class)('on')
            (k['Inv'].add_css_class if s.inv else k['Inv'].remove_css_class)('on')
            for base, (alt, _l) in INV_KEYS.items():
                k[base].set_label(alt if s.inv else base)
        elif prog:
            self.render_prog()

    def render_prog(self):
        p = self.prog
        if p.error:
            return
        v, bits, mask = p.val(), p.bits, (1 << p.bits) - 1
        for base, (_b, lab) in self.basebtn.items():
            raw = str(v) if base == 10 else format(v & mask, {16: 'X', 8: 'o', 2: 'b'}[base])
            lab.set_label(group(raw) if base == 10 else raw if base == 8 else nibbles(raw))
        u = v & mask
        for i, b in self.bitbtn.items():
            on = bool(u >> i & 1)
            b.set_label('1' if on else '0')
            (b.add_css_class if on else b.remove_css_class)('set')
            b.set_visible(i < bits)
        for low, nib in self.bitgroup.items():
            nib.set_visible(low < bits)
        for row in self.bitrow:
            row.set_visible(any(w.get_visible() for w in self._children(row)))
        for k, b in self.keys['prog'].items():
            d = 'C' if k == 'C#' else k
            if len(d) == 1 and d in '0123456789ABCDEF':
                b.set_sensitive(int(d, 16) < p.base)

    @staticmethod
    def _children(w):
        c = w.get_first_child()
        while c:
            yield c
            c = c.get_next_sibling()

    def press(self, k):
        if self.mode == 'standard':
            self.std_press(k)
        else:
            self.ex.press(k)

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
        self.hist_add(self.expr + ' =', self.display)

    def std_press(self, k):
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
                self.hist_add(self.expr, self.display)
            elif self.repeat:
                o, operand = self.repeat
                if o == '÷' and operand == 0:
                    return
                self.expr = f'{fmt(b)} {o} {fmt(operand)} ='
                self.display = fmt(apply(b, operand, o))
                self.hist_add(self.expr, self.display)
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
        s = self.ex
        self.win.get_clipboard().set(s.display)

    def paste(self):
        def done(cb, res):
            try:
                t = (cb.read_text_finish(res) or '').strip().replace(',', '').replace(' ', '')
            except Exception:  # noqa: BLE001 (nothing usable on the clipboard)
                return
            s = self.ex
            if self.mode == 'prog':
                try:
                    n = int(t, 16 if t.lower().startswith('0x') else s.base)
                except ValueError:
                    return
                s.error, s.fresh = False, False
                s.show(wrap(n, s.bits))
                s.fresh = False
            elif re.fullmatch(r'-?\d*\.?\d+', t):
                s.error, s.display, s.fresh = False, fmt(float(t)), False
            else:
                return
            self.render()
        self.win.get_clipboard().read_text_async(None, done)


if __name__ == '__main__':
    calc = Calc()
    mwx7ui.App('org.mwx7.calculator', 'Calculator', 'calculator', (260, 330), CSS, calc.build, resizable=False).run_main()
