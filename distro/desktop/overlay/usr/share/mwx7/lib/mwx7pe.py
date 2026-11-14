"""Tiny pure-Python reader for the product name of a Windows program (.exe / .dll): the ProductName string in the file's
version resource, which the "Run Windows programs" dialog uses to look for a Linux version of it. Reads only the headers and the
one resource it needs, never the whole file, and returns None for anything that is not a well-formed PE file."""
import re
import struct

RT_VERSION = 16
NAMES = ('ProductName', 'FileDescription')


def _rva_to_off(sections, rva):
    for va, vsize, raw, rsize in sections:
        if va <= rva < va + max(vsize, rsize):
            return raw + (rva - va)
    return None


def _read(f, off, n):
    f.seek(off)
    data = f.read(n)
    return data if len(data) == n else None


def _version_blob(f):
    head = _read(f, 0, 64)
    if not head or head[:2] != b'MZ':
        return None
    pe = struct.unpack_from('<I', head, 0x3C)[0]
    coff = _read(f, pe, 24)
    if not coff or coff[:4] != b'PE\0\0':
        return None
    nsec, = struct.unpack_from('<H', coff, 6)
    optsize, = struct.unpack_from('<H', coff, 20)
    opt = _read(f, pe + 24, optsize)
    if not opt or len(opt) < 2:
        return None
    magic, = struct.unpack_from('<H', opt, 0)
    dd = 96 if magic == 0x10b else 112 if magic == 0x20b else None
    if dd is None or len(opt) < dd + 8 * 3:
        return None
    res_rva, _res_size = struct.unpack_from('<II', opt, dd + 8 * 2)
    if not res_rva or nsec > 96:
        return None
    sec = _read(f, pe + 24 + optsize, 40 * nsec)
    if not sec:
        return None
    sections = []
    for i in range(nsec):
        vsize, va, rsize, raw = struct.unpack_from('<IIII', sec, i * 40 + 8)
        sections.append((va, vsize, raw, rsize))
    base = _rva_to_off(sections, res_rva)
    if base is None:
        return None

    def entries(off):
        """The (id, target offset, is_directory) rows of the resource directory at `off` (relative to the resource start)."""
        hdr = _read(f, base + off, 16)
        if not hdr:
            return []
        named, ids = struct.unpack_from('<HH', hdr, 12)
        rows = []
        for i in range(min(named + ids, 64)):
            row = _read(f, base + off + 16 + i * 8, 8)
            if not row:
                break
            ident, target = struct.unpack('<II', row)
            rows.append((ident, target & 0x7FFFFFFF, bool(target & 0x80000000)))
        return rows

    node = next((t for ident, t, d in entries(0) if ident == RT_VERSION and d), None)
    for _level in range(2):  # the resource's name, then its language
        first = next(iter(entries(node)), None) if node is not None else None
        if first is None:
            return None
        node = first[1]
    ent = _read(f, base + node, 8)
    if not ent:
        return None
    rva, size = struct.unpack('<II', ent)
    off = _rva_to_off(sections, rva)
    if off is None or not 0 < size <= 1 << 20:
        return None
    return _read(f, off, size)


def _string(blob, key):
    """The value of one version string: its UTF-16 key, padding to a 4-byte boundary, then the UTF-16 value."""
    k = key.encode('utf-16-le') + b'\0\0'
    i = blob.find(k)
    while i != -1:
        start = i + len(k)
        start += (-start) % 4  # values are 32-bit aligned from the start of the resource
        end = start
        while end + 1 < len(blob) and blob[end:end + 2] != b'\0\0':
            end += 2
        if end > start:
            text = blob[start:end].decode('utf-16-le', 'replace').strip()
            if text:
                return text
        i = blob.find(k, i + 1)
    return None


def product_name(path):
    """ProductName (else FileDescription) of a PE file, or None."""
    try:
        with open(path, 'rb') as f:
            blob = _version_blob(f)
    except (OSError, struct.error):
        return None
    if not blob:
        return None
    for key in NAMES:
        v = _string(blob, key)
        if v:
            return v[:100]
    return None


NOISE = re.compile(r'\b(setup|install(er)?|x64|x86|amd64|win(32|64)?|windows|msi|64bit|32bit|v?\d+(\.\d+)+|\d{6,})\b', re.I)


def name_from_file(path):
    """A search-friendly name from the file name: "Notepad++_Setup-v8.6.2_x64.exe" -> "Notepad++"."""
    stem = re.sub(r'\.(exe|msi|dll)$', '', path.replace('\\', '/').rsplit('/', 1)[-1], flags=re.I)
    spaced = stem.replace('_', ' ')  # before the noise filter, so "8.6.2" is still seen as a version
    cleaned = ' '.join(re.sub(r'[\-.]+', ' ', NOISE.sub(' ', spaced)).split())
    return cleaned or ' '.join(re.sub(r'[_\-.]+', ' ', stem).split()) or stem


def program_name(path):
    return product_name(path) or name_from_file(path)
